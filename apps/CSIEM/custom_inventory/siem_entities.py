#!/usr/bin/env python3
"""Query Sumo Logic Cloud SIEM (CSE) entities — a companion tool to
send_inventory.py for inspecting how posted inventory data resolved into
CSE entities and their relationships.

Wraps three CSE REST endpoints (api/sec/v1):
    GET /entities                      -- list entities matching a DSL query
    GET /entities/{id}                 -- get a single entity
    GET /entities/{id}/related-entities -- entities related to one, in a time window

The `q` filter on `list` uses Cloud SIEM's custom DSL (field:"value", field:>N,
field:A..B, field:in("a","b"), field:contains("phrase")). Supported fields on
/entities: activityScore, criticality, hasIndicator, hostname, id, ip,
lastSeen, recentSignalSeverity, reputation, sensorZone, tag, type, username,
value, whitelisted. Pass raw clauses with -q/--query, or use the convenience
flags below (combined with raw clauses via AND).

Auth/region follow the same convention as the sumo-ai CLI (cli/config.py):
  SUMO_ACCESS_ID / SUMO_ACCESS_KEY   credentials (required)
  SUMO_REGION                        region label, default AU
  SUMO_ENDPOINT                      full API base URL, overrides --region
All are overridable with --access-id/--access-key/--region/--endpoint.

Examples:
  ./siem_entities.py list --entity-type _hostname --last-seen 7d
  ./siem_entities.py list -q 'tag:"vip"' --min-activity 5 --format json
  ./siem_entities.py get <entity-id> --expand-inventory
  ./siem_entities.py related <entity-id> --window 24h --format csv
"""
import argparse
import base64
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_REGION = "AU"

# Known Sumo Logic deployment regions and their API base URLs, mirroring
# sumo-ai's cli/config.py REGION_ENDPOINTS so region names behave the same
# way across both tools.
REGION_ENDPOINTS = {
    "US1": "https://api.sumologic.com",
    "US2": "https://api.us2.sumologic.com",
    "EU":  "https://api.eu.sumologic.com",
    "AU":  "https://api.au.sumologic.com",
    "JP":  "https://api.jp.sumologic.com",
    "CA":  "https://api.ca.sumologic.com",
    "IN":  "https://api.in.sumologic.com",
    "DE":  "https://api.de.sumologic.com",
    "KR":  "https://api.kr.sumologic.com",
    "CH":  "https://api.ch.sumologic.com",
    "ESC": "https://api.esc.sumologic.com",
    "FED": "https://api.fed.sumologic.com",
}

# --list convenience flag -> DSL field name, per the GET /entities `q` spec.
DSL_FIELDS = {
    "entity_type": "type",
    "value": "value",
    "hostname": "hostname",
    "username": "username",
    "ip": "ip",
    "tag": "tag",
    "criticality": "criticality",
}

ENTITY_COLUMNS = [
    "id", "entityType", "value", "activityScore", "criticality",
    "recentSignalSeverity", "isSuppressed", "firstSeen", "lastSeen", "tags",
]
RELATED_COLUMNS = [
    "id", "entityType", "value", "activityScore", "criticality", "isSuppressed", "tags",
]


# ---------------------------------------------------------------------------
# Auth / region
# ---------------------------------------------------------------------------

def resolve_endpoint(region: str, endpoint_override: str = None) -> str:
    if endpoint_override:
        return endpoint_override.rstrip("/")
    region = (region or DEFAULT_REGION).strip().upper()
    endpoint = REGION_ENDPOINTS.get(region)
    if not endpoint:
        raise SystemExit(
            f"Unknown region '{region}'. Known regions: {', '.join(sorted(REGION_ENDPOINTS))}"
        )
    return endpoint


# ---------------------------------------------------------------------------
# HTTP client — basic auth + 429 retry/backoff, same policy as sumo-ai's
# cli/http_client.py (4 req/s throttle, retry only on 429).
# ---------------------------------------------------------------------------

class CSEAPIError(Exception):
    def __init__(self, status_code: int, message: str, url: str = ""):
        self.status_code = status_code
        self.message = message
        self.url = url
        super().__init__(f"{status_code}: {message}")


class CSEClient:
    def __init__(self, access_id: str, access_key: str, endpoint: str):
        self.endpoint = endpoint.rstrip("/")
        token = base64.b64encode(f"{access_id}:{access_key}".encode()).decode()
        self._auth_header = f"Basic {token}"
        self._last_request_ts = 0.0

    def _throttle(self) -> None:
        min_interval = 0.25  # 4 req/s — Sumo Logic per-key rate limit
        gap = min_interval - (time.monotonic() - self._last_request_ts)
        if gap > 0:
            time.sleep(gap)
        self._last_request_ts = time.monotonic()

    def get(self, path: str, params: dict = None, max_retries: int = 3) -> dict:
        url = f"{self.endpoint}/api/sec/v1{path}"
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        for attempt in range(max_retries + 1):
            self._throttle()
            req = urllib.request.Request(url, headers={
                "Authorization": self._auth_header,
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(req) as resp:
                    body = resp.read().decode()
                    return json.loads(body) if body.strip() else {}
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode()
                if exc.code == 429 and attempt < max_retries:
                    wait = min(5.0 * (2 ** attempt), 60.0)
                    print(f"  [rate-limited] waiting {wait:.0f}s before retry "
                          f"({attempt + 1}/{max_retries})...", file=sys.stderr)
                    time.sleep(wait)
                    continue
                raise CSEAPIError(exc.code, detail, url)
        raise CSEAPIError(429, "retries exhausted", url)


# ---------------------------------------------------------------------------
# DSL helpers
# ---------------------------------------------------------------------------

def quote_dsl_value(value) -> str:
    return '"' + str(value).replace('"', '\\"') + '"'


def dsl_clause(field: str, value) -> str:
    return f"{field}:{quote_dsl_value(value)}"


def parse_duration_clause(spec: str, field: str) -> str:
    """'7d'/'24h' -> 'field:>NOW-7D'. A value that already looks like a DSL
    comparison/range (contains '..', '>', '<', or ':') is passed through
    as-is (prefixed with the field name if it doesn't already have one)."""
    spec = spec.strip()
    if ":" in spec:
        return spec  # already a full "field:..." clause
    if any(op in spec for op in ("..", ">", "<")):
        return f"{field}:{spec}"
    m = re.match(r"^(\d+)([smhdw])$", spec.lower())
    if not m:
        raise SystemExit(
            f"Invalid duration '{spec}'. Use e.g. 24h, 7d, 30d, or a raw DSL range/comparison."
        )
    amount, unit = m.groups()
    return f"{field}:>NOW-{amount}{unit.upper()}"


def build_dsl_query(clauses: list) -> str:
    # The API docs show clauses joined by '+', but that's how a space looks
    # once URL-encoded (form-encoding turns ' ' into '+') -- the decoded `q`
    # value itself takes a literal space between clauses. A literal '+' here
    # survives urlencode as a literal '+' in the query string, which the
    # server does NOT treat as an AND-separator: confirmed empirically, every
    # second clause after the first was silently ignored (type+lastSeen /
    # type+activityScore always returned the type-only count).
    return " ".join(c for c in clauses if c)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def parse_window(spec: str) -> timedelta:
    m = re.match(r"^(\d+(?:\.\d+)?)([smhdw])$", spec.lower().strip())
    if not m:
        raise SystemExit(f"Invalid --window value {spec!r}. Use e.g. 1h, 24h, 7d, 30m")
    amount, unit = float(m.group(1)), m.group(2)
    seconds = amount * {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    return timedelta(seconds=seconds)


def to_api_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(spec: str) -> datetime:
    dt = datetime.fromisoformat(spec)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(client: CSEClient, args) -> list:
    clauses = list(args.query or [])
    for flag_name, dsl_field in DSL_FIELDS.items():
        value = getattr(args, flag_name, None)
        if value:
            clauses.append(dsl_clause(dsl_field, value))
    if args.min_activity is not None:
        clauses.append(f"activityScore:>{args.min_activity}")
    if args.last_seen:
        clauses.append(parse_duration_clause(args.last_seen, "lastSeen"))
    q = build_dsl_query(clauses)

    page_size = max(1, min(args.limit, 50))  # 50 is the API's documented default/observed max
    max_items = None if args.all else args.max_items
    params_base: dict = {"limit": page_size}
    if q:
        params_base["q"] = q
    if args.expand_inventory:
        params_base["expand"] = "inventory"

    items: list = []
    offset = 0
    while True:
        resp = client.get("/entities", params={**params_base, "offset": offset})
        data = resp.get("data", {})
        batch = data.get("objects", [])
        items.extend(batch)
        if max_items is not None and len(items) >= max_items:
            return items[:max_items]
        if not data.get("hasNextPage") or not batch:
            return items
        offset += len(batch)


def cmd_get(client: CSEClient, args) -> dict:
    params = {"expand": "inventory"} if args.expand_inventory else None
    resp = client.get(f"/entities/{urllib.parse.quote(args.entity_id, safe='')}", params=params)
    return resp.get("data", {})


def cmd_related(client: CSEClient, args) -> list:
    end = parse_iso(args.end) if args.end else datetime.now(timezone.utc)
    start = parse_iso(args.start) if args.start else end - parse_window(args.window)
    params = {"start": to_api_timestamp(start), "end": to_api_timestamp(end)}
    resp = client.get(
        f"/entities/{urllib.parse.quote(args.entity_id, safe='')}/related-entities",
        params=params,
    )
    return resp.get("data", [])


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _cell(row: dict, col: str) -> str:
    v = row.get(col)
    if isinstance(v, list):
        return ";".join(str(x) for x in v)
    if v is None:
        return ""
    return str(v)


def format_table(rows: list, columns: list) -> str:
    if not rows:
        return "(no results)"
    widths = {c: max(len(c), *(len(_cell(r, c)) for r in rows)) for c in columns}
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    sep = "  ".join("-" * widths[c] for c in columns)
    body = ["  ".join(_cell(r, c).ljust(widths[c]) for c in columns) for r in rows]
    return "\n".join([header, sep, *body])


def format_record(record: dict) -> str:
    if not record:
        return "(not found)"
    width = max(len(k) for k in record)
    lines = []
    for k, v in record.items():
        if isinstance(v, (list, dict)):
            v = json.dumps(v)
        lines.append(f"{k.ljust(width)} : {v}")
    return "\n".join(lines)


def format_csv(rows: list, columns: list) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({c: _cell(r, c) for c in columns})
    return buf.getvalue()


def _emit(text: str, output: str = None) -> None:
    if output:
        Path(output).write_text(text)
        print(f"Wrote {output}", file=sys.stderr)
    else:
        print(text)


def output_many(items: list, columns: list, args) -> None:
    if args.format == "json":
        _emit(json.dumps(items, indent=2), args.output)
    elif args.format == "csv":
        _emit(format_csv(items, columns), args.output)
    else:
        _emit(format_table(items, columns), args.output)
    print(f"{len(items)} result(s)", file=sys.stderr)


def output_one(record: dict, args) -> None:
    if args.format == "json":
        _emit(json.dumps(record, indent=2), args.output)
    elif args.format == "csv":
        _emit(format_csv([record], list(record.keys())), args.output)
    else:
        _emit(format_record(record), args.output)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--access-id", default=os.environ.get("SUMO_ACCESS_ID"),
                    help="Sumo Logic access ID (default: $SUMO_ACCESS_ID)")
    p.add_argument("--access-key", default=os.environ.get("SUMO_ACCESS_KEY"),
                    help="Sumo Logic access key (default: $SUMO_ACCESS_KEY)")
    p.add_argument("--region", default=os.environ.get("SUMO_REGION", DEFAULT_REGION),
                    help=f"Deployment region, e.g. AU, US1, EU (default: $SUMO_REGION or {DEFAULT_REGION})")
    p.add_argument("--endpoint", default=os.environ.get("SUMO_ENDPOINT"),
                    help="Full API base URL, overrides --region (default: $SUMO_ENDPOINT)")
    p.add_argument("--format", choices=["table", "json", "csv"], default="table",
                    help="Output format (default: table)")
    p.add_argument("--output", help="Write output to this file instead of stdout")


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", aliases=["query", "ls"],
                             help="List entities matching a DSL query")
    p_list.add_argument("-q", "--query", action="append",
                         help="Raw DSL clause, e.g. 'tag:\"vip\"' — repeatable, AND-combined")
    p_list.add_argument("--entity-type", dest="entity_type",
                         help="Entity type DSL field, e.g. _username, _hostname, _ip_address")
    p_list.add_argument("--value", help="Exact entity value, e.g. a hostname or username string")
    p_list.add_argument("--hostname")
    p_list.add_argument("--username")
    p_list.add_argument("--ip")
    p_list.add_argument("--tag")
    p_list.add_argument("--criticality", help="e.g. CRITICAL, HIGH, MEDIUM, LOW")
    p_list.add_argument("--min-activity", type=int, dest="min_activity",
                         help="Only entities with activityScore greater than N")
    p_list.add_argument("--last-seen", dest="last_seen",
                         help="Duration (24h, 7d, 30d) or raw DSL range/comparison for lastSeen")
    p_list.add_argument("--expand-inventory", action="store_true", dest="expand_inventory",
                         help="Include each entity's linked inventory records in the response")
    p_list.add_argument("--limit", type=int, default=50,
                         help="Page size per API call, max 50 (default: 50)")
    p_list.add_argument("--max-items", type=int, default=100, dest="max_items",
                         help="Stop after this many total matches (default: 100)")
    p_list.add_argument("--all", action="store_true",
                         help="Disable --max-items cap (API caps /entities at 10,000 total)")
    _add_common_args(p_list)

    p_get = sub.add_parser(
        "get", help="Get a single entity by ID",
        description="Get a single entity by ID. Note: an unknown ID does not 404 -- the "
                    "API returns 200 with a placeholder entity synthesized from the ID "
                    "(entityType/value derived by splitting on the first '-', all activity "
                    "fields null/zero/empty). Treat a record with null firstSeen/lastSeen "
                    "and activityScore 0 as 'not found', not a real entity.",
    )
    p_get.add_argument("entity_id")
    p_get.add_argument("--expand-inventory", action="store_true", dest="expand_inventory",
                        help="Include the entity's linked inventory records in the response")
    _add_common_args(p_get)

    p_rel = sub.add_parser("related", aliases=["related-entities"],
                            help="Get entities related to a given entity within a time window")
    p_rel.add_argument("entity_id")
    p_rel.add_argument("--start", help="ISO8601 start of time range (default: now - --window)")
    p_rel.add_argument("--end", help="ISO8601 end of time range (default: now)")
    p_rel.add_argument("--window", default="24h",
                        help="Relative window ending now, used when --start/--end omitted "
                             "(default: 24h; API rejects a start/end span over 30 days)")
    _add_common_args(p_rel)

    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if not args.access_id or not args.access_key:
        print("Error: missing credentials. Set SUMO_ACCESS_ID/SUMO_ACCESS_KEY "
              "or pass --access-id/--access-key.", file=sys.stderr)
        return 1

    endpoint = resolve_endpoint(args.region, args.endpoint)
    client = CSEClient(args.access_id, args.access_key, endpoint)

    try:
        if args.command in ("list", "query", "ls"):
            output_many(cmd_list(client, args), ENTITY_COLUMNS, args)
        elif args.command == "get":
            output_one(cmd_get(client, args), args)
        elif args.command in ("related", "related-entities"):
            output_many(cmd_related(client, args), RELATED_COLUMNS, args)
    except CSEAPIError as exc:
        print(f"API error {exc.status_code}: {exc.message}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
