#!/usr/bin/env python3
"""
extract_queries.py — Scrape Sumo Logic queries from dashboard/content exports.

Walks a set of Sumo Logic export JSON files (single dashboards, folder exports,
saved searches) and builds a deduplicated query library plus an extraction log.

Handles:
  - DashboardV2SyncDefinition   -> panel queries (Logs / Metrics / Traces)
  - FolderSyncDefinition        -> recurse children (nested folders, dashboards, saved searches)
  - SavedSearchWithScheduleSyncDefinition -> search.queryText
  - LookupTableSyncDefinition   -> skipped (counted)

Context captured per source: dashboard name/description, immediate parent folder,
panel title/type, visualization type, and nearest text-panel "row header" derived
from the dashboard grid layout. Template variables ({{param}}) are collected.

Dedup: records keyed by (queryType, normalized query text); identical queries collapse
into one record whose sources[] lists every occurrence.

Stdlib only. Usage:
  python3 extract_queries.py [--root DIR] [--out DIR] [FILE ...]
If FILEs are given, only those are scanned; otherwise globs ROOT/apps/**/*.json.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
from collections import OrderedDict

PARAM_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
# index/view scope tokens at the head of a logs query
SCOPE_RE = re.compile(r"\b(_index|_view|_sourceCategory|_sourceName|_collector)\s*=\s*(\"[^\"]*\"|\S+)", re.IGNORECASE)
# pipe operators: token after a leading `|`
OP_RE = re.compile(r"(?:^|\n)\s*\|\s*([a-zA-Z_][a-zA-Z0-9_]*)")
# Sumo metadata / special fields (prefixed with _), e.g. _index, _sourceCategory, _timeslice
META_FIELD_RE = re.compile(r"(?<![\w.])_[a-zA-Z][a-zA-Z0-9_]*")
# strip // line comments (not part of a URL like https://) and /* */ block comments
LINE_COMMENT_RE = re.compile(r"(?<!:)//[^\n]*")
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# Canonical Sumo operator / function vocabulary, sourced from the VS Code Sumo syntax
# highlighter (Hajime/syntaxes/sumo.tmLanguage.json). Pure boolean keywords
# (and/or/not/in/name) are excluded to avoid false positives.
SUMO_OPERATORS = frozenset({
    "abs", "accum", "acos", "asin", "atan", "atan2", "avg", "backshift", "base64Decode",
    "base64Encode", "bin", "cbrt", "ceil", "CIDR", "column", "concat", "contains", "cos",
    "cosh", "count", "count_distinct", "count_frequent", "csv", "decToHex", "diff", "exp",
    "expm1", "fields", "fillmissing", "filter", "first", "floor", "format", "formatDate",
    "geo lookup", "geoip", "haversine", "hexToDec", "hypot", "if", "ipv4ToNumber", "isBlank",
    "isEmpty", "isNull", "isNumeric", "isPrivateIP", "isPublicIP", "isValidIP", "join", "JSON",
    "keyvalue", "last", "least_recent", "length", "limit", "log", "log10", "log1p", "logcompare",
    "logreduce", "lookup", "luhn", "matches", "max", "median", "merge", "min", "most_recent",
    "nodrop", "now", "num", "outlier", "parse", "parse regex", "parseHex", "pct", "predict",
    "queryendtime", "querystarttime", "regex", "replace", "rollingstd", "round", "row", "save",
    "sessionize", "sin", "sinh", "smooth", "sort", "split", "sqrt", "stddev", "substring", "sum",
    "tan", "tanh", "threatip", "threatlookup", "timeslice", "toDegrees", "toLowerCase",
    "toRadians", "toUpperCase", "top", "total", "trace", "transaction", "transactionize",
    "transpose", "urldecode", "urlencode", "values", "where", "xml",
})
# match longest first so multiword ops (e.g. "parse regex") win; allow flexible whitespace
_OP_PATTERN = re.compile(
    r"(?<![\w.])(" + "|".join(
        re.escape(op).replace(r"\ ", r"\s+") for op in sorted(SUMO_OPERATORS, key=len, reverse=True)
    ) + r")(?![\w.])",
    re.IGNORECASE,
)
# canonical-case lookup keyed by lowercase, single-spaced
_OP_CANON = {re.sub(r"\s+", " ", op).lower(): op for op in SUMO_OPERATORS}


class Extractor:
    def __init__(self, root):
        self.root = root
        self.records = OrderedDict()  # hash -> record
        self.log = {
            "filesScanned": 0,
            "filesParsedOk": 0,
            "filesFailed": [],
            "objectsProcessed": {},
            "panelsProcessed": 0,
            "textPanels": 0,
            "queriesExtracted": 0,
            "uniqueQueries": 0,
            "byQueryType": {},
            "byQueryMode": {},
            "lookupTablesSkipped": 0,
            "warnings": [],
            "errors": [],
        }

    # ---------- helpers ----------
    def rel(self, path):
        try:
            return os.path.relpath(path, self.root)
        except ValueError:
            return path

    def warn(self, file, context, message):
        self.log["warnings"].append({"file": file, "context": context, "message": message})

    def bump(self, d, key):
        self.log[d][key] = self.log[d].get(key, 0) + 1

    @staticmethod
    def parse_params(text):
        seen = []
        for m in PARAM_RE.finditer(text or ""):
            tok = m.group(1).strip()
            if tok and tok not in seen:
                seen.append(tok)
        return seen

    @staticmethod
    def strip_comments(text):
        """Remove // line comments (not in URLs) and /* */ block comments."""
        if not text:
            return ""
        text = BLOCK_COMMENT_RE.sub(" ", text)
        text = LINE_COMMENT_RE.sub("", text)
        return text

    @staticmethod
    def parse_scopes(text):
        out = []
        for m in SCOPE_RE.finditer(text or ""):
            s = f"{m.group(1)}={m.group(2)}"
            if s not in out:
                out.append(s)
        return out[:12]

    @staticmethod
    def parse_operators(text):
        """Distinct Sumo operators/functions present, from the canonical vocabulary."""
        out = []
        for m in _OP_PATTERN.finditer(text or ""):
            canon = _OP_CANON[re.sub(r"\s+", " ", m.group(1)).lower()]
            if canon not in out:
                out.append(canon)
        return out

    @staticmethod
    def parse_metadata_fields(text):
        """Distinct Sumo metadata / special fields (prefixed with _) used in the query.

        Normalized to lowercase since Sumo metadata fields are case-insensitive.
        """
        out = []
        for m in META_FIELD_RE.finditer(text or ""):
            f = m.group(0).lower()
            if f not in out:
                out.append(f)
        return out

    @staticmethod
    def viz_type(visual_settings):
        """Pull the visualization type from a panel's visualSettings JSON string."""
        if not visual_settings:
            return None
        try:
            vs = json.loads(visual_settings)
        except (json.JSONDecodeError, TypeError):
            return None
        gen = vs.get("general", {}) if isinstance(vs, dict) else {}
        # canvas.js style: general.type ('table','text',...) or general.mode
        return gen.get("type") or gen.get("mode")

    # ---------- layout / context ----------
    @staticmethod
    def parse_layout(dash):
        """Return {panelKey: {x,y,w,h}} from layout.layoutStructures."""
        pos = {}
        layout = dash.get("layout") or {}
        for s in layout.get("layoutStructures", []) or []:
            key = s.get("key")
            try:
                st = json.loads(s.get("structure", "{}"))
            except (json.JSONDecodeError, TypeError):
                continue
            if key:
                pos[key] = {
                    "x": st.get("x", 0), "y": st.get("y", 0),
                    "w": st.get("width", 0), "h": st.get("height", 0),
                }
        return pos

    def row_context(self, panel, panels, pos):
        """Nearest text-panel header above the panel + same-row text panels."""
        pkey = panel.get("key")
        me = pos.get(pkey)
        text_panels = [p for p in panels if p.get("panelType") == "TextPanel"]
        ctx = []
        if not me or not text_panels:
            return ctx
        my_y = me["y"]
        header = None
        header_y = -1
        for tp in text_panels:
            tpos = pos.get(tp.get("key"))
            if not tpos:
                continue
            ty = tpos["y"]
            if ty <= my_y and ty > header_y:  # nearest above/at
                header, header_y = tp, ty
        if header is not None:
            label = (header.get("title") or "").strip() or (header.get("text") or "").strip()
            if label:
                ctx.append(label[:200])
        return ctx

    # ---------- upload (logSearches API) mapping ----------
    # dashboard visualization type -> saved-search aggregateViewerType
    VIEWER_MAP = {
        "table": "table", "bar": "bar", "column": "column", "line": "line",
        "area": "area", "pie": "pie", "map": "map", "svv": "svv",
        "distribution": "table", "TextPanel": "table",
    }

    @classmethod
    def viewer_type(cls, visualization):
        if not visualization:
            return "table"
        return cls.VIEWER_MAP.get(visualization, visualization)

    @staticmethod
    def build_query_parameters(query_text, variables):
        """Build logSearches-API queryParameters[] from {{params}} + dashboard variables.

        Params are emitted as dataType 'ANY' (raw substitution, matching dashboard
        template semantics) with the dashboard default as the value.
        """
        var_by_name = {v.get("name"): v for v in (variables or []) if v.get("name")}
        out = []
        seen = set()
        for m in PARAM_RE.finditer(query_text or ""):
            name = m.group(1).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            v = var_by_name.get(name, {})
            default = v.get("defaultValue")
            out.append({
                "autoComplete": {
                    "type": "SKIP_AUTOCOMPLETE",
                    "autoCompleteKey": "",
                    "autoCompleteValues": [],
                    "lookupMetaData": {},
                },
                "name": name,
                "description": (v.get("values") or "") if isinstance(v.get("values"), str) else "",
                "dataType": "ANY",
                "value": "" if default is None else str(default),
            })
        return out

    @staticmethod
    def dashboard_variables(dash):
        out = []
        for v in dash.get("variables", []) or []:
            src = v.get("sourceDefinition") or {}
            out.append({
                "name": v.get("name"),
                "defaultValue": v.get("defaultValue"),
                "values": src.get("values"),
                "allowMultiSelect": v.get("allowMultiSelect"),
            })
        return out

    # ---------- record building ----------
    def add_query(self, query_text, query_type, query_mode, source, metrics_data=None, traces_data=None):
        query_text = (query_text or "").strip()
        struct = metrics_data if metrics_data is not None else traces_data
        if not query_text and struct is None:
            self.warn(source["file"], source.get("panelTitle") or source.get("dashboardName"),
                      "empty query skipped")
            return
        self.log["queriesExtracted"] += 1
        self.bump("byQueryType", query_type or "Unknown")
        self.bump("byQueryMode", query_mode or "Unknown")

        key_text = query_text if query_text else json.dumps(struct, sort_keys=True)
        h = hashlib.sha1(f"{query_type}\n{key_text}".encode("utf-8")).hexdigest()[:12]
        rec = self.records.get(h)
        if rec is None:
            clean = self.strip_comments(query_text)
            rec = {
                "id": None,  # assigned at finalize
                "hash": h,
                "queryType": query_type,
                "queryMode": query_mode,
                "query": query_text,
                "parameters": self.parse_params(clean),
                "scopes": self.parse_scopes(clean) if query_type == "Logs" else [],
                "operators": self.parse_operators(clean),
                "metadataFields": self.parse_metadata_fields(clean),
                # upload-ready (logSearches API) fields — small, kept in main JSON
                "viewerType": self.viewer_type(source.get("visualization")),
                "queryParameters": self.build_query_parameters(clean, source.get("variables")),
                # heavy fields — moved to detail files at write time
                "metricsQueryData": metrics_data,
                "tracesQueryData": traces_data,
                "sourceCount": 0,
                "sources": [],
            }
            self.records[h] = rec
        rec["sources"].append(source)
        rec["sourceCount"] = len(rec["sources"])

    # ---------- object processors ----------
    def process_dashboard(self, dash, file, folder):
        self.bump("objectsProcessed", "Dashboard")
        pos = self.parse_layout(dash)
        panels = dash.get("panels", []) or []
        dvars = self.dashboard_variables(dash)
        dname = (dash.get("name") or dash.get("title") or "").strip()
        ddesc = (dash.get("description") or "").strip()
        for panel in panels:
            ptype = panel.get("panelType")
            if ptype == "TextPanel":
                self.log["textPanels"] += 1
                continue
            self.log["panelsProcessed"] += 1
            queries = panel.get("queries", []) or []
            if not queries:
                self.warn(file, panel.get("title"), f"{ptype} has no queries")
                continue
            for q in queries:
                qtype = q.get("queryType")
                qstr = q.get("queryString")
                mdata = q.get("metricsQueryData")
                tdata = q.get("tracesQueryData") or q.get("spansQueryData")
                if qtype == "Metrics":
                    mode = "Metrics-Basic" if mdata else "Metrics-Advanced"
                elif qtype == "Traces":
                    mode = "Traces"
                else:
                    mode = "Logs"
                source = {
                    "file": self.rel(file),
                    "objectType": "Dashboard",
                    "folder": folder,
                    "dashboardName": dname,
                    "dashboardDescription": ddesc,
                    "panelTitle": (panel.get("title") or "").strip(),
                    "panelType": ptype,
                    "panelKey": panel.get("key"),
                    "visualization": self.viz_type(panel.get("visualSettings")),
                    "visualSettingsRaw": panel.get("visualSettings"),
                    "rowContext": self.row_context(panel, panels, pos),
                    "variables": dvars,
                }
                self.add_query(qstr, qtype, mode, source, metrics_data=mdata, traces_data=tdata)

    def process_saved_search(self, obj, file, folder):
        self.bump("objectsProcessed", "SavedSearch")
        search = obj.get("search") or {}
        qtext = search.get("queryText")
        source = {
            "file": self.rel(file),
            "objectType": "SavedSearch",
            "folder": folder,
            "dashboardName": (obj.get("name") or "").strip(),
            "dashboardDescription": (obj.get("description") or "").strip(),
            "panelTitle": (obj.get("name") or "").strip(),
            "panelType": "SavedSearch",
            "panelKey": None,
            "visualization": None,
            "rowContext": [],
            "variables": [],
            "defaultTimeRange": search.get("defaultTimeRange"),
        }
        self.add_query(qtext, "Logs", "SavedSearch", source)

    def process_object(self, obj, file, folder):
        """Dispatch on an object's type. `folder` = immediate parent folder name (or None)."""
        if not isinstance(obj, dict):
            return
        t = obj.get("type")
        if t == "DashboardV2SyncDefinition":
            self.process_dashboard(obj, file, folder)
        elif t == "SavedSearchWithScheduleSyncDefinition":
            self.process_saved_search(obj, file, folder)
        elif t == "FolderSyncDefinition":
            self.bump("objectsProcessed", "Folder")
            fname = (obj.get("name") or "").strip()
            for child in obj.get("children", []) or []:
                # immediate parent = this folder
                self.process_object(child, file, fname)
        elif t == "LookupTableSyncDefinition":
            self.log["lookupTablesSkipped"] += 1
        elif t:
            self.warn(file, t, "unhandled object type")

    # ---------- file walk ----------
    def process_file(self, path):
        self.log["filesScanned"] += 1
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:  # noqa: BLE001 - want to log any failure
            self.log["errors"].append({"file": self.rel(path), "error": f"{type(e).__name__}: {e}"})
            return
        self.log["filesParsedOk"] += 1
        self.process_object(data, path, None)

    def finalize(self):
        for i, rec in enumerate(self.records.values(), 1):
            rec["id"] = f"q{i:04d}"
        self.log["uniqueQueries"] = len(self.records)

    # slim fields kept per source in the main (embedded) library
    SLIM_SOURCE_KEYS = ("file", "objectType", "folder", "dashboardName",
                        "panelTitle", "panelType", "visualization")

    @classmethod
    def _has_detail(cls, rec):
        if rec.get("metricsQueryData") or rec.get("tracesQueryData"):
            return True
        for s in rec["sources"]:
            if s.get("visualSettingsRaw") or s.get("variables") or s.get("rowContext") \
               or s.get("dashboardDescription"):
                return True
        return rec["sourceCount"] > 1

    def split_record(self, rec):
        """Return (slim_record_for_main, detail_record_or_None)."""
        has_detail = self._has_detail(rec)
        slim = {
            "id": rec["id"], "hash": rec["hash"],
            "queryType": rec["queryType"], "queryMode": rec["queryMode"],
            "query": rec["query"],
            "parameters": rec["parameters"], "scopes": rec["scopes"],
            "operators": rec["operators"],
            "metadataFields": rec["metadataFields"],
            "viewerType": rec["viewerType"],
            "queryParameters": rec["queryParameters"],
            "sourceCount": rec["sourceCount"],
            "detailFile": f"details/{rec['id']}.json" if has_detail else None,
            "sources": [{k: s.get(k) for k in self.SLIM_SOURCE_KEYS} for s in rec["sources"]],
        }
        detail = None
        if has_detail:
            detail = {
                "id": rec["id"], "hash": rec["hash"],
                "queryType": rec["queryType"], "queryMode": rec["queryMode"],
                "query": rec["query"],
                "queryParameters": rec["queryParameters"],
                "viewerType": rec["viewerType"],
                "metricsQueryData": rec["metricsQueryData"],
                "tracesQueryData": rec["tracesQueryData"],
                "sources": rec["sources"],  # full, incl. visualSettingsRaw / variables / context
            }
        return slim, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getcwd(), help="repo root for relative paths / glob")
    ap.add_argument("--out", default=None, help="output dir (default: <root>/ask_rick/output)")
    ap.add_argument("--tree", action="store_true",
                    help="scan the WHOLE project tree for Sumo exports (dashboards, folders, "
                         "saved searches, lookups), skipping .git/tmp/ask_rick/node_modules")
    ap.add_argument("files", nargs="*", help="explicit files (default: glob apps/**/*.json)")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    out_dir = args.out or os.path.join(root, "ask_rick", "output")
    os.makedirs(out_dir, exist_ok=True)

    SUMO_TYPES = {"DashboardV2SyncDefinition", "FolderSyncDefinition",
                  "SavedSearchWithScheduleSyncDefinition", "LookupTableSyncDefinition"}
    SKIP_DIRS = {".git", "tmp", "ask_rick", "node_modules", ".venv", "venv"}

    if args.files:
        files = [os.path.abspath(f) for f in args.files]
    elif args.tree:
        files = []
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for fn in fns:
                if not fn.endswith(".json"):
                    continue
                p = os.path.join(dp, fn)
                try:
                    with open(p, encoding="utf-8") as fh:
                        if (json.load(fh) or {}).get("type") in SUMO_TYPES:
                            files.append(p)
                except (json.JSONDecodeError, OSError, AttributeError):
                    continue  # non-Sumo / unreadable JSON — skipped from the scan
        files.sort()
    else:
        files = sorted(glob.glob(os.path.join(root, "apps", "**", "*.json"), recursive=True))

    ex = Extractor(root)
    for f in files:
        ex.process_file(f)
    ex.finalize()

    # split into slim main library + per-record detail files
    details_dir = os.path.join(out_dir, "details")
    os.makedirs(details_dir, exist_ok=True)
    slim_records = []
    detail_count = 0
    for rec in ex.records.values():
        slim, detail = ex.split_record(rec)
        slim_records.append(slim)
        if detail is not None:
            with open(os.path.join(details_dir, f"{rec['id']}.json"), "w", encoding="utf-8") as fh:
                json.dump(detail, fh, indent=2, ensure_ascii=False)
            detail_count += 1

    library = {
        "meta": {
            "sourceRoot": os.path.basename(root),
            "filesScanned": ex.log["filesScanned"],
            "uniqueQueries": ex.log["uniqueQueries"],
            "queriesExtracted": ex.log["queriesExtracted"],
            "detailFiles": detail_count,
            "byQueryType": ex.log["byQueryType"],
            "byQueryMode": ex.log["byQueryMode"],
        },
        "queries": slim_records,
    }

    lib_path = os.path.join(out_dir, "query_library.json")
    log_path = os.path.join(out_dir, "extraction_log.json")
    with open(lib_path, "w", encoding="utf-8") as fh:
        json.dump(library, fh, indent=2, ensure_ascii=False)
    with open(log_path, "w", encoding="utf-8") as fh:
        json.dump(ex.log, fh, indent=2, ensure_ascii=False)

    print(f"files scanned : {ex.log['filesScanned']}  ok={ex.log['filesParsedOk']}  failed={len(ex.log['filesFailed']) + len(ex.log['errors'])}")
    print(f"objects       : {ex.log['objectsProcessed']}")
    print(f"panels        : {ex.log['panelsProcessed']}  textPanels={ex.log['textPanels']}")
    print(f"queries       : extracted={ex.log['queriesExtracted']}  unique={ex.log['uniqueQueries']}")
    print(f"byType        : {ex.log['byQueryType']}")
    print(f"byMode        : {ex.log['byQueryMode']}")
    print(f"warnings={len(ex.log['warnings'])}  errors={len(ex.log['errors'])}")
    print(f"detail files  : {detail_count}")
    print(f"wrote: {ex.rel(lib_path)}  {ex.rel(log_path)}  details/")


if __name__ == "__main__":
    main()
