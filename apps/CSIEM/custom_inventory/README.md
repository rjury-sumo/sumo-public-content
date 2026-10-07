# send-test-data

Scripts for generating and posting mock Cloud SIEM data, and for inspecting
the resulting entities/relationships via the CSE API.

- [send_inventory.py](send_inventory.md) — posts mock custom inventory
  records (users/computers) to a Sumo Logic HTTP source.
- [siem_entities.py](siem_entities.md) — queries Cloud SIEM entities and
  their relationships via the DSL search API, to see how posted inventory
  resolved.
- [related-entities-experiment.md](related-entities-experiment.md) — write-up
  of an experiment proving inventory data can create/enrich entities but
  never creates relationships between them (those require normalized log
  records).
- [custom-inventory-direct-post.md](custom-inventory-direct-post.md) —
  supplements Sumo's own custom-inventory docs: proves/documents direct HTTP
  posting (no scheduled search/webhook connector needed) and the field
  behavior we found along the way.
