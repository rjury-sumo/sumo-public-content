#!/usr/bin/env python3
"""
make_enrichment_input.py — Produce a slim, upload-ready input for AI enrichment,
grouped by source dashboard so an enrichment model sees each dashboard's panels
together (shared context → more coherent descriptions and consistent tags).

Trims query_library.json to only the fields enrichment needs, then groups queries by
their primary source (file + dashboard). Dashboard/folder context lives once per group;
each query keeps its panel-level detail.

Output: ask_rick/output/enrichment_input.json — a JSON array of groups:
  [ { "file", "objectType", "dashboard", "folder", "queries": [ {id, hash, queryType,
      queryMode, panelTitle, visualization, query, parameters, scopes, operators,
      metadataFields}, ... ] }, ... ]

Usage:  python3 make_enrichment_input.py [--out DIR] [--missing-only]

--missing-only: emit only queries that don't yet have a (non-empty) description in
existing enrichment (enrichment.json and/or enrichment/*.json), matched by hash — so a
follow-up run only covers newly-added queries. Append its results to enrichment.json.
"""
import argparse
import json
import os
from collections import OrderedDict


def enriched_hashes(out_dir):
    """Hashes that already have a non-empty description (same sources as build_webview)."""
    done = set()

    def take(e):
        if isinstance(e, dict) and e.get("hash") and (e.get("description") or "").strip():
            done.add(e["hash"])

    ed = os.path.join(out_dir, "enrichment")
    if os.path.isdir(ed):
        for fn in os.listdir(ed):
            if fn.endswith(".json"):
                try:
                    take(json.load(open(os.path.join(ed, fn), encoding="utf-8")))
                except (json.JSONDecodeError, OSError):
                    pass
    cf = os.path.join(out_dir, "enrichment.json")
    if os.path.isfile(cf):
        try:
            data = json.load(open(cf, encoding="utf-8"))
            for e in (data if isinstance(data, list)
                      else data.get("enrichments") or data.get("queries") or []):
                take(e)
        except (json.JSONDecodeError, OSError):
            pass
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "output"))
    ap.add_argument("--missing-only", action="store_true",
                    help="only queries with no existing description (matched by hash)")
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out)

    with open(os.path.join(out_dir, "query_library.json"), encoding="utf-8") as fh:
        lib = json.load(fh)

    skip = enriched_hashes(out_dir) if args.missing_only else set()

    groups = OrderedDict()  # (file, dashboard) -> group
    for r in lib["queries"]:
        if r["hash"] in skip:
            continue
        s = (r.get("sources") or [{}])[0]
        key = (s.get("file"), s.get("dashboardName"))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "file": s.get("file"),
                "objectType": s.get("objectType"),
                "dashboard": s.get("dashboardName"),
                "folder": s.get("folder"),
                "queries": [],
            }
        g["queries"].append({
            "id": r["id"],
            "hash": r["hash"],
            "queryType": r["queryType"],
            "queryMode": r["queryMode"],
            "panelTitle": s.get("panelTitle"),
            "visualization": s.get("visualization"),
            "query": r["query"],
            "parameters": r["parameters"],
            "scopes": r["scopes"],
            "operators": r["operators"],
            "metadataFields": r["metadataFields"],
        })

    grouped = list(groups.values())
    fname = "enrichment_input_missing.json" if args.missing_only else "enrichment_input.json"
    path = os.path.join(out_dir, fname)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(grouped, fh, ensure_ascii=False)  # compact — smaller upload

    qn = sum(len(g["queries"]) for g in grouped)
    mode = "MISSING-ONLY" if args.missing_only else "full"
    print(f"wrote {os.path.relpath(path)}  [{mode}]  ({len(grouped)} dashboards/groups, "
          f"{qn} queries, {os.path.getsize(path)//1024} KB)")
    if args.missing_only:
        print(f"(skipped {len(skip)} already-described queries; run Desktop on these, then "
              f"append results to enrichment.json)")
    if grouped:
        sizes = sorted(len(g["queries"]) for g in grouped)
        print(f"group sizes: min {sizes[0]} / median {sizes[len(sizes)//2]} / max {sizes[-1]} queries")
    else:
        print("nothing to enrich — every query already has a description.")


if __name__ == "__main__":
    main()
