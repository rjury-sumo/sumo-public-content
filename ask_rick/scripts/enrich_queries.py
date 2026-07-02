#!/usr/bin/env python3
"""
enrich_queries.py — One-time AI enrichment of the query library.

For each unique query in query_library.json, calls Claude to produce a plain-English
description of what the query does plus a set of semantic tags, and writes the result to
enrichment/<id>.json. Keyed by the query hash so enrichment survives re-extraction as long
as the query text is unchanged.

Idempotent / resumable: skips any query that already has a matching enrichment file
(same hash). Safe to re-run after interruption.

Requires the Anthropic SDK (`pip install anthropic`) and ANTHROPIC_API_KEY in the env.

Usage:
  python3 enrich_queries.py [--out DIR] [--model claude-opus-4-8] [--limit N] [--force]

Cost note: this is a bulk, non-latency-sensitive job. For the full library (~1000+ queries)
consider the Message Batches API (50% cost) — see the note at the bottom of this file.
"""
import argparse
import json
import os
import sys

try:
    import anthropic
except ImportError:
    sys.exit("anthropic SDK not installed. Run: pip install anthropic")

from pydantic import BaseModel


class Enrichment(BaseModel):
    description: str          # 1-3 sentence plain-English explanation of what the query does
    tags: list[str]           # 3-8 lowercase kebab-case semantic tags


SYSTEM = (
    "You are a Sumo Logic query expert. Given a Sumo Logic search or metrics query and its "
    "dashboard context, explain in plain English what the query does and what question it "
    "answers, then assign concise semantic tags. Be accurate and specific about the data "
    "source, transformations, and intent. Descriptions: 1-3 sentences, no preamble. "
    "Tags: 3-8 lowercase kebab-case terms covering domain (e.g. audit, security, cost, "
    "kubernetes), data source (e.g. audit-events, search-usage), technique (e.g. geoip, "
    "time-compare, json-parsing), and intent (e.g. anomaly-detection, capacity-planning)."
)


def build_prompt(rec):
    src = (rec.get("sources") or [{}])[0]
    ctx = {
        "queryType": rec.get("queryType"),
        "queryMode": rec.get("queryMode"),
        "dashboard": src.get("dashboardName"),
        "folder": src.get("folder"),
        "panelTitle": src.get("panelTitle"),
        "visualization": src.get("visualization"),
        "parameters": rec.get("parameters"),
        "operators": rec.get("operators"),
        "scopes": rec.get("scopes"),
    }
    body = rec.get("query") or json.dumps(rec.get("metricsQueryData") or rec.get("tracesQueryData") or {})
    return (
        f"Context:\n{json.dumps(ctx, indent=2)}\n\n"
        f"Query:\n```\n{body}\n```\n\n"
        "Describe what this query does and assign tags."
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "output"))
    ap.add_argument("--model", default="claude-haiku-4-5",
                    help="Claude model (default: claude-haiku-4-5 for cost; "
                         "use --model claude-opus-4-8 for higher quality)")
    ap.add_argument("--limit", type=int, default=None, help="max queries to enrich this run")
    ap.add_argument("--force", action="store_true", help="re-enrich even if a file exists")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    enrich_dir = os.path.join(out_dir, "enrichment")
    os.makedirs(enrich_dir, exist_ok=True)

    with open(os.path.join(out_dir, "query_library.json"), encoding="utf-8") as fh:
        library = json.load(fh)

    client = anthropic.Anthropic()
    queries = library["queries"]
    done = skipped = failed = 0
    for rec in queries:
        path = os.path.join(enrich_dir, f"{rec['id']}.json")
        if os.path.exists(path) and not args.force:
            # verify hash still matches; if not, re-enrich
            try:
                if json.load(open(path)).get("hash") == rec["hash"]:
                    skipped += 1
                    continue
            except (json.JSONDecodeError, OSError):
                pass
        if args.limit is not None and done >= args.limit:
            break
        try:
            resp = client.messages.parse(
                model=args.model,
                max_tokens=1024,
                system=SYSTEM,
                messages=[{"role": "user", "content": build_prompt(rec)}],
                output_format=Enrichment,
            )
            e = resp.parsed_output
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "id": rec["id"],
                        "hash": rec["hash"],
                        "description": e.description,
                        "tags": [t.strip().lower() for t in e.tags if t.strip()],
                        "model": args.model,
                    },
                    fh, indent=2, ensure_ascii=False,
                )
            done += 1
            if done % 25 == 0:
                print(f"  enriched {done} (skipped {skipped}, failed {failed})")
        except Exception as ex:  # noqa: BLE001 - keep going on any single-query failure
            failed += 1
            print(f"  FAILED {rec['id']}: {type(ex).__name__}: {ex}", file=sys.stderr)

    print(f"done: enriched {done}, skipped(existing) {skipped}, failed {failed}")
    print(f"enrichment files in: {os.path.relpath(enrich_dir)}")


if __name__ == "__main__":
    main()

# Scaling to the full library with the Batches API (50% cheaper, async):
#   Build one Request(custom_id=rec["id"], params=MessageCreateParamsNonStreaming(...))
#   per query, submit via client.messages.batches.create(requests=[...]), poll until
#   processing_status == "ended", then write enrichment/<custom_id>.json from each result.
#   Results are unordered — key by custom_id. See the claude-api skill (batches.md).
