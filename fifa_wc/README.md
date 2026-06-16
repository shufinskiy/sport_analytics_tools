# fifa_wc — FIFA World Cup 2026 Post Match Summary Report Extractor

Turn FIFA's 2026 World Cup [**Post Match Summary Reports**](https://www.fifatrainingcentre.com/en/fifa-world-cup-2026/match-report-hub.php) (PMSR) from locked-up PDFs into clean,
structured, analysis-ready **JSON**.

After every match, FIFA publishes a 52-page PMSR — one of the richest public match datasets in
football: shot maps, passing networks, line breaks, pressing and defensive actions, possession
phases, set plays, goalkeeping, and per-player physical/running data. The catch is that all of it
lives inside charts, pitch diagrams and tables in a PDF, so analysts either ignore it or copy the
numbers out by hand — slow, tedious and error-prone. `fifa_wc` removes that wall and gives you the
whole report as a single JSON file you can drop straight into your own models, dashboards or
notebooks.

---

## Two ways to collect the data

The project ships **two interchangeable extraction backends** that produce the **same**
`result.json` schema. Pick whichever fits your stack.

### 1. Prompt-based extraction (`parse_fifa_report_prompt.md`)

A self-contained extraction prompt instructs a Claude model to read the report page by page and
return the structured JSON directly. No parsing code to maintain — the model handles layout
understanding (tables, charts, pitch widgets) and structuring.

- Attach `parse_fifa_report_prompt.md` and the PMSR PDF to a Claude conversation; the model returns `result.json` and nothing else.
- Best when you want zero parsing maintenance, or when FIFA tweaks the report layout (the model adapts where a hard-coded parser would break).
- **Tested on:** `claude-opus-4-8` (high thinking) and `claude-sonnet-4-6` (low thinking).

### 2. Programmatic parser (`parse_fifa_report.py`)

A Python script that walks the PDF page by page using `PyMuPDF` and extracts the same fields without any LLM calls.

- Best when you want deterministic, repeatable, zero-cost runs and full control over the output.
- Runs entirely locally.

**Usage:**
```bash
python fifa_wc/parse_fifa_report.py <path/to/report.pdf> [output.json]
```

**Requirements:** `PyMuPDF` (`pip install pymupdf`)

---

## Output: `result.json`

A single JSON file. Top-level shape:

```json
{
  "_meta": {
    "source_file": "PMSR.pdf",
    "description": "Structured extraction of FIFA Post Match Summary Report",
    "skipped_pages": [5, 24, 30, 38, 41, 46, 49, 52],
    "skipped_pages_reason": "Section divider / title pages and the closing FIFA logo page (no data).",
    "pages_processed": [1, 2, 3, 4, 6, 7, "..."]
  },
  "match": {
    "home_team_name": "Brazil", "away_team_name": "Morocco",
    "score": { "home": 1, "away": 1 },
    "competition": "FIFA World Cup 2026",
    "stage": "Group C", "match_number": 7,
    "date": "2026-06-13", "kickoff": "19:00", "venue": "...",
    "report_type": "Post Match Summary Report"
  },
  "pages": {
    "<page_number>": { "title": "...", "type": "...", "data": { } }
  }
}
```

Each processed page becomes one entry under `pages`, carrying a generic `title`, a `type`, and a
`data` payload shaped to that page type. JSON keys identifying a side always use `home_team` /
`away_team`; value fields (e.g. `data.team`) use the real team name.

See `example/bra_mor.json` for a complete sample output from the Brazil vs Morocco fixture.

---

## What gets extracted (page coverage)

44 data pages are extracted; 8 are skipped. The skipped pages
(**5, 24, 30, 38, 41, 46, 49, 52**) are full-bleed section dividers and the closing FIFA logo page
— they carry no statistics.

| Section | Pages | Content extracted |
|---|---|---|
| Match Summary | 1–4 | Cover/metadata, lineups (formations, goals, cards, subs), key statistics, phases of play |
| In Possession | 6–23 | Line height & team length, line breaks (team + per player), passing networks, attempts at goal (map + shot log), crosses, offering to receive, movement to receive |
| Out of Possession | 25–29 | Defensive actions, defensive line height & team length, defensive pressure |
| Goalkeeping | 31–37 | GK involvement, GK distribution, goal prevention, aerial control |
| Set Plays | 39–40 | Free kicks, corners (type/style), throw-ins, penalties |
| Individual — In Possession | 42–45 | Per-player distributions; offers & receptions |
| Individual — Out of Possession | 47–48 | Per-player tackles, blocks, interceptions, pressing, duels, regains, etc. |
| Individual — Physical | 50–51 | Per-player distance by speed zone, high-speed runs, sprints, top speed |

---

## Known limitations

Some widgets are inherently lossy in a text export; these are handled explicitly and flagged in the
JSON with a `"_note"`:

- **Passing networks** — the player-to-player matrix collapses blank cells, so sparse rows
  under-count. The Top-5 passers table is captured verbatim; the full matrix is stored as
  `passing_matrix_partial`.
- **Out-of-possession tables** — a few sparse interior columns are best-effort.
- Point-cloud maps, arrow maps, and minute-by-minute sparklines have no readable coordinates — only
  their summary counts/totals are captured.
- The programmatic parser's x-coordinate column maps are calibrated to the FIFA 2026 PMSR layout;
  a different template version may require recalibration.

---

## Repository layout

```
fifa_wc/
├── README.md                    # this file
├── parse_fifa_report_prompt.md  # backend 1: Claude prompt → result.json
├── parse_fifa_report.py         # backend 2: deterministic PDF parser
└── example/
    └── bra_mor.json             # sample output (Brazil vs Morocco)
```
