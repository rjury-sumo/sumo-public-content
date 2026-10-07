# siem_entities.py

A read-only companion to [send_inventory.py](send_inventory.md) for
inspecting how posted inventory data (and any other log activity) resolved
into Cloud SIEM entities and their relationships. Wraps three CSE REST
endpoints:

```text
GET /entities                        list    -- entities matching a DSL query
GET /entities/{id}                   get     -- a single entity
GET /entities/{id}/related-entities  related -- entities related to one, in a time window
```

## Quick start

```bash
./siem_entities.py list --entity-type _hostname --max-items 10
./siem_entities.py get _hostname-chi--dt--0008 --expand-inventory
./siem_entities.py related _username-someuser --window 24h --format csv
```

## Auth / region

Same convention as the `sumo-ai` CLI:

| Source | Purpose |
| --- | --- |
| `SUMO_ACCESS_ID` / `SUMO_ACCESS_KEY` | credentials (required) |
| `SUMO_REGION` | region label, default `AU` |
| `SUMO_ENDPOINT` | full API base URL — takes priority over `--region`/`SUMO_REGION` |
| `--access-id` / `--access-key` / `--region` / `--endpoint` | per-invocation overrides |

## DSL query (`list`)

The CSE `q` filter uses field-colon-value clauses, e.g. `type:"_hostname"`,
`activityScore:>5`, `tag:in("vip","exec")`. **Multiple clauses are joined
with a literal space, not `+`** — the `+` shown in Sumo's own API docs is how
a space renders once URL-encoded, not a literal character in the decoded
query. (Confirmed empirically: a literal `+` between clauses makes every
clause after the first silently no-op.)

Supported fields on `/entities`: `activityScore`, `criticality`,
`hasIndicator`, `hostname`, `id`, `ip`, `lastSeen`, `recentSignalSeverity`,
`reputation`, `sensorZone`, `tag`, `type`, `username`, `value`,
`whitelisted`.

Pass raw clauses with `-q`/`--query` (repeatable), or use convenience flags
that map to the same fields and AND-combine with any raw clauses:
`--entity-type`, `--value`, `--hostname`, `--username`, `--ip`, `--tag`,
`--criticality`, `--min-activity`, `--last-seen` (duration like `7d`/`24h`,
or a raw range/comparison).

```bash
./siem_entities.py list -q 'tag:"vip"' --min-activity 5 --format json
```

Results auto-paginate up to `--max-items` (default 100; `--all` removes the
cap, up to the API's 10,000-entity ceiling for `/entities`).

## Entity lookup (`get`)

An unknown ID does **not** 404 — the API returns 200 with a placeholder
entity synthesized from the ID string itself (entityType/value derived by
splitting on the first `-`, activity fields null/zero/empty). Treat a
result with null `firstSeen`/`lastSeen` and `activityScore: 0` as "not
found," not a real entity. `--expand-inventory` includes the raw inventory
record(s) backing the entity — useful for confirming a `send_inventory.py`
post actually resolved into the expected entity.

## Related entities (`related`)

Requires a time window (`start`/`end`); `--window` (default `24h`) sets it
relative to now when `--start`/`--end` aren't given. The API rejects a
window wider than 30 days.

**Custom inventory data does not create related entities — confirmed
empirically.** Cloud SIEM's relationship detection (both this endpoint and
the Insight graph view) scans *normalized log records* for entity-pattern
fields (`*_hostname`, `*_ip`, `*_username`, etc.) that co-occur in the same
record; it does not treat inventory webhook posts as records for this
purpose. Test: posted 5 `user`-type inventory entries for one username
across 5 sources, each naming a different hostname (simulating one person
using 5 computers), plus matching `computer`-type posts for 2 of those
hostnames so they'd exist as real entities too. After waiting 8 minutes:
`activityScore`/`firstSeen`/`lastSeen` were unchanged (still `0`/`null`/
`null`) and `related` returned `[]` for the username AND for both hostname
entities — even though the username's own inventory metadata literally
named both hostnames. Relationships need actual co-occurring log/signal
activity, not inventory assignment.

A related finding from the same test: a hostname only becomes its own
`_hostname` entity when posted as a `computer`-type inventory record
directly. Referencing a hostname inside a `user`-type record's `hostname`
field (as `send_inventory.py`'s user payloads do) never promotes it to a
standalone entity — of the 3 hostnames only named inside jsmith's user
inventory (never posted as `computer` type), none existed as real entities,
while the 2 also posted as `computer` type did.

## Output formats

`--format table|json|csv` (default `table`); `--output FILE` writes to a
file instead of stdout.

## Sample data

`entities_sample_*.json` were captured against the default sandbox
instance (AU region) while smoke-testing this tool — safe to commit since
it's synthetic/mock org data, not real customer data. They're a quick
reference for each endpoint's response shape:

- `entities_sample_hostname.json` — `list --entity-type _hostname --expand-inventory`
- `entities_sample_active.json` — `list -q 'activityScore:>0'`
- `entities_sample_get_hostname.json` — `get <id> --expand-inventory`, confirming a `send_inventory.py` post resolved into a real entity
- `entities_sample_related.json` — `related <id>`; empty in this sandbox (sparse log activity means few/no correlated relationships yet), but shows the valid empty-array shape
