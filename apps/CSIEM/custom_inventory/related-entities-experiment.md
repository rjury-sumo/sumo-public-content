# Experiment: does custom inventory data create Cloud SIEM entity relationships?

**Question:** Cloud SIEM entities have a `related-entities` API/UI feature. Custom
inventory posts ([send_inventory.py](send_inventory.md)) can create and enrich
entities. Does posting inventory data that cross-references multiple entities
(e.g. a user assigned to several hostnames) cause CSE to link those entities as
"related"?

**Answer: No.** Relationships are driven entirely by normalized log records, not
inventory data. Inventory can create and enrich entities, but cannot create
relationships between them.

## Background from Sumo's documentation

Before testing, we checked what Cloud SIEM's docs say about how relationships
are computed:

- **Involved entities** (insight-scoped only): entities that co-occur in the
  *same signal record* as an insight's primary entity.
- **Related entities** (insight graph view, and the standalone
  `GET /entities/{id}/related-entities` API): entities connected by a
  **"detected relationship"**, defined in the docs as *"when a relationship is
  detected between entities (for example, when an IP and hostname appear in a
  record together, but not necessarily in the insight being viewed)."*
- Per the Insight Generation Process doc, this works by scanning **normalized
  log records** for entity-pattern fields (`*_hostname`, `*_ip`, `*_username`,
  `*_mac`, `*_email`, `*_domain`, etc.) and treating two entity values as
  related if they co-occur **within one record**.
- The graph view's "time frame control" (how far outside an insight's own
  window to search for detected relationships) appears to be the same
  mechanism backing the API's required `start`/`end` window params — i.e. the
  standalone endpoint is a non-insight-scoped version of the same engine.

Nowhere do the docs describe custom inventory webhook posts as a source of
"records" for this purpose — everything is framed in terms of ingested log
events. That gap is what this experiment tests directly.

Sources:
- [About the Insight UI](https://www.sumologic.com/help/docs/cse/get-started-with-cloud-siem/about-cse-insight-ui/)
- [View and Manage Entities](https://www.sumologic.com/help/docs/cse/records-signals-entities-insights/view-manage-entities/)
- [Insight Generation Process](https://www.sumologic.com/help/docs/cse/get-started-with-cloud-siem/insight-generation-process/)

## Method

1. Picked `jsmith@acme.corp`, a username entity already created by earlier
   `send_inventory.py` testing, with 2 inventory entries (Okta → hostname
   `SEA-WS-0000`, Azure AD → hostname `CHI-WS-0000`).
2. Captured a **before** snapshot via [siem_entities.py](siem_entities.md):
   `get --expand-inventory`, `related`, and existence checks on both
   hostnames.
3. Posted 3 more `user`-type inventory records for the *same* username across
   3 new sources (`googleworkspace`, `sailpoint`, `vpn-mock`), each naming a
   *different* hostname/IP — simulating one person logging into 5 different
   computers in total.
4. Posted 2 matching `computer`-type inventory records (sources `crowdstrike`,
   `carbonblack`) for 2 of those new hostnames, so they'd exist as real,
   independently-tracked `_hostname` entities rather than just strings inside
   the user's inventory metadata.
5. Waited 8 minutes for Cloud SIEM to process.
6. Captured an **after** snapshot with the same checks, plus `related` on the
   two new hostname entities.

## Results

| Check | Before | After |
|---|---|---|
| jsmith inventory entries | 2 (Okta, Azure AD) | **5** (+googleworkspace, sailpoint, vpn-mock) |
| jsmith `activityScore` / `firstSeen` / `lastSeen` | `0` / `null` / `null` | unchanged |
| jsmith `related` (720h window) | `[]` | unchanged — `[]` |
| `AUS-LT-0099`, `LON-DT-0088` as real `_hostname` entities | didn't exist | now exist (posted as `computer` type) |
| `SEA-WS-0000`, `CHI-WS-0000`, `RMT-LT-0077` as real entities | didn't exist | **still don't exist** (only ever named inside a `user` record's `hostname` field) |
| `related` for `AUS-LT-0099` or `LON-DT-0088` → jsmith | — | `[]` — no link, despite jsmith's own inventory metadata naming both hostnames |

Full request/response payloads are in `entities_sample_*.json` and the
inline examples in [siem_entities.md](siem_entities.md#related-entities-related).

## Conclusion

1. **Inventory enriches and can create entities, but never creates
   relationships between them.** Tripling jsmith's inventory footprint (2 → 5
   "computers," spanning 5 distinct inventory sources) produced zero change
   in `activityScore`, `firstSeen`/`lastSeen`, or `related-entities` — for the
   username or for either hostname that was promoted to a real entity. This
   held even though jsmith's own inventory metadata literally contained both
   hostname strings — self-referencing data inside one entity's inventory
   does not get cross-indexed into another entity's relationships.
2. **Relationships require actual log/signal records with multiple
   entity-pattern fields co-occurring in the same record** (e.g. an
   authentication event with both `user_username` and `srcDevice_hostname`
   set). Custom inventory posts are never treated as "records" for this
   purpose, confirming the gap identified in the docs research above.
3. **A hostname only becomes its own `_hostname` entity via a `computer`-type
   inventory post (or real log activity) — not by being named inside a
   `user`-type record's `hostname` field.** Of the 3 hostnames only ever
   referenced inside jsmith's user inventory, none became entities; the 2
   also posted as `computer`-type inventory did.

**Practical implication:** to generate test data that exercises Cloud SIEM's
entity-relationship / related-entities features (e.g. for demoing the graph
view or testing automation that reads `related-entities`), posting via
`send_inventory.py` is not sufficient — it only populates entities and their
inventory metadata. Producing actual relationships requires sending
normalized log records (not inventory webhook posts) containing multiple
co-occurring entity fields.
