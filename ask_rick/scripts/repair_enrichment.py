#!/usr/bin/env python3
"""
repair_enrichment.py — Re-key enrichment.json to the current query_library.json.

After a fresh full extract, query ids are renumbered (q0001…). If enrichment.json was
assembled across extractions its `id` values can be stale/duplicated (the hash is always the
real join key). This rewrites each entry's `id` to the current library's id for its hash,
dedupes by hash, drops entries whose hash no longer exists, and orders entries to match the
library — leaving a clean, id-unique file. Matching is by hash throughout.

A backup of the original is written to enrichment.json.bak.

Usage:  python3 repair_enrichment.py [--out DIR]
"""
import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "output"))
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out)

    lib = json.load(open(os.path.join(out_dir, "query_library.json"), encoding="utf-8"))["queries"]
    hash2id = {q["hash"]: q["id"] for q in lib}

    path = os.path.join(out_dir, "enrichment.json")
    data = json.load(open(path, encoding="utf-8"))
    entries = data if isinstance(data, list) else (
        data.get("enrichments") or data.get("queries") or [])

    by_hash, dropped, dupes = {}, 0, 0
    for e in entries:
        h = e.get("hash")
        if h not in hash2id:
            dropped += 1
            continue
        if h in by_hash:
            dupes += 1        # duplicate hash — keep the first
            continue
        by_hash[h] = e

    # emit in library order, with the current id
    repaired = []
    for q in lib:
        e = by_hash.get(q["hash"])
        if e:
            repaired.append({
                "id": q["id"],
                "hash": q["hash"],
                "description": e.get("description"),
                "tags": e.get("tags", []),
            })

    ids = [r["id"] for r in repaired]
    assert len(ids) == len(set(ids)), "id collision after repair — should not happen"

    with open(path + ".bak", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(repaired, fh, ensure_ascii=False)

    print(f"library queries : {len(lib)}")
    print(f"repaired entries: {len(repaired)} (ids now unique, ordered to library)")
    print(f"dropped (hash not in library): {dropped} | duplicate-hash entries removed: {dupes}")
    print(f"library queries still without enrichment: {len(lib) - len(repaired)}")
    print(f"backup: {os.path.relpath(path)}.bak")


if __name__ == "__main__":
    main()
