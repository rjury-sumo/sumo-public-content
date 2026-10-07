# Supplement: posting custom inventory directly, without a scheduled search

Sumo's own docs for this feature —
[Custom Inventory Sources](https://www.sumologic.com/help/docs/cse/administration/custom-inventory-sources/) —
describe only one ingestion path: configure a **scheduled search** whose
results feed a **Webhook alert** that posts to an HTTP Source. That's the
right approach for *live* data (e.g. mirroring a real JAMF/CarbonBlack
inventory on a schedule), but it implies the webhook/scheduled-search
machinery is required to get data in at all.

It isn't. [send_inventory.py](send_inventory.md) in this directory proves
the inventory webhook is a plain HTTP endpoint — any direct `POST` with the
right fields and headers works, with no scheduled search or webhook
connector involved. This doc captures what we learned building and testing
it that the published doc doesn't spell out.

## Why this matters: criticality, not just relationships

The same docs page's FAQ answers a question directly relevant here:

> **Can you use a custom inventory source to set entity criticality?**
> Yes. Attributes ingested through a custom inventory source can be used in
> entity groups to set attributes on entities, which you can then use in
> detection rule definitions and to adjust signal severity through
> criticality.

So while [related-entities-experiment.md](related-entities-experiment.md)
shows inventory data can't create *relationships*, it's explicitly the
supported mechanism for driving entity **criticality** — via *entity group*
configs (`entity-group-configurations` / `entity-criticality-configs` in
the CSE API) that match on inventory attributes and assign a criticality
tier, which then feeds signal severity and rule logic.

[Create an Entity Group](https://www.sumologic.com/help/docs/cse/records-signals-entities-insights/create-an-entity-group/)
spells out how that matching works, and it lines up directly with the
fields `send_inventory.py` posts:

- An entity group can be **inventory-based** (vs. values-based matching on
  the entity's own value/prefix/suffix/IP range). Inventory-based groups
  match on **Computer** or **User** inventory type, and the inventory key
  you match on can be a "second-level unnormalized inventory attribute"
  like `fields.foo.bar` — **or the `groups` attribute itself**, which is
  literally the field `send_inventory.py` populates on every user/computer
  record (e.g. `["Domain Users", "Sales-Team"]`). Matching supports regex.
- Criticality (and suppression) are set **at the group level** and
  inherited by every entity that matches: *"Each laptop in the 'laptops'
  group will automatically inherit the criticality defined for the entity
  group."*
- Group **tags** are inherited by the entity and then by any insight that
  fires on it, and are readable in rule logic via
  `array_contains(fieldTags["srcDevice_ip"], "DB Server")`-style
  expressions.
- If an entity matches multiple entity groups, **tags from all matching
  groups apply, but criticality/suppression come from only the first
  matching group** — so group match order matters once you have more than
  one inventory-based group.

Practically: posting via `send_inventory.py` with a deliberately-chosen
`--source`/department/groups combination is a realistic way to generate
inventory that an inventory-based entity group can match on, to test
criticality-driven signal severity end-to-end — distinct from testing
relationship detection, which (per the experiment above) inventory data
cannot drive.

### The full chain, end to end

Putting the pieces from the three docs above together, custom inventory can
influence rule/signal behavior through one specific path:

```text
1. POST custom inventory  ──────────────────────────────────────────────
   (send_inventory.py)       creates/enriches an entity, e.g. sets
                              `groups: ["Domain Users", "Sales-Team"]`
                              on a _username entity's inventory metadata
                              └─ Custom Inventory Sources docs

2. Entity Group match      ──────────────────────────────────────────────
   (inventory-based)          an entity group configured to match
                              inventory type "User", key `groups`,
                              value "Sales-Team" matches the entity
                              └─ Create an Entity Group docs

3. Group assigns           ──────────────────────────────────────────────
   criticality + tags         the matching entity inherits the group's
                              criticality (e.g. "High") and any keyword
                              tags (e.g. "DB Server") the group applies
                              └─ Create an Entity Group docs

4. Tag used in a rule      ──────────────────────────────────────────────
   expression                 a detection rule (or rule tuning expression)
                              checks the tag via:
                                array_contains(fieldTags["srcDevice_ip"], "DB Server")
                              └─ Cloud SIEM Rules Syntax docs

5. Signal/insight impact   ──────────────────────────────────────────────
                              the rule fires differently (or not at all)
                              depending on the tag check, and/or the
                              entity's inherited criticality adjusts the
                              resulting signal's severity
                              └─ Custom Inventory Sources FAQ (criticality → severity)
```

So `send_inventory.py` sits at step 1 of a chain that can genuinely reach
rule logic and signal severity — just never at step 2 directly. Inventory
data can't be read by a rule expression itself; it only matters once an
entity group has turned an inventory attribute into criticality or a tag.
That's the structural reason the relationship-detection experiment came up
empty (there's no entity-group-equivalent step for relationships — see
[related-entities-experiment.md](related-entities-experiment.md)) while
criticality/tagging genuinely works.

References for this chain:

- [Custom Inventory Sources](https://www.sumologic.com/help/docs/cse/administration/custom-inventory-sources/) (step 1)
- [Create an Entity Group](https://www.sumologic.com/help/docs/cse/records-signals-entities-insights/create-an-entity-group/) (steps 2-3)
- [Cloud SIEM Rules Syntax](https://www.sumologic.com/help/docs/cse/rules/cse-rules-syntax/) (step 4, `fieldTags`/`array_contains` syntax)

## Minimum setup for direct posting

1. An **HTTP Source** on a Hosted Collector (the exact same kind of endpoint
   used for log ingestion — nothing inventory-specific about the source
   itself).
2. Cloud SIEM needs to know the posted data is (a) meant for SIEM at all and
   (b) specifically inventory data. The docs describe doing this once, at
   the source level: tick "Enable SIEM Processing" and add a custom field
   `_siemdatatype = inventory` on the HTTP Source.

   Posting directly, you don't need to touch the source config at all —
   send the equivalent metadata **per request** instead, via the
   `X-Sumo-Fields` header:

   ```
   X-Sumo-Fields: _siemdatatype=inventory,_siemForward=true
   ```

   `_siemForward=true` is the general "send this to Cloud SIEM" flag (the
   source-level checkbox is just this field pre-set for you); `_siemdatatype
   =inventory` is what tells CSE to treat the payload as inventory rather
   than a log record. Both work identically whether set on the source or
   per-request — `send_inventory.py` uses the per-request form so the HTTP
   Source needs zero special configuration.
3. `Content-Type: application/json`, body = one inventory record per POST.
   `X-Sumo-Category` is optional/free-text (we use
   `cse/custom/inventory/<source>`) — it doesn't affect inventory
   processing, just log categorization.

## Payload fields, confirmed by testing

Mandatory on every record (per the published docs, confirmed by us): `type`
(`"user"` or `"computer"`), `source` (free-text label for the origin
system), `customInventory: true`.

Beyond that, what actually matters is which field CSE uses to **resolve the
entity value**:

- `type: "user"` → entity value comes from `username` (confirmed: posting
  `username: "jsmith@acme.corp"` produces entity id
  `_username-jsmith@acme.corp`, regardless of what `userId`/`uniqueID` you
  send).
- `type: "computer"` → entity value comes from `hostname` (confirmed:
  posting `hostname: "AUS-LT-0099"` produces entity id
  `_hostname-aus--lt--0099`).

Everything else (`emails`, `department`, `groups`, `ip`, `mac`, `osVersion`,
`uniqueID`, …) is enrichment stored in that inventory entry's `metadata`,
not used for entity resolution. The docs' "at a minimum" field lists
(`username`/`userID`/`emails`/`groups` for users;
`computername`/`deviceUniqueId`/`hostname` for hosts) are good practice for
a usable inventory record, but only `username`/`hostname` is load-bearing
for which entity you hit.

## Behavior the docs don't mention

- **One POST = one inventory entry, keyed by `(source, entity value)` — not
  by any ID you send.** Re-posting the same `username`+`source` overwrites
  that single entry. Posting the same `username` under a *different*
  `source` string adds an **additional** entry — the entity's `inventory[]`
  array accumulates one entry per distinct source, not per post. We
  confirmed a single username entity holding 5 separate inventory entries
  (Okta, Azure AD, googleworkspace, sailpoint, and a made-up `vpn-mock`
  source), each with different `hostname`/`ip` — see
  [related-entities-experiment.md](related-entities-experiment.md).
- **A `user` record's `hostname` field does not create a `_hostname`
  entity.** It only enriches the username entity's inventory metadata. A
  hostname becomes its own tracked entity only via a `type: "computer"`
  post naming it.
- **Processing is near-real-time**, not scheduled-search-cadence: comparing
  the `timestamp` we sent vs. the server-assigned `parsedTime` in the
  entity's `inventory[]` array, posts were processed within ~20-30 seconds.
  `siem_entities.py get <id> --expand-inventory` right after a post is
  enough to confirm it landed — no need to wait minutes.
- **Posting inventory never creates entity relationships**, no matter how
  much cross-referencing data you put in it. Full write-up:
  [related-entities-experiment.md](related-entities-experiment.md).

## See also

- [send_inventory.py](send_inventory.md) — the direct-post implementation.
- [siem_entities.py](siem_entities.md) — verifying what a post actually
  created via the CSE entities API.
