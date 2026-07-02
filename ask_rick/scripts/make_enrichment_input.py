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

Usage:  python3 make_enrichment_input.py [--out DIR]
"""
import argparse
import json
import os
from collections import OrderedDict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "output"))
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out)

    with open(os.path.join(out_dir, "query_library.json"), encoding="utf-8") as fh:
        lib = json.load(fh)

    groups = OrderedDict()  # (file, dashboard) -> group
    for r in lib["queries"]:
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
    path = os.path.join(out_dir, "enrichment_input.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(grouped, fh, ensure_ascii=False)  # compact — smaller upload

    qn = sum(len(g["queries"]) for g in grouped)
    sizes = sorted(len(g["queries"]) for g in grouped)
    med = sizes[len(sizes)//2] if sizes else 0
    print(f"wrote {os.path.relpath(path)}  ({len(grouped)} dashboards/groups, "
          f"{qn} queries, {os.path.getsize(path)//1024} KB)")
    print(f"group sizes: min {sizes[0]} / median {med} / max {sizes[-1]} queries")


if __name__ == "__main__":
    main()
