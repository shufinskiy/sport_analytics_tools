# Prompt — FIFA Post Match Summary Report → `result.json`

You are given **one PDF**: a FIFA *Post Match Summary Report* (PMSR) from the 2026 World Cup
(standard 52-page template; any fixture). Your job is to extract every readable data point and
return **one file only: `result.json`**.

**Do NOT** produce a `research.md`, a narrative log, or any other file. The page-by-page
reasoning below is your *internal working method* — run it in your head, write only the JSON.

---

## 1. Working method (run internally for every page)

Process pages **in order**. For each page run this cycle and do not advance until the check passes:

1. **Examine** what is on the page (text, table, chart, pitch diagram, or a set of widgets).
2. **Plan** which data points to collect from it.
3. **Pick the structure** from the schema in §5 (the schema is fixed per page type — use it).
4. **Collect** the data into that structure.
5. **Verify** against the plan and the cross-checks in §4. If something is missing or fails a
   check, re-read the page and re-collect. Repeat until it passes, *then* move to the next page.

---

## 2. Global rules

- **Generic team naming.** This template is reused for all 104 tournament fixtures, so the
  structural layer (titles and keys) must stay identical across every match — never put a
  country/team name there. There are three distinct zones, each with its own rule:
   * **Page titles / names → use `Home` / `Away`.** Any visible page title or label refers to
     the teams as `Home` and `Away`, never by country (e.g. `"Defensive Actions - Home"`,
     `"Crosses (Open Play) - Away"`).
   * **Keys → use `home_team` / `away_team`.** Every JSON key that denotes a side uses the
     literal `home_team` / `away_team` (e.g. `"home_team": {...}`, `possession_pct.away_team`).
   * **Values → use the real team name.** In value positions, write the actual name. This
     includes the per-page side tag: set `data.team` to the real name (e.g.
     `"data": { "team": "Korea Republic", ... }`), not to `"home_team"`.
   * **Side assignment.** The cover page reads `X v Y` (and `X score Y`). The team named first /
     on the left is `Home` / `home_team`; the second is `Away` / `away_team`. Each single-team
     page shows a team name + flag in its header — use it to decide which side that page belongs
     to.
   * **Record the real names once** in `match` as `home_team_name` and `away_team_name`.
- **Skip pages.** Skip section-divider / title pages (full-bleed: a section name + `X v Y` +
  flags, no stats) and the closing FIFA logo page. In the standard template these are
  **5, 24, 30, 38, 41, 46, 49, 52**. Process the other 44 pages. (If a fixture's template shifts,
  identify dividers by content, not by number.)
- **Values.** Keep numbers as numbers; convert percentages to integers by stripping the `%` sign(e.g. `"77%"` → `77` as an integer in `*_pct` fields, and similarly for `pass_completion_pct` etc. per the field types in §5. For a paired
  cell like `16 (4)` or `547 (495)` store a nested object (e.g. `{ "total": 16, "on_target": 4 }`).
- **Un-digitisable visuals.** Point-cloud maps, arrow maps, minute-by-minute sparklines and shot
  marker coordinates have no reliably readable values — capture the **summary counts/totals only**
  and ignore the geometry. Do not invent coordinates.
- **Honesty / `_note`.** Where the source export is lossy (see §3) add a `"_note"` string to that
  page's `data` describing the limitation rather than fabricating values.

---

## 3. Known lossy areas — handle explicitly

- **Passing networks (pp. 12–13).** The player-to-player matrix comes from a text export that
  collapses blank/zero cells, so sparse rows under-count. Capture the **Top-5 passers table
  verbatim** (high confidence) and store the matrix as `passing_matrix_partial` with a `_note`.
  Sanity-check each "from" row total against that player's *passes completed* (distributions
  page); full-match players should reconcile, sparse rows may not.
- **Out of possession (pp. 47–48).** 14 columns with many blanks. Anchor and **verify the
  `possession_regains` column against the Defensive Actions page** (25 / 26) — it must match.
  Interior sparse columns are best-effort; add a `_note`.
- **Distributions Take-Ons vs Step-Ins (pp. 42, 44).** If the export collapses a blank between
  these two columns, infer the split from player position and add a `_note`.

---

## 4. Verification checks (must hold before finalising)

- Per-player **total distance** sums (physical pages) ≈ the *Total Distance Covered* values on the
  Key Statistics page, per team.
- **`possession_regains`** column (out-of-possession pages) == per-player regains on the
  Defensive Actions pages, per team.
- **Line-break direction** attempts (`through + around + over`) == `total_attempted`; each unit's
  line attempts sum to that unit's `attempted`.
- **Crosses attempted** (distributions pages) == team *Crosses* on the Key Statistics page.
- **Offers made** per-player sum == `total_offers_made`; and `offers_made_by_third` sum to it too.
- **Movement** `by_pitch_third` per type sums == `all_movement_types` per type.
- **Shot logs** row counts == the goals+on+off+blocked+incomplete totals on the shot-map page.
- **Free-kick / corner** sub-totals reconcile to the headline set-play totals.

---

## 5. Output: `result.json` shape

Top level:

```json
{
  "_meta": {
    "source_file": "<pdf filename>",
    "description": "Structured extraction of FIFA Post Match Summary Report",
    "skipped_pages": [5,24,30,38,41,46,49,52],
    "skipped_pages_reason": "Section divider / title pages and the closing FIFA logo page (no data).",
    "pages_processed": [1,2,3,4,6,7, ...]
  },
  "match": {
    "home_team_name": "<real name>", "away_team_name": "<real name>",
    "score": { "home": <int>, "away": <int> },
    "competition": "FIFA World Cup 2026",
    "stage": "<e.g. Group A>", "match_number": <int>,
    "date": "<YYYY-MM-DD>", "kickoff": "<HH:MM>", "venue": "<stadium>",
    "report_type": "Post Match Summary Report"
  },
  "pages": { "<page_number>": { "title": "<generic title>", "type": "<type>", "data": { ... } } }
}
```

`title` must use the `Home` / `Away` labels, e.g. `"Defensive Actions - Home"`, never a country name.

### Per-page `data` schemas

Pairs marked **(home / away)** share an identical schema; tag each with `data.team` set to the **real team name** (map it to the correct side via `match.home_team_name` / `away_team_name`).

- **Page 1 — cover / metadata** (`type:title_page`)
  `data` = a copy of the `match` object above.

- **Page 2 — lineups** (`type:lineups`)
  ```
  data: {
    formations: { home_team: "<e.g. 4-1-2-3>", away_team: "<...>" },
    score: { home, away },
    home_team: { starting: [player], substitutes: [player] },
    away_team: { starting: [player], substitutes: [player] }
  }
  player = {
    number, position, name,
    goals?: [minute, ...],            // LIST — normal goals (plain ball icon); a brace is two entries
    own_goals?: [minute, ...],        // LIST — own goal = red-white ball icon (NOT a plain ball); counts toward the OPPONENT's score, so list it under the scorer but credit the other team when reconciling the scoreline
    cards?: [{ type: "yellow"|"red", minute }, ...],  // LIST — supports a 2nd yellow or a red; NOT every card is yellow
    subbed_on?: minute,
    subbed_off?: minute
  }
  ```

- **Page 3 — key statistics** (`type:team_comparison_table`)
  ```
  data: {
    possession_pct: { home_team, contested, away_team },
    statistics: [ { stat, home_team, away_team } ]   // nested objects for paired cells
  }
  ```

- **Page 4 — phases of play** (`type:team_comparison_table`)
  ```
  data: {
    in_possession:     [ { phase, home_team_pct, away_team_pct } ],
    out_of_possession: [ { phase, home_team_pct, away_team_pct } ]
  }
  ```

- **Pages 6 & 7 — In Possession Line Height & Team Length (home / away)** (`type:pitch_diagram`)
  ```
  data: { team, build_up_low: M, build_up_mid: M, final_third_phase: M }
  M = { width_m, length_m, distance_to_goal_m }
  ```

- **Pages 8 & 9 — Line Breaks, team (home / away)** (`type:diagram_widgets`)
  ```
  data: {
    team,
    total_attempted,
    by_direction: { through:{attempted,completed}, around:{...}, over:{...} },
    by_units: {
      "4_units": U, "3_units": U, "2_units": U
    }
  }
  U = { attempted, inside_shape, outside_shape, lines: [ { line, attempted, completed } ] }
  ```
  **Line names & order — important.** Lines fill **bottom-to-top in the direction of play**: the
  line nearest the team's **own goal** is `defensive`, the line nearest the **opponent goal** is
  `attacking`. A naive top-to-bottom read of the page is REVERSED — assign the values accordingly.
  Allowed `line` values:
  - 4 units → `attacking`, `advanced midfield`, `midfield`, `defensive`
  - 3 units → `attacking`, `midfield`, `defensive`
  - 2 units → `midfield`, `defensive`

- **Pages 10 & 11 — Line Breaks, per player (home / away)** (`type:player_table`)
  ```
  data: { team, players: [ {
    num, name, attempted, completed, completion_pct,
    "4u_attacking","4u_attacking_mid","4u_midfield","4u_defensive",
    "3u_attacking","3u_midfield","3u_defensive",
    "2u_midfield","2u_defensive",
    dir_through, dir_around, dir_over,
    dist_type_pass, dist_type_cross, dist_type_ball_progression
  } ] }
  ```

- **Pages 12 & 13 — Passing Networks (home / away)** (`type:matrix_plus_table`)
  ```
  data: {
    team,
    top5_player_to_player_passers: [ { from, to, pct_of_team_passes } ],
    passing_matrix_partial: { "_note": "...partial reconstruction...", "<from>": { "<to>": passes } }
  }
  ```

- **Pages 14 & 16 — Attempts at Goal, summary (home / away)** (`type:shot_map_summary`)
  ```
  data: { team, outcomes:{ goals, on_target, off_target, blocked, incomplete }, total_shots }
  ```

- **Pages 15 & 17 — Attempts at Goal, shot log (home / away)** (`type:event_table`)
  ```
  data: { team, shots: [ { minute, number, player, outcome, body_part, delivery_type } ] }
  ```

- **Pages 18 & 19 — Crosses, open play (home / away)** (`type:diagram_plus_table`)
  ```
  data: {
    team, attempted, completed,
    most_attempted: { count, player, position },
    delivery_type_totals: { inswing, outswing, driven, lofted, cutback, push_cross, total },
    cross_zones: { left, center_left, center_right, right },
    players: [ { num, name, inswing, outswing, driven, lofted, cutback, push_cross, total_attempted } ]
  }
  ```

- **Pages 20 & 21 — Offering to Receive (home / away)** (`type:widgets_plus_table`)
  ```
  data: {
    team, total_offers_made, total_offers_received,
    most_offers: { count, player, position },
    offers_made_by_third: { final, middle, defensive },
    offers_made_shape: { inside_shape, outside_shape },
    players: [ { num, name, offers_made, offers_received, pct_made_received } ]
  }
  ```

- **Pages 22 & 23 — Movement to Receive (home / away)** (`type:widgets_plus_charts`)
  ```
  data: {
    team,
    all_movement_types: { total, in_front, in_between, out_to_in, in_to_out, in_behind },
    by_phase_totals: { final_third_phase, progression_phase, build_up_phase },
    by_pitch_third: { final_third: T, middle_third: T, defensive_third: T },
    top_ranked_players: { in_front:{player,movements}, in_between:{...}, out_to_in:{...}, in_to_out:{...}, in_behind:{...} }
  }
  T = { in_front, in_between, out_to_in, in_to_out, in_behind }
  ```
  (Phase-donut per-type segment order is ambiguous → store phase **totals** only.)

- **Pages 25 & 26 — Defensive Actions (home / away)** (`type:widgets_plus_table`)
  ```
  data: {
    team, forced_turnovers, possession_regained, interceptions, tackles,
    possession_actions_per_defensive_action,
    blocks: { total, passes, attempts_at_goal, crosses, clearances },
    possession_contests: { total, physical_duels, aerial_duels, duels },
    most_possession_regains: { count, player, position },
    players: [ { num, name, total_possession_regains } ]
  }
  ```

- **Pages 27 & 28 — Defensive Line Height & Team Length (home / away)** (`type:pitch_diagram`)
  ```
  data: { team, high_block_press: M, mid_block: M, low_block: M }
  M = { width_m, length_m, distance_to_goal_m }
  ```

- **Page 29 — Defensive Pressure** (`type:team_comparison_table`)
  ```
  data: {
    statistics: [ { stat, home_team, away_team } ],
    most_direct_pressures: { home_team:{count,player,position}, away_team:{...} }
  }
  ```

- **Page 31 — Goalkeeping Involvement** (`type:timeline_charts`)
  ```
  data: { home_team:{ total_involvements }, away_team:{ total_involvements } }
  ```

- **Pages 32 & 33 — Goalkeeping Distribution (home / away)** (`type:diagram_widgets`)
  ```
  data: {
    team, goalkeeper,
    kick_from_feet:    { total, play_onto, play_into, play_around, play_through, play_beyond, other },
    kick_from_hands:   { total, side_kick, from_hands, drop_kick },
    throw_distribution:{ total, over_arm, under_arm, side_arm, chest },
    total_distributions, goalkeeper_line_breaks
  }
  ```

- **Pages 34 & 35 — Goal Prevention (home / away)** (`type:diagram_widgets`)
  ```
  data: {
    team, goalkeeper, total_attempts_faced, save_pct,
    intervention_breakdown: { total_goal_interventions, save_and_retain, deflect_and_retain,
                              save_and_deflect, save_attempt, no_save_attempt },
    intervention_body_type: { head, hands, upper_body, lower_body, feet }
  }
  ```
  (Use the explicit summary table as authoritative; donut totals can be internally inconsistent.)

- **Pages 36 & 37 — Aerial Control (home / away)** (`type:diagram_widgets`)
  ```
  data: {
    team, goalkeeper, total_interventions,
    punches:{complete,incomplete}, claims:{complete,incomplete}, tipped_palmed:{complete,incomplete},
    crosses_faced_delivery_types: { total, in_swing, out_swing, driven, lofted, cutback, push }
  }
  ```

- **Pages 39 & 40 — Set Plays (home / away)** (`type:widgets_plus_tables`)
  ```
  data: {
    team,
    totals: { set_plays, free_kicks, penalties, corners, throw_ins },
    free_kicks: { direct, direct_on_target, direct_off_target, indirect },
    corners_by_delivery_type: { direct_to_area:S, short:S, edge_of_penalty_area:S },
    corners_by_delivery_style: { inswing, outswing, driven, lofted }
  }
  S = { from_left, from_right, total }
  ```

- **Pages 42 & 44 — In Possession · Distributions, per player (home / away)** (`type:player_table`)
  ```
  data: { team, "_note"?: "...", players: [ {
    num, name, passes_attempted, passes_completed, pass_completion_pct,
    switches_of_play, crosses_attempted, crosses_completed,
    line_breaks_attempted, line_breaks_completed, line_break_completion_pct,
    ball_progressions, take_ons, step_ins, attempts_at_goal, goals
  } ] }
  ```

- **Pages 43 & 45 — In Possession · Offers & Receptions, per player (home / away)** (`type:player_table`)
  ```
  data: { team, players: [ {
    num, name, total_offers, in_front, in_between, out_to_in, in_to_out, in_behind,
    no_movement, offers_received
  } ] }
  ```

- **Pages 47 & 48 — Out of Possession, per player (home / away)** (`type:player_table`)
  ```
  data: { team, "_note": "regains column validated against Defensive Actions page", players: [ {
    num, name, tackles_made, tackles_won, blocks, interceptions,
    pressing_direct, pressing_indirect, duels_won_aerial, duels_won_physical,
    possession_contests_won, clearances, loose_ball_receptions,
    pushing_on, pushing_on_into_pressing, possession_regains, possession_interrupted
  } ] }
  ```

- **Pages 50 & 51 — Physical Data, per player (home / away)** (`type:player_table`)
  ```
  data: { team, players: [ {
    num, name, total_distance_m, zone1_0_7_m, zone2_7_15_m, zone3_15_20_m,
    zone4_20_25_m, zone5_25plus_m, high_speed_runs_zone3, sprints_zone4_5, top_speed_kmh
  } ] }
  ```

---

## 6. Deliverable

Emit valid UTF-8 JSON matching §5 and passing §4 — **`result.json` only.** No prose, no log file.
