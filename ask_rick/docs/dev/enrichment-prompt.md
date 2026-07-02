# Enriching the query library in Claude Desktop (bring-your-own-model)

Generate `description` + `tags` for every query using a model you pick — no API key, no scripts.
Then feed the result back into the webview. Setup is copy-paste.

## Set up the project (once)
1. **Claude Desktop → new Project.** Name it e.g. `Sumo Query Library — Enrichment`. Pick your model.
2. **Add project knowledge:** upload `ask_rick/output/enrichment_input.json`
   (the slim, upload-ready file — ~1.1 MB, only the fields enrichment needs).
   Regenerate it any time with `python3 ask_rick/scripts/make_enrichment_input.py`.
3. **Paste the block below into the project's Custom Instructions** (or just send it as the
   first message).

## Run it
4. Start a chat in the project and say: `Begin with batch 1.`
5. Claude emits results in batches of 40 as JSON arrays. Say `next` after each until it says `DONE`.
6. Collect every batch's array into one flat JSON array and save as
   **`ask_rick/output/enrichment.json`**.
7. Rebuild:
   ```
   python3 ask_rick/scripts/build_webview.py
   ```
   It merges `enrichment.json` (matched by `hash`, falling back to `id`) and reports how many
   queries were described.

> Assembly tip: each batch is a bare `[ ... ]` array. Paste them into one file, comma-separating
> between batches, wrapped in a single outer `[ ]`. Or, at `DONE`, ask Claude to reprint the full
> combined array in one code block if it fits.

---

## Custom Instructions / first-message prompt (paste this)

You are a Sumo Logic query expert. The project file `enrichment_input.json` is a JSON array of
Sumo Logic search and metrics queries extracted from dashboards. Your job is to write, for every
query, a plain-English description of what it does and a set of semantic tags.

**Each input record** looks like:
`{ id, hash, queryType, queryMode, query, parameters, scopes, operators, metadataFields,
context: { dashboard, folder, panelTitle, visualization } }`.
Use the `query` text plus `context` to understand intent.

**For each query, produce an object:**
```json
{
  "id": "<copy verbatim from input>",
  "hash": "<copy verbatim from input>",
  "description": "1-3 sentences, plain English. State the data source (index/view), the key
                  transformations, and the question it answers. No preamble, no 'This query'.",
  "tags": ["3-8 lowercase-kebab-case tags"]
}
```

**Tag guidance** — cover these dimensions where they apply, and reuse consistent tags across
queries so they cluster well:
- domain: `audit`, `security`, `cost`, `capacity`, `kubernetes`, `tracing`, `data-volume`, …
- data source: `audit-events`, `search-usage`, `collector`, `metrics`, …
- technique: `geoip`, `json-parsing`, `timeslice`, `time-compare`, `transpose`, `lookup`, …
- intent: `anomaly-detection`, `capacity-planning`, `troubleshooting`, `alerting`, `overview`, …

**Rules:**
- Copy `id` and `hash` exactly — they are the join key; never invent or reorder them.
- Be accurate and specific. If a query is parameterized (`{{param}}`), say what the filter does.
  For metrics queries, note the metric filter and aggregation. For a query with empty text
  (structured metrics/traces), infer intent from `context.panelTitle`.
- Keep descriptions tight — one to three sentences.

**Output protocol (to avoid truncation):**
- Process the queries in input order, in **batches of 40**.
- For each batch, output **only** a single fenced ```json code block containing a JSON array of
  that batch's objects — nothing else.
- Then stop and wait for me to say `next`. Continue from where you left off.
- After the final batch, output `DONE` and the total count you produced.
