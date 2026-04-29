# Sumo Logic Virtual Training Schedule

Scripts in this folder fetch the Sumo Logic instructor-led virtual class schedule from [sumologic.com/learn/training](https://www.sumologic.com/learn/training) and produce two output files:

| Output                   | Description                               |
|--------------------------|-------------------------------------------|
| `training_schedule.html` | Filterable web page — open in any browser |
| `training_schedule.pptx` | Slide deck for use in presentations       |

---

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Install the Chromium browser used for page rendering (once per machine)
uv run playwright install chromium
```

---

## Running

```bash
uv run python fetch_training_schedule.py
```

The script fetches the live page (all pagination pages), parses the schedule, and overwrites both output files. A `debug_raw.html` snapshot of the first fetched page is also saved for troubleshooting.

---

## How it works

The training page is JavaScript-rendered and uses **FacetWP** pagination. The script:

1. Launches a headless Chromium browser via Playwright
2. Detects the total page count from the `.facetwp-pager` element
3. Clicks through every numbered page, waiting for the session grid to reload after each click
4. Parses all `<a class="blog-item-link">` cards — each contains an `<h3>` course title and a `<time data-start="..." data-end="...">` element with ISO 8601 timestamps
5. Converts timestamps into four timezones (see below)
6. Scrapes course descriptions from the Certifications overview section on the same page

---

## Timezones

All session times are converted from the page's UTC offsets into:

| Column | Timezone             |
|--------|----------------------|
| PT     | America/Los_Angeles  |
| NZ     | Pacific/Auckland     |
| AET    | Australia/Sydney     |
| SGT    | Asia/Singapore       |

---

## HTML page features

- **Future sessions shown by default** — past sessions are hidden on load; tick *Show past sessions* to reveal them
- **Search** by course name (live filter as you type)
- **Month filter** dropdown — populated from the sessions present in the data
- **Sortable columns** — click any column header to sort ascending/descending
- **Expandable course descriptions** — click the ▶ arrow next to a course title to expand the certification overview description matched from the Certifications overview section
- **"Copy for email" button** — copies the currently visible (filtered) rows to the clipboard as both a rich HTML table and plain text:
  - Pasting into Gmail or Outlook renders a formatted table with live Register links
  - Pasting into plain text gives a fixed-width columnar layout with register URLs

---

## PowerPoint features

- 16:9 widescreen format, Sumo Logic dark colour scheme
- Contains only **upcoming** sessions (past sessions excluded), sorted by date
- Splits automatically at 10 rows per slide
- Each slide heading includes the **date range** of sessions shown on that slide, e.g. `· 05 May – 12 May 2026 (1/5)`
- Columns: Course | PT (Los Angeles) | NZ (Auckland) | AET (Sydney) | SGT (Singapore) | Register URL
- PT column shows start → end time; register URLs are live hyperlinks

---

## Dependencies

Managed via `pyproject.toml` / `uv.lock`:

| Package          | Purpose                                                                    |
|------------------|----------------------------------------------------------------------------|
| `playwright`     | Headless browser to render JavaScript content and click through pagination |
| `beautifulsoup4` | HTML parsing                                                               |
| `python-pptx`    | PowerPoint generation                                                      |
