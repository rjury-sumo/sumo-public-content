# send_inventory.py

Posts mock Cloud SIEM custom inventory records (users and/or computers) to a
Sumo Logic HTTP source, using the generic
[custom inventory webhook schema](https://www.sumologic.com/help/docs/cse/administration/custom-inventory-sources/).

## Quick start

```bash
export SUMO_URL=https://.../receiver/v1/http/XXXX
./send_inventory.py --source okta --count 5
```

Dry-run without sending anything:

```bash
./send_inventory.py --source crowdstrike --count 3 --dry-run
```

## Sources

`--source` accepts any free-text label for a generic/custom mock, or one of
the known native inventory sources from
[Inventory sources and data](https://www.sumologic.com/help/docs/cse/administration/inventory-sources-and-data/):

`okta`, `azuread`, `crowdstrike`, `carbonblack`, `awsec2`, `cylance`,
`googleworkspace`, `qualys`, `rapid7`, `sailpoint`, `sentinelone`, `tenable`,
`windowsad`, `armis`.

For those, the mocked `uniqueID`/`deviceUniqueId` follow that source's real
ID prefix/format, so the data looks like what Sumo's actual connector would
produce, even though delivery still goes through the generic custom
inventory webhook. Run `--list-sources` to see each one's supported entity
type(s):

```bash
./send_inventory.py --list-sources
```

## Entity pools

Each `(source, entity-type)` pair keeps a local JSON pool file next to this
script: `inventory_pool_<source>_<type>.json`. This keeps an entity's
`uniqueID`/`deviceUniqueId` and other mocked attributes consistent across
runs instead of generating fresh random identities every time. Pools grow on
demand, up to `--pool-size` (default 1000) unique entities.

Inspect a pool without sending anything:

```bash
./send_inventory.py --source azuread --type computer --list
```

Pool files are regenerated data, not hand-authored fixtures — delete one to
force fresh mock identities/names for that source+type (e.g. after changing
the name lists in the script).

## Key options

| Flag | Purpose |
| --- | --- |
| `--source` | Source name (native or free-text custom), default `mocksource` |
| `--type` | `user`, `computer`, or custom; defaults to what `--source` supports, else `user` |
| `--count` | Number of records to send (default 1) |
| `--select {random,sequential}` | How to pick entities from the pool each run (default `random`) |
| `--indices` | Comma-separated explicit pool indices to send, overrides `--count`/`--select` |
| `--seed` | Seed for `--select random`, for reproducible selection |
| `--pool-size` | Max unique mocked entities per source/type (default 1000) |
| `--domain` | Email domain for mocked users (default `acme.corp`) |
| `--url` | Sumo HTTP source URL (default `$SUMO_URL`) |
| `--category` | Override `X-Sumo-Category` (default `cse/custom/inventory/<source>`) |
| `--fields` | Override `X-Sumo-Fields` |
| `--dry-run` | Print payloads instead of sending |
| `--list` | Print pool contents and exit |

Run `./send_inventory.py --help` for the full reference.

## Mocked names

User records draw first/last names from two pools (`FIRST_NAMES`,
`LAST_NAMES` in the script) covering a broad range of cultural origins
(East Asian, South Asian, African, Middle Eastern, Hispanic, Slavic, and
Western European, among others). Pairing is index-based but intentionally
decorrelated (first name cycles every record, last name is permuted by a
coprime stride) so even small `--count` runs produce varied full names
instead of repeating the same surname.

## See also

[siem_entities.py](siem_entities.md) — query the Cloud SIEM entities this
script's posted inventory data resolves into.
