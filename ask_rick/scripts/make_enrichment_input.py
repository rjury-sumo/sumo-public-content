#!/usr/bin/env python3
"""
make_enrichment_input.py — Produce a slim, upload-ready input for AI enrichment.

Trims query_library.json down to only the fields an enrichment model needs (id, hash,
query text, and minimal context), dropping verbose fields (queryParameters, viewerType,
full source lists) so the Claude Desktop upload is smaller and the model sees less noise.

Output: ask_rick/output/enrichment_input.json  (a flat JSON array of query records).

Usage:  python3 make_enrichment_input.py [--out DIR]
"""
import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "output"))
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out)

    with open(os.path.join(out_dir, "query_library.json"), encoding="utf-8") as fh:
        lib = json.load(fh)

    slim = []
    for r in lib["queries"]:
        s = (r.get("sources") or [{}])[0]
        slim.append({
            "id": r["id"],
            "hash": r["hash"],
            "queryType": r["queryType"],
            "queryMode": r["queryMode"],
            "query": r["query"],
            "parameters": r["parameters"],
            "scopes": r["scopes"],
            "operators": r["operators"],
            "metadataFields": r["metadataFields"],
            "context": {
                "dashboard": s.get("dashboardName"),
                "folder": s.get("folder"),
                "panelTitle": s.get("panelTitle"),
                "visualization": s.get("visualization"),
            },
        })

    path = os.path.join(out_dir, "enrichment_input.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(slim, fh, ensure_ascii=False)  # compact — smaller upload
    print(f"wrote {os.path.relpath(path)}  ({len(slim)} queries, {os.path.getsize(path)//1024} KB)")


if __name__ == "__main__":
    main()
