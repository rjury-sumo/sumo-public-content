#!/usr/bin/env python3
"""
querylib.py — Browse the local Sumo Logic query library from the CLI.

Reads the library produced by extract_queries.py (ask_rick/output/query_library.json)
and merges descriptions + tags from enrichment.json (by query hash). No API calls.
Three commands, each with tabular (default) or --json output:

    list    Enumerate queries, or facet values (apps/tags/operators/fields/types/modes)
    filter  Multi-criteria search: text, type, mode, app, tag, operator, field, param, scope
    show    Full detail for one query (by id or hash)

Usage:
    python3 querylib.py list                         # first N queries (table)
    python3 querylib.py list tags                     # tag values + counts
    python3 querylib.py list apps --json
    python3 querylib.py filter --text "access key" --type Logs
    python3 querylib.py filter --tag geoip --tag security --operator lookup -n 30
    python3 querylib.py filter --app kubernetes --field _sourcecategory --json
    python3 querylib.py show q0001
    python3 querylib.py show q0001 --json

Filter semantics mirror the web UI: repeatable flags (--tag/--operator/--field/--param)
are OR within a flag, AND across different flags; --text is a substring match across
query text, description, tags, operators, fields, and dashboard context.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from pathlib import Path

_OUTPUT_DIR   = Path(__file__).parent.parent.resolve() / "output"
_DEFAULT_LIB  = _OUTPUT_DIR / "query_library.json"

FACETS = {
    "tags":      lambda q: q.get("tags") or [],
    "operators": lambda q: q.get("operators") or [],
    "fields":    lambda q: q.get("metadataFields") or [],
    "apps":      lambda q: [q["_app"]],
    "types":     lambda q: [q["queryType"]],
    "modes":     lambda q: [q["queryMode"]],
}

# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------
_CYAN, _GREEN, _YELLOW, _MAGENTA, _GREY, _BOLD, _RESET = (
    "\033[36m", "\033[32m", "\033[33m", "\033[35m", "\033[90m", "\033[1m", "\033[0m")


def _c(text, code, use_color):
    return f"{code}{text}{_RESET}" if use_color else str(text)


def _type_color(t):
    return {"Logs": _CYAN, "Metrics": _GREEN, "Traces": _YELLOW}.get(t, _GREY)


# ---------------------------------------------------------------------------
# Load + merge
# ---------------------------------------------------------------------------

def _app_of(rec):
    f = (rec.get("sources") or [{}])[0].get("file") or ""
    parts = f.split("/")
    if parts and parts[0] == "apps" and len(parts) > 1:
        return parts[1]
    return parts[0] if parts and parts[0] else "(other)"


def _load(lib_path: Path) -> list[dict]:
    if not lib_path.exists():
        raise SystemExit(f"Library not found: {lib_path}\n"
                         "Run: python3 scripts/extract_queries.py --tree")
    lib = json.loads(lib_path.read_text())
    queries = lib["queries"]

    # merge enrichment (by hash; id fallback only for hash-less entries)
    by_hash, by_id = {}, {}
    out_dir = lib_path.parent

    def index(e):
        if not isinstance(e, dict):
            return
        if e.get("hash"):
            by_hash[e["hash"]] = e
        elif e.get("id"):
            by_id[e["id"]] = e

    ed = out_dir / "enrichment"
    if ed.is_dir():
        for fn in ed.glob("*.json"):
            try:
                index(json.loads(fn.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
    cf = out_dir / "enrichment.json"
    if cf.is_file():
        try:
            data = json.loads(cf.read_text())
            for e in (data if isinstance(data, list)
                      else data.get("enrichments") or data.get("queries") or []):
                index(e)
        except (json.JSONDecodeError, OSError):
            pass

    for q in queries:
        e = by_hash.get(q["hash"]) or by_id.get(q["id"])
        q["description"] = (e or {}).get("description")
        q["tags"] = (e or {}).get("tags") or []
        q["_app"] = _app_of(q)
    return queries


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def _text_blob(q):
    s = (q.get("sources") or [{}])[0]
    return " ".join(filter(None, [
        q.get("query"), q.get("description"), " ".join(q.get("tags") or []),
        " ".join(q.get("operators") or []), " ".join(q.get("metadataFields") or []),
        s.get("dashboardName"), s.get("panelTitle"), s.get("folder"),
    ])).lower()


def _filter(queries, *, text=None, qtype=None, mode=None, app=None,
            tags=None, operators=None, fields=None, params=None, scope=None):
    def ok(q):
        if qtype and q["queryType"].lower() != qtype.lower():
            return False
        if mode and q["queryMode"].lower() != mode.lower():
            return False
        if app and app.lower() not in q["_app"].lower():
            return False
        # repeatable: OR within a flag, AND across flags
        if tags and not (set(t.lower() for t in tags) & set(x.lower() for x in q.get("tags") or [])):
            return False
        if operators and not (set(o.lower() for o in operators) & set(x.lower() for x in q.get("operators") or [])):
            return False
        if fields and not (set(f.lower() for f in fields) & set(x.lower() for x in q.get("metadataFields") or [])):
            return False
        if params and not (set(p.lower() for p in params) & set(x.lower() for x in q.get("parameters") or [])):
            return False
        if scope and not any(scope.lower() in s.lower() for s in q.get("scopes") or []):
            return False
        if text and text.lower() not in _text_blob(q):
            return False
        return True
    return [q for q in queries if ok(q)]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _trunc(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _table(rows, headers, use_color, aligns=None):
    aligns = aligns or ["l"] * len(headers)
    widths = [len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(_strip(str(cell))))
    def fmt(cells, color_hdr=False):
        out = []
        for i, cell in enumerate(cells):
            raw = str(cell)
            pad = widths[i] - len(_strip(raw))
            out.append((raw + " " * pad) if aligns[i] == "l" else (" " * pad + raw))
        line = "  ".join(out)
        return _c(line, _BOLD, use_color) if color_hdr else line
    print(fmt(headers, color_hdr=True))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt(r))


def _strip(s):
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)


def _query_row(q, use_color, desc_width):
    title = (q.get("sources") or [{}])[0].get("panelTitle") or ""
    desc = q.get("description") or title or ""
    return [
        _c(q["id"], _BOLD, use_color),
        _c(q["queryType"], _type_color(q["queryType"]), use_color),
        _trunc(q["_app"], 22),
        _trunc(desc, desc_width),
        _trunc(",".join(q.get("tags") or []), 30),
    ]


def _print_queries(queries, use_color, full=False):
    if not queries:
        print("No matching queries.")
        return
    dw = 200 if full else 60
    rows = [_query_row(q, use_color, dw) for q in queries]
    _table(rows, ["ID", "TYPE", "APP", "DESCRIPTION" if any(q.get("description") for q in queries) else "PANEL", "TAGS"],
           use_color)
    print(f"\n{len(queries)} quer{'y' if len(queries)==1 else 'ies'}")


def _facet_counts(queries, key):
    from collections import Counter
    acc = FACETS[key]
    c = Counter()
    for q in queries:
        for v in acc(q):
            c[v] += 1
    return c.most_common()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _add_filter_args(p):
    p.add_argument("--text", "-q", metavar="STR",
                   help="substring match across query text, description, tags, operators, fields, context")
    p.add_argument("--type", "-t", dest="qtype", metavar="TYPE",
                   choices=["Logs", "Metrics", "Traces", "logs", "metrics", "traces"],
                   help="query type: Logs | Metrics | Traces")
    p.add_argument("--mode", "-m", metavar="MODE",
                   help="query mode: Logs | Metrics-Advanced | Metrics-Basic | Traces | SavedSearch")
    p.add_argument("--app", "-a", metavar="NAME", help="source app/folder substring")
    p.add_argument("--tag", action="append", metavar="TAG", help="tag (repeatable; OR)")
    p.add_argument("--operator", action="append", metavar="OP", help="Sumo operator (repeatable; OR)")
    p.add_argument("--field", action="append", metavar="FIELD", help="metadata field e.g. _index (repeatable; OR)")
    p.add_argument("--param", action="append", metavar="P", help="template parameter (repeatable; OR)")
    p.add_argument("--scope", metavar="STR", help="substring match on scope (e.g. _index=sumologic_audit)")


def _apply_filter(queries, a):
    return _filter(queries, text=a.text, qtype=a.qtype, mode=a.mode, app=a.app,
                   tags=a.tag, operators=a.operator, fields=a.field,
                   params=a.param, scope=a.scope)


def cmd_list(argv, prog, lib_default):
    p = argparse.ArgumentParser(prog=prog, description="List queries, or distinct facet values.")
    p.add_argument("kind", nargs="?", default="queries",
                   choices=["queries", "tags", "operators", "fields", "apps", "types", "modes"],
                   help="what to list (default: queries)")
    _add_filter_args(p)
    p.add_argument("-n", "--limit", type=int, default=25, metavar="N", help="max rows (default 25; 0 = all)")
    p.add_argument("--full", action="store_true", help="don't truncate descriptions")
    p.add_argument("--json", action="store_true", dest="output_json")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--db", default=str(lib_default), metavar="PATH", help="query_library.json path")
    a = p.parse_args(argv)
    use_color = not a.no_color and sys.stdout.isatty()
    queries = _apply_filter(_load(Path(a.db)), a)

    if a.kind != "queries":
        facet_key = a.kind
        counts = _facet_counts(queries, facet_key)
        if a.limit:
            counts = counts[: a.limit]
        if a.output_json:
            print(json.dumps({"status": "success", "kind": facet_key, "count": len(counts),
                              "values": [{"value": v, "queries": n} for v, n in counts]}, indent=2))
        else:
            _table([[_c(v, _MAGENTA, use_color), n] for v, n in counts],
                   [facet_key.upper(), "QUERIES"], use_color, aligns=["l", "r"])
            print(f"\n{len(counts)} {facet_key}")
        return 0

    total = len(queries)
    if a.limit:
        queries = queries[: a.limit]
    if a.output_json:
        print(json.dumps({"status": "success", "count": len(queries), "total_matched": total,
                          "results": [_slim(q) for q in queries]}, indent=2))
    else:
        _print_queries(queries, use_color, full=a.full)
        if a.limit and total > a.limit:
            print(f"(showing {a.limit} of {total}; use -n 0 for all)")
    return 0


def cmd_filter(argv, prog, lib_default):
    p = argparse.ArgumentParser(prog=prog, description="Multi-criteria search of the query library.",
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=textwrap.dedent("""\
                                examples:
                                  filter --text "access key" --type Logs
                                  filter --tag geoip --tag security --operator lookup -n 30
                                  filter --app kubernetes --field _sourcecategory --json
                                """))
    _add_filter_args(p)
    p.add_argument("-n", "--limit", type=int, default=25, metavar="N", help="max rows (default 25; 0 = all)")
    p.add_argument("--full", action="store_true", help="don't truncate descriptions")
    p.add_argument("--json", action="store_true", dest="output_json")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--db", default=str(lib_default), metavar="PATH", help="query_library.json path")
    a = p.parse_args(argv)
    if not any([a.text, a.qtype, a.mode, a.app, a.tag, a.operator, a.field, a.param, a.scope]):
        p.error("provide at least one filter (e.g. --text, --tag, --type, --app)")
    use_color = not a.no_color and sys.stdout.isatty()
    matched = _apply_filter(_load(Path(a.db)), a)
    total = len(matched)
    shown = matched[: a.limit] if a.limit else matched
    if a.output_json:
        print(json.dumps({"status": "success", "count": len(shown), "total_matched": total,
                          "results": [_slim(q) for q in shown]}, indent=2))
    else:
        _print_queries(shown, use_color, full=a.full)
        if a.limit and total > a.limit:
            print(f"(showing {a.limit} of {total}; use -n 0 for all)")
    return 0


def cmd_show(argv, prog, lib_default):
    p = argparse.ArgumentParser(prog=prog, description="Show full detail for one query (by id or hash).")
    p.add_argument("id", metavar="ID", help="query id (e.g. q0001) or hash")
    p.add_argument("--json", action="store_true", dest="output_json")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--db", default=str(lib_default), metavar="PATH", help="query_library.json path")
    a = p.parse_args(argv)
    use_color = not a.no_color and sys.stdout.isatty()
    queries = _load(Path(a.db))
    q = next((x for x in queries if x["id"] == a.id or x["hash"] == a.id), None)
    if not q:
        if a.output_json:
            print(json.dumps({"status": "error", "error": f"no query with id/hash {a.id!r}"}))
        else:
            print(f"No query with id or hash {a.id!r}", file=sys.stderr)
        return 1

    # Pull richer data from the per-query detail file when present (structured
    # metrics/traces queries, row context, template-variable definitions, full sources).
    detail = None
    if q.get("detailFile"):
        dp = Path(a.db).parent / q["detailFile"]
        if dp.is_file():
            try:
                detail = json.loads(dp.read_text())
            except (json.JSONDecodeError, OSError):
                detail = None

    if a.output_json:
        out = dict(q)
        if detail:
            out["metricsQueryData"] = detail.get("metricsQueryData")
            out["tracesQueryData"] = detail.get("tracesQueryData")
            out["queryParameters"] = detail.get("queryParameters")
            out["sources"] = detail.get("sources", q.get("sources"))  # full sources
        print(json.dumps({"status": "success", "query": out}, indent=2))
        return 0

    dsrc = (detail.get("sources") or [{}])[0] if detail else {}

    def h(label):
        print(_c(label, _BOLD, use_color))
    print(_c(f"{q['id']}  ", _BOLD, use_color) + _c(f"[{q['queryType']}]", _type_color(q["queryType"]), use_color)
          + f"  {q['queryMode']}  viewerType={q.get('viewerType')}  sources={q.get('sourceCount')}")
    if q.get("description"):
        h("\nDescription"); print(f"  {q['description']}")
    if q.get("tags"):
        h("\nTags"); print("  " + ", ".join(q["tags"]))

    # Query — text, or the structured query from the detail file
    if (q.get("query") or "").strip():
        h("\nQuery"); print(textwrap.indent(q["query"], "  "))
    elif detail and detail.get("tracesQueryData"):
        h("\nQuery (structured tracesQueryData)")
        print(textwrap.indent(json.dumps(detail["tracesQueryData"], indent=2), "  "))
    elif detail and detail.get("metricsQueryData"):
        h("\nQuery (structured metricsQueryData)")
        print(textwrap.indent(json.dumps(detail["metricsQueryData"], indent=2), "  "))
    else:
        h("\nQuery"); print("  (no query text; detail file unavailable)")

    if q.get("parameters"):
        h("\nParameters"); print("  " + ", ".join("{{%s}}" % p for p in q["parameters"]))
    if q.get("scopes"):
        h("\nScope"); print("  " + ", ".join(q["scopes"]))
    if q.get("operators"):
        h("\nOperators"); print("  " + ", ".join(q["operators"]))
    if q.get("metadataFields"):
        h("\nMetadata fields"); print("  " + ", ".join(q["metadataFields"]))

    # Template-variable definitions (from the detail file — richer than the flat param list)
    if dsrc.get("variables"):
        h("\nTemplate variables (dashboard)")
        for v in dsrc["variables"]:
            default = v.get("defaultValue")
            vals = v.get("values")
            line = f"  {v.get('name')} = {default!r}"
            if vals:
                line += f"   (values: {_trunc(str(vals), 60)})"
            print(line)
    if dsrc.get("rowContext"):
        h("\nRow context"); print("  " + " / ".join(dsrc["rowContext"]))

    h(f"\nSources ({q.get('sourceCount')})")
    for src in (detail.get("sources") if detail else q.get("sources")) or []:
        print(f"  • {src.get('panelTitle') or src.get('dashboardName')} — {src.get('objectType')}"
              f"{' · '+src['visualization'] if src.get('visualization') else ''}")
        print(f"    {src.get('dashboardName')}"
              f"{'  |  folder: '+src['folder'] if src.get('folder') else ''}  ({src.get('file')})")
        if src.get("dashboardDescription"):
            print(f"    desc: {_trunc(src['dashboardDescription'], 100)}")
    if q.get("detailFile"):
        h("\nDetail"); print(f"  {q['detailFile']} (visualSettings + full context)")
    return 0


def _slim(q):
    s = (q.get("sources") or [{}])[0]
    return {
        "id": q["id"], "hash": q["hash"], "queryType": q["queryType"], "queryMode": q["queryMode"],
        "app": q["_app"], "dashboard": s.get("dashboardName"), "panel": s.get("panelTitle"),
        "description": q.get("description"), "tags": q.get("tags"),
        "parameters": q.get("parameters"), "operators": q.get("operators"),
        "metadataFields": q.get("metadataFields"), "sourceCount": q.get("sourceCount"),
        "query": q.get("query"),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_DISPATCH = {"list": cmd_list, "filter": cmd_filter, "show": cmd_show}
_ALIASES = {"ls": "list", "f": "filter", "s": "show", "search": "filter"}


def main(argv=None, prog=None):
    argv = argv if argv is not None else sys.argv[1:]
    _prog = prog or "querylib"
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: querylib <command> [args...]\n\ncommands:")
        print("  list [KIND]   list queries, or facet values (tags/operators/fields/apps/types/modes)")
        print("  filter        multi-criteria search (--text/--type/--tag/--operator/--field/--app/…)")
        print("  show ID       full detail for one query (by id or hash)")
        print("\nAll commands accept --json and --no-color. Run 'querylib <command> --help' for flags.")
        return 0
    cmd = _ALIASES.get(argv[0], argv[0])
    if cmd not in _DISPATCH:
        print(f"querylib: unknown command {argv[0]!r}. Commands: list, filter, show", file=sys.stderr)
        return 1
    return _DISPATCH[cmd](argv[1:], prog=f"{_prog} {cmd}", lib_default=_DEFAULT_LIB)


if __name__ == "__main__":
    sys.exit(main())
