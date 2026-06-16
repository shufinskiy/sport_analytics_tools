#!/usr/bin/env python3
"""
FIFA Post Match Summary Report (PMSR) PDF → result.json
Purely programmatic extraction using PyMuPDF — no LLM calls.

Usage:
    python parse_pmsr.py <path/to/report.pdf> [output.json]
"""

import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
import math


# ─── Constants ────────────────────────────────────────────────────────────────

SKIP_PAGES_1IDX = {5, 24, 30, 38, 41, 46, 49, 52}
PROCESSED_PAGES = sorted(set(range(1, 53)) - SKIP_PAGES_1IDX)

# Minute-marker colors on lineup page (fitz encodes color as packed RGB int)
COLOR_SUB_OFF = 14427686   # red/crimson  → player coming off
COLOR_SUB_ON  = 366185     # green        → player coming on
COLOR_EVENT   = 3034623    # teal/orange  → goal OR yellow card


# ─── Low-level helpers ────────────────────────────────────────────────────────

def page_words(page, x_min=0, x_max=9999, y_min=0, y_max=9999):
    """Return [(x0, y0, text), ...] filtered by region, sorted by y then x."""
    out = []
    for w in page.get_text("words"):
        x, y = w[0], w[1]
        if x_min <= x <= x_max and y_min <= y <= y_max:
            out.append((x, y, w[4]))
    return sorted(out, key=lambda t: (t[1], t[0]))


def group_rows(words, y_tol=5):
    """Cluster [(x,y,text),...] into rows; each row is [(x,y,text),...] sorted by x."""
    rows: list[list] = []
    for word in sorted(words, key=lambda t: (t[1], t[0])):
        placed = False
        for row in reversed(rows):
            if abs(word[1] - row[0][1]) <= y_tol:
                row.append(word)
                placed = True
                break
        if not placed:
            rows.append([word])
    return rows


def row_texts(row):
    """Extract just the text tokens from a word-row, in x-order."""
    return [w[2] for w in sorted(row, key=lambda t: t[0])]


def to_num(text):
    """Parse int or float from text, stripping %, km, s suffixes."""
    t = re.sub(r'[%a-zA-Z]', '', text.strip())
    try:
        return int(t)
    except ValueError:
        try:
            return float(t)
        except ValueError:
            return None


def pct_int(text):
    """Return percentage as integer (strip %)."""
    return int(re.sub(r'[^0-9]', '', text))


def closest(x, col_map, tol=35):
    """Return column-name whose x-center is nearest to x, within tolerance."""
    best, best_d = None, tol + 1
    for name, cx in col_map.items():
        d = abs(x - cx)
        if d < best_d:
            best, best_d = name, d
    return best


def parse_pair(tokens):
    """Parse '12 (5)' → {'total': 12, 'on_target': 5}, or plain number."""
    joined = " ".join(tokens)
    m = re.match(r'^(\d+\.?\d*)\s*\((\d+\.?\d*)\)$', joined.strip())
    if m:
        a, b = to_num(m.group(1)), to_num(m.group(2))
        return a, b
    return to_num(joined.strip()), None


# ─── Page 1: Cover ────────────────────────────────────────────────────────────

def parse_page1(page):
    text = page.get_text("text")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # "Brazil 1 - 1 Morocco"
    m = re.match(r'^(.+?)\s+(\d+)\s*-\s*(\d+)\s+(.+)$', lines[0])
    home_team = m.group(1).strip()
    home_score = int(m.group(2))
    away_score = int(m.group(3))
    away_team = m.group(4).strip()
    # "Group C - Match 7"
    m2 = re.match(r'^(.+?)\s*-\s*Match\s+(\d+)$', lines[1])
    stage = m2.group(1).strip()
    match_num = int(m2.group(2))
    # "13 June 2026"
    date = datetime.strptime(lines[2], "%d %B %Y").strftime("%Y-%m-%d")
    kickoff = lines[3].split()[0]
    venue = lines[4]
    return {
        "home_team_name": home_team,
        "away_team_name": away_team,
        "score": {"home": home_score, "away": away_score},
        "competition": "FIFA World Cup 2026",
        "stage": stage,
        "match_number": match_num,
        "date": date,
        "kickoff": kickoff,
        "venue": venue,
        "report_type": "Post Match Summary Report",
    }


# ─── Shot-log helper (pages 15 & 17) ─────────────────────────────────────────
# Parsed early to help identify goal minutes on the lineup page.

def _parse_shot_log(page):
    """
    Return list of {minute, jersey_num, player, outcome, body_part, delivery_type}.
    Column x-positions: minute~61, jersey~126, player~138-410, outcome~430-660,
    body_part~660-805, delivery_type~805+
    """
    words = page_words(page, y_min=80)
    rows = group_rows(words, y_tol=5)
    shots = []
    for row in rows:
        # Require a minute token at x < 100
        minute_words = [w for w in row if w[0] < 100]
        if not minute_words:
            continue
        try:
            minute = int(minute_words[0][2])
        except ValueError:
            continue
        # Skip header and footer rows (footer has only jersey numbers)
        player_words = [w[2] for w in row if 130 <= w[0] < 430 and
                        re.match(r'^[A-Za-z]', w[2])]
        if not player_words:
            continue
        jersey_words = [w[2] for w in row if 100 <= w[0] < 135 and
                        re.match(r'^\d+$', w[2])]
        jersey_num = int(jersey_words[0]) if jersey_words else None
        player = " ".join(player_words)
        outcome_words = [w[2] for w in row if 430 <= w[0] < 660]
        body_words = [w[2] for w in row if 660 <= w[0] < 805]
        delivery_words = [w[2] for w in row if w[0] >= 805]
        shots.append({
            "minute": minute,
            "number": jersey_num,
            "player": player,
            "outcome": " ".join(outcome_words),
            "body_part": " ".join(body_words),
            "delivery_type": " ".join(delivery_words),
        })
    return shots


# ─── Page 2: Lineups ──────────────────────────────────────────────────────────

def _lineup_minutes_with_color(page):
    """Return {(x,y): (text, color)} for minute markers on the lineup page."""
    out = {}
    # Use "dict" mode — spans have a "text" key (rawdict only has per-char data)
    raw = page.get_text("dict")
    for block in raw["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                t = span.get("text", "").strip()
                if re.match(r"^\d{1,3}(?:\+\d+)?'$", t):
                    color = span.get("color", 0)
                    bbox = span.get("bbox", [])
                    if len(bbox) >= 2:
                        x = bbox[0]
                        y = bbox[1]
                    else:
                        x = span["origin"][0]
                        y = span["origin"][1]
                    out[(round(x), round(y))] = (t, color)
    return out


def _parse_team_lineups(page, home_team, away_team, goal_minutes_by_player):
    """
    Return (home_players, away_players, home_formation, away_formation).
    Each player list: starting + substitutes with goals/cards/sub times.
    """
    minute_colors = _lineup_minutes_with_color(page)

    # --- Brazil side (x < 500) ---
    bra_words = page_words(page, x_max=300, y_min=100)
    bra_rows = group_rows(bra_words, y_tol=4)

    # --- Morocco side (x > 700) ---
    # Start at x=700 to exclude the formation label (x~627) which sits at
    # the same y as a player row and would corrupt the name parse.
    mar_words = page_words(page, x_min=700, y_min=100)
    mar_rows = group_rows(mar_words, y_tol=4)

    # Formation text lives in middle band x~300-700
    mid_words = page_words(page, x_min=300, x_max=700, y_min=100)
    formations = {"home_team": "Unknown", "away_team": "Unknown"}
    for x, y, text in mid_words:
        if re.match(r'^\d+-\d+', text):
            # Two formations appear: home left, away right of center
            if x < 500:
                formations["home_team"] = text
            else:
                formations["away_team"] = text

    def build_players(rows, is_home):
        """Parse player rows for one team side."""
        section = None   # "starting" or "substitutes"
        players = {"starting": [], "substitutes": []}
        for row in rows:
            texts = row_texts(row)
            joined = " ".join(texts)
            if "STARTING" in joined:
                section = "starting"
                continue
            if "SUBSTITUTES" in joined:
                section = "substitutes"
                continue
            if section is None:
                continue
            # Skip section headers and legend rows
            if any(t in joined for t in ("FORMATION", "Distribution")):
                continue

            # Identify minute-marker tokens vs. name/pos/num tokens
            minute_tokens = []
            other_tokens = []
            for w in sorted(row, key=lambda t: t[0]):
                xy = (round(w[0]), round(w[1]))
                if xy in minute_colors:
                    minute_tokens.append((w[0], w[2], minute_colors[xy][1]))
                elif re.match(r"^\d{1,3}(?:\+\d+)?'$", w[2]):
                    # minute not in color dict (e.g. "90+5'") — fall back
                    minute_tokens.append((w[0], w[2], None))
                else:
                    other_tokens.append((w[0], w[2]))

            # Parse number, position, name from other_tokens
            num, pos, name = _parse_player_identity(other_tokens, is_home)
            if num is None:
                continue  # pitch diagram number row or other non-player row

            # Classify minute markers by color
            goals, cards, subbed_on, subbed_off = [], [], None, None
            player_goal_mins = goal_minutes_by_player.get(name, [])

            pending_sub_off = []
            for mx, mtext, mcolor in sorted(minute_tokens, key=lambda t: t[0]):
                # For stoppage-time markers like "90+5'", use just the base minute
                m_base = re.match(r'^(\d+)', mtext)
                minute_val = int(m_base.group(1)) if m_base else 0
                if mcolor == COLOR_SUB_ON:
                    subbed_on = minute_val
                elif mcolor == COLOR_SUB_OFF:
                    pending_sub_off.append(minute_val)
                elif mcolor == COLOR_EVENT or mcolor is None:
                    # goal or card
                    is_goal = any(abs(minute_val - gm) <= 2 for gm in player_goal_mins)
                    if is_goal:
                        goals.append(minute_val)
                    else:
                        cards.append({"type": "yellow", "minute": minute_val})

            # Resolve pending sub-offs: if player was subbed_on and a COLOR_SUB_OFF
            # marker is within ≤2 minutes of sub-on, it's an own goal, not a sub-off.
            for m in pending_sub_off:
                if subbed_on is not None and abs(m - subbed_on) <= 2:
                    goals.append(m)
                else:
                    subbed_off = m

            player = {"number": num, "position": pos, "name": name}
            if goals:
                player["goals"] = goals
            if cards:
                player["cards"] = cards
            if subbed_on is not None:
                player["subbed_on"] = subbed_on
            if subbed_off is not None:
                player["subbed_off"] = subbed_off

            players[section].append(player)

        return players

    home_players = build_players(bra_rows, is_home=True)
    away_players = build_players(mar_rows, is_home=False)
    return home_players, away_players, formations


def _parse_player_identity(other_tokens, is_home):
    """
    Extract (number, position, name) from the non-minute tokens of a player row.
    Brazil format: num pos name...
    Morocco format: name... pos num  (reversed)
    """
    POSITIONS = {"GK", "DF", "MF", "FW"}
    texts = [t for _, t in sorted(other_tokens, key=lambda t: t[0])]
    if not texts:
        return None, None, None

    # Check if the row contains a position keyword
    pos_indices = [i for i, t in enumerate(texts) if t.upper() in POSITIONS or
                   re.match(r'^[A-Z]{2}\d+$', t)]
    if not pos_indices:
        # Might be a number-only row (pitch diagram) — skip
        return None, None, None

    if is_home:
        # Format: num pos name...
        try:
            num = int(texts[0])
        except ValueError:
            return None, None, None
        pos = texts[1].upper() if len(texts) > 1 else ""
        # handle "FW10" attached
        if re.match(r'^[A-Z]{2}\d+$', pos):
            num = int(re.sub(r'[^0-9]', '', pos)) if num == int(texts[0]) else num
            pos = pos[:2]
        name_tokens = [t for t in texts[2:] if not re.match(r'^\d+$', t)]
        name = " ".join(name_tokens) if name_tokens else ""
    else:
        # Format: name... pos num  (Morocco — right to left)
        # Last token is jersey number (int) or combined "FW10"
        m_combined = re.match(r'^([A-Z]{2})(\d+)$', texts[-1])
        if m_combined:
            # e.g. "FW10" — pos and num combined
            pos = m_combined.group(1)
            num = int(m_combined.group(2))
            name = " ".join(texts[:-1])  # everything before the combined token
            return num, pos, name

        try:
            num = int(texts[-1])
        except ValueError:
            return None, None, None

        # Second-to-last token is position
        pos_tok = texts[-2].upper() if len(texts) >= 2 else ""
        if re.match(r'^[A-Z]{2}$', pos_tok):
            pos = pos_tok
            name = " ".join(texts[:-2])
        else:
            pos = ""
            name = " ".join(texts[:-1])

    return num, pos, name


def parse_page2(doc, home_team, away_team, home_shot_log, away_shot_log, score):
    """Parse lineups page."""
    page = doc[1]

    # Build goal-minute lookup from shot logs
    def build_goal_map(shot_log):
        gmap = {}
        for s in shot_log:
            if "Goal" in s.get("outcome", ""):
                p = s["player"]
                gmap.setdefault(p, []).append(s["minute"])
        return gmap

    home_goals = build_goal_map(home_shot_log)
    away_goals = build_goal_map(away_shot_log)
    all_goals = {**home_goals, **away_goals}

    home_players, away_players, formations = _parse_team_lineups(
        page, home_team, away_team, all_goals
    )

    return {
        "formations": formations,
        "score": score,
        "home_team": home_players,
        "away_team": away_players,
    }


# ─── Page 3: Key Statistics ───────────────────────────────────────────────────

def parse_page3(page):
    words = page_words(page, y_min=100)
    rows = group_rows(words, y_tol=4)

    data = {"possession_pct": {}, "statistics": []}

    for row in rows:
        wxs = sorted(row, key=lambda t: t[0])
        texts = [w[2] for w in wxs]
        xs = [w[0] for w in wxs]
        if not texts:
            continue

        # Possession row: three % values
        if any("%" in t and t != "%" for t in texts):
            pcts = [t for t in texts if "%" in t]
            if len(pcts) == 3:
                data["possession_pct"] = {
                    "home_team": float(pcts[0].replace("%", "")),
                    "contested": float(pcts[1].replace("%", "")),
                    "away_team": float(pcts[2].replace("%", "")),
                }
                continue

        # Skip header/label rows
        if texts[0].upper() in ("POSSESSION", "TOTAL", "MATCH", "BRAZIL", "MOROCCO"):
            continue

        # Statistics rows: left values (x<300), center stat name (x 300-800), right values (x>800)
        left_vals = [w for w in wxs if w[0] < 300]
        center_words = [w for w in wxs if 300 <= w[0] <= 800]
        right_vals = [w for w in wxs if w[0] > 800]

        if not center_words:
            continue

        stat_name = " ".join(w[2] for w in sorted(center_words, key=lambda t: t[0]))
        # Skip non-stat rows
        if not left_vals or not right_vals:
            continue

        def parse_side(vals):
            toks = [v[2] for v in sorted(vals, key=lambda t: t[0])]
            joined = " ".join(toks)
            m = re.match(r'^(\d+\.?\d*)\s*\((\d+\.?\d*)\)$', joined.strip())
            if m:
                a, b = to_num(m.group(1)), to_num(m.group(2))
                # Determine inner key from stat name
                if "On Target" in stat_name:
                    return {"total": a, "on_target": b}
                elif "Complete" in stat_name and "Pass" in stat_name:
                    return {"total": a, "complete": b}
                elif "Direct" in stat_name and "Pressure" in stat_name:
                    return {"total": a, "direct": b}
                return {"total": a, "value2": b}
            t = joined.strip()
            # strip km suffix
            t = re.sub(r'\s*km$', '', t)
            # "Pass Completion %" → integer
            if "%" in t:
                return pct_int(t)
            return to_num(t)

        home_val = parse_side(left_vals)
        away_val = parse_side(right_vals)

        # Normalise stat name
        stat_name = re.sub(r'\s+', ' ', stat_name).strip()
        # Replace em dash with hyphen, remove trailing colons from tokens
        stat_name = stat_name.replace('–', '-').replace(':', '')
        stat_name = re.sub(r'\s+', ' ', stat_name).strip()
        # Add km to distance stats
        if "Distance" in stat_name and "km" not in stat_name:
            stat_name += " (km)"
        if "Zone 4" in stat_name and not stat_name.endswith("(km)"):
            stat_name += " (km)"
        # Remove spurious (km) suffix if stat name already ends with km/h
        if stat_name.endswith("km/h (km)") and "Zone 4" not in stat_name:
            stat_name = stat_name[:-5].rstrip()

        data["statistics"].append({
            "stat": stat_name,
            "home_team": home_val,
            "away_team": away_val,
        })

    return data


# ─── Page 4: Phases of Play ───────────────────────────────────────────────────

def parse_page4(page):
    text = page.get_text("text")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    in_poss, out_poss = [], []
    section = None
    i = 0
    while i < len(lines):
        l = lines[i]
        if l == "IN POSSESSION":
            section = "in"
            i += 1
            continue
        if l == "OUT OF POSSESSION":
            section = "out"
            i += 1
            continue
        if section and re.match(r'^\d+%$', l):
            home_pct = pct_int(l)
            i += 1
            phase_name = lines[i]; i += 1
            away_pct = pct_int(lines[i]); i += 1
            entry = {"phase": phase_name, "home_team_pct": home_pct,
                     "away_team_pct": away_pct}
            if section == "in":
                in_poss.append(entry)
            else:
                out_poss.append(entry)
        else:
            i += 1
    return {"in_possession": in_poss, "out_of_possession": out_poss}


# ─── Pages 6/7: In Possession Line Height ─────────────────────────────────────

def _parse_pitch_diagram_3blocks(page, sections):
    """
    Parse 3 pitch diagrams each showing 3 measurements (width, length, dist_to_goal).
    sections: list of section labels in order (e.g. ["build_up_low","build_up_mid","final_third_phase"])
    Returns dict with section keys → {width_m, length_m, distance_to_goal_m}
    """
    text = page.get_text("text")
    # Find all integers following "DIRECTION"
    # Each "DIRECTION" block has 3 measurements
    blocks = re.findall(r'DIRECTION\s+([\d.]+)m\s+([\d.]+)m\s+([\d.]+)m', text)
    result = {}
    for i, sec in enumerate(sections):
        if i < len(blocks):
            w, l, d = blocks[i]
            result[sec] = {
                "width_m": to_num(w),
                "length_m": to_num(l),
                "distance_to_goal_m": to_num(d),
            }
    return result


def parse_pages_6_7(doc, home_team, away_team):
    secs = ["build_up_low", "build_up_mid", "final_third_phase"]
    p6 = _parse_pitch_diagram_3blocks(doc[5], secs)
    p7 = _parse_pitch_diagram_3blocks(doc[6], secs)
    p6["team"] = home_team
    p7["team"] = away_team
    return p6, p7


# ─── Pages 8/9: Line Breaks (team) ───────────────────────────────────────────

def _parse_linebreaks_team(page, team):
    """
    Parse line breaks team summary page using text extraction.

    Text structure (from actual PDF):
    - Total attempted line breaks: first large integer in text
    - By direction: three number pairs (att, comp) × (through, around, over)
    - By units header: "N Units / Attempted Line Breaks / N / Inside Shape / N / Outside Shape / N"
    - Per-unit lines (in the right side chart section):
      "Attempted / Complete / v1 / v2 / ... / DIRECTION OF PLAY / LABEL1 / LABEL2 / ..."
      Numbers appear first (N_lines × 2 values), then line labels follow.
    """
    text = page.get_text("text")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # ── Total attempted ──
    total = None
    for l in lines:
        if re.match(r'^\d+$', l) and int(l) > 50:
            total = int(l)
            break

    # ── By direction: three Attempted/Complete pairs ──
    # Text structure: total, then pairs interleaved as att, comp (for through, around, over)
    direction_nums = []
    found_total = False
    for l in lines:
        if l == str(total) and not found_total:
            found_total = True
            continue
        if found_total:
            if re.match(r'^\d+$', l):
                direction_nums.append(int(l))
                if len(direction_nums) == 6:
                    break
            elif l in ("Attempted", "Complete", "Attempted Line Breaks"):
                continue
            elif re.match(r'^[0-9A-Z]', l):
                pass  # allow other text between numbers

    by_direction = {
        "through": {"attempted": direction_nums[0] if len(direction_nums) > 0 else 0,
                    "completed": direction_nums[1] if len(direction_nums) > 1 else 0},
        "around":  {"attempted": direction_nums[2] if len(direction_nums) > 2 else 0,
                    "completed": direction_nums[3] if len(direction_nums) > 3 else 0},
        "over":    {"attempted": direction_nums[4] if len(direction_nums) > 4 else 0,
                    "completed": direction_nums[5] if len(direction_nums) > 5 else 0},
    }

    # ── Units ──
    # Labels appear in the text chart blocks as DEFENSIVE → MIDFIELD → ... → ATTACKING
    # (top of pitch diagram = defensive end, bottom = attacking end)
    LINE_LABELS_MAP = {
        4: ["defensive", "midfield", "advanced midfield", "attacking"],
        3: ["defensive", "midfield", "attacking"],
        2: ["defensive", "midfield"],
    }

    # Chart blocks appear in the text AFTER all unit headers, in order: 4, 3, 2
    # Each block: "Attempted\nComplete\n<N×2 numbers>\nDIRECTION OF PLAY\n..."
    chart_blocks = re.findall(
        r'Attempted\s+Complete\s+((?:\d+\s*)+?)DIRECTION', text, re.S
    )

    units_data = {}
    for idx, n_units in enumerate([4, 3, 2]):
        key = f"{n_units}_units"
        # Extract header totals
        m = re.search(
            rf'{n_units}\s+Units\s+Attempted Line Breaks\s+(\d+)\s+Inside Shape\s+(\d+)\s+Outside Shape\s+(\d+)',
            text, re.S
        )
        if m:
            att, ins, outs = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            att, ins, outs = 0, 0, 0

        expected_labels = LINE_LABELS_MAP[n_units]
        lines_list = []
        if idx < len(chart_blocks):
            nums = [int(x) for x in re.findall(r'\d+', chart_blocks[idx])]
            # nums: [att_line0, comp_line0, att_line1, comp_line1, ...]
            for i, lname in enumerate(expected_labels):
                a = nums[i * 2] if i * 2 < len(nums) else 0
                c = nums[i * 2 + 1] if i * 2 + 1 < len(nums) else 0
                lines_list.append({"line": lname, "attempted": a, "completed": c})
        else:
            for lname in expected_labels:
                lines_list.append({"line": lname, "attempted": 0, "completed": 0})
        lines_list.reverse()

        units_data[key] = {
            "attempted": att,
            "inside_shape": ins,
            "outside_shape": outs,
            "lines": lines_list,
        }

    return {
        "team": team,
        "total_attempted": total or 0,
        "by_direction": by_direction,
        "by_units": units_data,
    }


def parse_pages_8_9(doc, home_team, away_team):
    p8 = _parse_linebreaks_team(doc[7], home_team)
    p9 = _parse_linebreaks_team(doc[8], away_team)
    return p8, p9


# ─── Pages 10/11: Line Breaks per player ──────────────────────────────────────

_LB_COLS = [
    "num", "name", "attempted", "completed", "completion_pct",
    "4u_attacking", "4u_attacking_mid", "4u_midfield", "4u_defensive",
    "3u_attacking", "3u_midfield", "3u_defensive",
    "2u_midfield", "2u_defensive",
    "dir_through", "dir_around", "dir_over",
    "dist_type_pass", "dist_type_cross", "dist_type_ball_progression",
]

# x-centers for line breaks player table columns
_LB_X = {
    "attempted": 197, "completed": 241, "completion_pct": 279,
    "4u_attacking": 330, "4u_attacking_mid": 372, "4u_midfield": 415,
    "4u_defensive": 456, "3u_attacking": 498, "3u_midfield": 540,
    "3u_defensive": 583, "2u_midfield": 625, "2u_defensive": 666,
    "dir_through": 709, "dir_around": 750, "dir_over": 792,
    "dist_type_pass": 834, "dist_type_cross": 876,
    "dist_type_ball_progression": 921,
}


def _parse_lb_player_table(page, team):
    words = page_words(page, y_min=130)
    rows = group_rows(words, y_tol=5)
    players = []
    for row in rows:
        if not row:
            continue
        # Jersey number is the leftmost token with x<40
        num_words = [w for w in row if w[0] < 40]
        name_words = [w for w in row if 40 <= w[0] < 170]
        if not num_words:
            continue
        try:
            num = int(num_words[0][2])
        except ValueError:
            continue
        name = " ".join(w[2] for w in sorted(name_words, key=lambda t: t[0]))
        if not name:
            continue

        # Map remaining values to columns by x-position
        data_words = [w for w in row if w[0] >= 170]
        player = {"num": num, "name": name}
        for x, y, text in data_words:
            col = closest(x, _LB_X, tol=25)
            if col:
                player[col] = pct_int(text) if "%" in text else to_num(text) or 0

        # Fill missing columns with 0
        for col in _LB_COLS[2:]:
            if col not in player:
                player[col] = 0
        players.append(player)
    return {"team": team, "players": players}


def parse_pages_10_11(doc, home_team, away_team):
    p10 = _parse_lb_player_table(doc[9], home_team)
    p11 = _parse_lb_player_table(doc[10], away_team)
    return p10, p11


# ─── Pages 12/13: Passing Networks ───────────────────────────────────────────

def _parse_passing_networks(page, team):
    text = page.get_text("text")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Top-5 passers table
    top5 = []
    in_top5 = False
    top5_buf = []
    for l in lines:
        if "Top 5 Player" in l:
            in_top5 = True
            continue
        if in_top5:
            if l in ("Player", "Passed To", "% of Total Team", "Passes"):
                continue
            if "June" in l or "Stadium" in l:
                break
            top5_buf.append(l)

    # Matrix: row totals per player (zero-collapse makes full matrix unreliable)
    # Build known_names FIRST so we can use them for top5 parsing
    words = page_words(page, y_min=100)
    rows = group_rows(words, y_tol=5)
    row_totals = {}
    known_names = []
    for row in rows:
        texts = row_texts(row)
        # Player rows start with jersey num then name
        if not texts:
            continue
        try:
            jersey = int(texts[0])
        except ValueError:
            continue
        name_parts = []
        nums_found = []
        for t in texts[1:]:
            if re.match(r'^\d+$', t):
                nums_found.append(int(t))
            else:
                if not nums_found:
                    name_parts.append(t)
        if name_parts and nums_found:
            pname = " ".join(name_parts)
            row_totals[pname] = sum(nums_found)
            known_names.append(pname)
    # Also add any single-word capitalized names from column headers
    for l in top5_buf:
        if re.match(r'^[A-Z][a-z]', l) and l not in known_names and not re.match(r'^\d', l):
            # Could be a name token; add as-is
            pass  # handled by greedy matching below

    def _split_entry_tokens(toks, knames):
        """Split token list into (from_name, to_name) using greedy name matching."""
        # Try all known names as from prefix (longest first)
        for n in sorted(knames, key=lambda x: -len(x.split())):
            nparts = n.split()
            # Match against flattened tokens: "Issa DIOP" as single token OR "Issa", "DIOP"
            # Case 1: first token is exact name
            if len(toks) >= 1 and toks[0] == n:
                rest = toks[1:]
                for n2 in sorted(knames, key=lambda x: -len(x.split())):
                    n2parts = n2.split()
                    if len(rest) >= 1 and rest[0] == n2:
                        return n, n2
                    if len(rest) >= len(n2parts) and rest[:len(n2parts)] == n2parts:
                        return n, n2
                    if len(rest) >= 1 and " ".join(rest) == n2:
                        return n, n2
                # No known name matched for to; join rest
                return n, (" ".join(rest) if rest else None)
            # Case 2: first len(nparts) tokens join to n
            if len(toks) >= len(nparts) and toks[:len(nparts)] == nparts:
                rest = toks[len(nparts):]
                for n2 in sorted(knames, key=lambda x: -len(x.split())):
                    n2parts = n2.split()
                    if len(rest) >= 1 and rest[0] == n2:
                        return n, n2
                    if len(rest) >= len(n2parts) and rest[:len(n2parts)] == n2parts:
                        return n, n2
                    if len(rest) >= 1 and " ".join(rest) == n2:
                        return n, n2
                return n, (" ".join(rest) if rest else None)
        # Fallback: first token from, rest to
        return (toks[0] if toks else None, " ".join(toks[1:]) if len(toks) > 1 else None)

    # top5_buf: flat list of tokens. Find pct tokens, extract segment before each.
    i = 0
    while i < len(top5_buf):
        # Find next pct token
        pct_idx = None
        for j in range(i, len(top5_buf)):
            if re.match(r'^\d+\.?\d*%$', top5_buf[j]):
                pct_idx = j
                break
        if pct_idx is None:
            break
        pct_clean = re.sub(r'[^0-9.]', '', top5_buf[pct_idx])
        pct_val_f = float(pct_clean) if pct_clean else 0.0
        pct_val = int(pct_val_f) if pct_val_f == int(pct_val_f) else pct_val_f
        segment = top5_buf[i:pct_idx]
        from_name, to_name = _split_entry_tokens(segment, known_names)
        top5.append({"from": from_name, "to": to_name, "pct_of_team_passes": pct_val})
        i = pct_idx + 1

    NOTE = ("Player-to-player matrix omitted as cell-level data: the source text export "
            "collapses blank/zero cells so individual from->to assignments cannot be reliably "
            "reconstructed. Per-'from' row totals are provided instead and reconcile with each "
            "player's passes completed (distributions page); sparse rows (e.g. DOUGLAS SANTOS, "
            "ROGER IBANEZ) under-count. Top-5 passers captured verbatim.")
    return {
        "team": team,
        "top5_player_to_player_passers": top5,
        "passing_matrix_partial": {"_note": NOTE, "row_totals": row_totals},
    }


def parse_pages_12_13(doc, home_team, away_team):
    p12 = _parse_passing_networks(doc[11], home_team)
    p13 = _parse_passing_networks(doc[12], away_team)
    return p12, p13


# ─── Pages 14/16: Shot Map Summary ───────────────────────────────────────────

def _parse_shot_summary(page, team):
    text = page.get_text("text")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    outcomes = {"goals": 0, "on_target": 0, "off_target": 0, "blocked": 0, "incomplete": 0}
    key_map = {"Goals": "goals", "On Target": "on_target", "Off Target": "off_target",
               "Blocked": "blocked", "Incomplete": "incomplete"}
    # In the shot summary page, labels come BEFORE the number: "Goals\n1\nOn Target\n4..."
    # Find the "Shots" header, then parse label-number pairs after it.
    in_table = False
    for i, l in enumerate(lines):
        if l == "Shots":
            in_table = True
            continue
        if not in_table:
            continue
        for k, v in key_map.items():
            if l == k and i + 1 < len(lines):
                try:
                    outcomes[v] = int(lines[i + 1])
                except ValueError:
                    pass
    total = sum(outcomes.values())
    return {"team": team, "outcomes": outcomes, "total_shots": total}


def parse_pages_14_16(doc, home_team, away_team):
    p14 = _parse_shot_summary(doc[13], home_team)
    p16 = _parse_shot_summary(doc[15], away_team)
    return p14, p16


# ─── Pages 15/17: Shot Logs ────────────────────────────────────────────────────

def _parse_shot_log_full(page, team):
    """Full shot log using the same coordinate-based parser as _parse_shot_log."""
    shots = _parse_shot_log(page)
    return {"team": team, "shots": shots}


def parse_pages_15_17(doc, home_team, away_team, extra=0):
    p15 = _parse_shot_log_full(doc[14], home_team)
    if extra > 0:
        shots_a = _parse_shot_log(doc[16])
        shots_b = _parse_shot_log(doc[17])
        p17 = {"team": away_team, "shots": shots_a + shots_b}
    else:
        p17 = _parse_shot_log_full(doc[16], away_team)
    return p15, p17


# ─── Pages 18/19: Crosses (Open Play) ─────────────────────────────────────────

def _parse_crosses(page, team):
    words_all = page_words(page)
    text = page.get_text("text")

    # ── Overall stats ──
    attempted = _extract_labeled_int(text, r'Attempted\s*\n(\d+)')
    completed = _extract_labeled_int(text, r'Completed\s*\n(\d+)')
    most_count = _extract_labeled_int(text, r'Most Crosses Attempted\s*\n(\d+)')
    most_player = _extract_labeled_str(text, r'Most Crosses Attempted\s*\n\d+\s*\n(.+)')

    # ── Delivery types (horizontal bar chart) ──
    # Labels are at x~300-340, values are at x>340 on the same y-row
    DELIVERY_LABELS = {
        "Inswing": "inswing", "Outswing": "outswing", "Driven": "driven",
        "Lofted": "lofted", "Cutback": "cutback", "Push": "push_cross",
    }
    label_ys = {}
    total_y = None
    for x, y, t in words_all:
        if 290 <= x <= 345:
            if t in DELIVERY_LABELS:
                label_ys[y] = DELIVERY_LABELS[t]
            elif t == "Total":
                total_y = y

    delivery = {v: 0 for v in DELIVERY_LABELS.values()}
    delivery_total = attempted or 0
    for x, y, t in words_all:
        if 345 < x < 530 and re.match(r'^\d+$', t):
            # Skip y-axis labels: these are in a row at y~270 and form a descending sequence
            # They appear at the bottom of the chart as a horizontal strip
            # Identify by checking if y matches the axis row (>= 265 typically)
            # Instead: match by label y-proximity
            best_label = None
            best_d = 15
            for ly, lname in label_ys.items():
                d = abs(y - ly)
                if d < best_d:
                    best_d = d
                    best_label = lname
            if best_label:
                delivery[best_label] = int(t)
            elif total_y and abs(y - total_y) < 10 and x > 450:
                delivery_total = int(t)

    delivery["total"] = delivery_total

    # ── Cross zones (pitch diagram left side) ──
    # 4 values in x<280, y>300 sorted by x → left, center_left, center_right, right
    zone_vals = sorted(
        [(x, int(t)) for x, y, t in words_all
         if x < 280 and y > 300 and re.match(r'^\d+$', t)],
        key=lambda t: t[0]
    )
    zone_names = ["left", "center_left", "center_right", "right"]
    cross_zones = dict(zip(zone_names, [v for _, v in zone_vals[:4]]))

    # ── Most attempted player and position ──
    # Use most_player from above; position appears below the player name if available
    most_player_name = most_player.strip() if most_player else ""
    pos_m = re.search(r'Most Crosses Attempted\s*\n\d+\s*\n(.+?)\n([A-Z ]+)\s*\n', text)
    if pos_m:
        most_position = pos_m.group(2).strip()
    else:
        # Word-based: ALL-CAPS words just below the player name's y
        player_yw = [(x, y) for x, y, t in words_all if x < 550 and most_player_name and t in most_player_name.split()]
        if player_yw:
            py = max(yy for _, yy in player_yw)
            pos_words = [t for x, y, t in words_all if x < 550 and py + 5 < y < py + 30 and re.match(r'^[A-Z]+$', t)]
            most_position = " ".join(pos_words) if pos_words else ""
        else:
            most_position = ""

    # ── Player table ──
    # Columns (x-centers): # ~590-600, player ~605, inswing~734, outswing~769,
    # driven~802, lofted~830, cutback~862, push_cross~892, total~926
    CROSS_PLAYER_X = {
        "inswing": 734, "outswing": 769, "driven": 802,
        "lofted": 830, "cutback": 862, "push_cross": 892, "total_attempted": 926,
    }
    player_words = page_words(page, x_min=580, y_min=80)
    player_rows = group_rows(player_words, y_tol=5)
    players = []
    header_done = False
    for row in player_rows:
        texts = row_texts(row)
        if "Player" in texts:
            header_done = True
            continue
        if not header_done:
            continue
        num_words = [w for w in row if w[0] < 600]
        name_words = [w for w in row if 600 <= w[0] < 710]
        if not num_words:
            continue
        try:
            num = int(num_words[0][2])
        except ValueError:
            continue
        name = " ".join(w[2] for w in sorted(name_words, key=lambda t: t[0]))
        if not name:
            continue
        p = {"num": num, "name": name}
        for col in CROSS_PLAYER_X:
            p[col] = 0
        for x, y, t in row:
            if x >= 720 and re.match(r'^\d+$', t):
                col = closest(x, CROSS_PLAYER_X, tol=20)
                if col:
                    p[col] = int(t)
        players.append(p)

    players = [p for p in players if any(v > 0 for v in [p.get('total_attempted', 0), p.get('inswing', 0), p.get('outswing', 0), p.get('driven', 0), p.get('lofted', 0), p.get('cutback', 0), p.get('push_cross', 0)])]

    return {
        "team": team,
        "attempted": attempted or 0,
        "completed": completed or 0,
        "most_attempted": {
            "count": most_count or 0,
            "player": most_player_name,
            "position": most_position,
        },
        "delivery_type_totals": delivery,
        "cross_zones": cross_zones,
        "players": players,
    }


def _extract_labeled_int(text, pattern):
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def _extract_labeled_str(text, pattern):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else ""


def parse_pages_18_19(doc, home_team, away_team, extra=0):
    p18 = _parse_crosses(doc[17 + extra], home_team)
    p19 = _parse_crosses(doc[18 + extra], away_team)
    return p18, p19


# ─── Pages 20/21: Offering to Receive ────────────────────────────────────────

def _parse_offering(page, team):
    text = page.get_text("text")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    words = page_words(page)

    total_made = _extract_labeled_int(text, r'(\d+)\s*\nTotal Offers Made')
    total_recv = _extract_labeled_int(text, r'(\d+)\s*\nTotal Offers Received')
    most_count = _extract_labeled_int(text, r'Most Offers\s*\n(\d+)')
    # Most player
    mp_m = re.search(r'Most Offers\s*\n(\d+)\s*\n(.+)', text)
    most_player = mp_m.group(2).strip() if mp_m else ""
    # Position: look in words widget area (left half, x<650), ALL-CAPS below player name
    pos_m = re.search(r'Most Offers\s*\n\d+\s*\n(.+?)\n([A-Z ]+)\s*\n', text)
    if pos_m:
        most_position = pos_m.group(2).strip()
    else:
        # Try word-based extraction: find player name y then get ALL-CAPS words just below
        player_yw = [(x, y) for x, y, t in words if x < 650 and most_player and t in most_player.split()]
        if player_yw:
            py = max(yy for _, yy in player_yw)
            pos_words = [t for x, y, t in words if x < 650 and py + 5 < y < py + 30 and re.match(r'^[A-Z]+$', t)]
            most_position = " ".join(pos_words) if pos_words else ""
        else:
            most_position = ""

    # Thirds
    final_m = re.search(r'(\d+)\s*\nOffers Made in Final Third', text)
    mid_m = re.search(r'(\d+)\s*\nOffers Made in Middle Third', text)
    def_m = re.search(r'(\d+)\s*\nOffers Made in Defensive', text)
    by_third = {
        "final": int(final_m.group(1)) if final_m else 0,
        "middle": int(mid_m.group(1)) if mid_m else 0,
        "defensive": int(def_m.group(1)) if def_m else 0,
    }

    # Shape: inside_shape (x~310-320, y~350) and outside_shape (x~530-540, y~440)
    # Both appear on the pitch diagram in the left half of the page (x<650)
    shape_words = [(x, y, int(t)) for x, y, t in words
                   if re.match(r'^\d+$', t) and 280 <= y <= 480 and 290 <= x < 570]
    shape_sorted = sorted(shape_words, key=lambda t: t[0])
    inside = shape_sorted[0][2] if len(shape_sorted) >= 1 else 0
    outside = shape_sorted[1][2] if len(shape_sorted) >= 2 else 0

    # Player table
    OFFER_X = {"offers_made": 215, "offers_received": 385, "pct_made_received": 485}
    # Columns are at different x than before - check with coordinates
    # From analysis: offers_made≈215, offers_received≈385, pct≈485
    # Player table is on the RIGHT half of the page (x > 650)
    # num at x~660-690, name at x~690-820, values at x>820
    player_words = page_words(page, x_min=650, y_min=108)
    player_rows = group_rows(player_words, y_tol=5)
    players = []
    for row in player_rows:
        num_words = [w for w in row if 650 <= w[0] < 682]
        name_words = [w for w in row if 682 <= w[0] < 820]
        if not num_words or not name_words:
            continue
        try:
            num = int(num_words[0][2])
        except ValueError:
            continue
        name = " ".join(w[2] for w in sorted(name_words, key=lambda t: t[0]))
        if not name:
            continue
        made, recv, pct = 0, 0, 0.0
        for x, y, t in row:
            if x >= 820:
                v = to_num(re.sub('%', '', t))
                if v is None:
                    continue
                if 820 <= x < 870:
                    made = int(v)
                elif 870 <= x < 910:
                    recv = int(v)
                elif x >= 910:
                    pct = float(v)
                    if pct == int(pct):
                        pct = int(pct)
        players.append({"num": num, "name": name,
                         "offers_made": made, "offers_received": recv,
                         "pct_made_received": pct})

    return {
        "team": team,
        "total_offers_made": total_made or 0,
        "total_offers_received": total_recv or 0,
        "most_offers": {"count": most_count or 0, "player": most_player,
                         "position": most_position},
        "offers_made_by_third": by_third,
        "offers_made_shape": {"inside_shape": inside, "outside_shape": outside},
        "players": players,
    }


def parse_pages_20_21(doc, home_team, away_team, extra=0):
    p20 = _parse_offering(doc[19 + extra], home_team)
    p21 = _parse_offering(doc[20 + extra], away_team)
    return p20, p21


# ─── Pages 22/23: Movement to Receive ────────────────────────────────────────

def _parse_movement(page, team):
    text = page.get_text("text")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    words = page_words(page)

    # Phase totals (3 numbers for Final Third, Progression, Build Up)
    # Appear as 3 numbers in left section (x~100-140, y~185/316/447)
    phase_words = sorted(
        [(y, int(t)) for x, y, t in words
         if re.match(r'^\d+$', t) and 100 <= x <= 140 and y > 100],
        key=lambda t: t[0]
    )
    phase_vals = [v for _, v in phase_words[:3]]
    by_phase = {
        "final_third_phase": phase_vals[0] if len(phase_vals) > 0 else 0,
        "progression_phase": phase_vals[1] if len(phase_vals) > 1 else 0,
        "build_up_phase": phase_vals[2] if len(phase_vals) > 2 else 0,
    }

    # Total (donut center, x~400-420)
    total_words = [(y, int(t)) for x, y, t in words
                   if re.match(r'^\d+$', t) and 390 <= x <= 430 and t != "0"]
    total = total_words[0][1] if total_words else 0

    # Top ranked players table
    # Labels: In Front, In Between, Out to In, In to Out, In Behind
    TYPE_LABELS = ["in_front", "in_between", "out_to_in", "in_to_out", "in_behind"]
    LABEL_TEXT_MAP = {
        "Front": "in_front", "Between": "in_between",
        "In": "out_to_in",   # "Out to In" → tricky
        "Out": "in_to_out",  # "In to Out"
        "Behind": "in_behind",
    }
    # Better: find "Top Ranked Players" section and parse rows
    top_ranked = {}
    tr_section = False
    buf = []
    for l in lines:
        if "Top Ranked" in l:
            tr_section = True
            continue
        if tr_section:
            if "Pitch Third" in l or "DIRECTION" in l:
                break
            buf.append(l)

    # buf: Type, Player, Movements interleaved
    # e.g. ["In Front", "BRUNO GUIMARAES", "24", "In Between", ...]
    type_map = {
        "In Front": "in_front", "In Between": "in_between",
        "Out to In": "out_to_in", "In to Out": "in_to_out", "In Behind": "in_behind",
    }
    multi = [" ".join(buf[i:i+2]) for i in range(0, len(buf) - 1)]
    type_map_keys = set(type_map.keys())
    # Also handle single-token type labels (e.g. "In Front" as one string)
    type_map_single = {" ".join(k.split()): v for k, v in type_map.items()}
    i = 0
    while i < len(buf) and len(top_ranked) < len(type_map):
        matched = False
        for tname, tkey in type_map.items():
            hit = False
            n_skip = 0
            # Case 1: single token matching full label
            if buf[i] == tname:
                hit = True; n_skip = 1
            # Case 2: multi-word tokens
            if not hit:
                parts = tname.split()
                if buf[i:i + len(parts)] == parts:
                    hit = True; n_skip = len(parts)
            if hit:
                label_end = i + n_skip
                player_parts = []
                j = label_end
                while j < len(buf) and not re.match(r'^\d+$', buf[j]) and buf[j] not in type_map_keys:
                    player_parts.append(buf[j])
                    j += 1
                movements = int(buf[j]) if j < len(buf) and re.match(r'^\d+$', buf[j]) else 0
                top_ranked[tkey] = {
                    "player": " ".join(player_parts),
                    "movements": movements,
                }
                i = j + 1
                matched = True
                break
        if not matched:
            i += 1

    # Pitch third breakdown (right side charts, x>690)
    # Three chart sections: FINAL THIRD (y~130-230), MIDDLE THIRD (y~260-360),
    #                       DEFENSIVE THIRD (y~390-480)
    # Each section has 5 values for: In Front, In Between, Out to In, In to Out, In Behind
    # Labels appear at x~695-720 for the 5 types

    MOVE_TYPES = ["in_front", "in_between", "out_to_in", "in_to_out", "in_behind"]

    def extract_third_values(y_min, y_max):
        """Get 5 values from a chart section on the right of the page."""
        chart_words = [(x, y, t) for x, y, t in words
                       if x > 730 and y_min <= y <= y_max and re.match(r'^\d+$', t)]
        # These values appear at specific y-positions matching the label y's
        # Labels (In Front etc.) are at x~695-720
        label_words = [(x, y, t) for x, y, t in words
                       if 690 <= x <= 730 and y_min <= y <= y_max]
        # Build label-y mapping
        label_ys = {}
        for x, y, t in label_words:
            # "In", "Front" etc. — combine adjacent
            pass
        # Simpler: values appear in vertical order matching label vertical order
        # Sort chart values by y and assign to types in order
        sorted_vals = sorted(chart_words, key=lambda t: t[1])
        result = {}
        for i, ttype in enumerate(MOVE_TYPES):
            if i < len(sorted_vals):
                result[ttype] = int(sorted_vals[i][2])
            else:
                result[ttype] = 0
        return result

    # Find y-ranges for each third section from "FINAL THIRD" / "MIDDLE THIRD" labels
    # These appear at specific y positions
    third_labels = {t: [] for t in ["FINAL", "MIDDLE", "DEFENSIVE"]}
    for x, y, t in words:
        if t.upper() in third_labels:
            third_labels[t.upper()].append(y)

    final_ys = sorted(third_labels.get("FINAL", [130]))
    mid_ys = sorted(third_labels.get("MIDDLE", [260]))
    def_ys = sorted(third_labels.get("DEFENSIVE", [390]))

    f_y = final_ys[0] if final_ys else 130
    m_y = mid_ys[0] if mid_ys else 260
    d_y = def_ys[0] if def_ys else 390

    by_pitch_third = {
        "final_third": extract_third_values(f_y - 60, m_y - 55),
        "middle_third": extract_third_values(m_y - 55, d_y - 55),
        "defensive_third": extract_third_values(d_y - 55, d_y + 120),
    }

    # Derive all_movement_types from pitch third sums
    all_types = {"total": total}
    for ttype in MOVE_TYPES:
        all_types[ttype] = sum(
            by_pitch_third[third].get(ttype, 0) for third in by_pitch_third
        )

    return {
        "team": team,
        "all_movement_types": all_types,
        "by_phase_totals": by_phase,
        "by_pitch_third": by_pitch_third,
        "top_ranked_players": top_ranked,
    }


def parse_pages_22_23(doc, home_team, away_team, extra=0):
    p22 = _parse_movement(doc[21 + extra], home_team)
    p23 = _parse_movement(doc[22 + extra], away_team)
    return p22, p23


# ─── Pages 25/26: Defensive Actions ──────────────────────────────────────────

# Donut-chart fill colors (RGB float tuples from fitz)
_COLOR_BLUE       = (0.18039999902248383, 0.3019999861717224, 1.0)
_COLOR_ORANGE     = (1.0, 0.23919999599456787, 0.0)
_COLOR_PURPLE     = (0.7020000219345093, 0.53329998254776, 1.0)
_COLOR_LIGHT_BLUE = (0.35690000653266907, 0.6078000068664551, 0.8353000283241272)
_COLOR_YELLOW     = (0.9607999920845032, 0.7372000217437744, 0.0)

def _color_name(fill, tol=0.02):
    """Match fill RGB tuple to a named color string, or None."""
    if not fill:
        return None
    for name, c in [('blue', _COLOR_BLUE), ('orange', _COLOR_ORANGE),
                    ('purple', _COLOR_PURPLE), ('light_blue', _COLOR_LIGHT_BLUE),
                    ('yellow', _COLOR_YELLOW)]:
        if all(abs(fill[i] - c[i]) < tol for i in range(3)):
            return name
    return None


def get_arc_span(items, cx, cy, outer_r, tol=6):
    """Measure the angular sweep of an arc/donut-segment shape using a fixed circle center."""
    pts = []
    for item in items:
        t = item[0]
        if t == 'c':
            for pt in [item[1], item[2], item[3]]:
                d = math.sqrt((pt.x - cx) ** 2 + (pt.y - cy) ** 2)
                if abs(d - outer_r) < tol:
                    pts.append((pt.x, pt.y))
        elif t in ('l', 'm'):
            pt = item[1]
            d = math.sqrt((pt.x - cx) ** 2 + (pt.y - cy) ** 2)
            if abs(d - outer_r) < tol:
                pts.append((pt.x, pt.y))
    if len(pts) < 2:
        return 0.0
    angles = [math.atan2(y - cy, x - cx) for x, y in pts]
    unwrapped = [angles[0]]
    for a in angles[1:]:
        diff = (a - unwrapped[-1] + math.pi) % (2 * math.pi) - math.pi
        unwrapped.append(unwrapped[-1] + diff)
    return abs(unwrapped[-1] - unwrapped[0])


def _decode_donut(page, cx, cy, outer_r, total, color_map, area_rect):
    """Decode a donut chart into {category: value} using arc geometry."""
    result = {cat: 0 for cat in color_map.values()}
    if total == 0:
        return result
    for d in page.get_drawings():
        rect = d.get('rect')
        fill = d.get('fill')
        if not rect or not fill or fill == (1.0, 1.0, 1.0):
            continue
        x0, y0, x1, y1 = area_rect
        if not (x0 <= rect.x0 <= x1 and y0 <= rect.y0 <= y1):
            continue
        color = _color_name(tuple(fill))
        if color not in color_map:
            continue
        cat = color_map[color]
        span = get_arc_span(d['items'], cx, cy, outer_r)
        if span > 0:
            val = round(span / (2 * math.pi) * total)
            result[cat] = val
    return result


_BLOCKS_COLOR_MAP = {
    'blue': 'passes',
    'orange': 'attempts_at_goal',
    'purple': 'crosses',
    'light_blue': 'clearances',
}

_CONTESTS_COLOR_MAP = {
    'blue': 'physical_duels',
    'orange': 'aerial_duels',
    'purple': 'duels',
}


def _build_blocks(page, total):
    decoded = _decode_donut(page, 547.1, 156.5, 39, total, _BLOCKS_COLOR_MAP, (490, 115, 610, 195))
    return {
        "total": total,
        "passes": decoded.get('passes', 0),
        "attempts_at_goal": decoded.get('attempts_at_goal', 0),
        "crosses": decoded.get('crosses', 0),
        "clearances": decoded.get('clearances', 0),
    }


def _build_contests(page, total):
    decoded = _decode_donut(page, 551, 317.5, 43, total, _CONTESTS_COLOR_MAP, (500, 270, 610, 365))
    return {
        "total": total,
        "physical_duels": decoded.get('physical_duels', 0),
        "aerial_duels": decoded.get('aerial_duels', 0),
        "duels": decoded.get('duels', 0),
    }


def _parse_defensive_actions(page, team):
    text = page.get_text("text")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    words = page_words(page)

    def grab(pattern):
        m = re.search(pattern, text)
        return to_num(m.group(1)) if m else None

    forced = grab(r'(\d+)\s*\nForced\s*\nTurnovers')
    regained = grab(r'(\d+)\s*\nPossession\s*\nRegained')
    interceptions = grab(r'(\d+)\s*\nInterceptions')
    tackles = grab(r'(\d+)\s*\nTackles')
    ratio_m = re.search(r'(\d+\.?\d*)\s*\nPossession\s*\nActions', text)
    ratio = float(ratio_m.group(1)) if ratio_m else None

    # blocks_total is at y~115-200, contests_total at y~275-360
    blocks_total = None
    for x, y, t in words:
        if 480 <= x <= 620 and 115 <= y <= 200 and re.match(r'^\d+$', t):
            blocks_total = int(t)
            break

    contests_total = None
    for x, y, t in words:
        if 480 <= x <= 620 and 275 <= y <= 360 and re.match(r'^\d+$', t):
            contests_total = int(t)
            break

    # Most possession regains
    most_count_m = re.search(r'Most Possession Regains\s*\n(\d+)', text)
    most_player_m = re.search(r'Most Possession Regains\s*\n\d+\s*\n(.+)', text)
    most_pos_m = re.search(r'Most Possession Regains\s*\n\d+\s*\n.+?\n([A-Z ]+)\s*\n', text)
    # Position also in word layer just below player name
    if not most_pos_m and most_player_m:
        mp_name = most_player_m.group(1).strip()
        mp_words_all = page_words(page)
        player_yw = [(x, y) for x, y, t in mp_words_all if t in mp_name.split()]
        if player_yw:
            py = max(yy for _, yy in player_yw)
            pos_words = [t for x, y, t in mp_words_all if py + 5 < y < py + 30 and re.match(r'^[A-Z]+$', t) and x < 700]
            _most_position_possession = " ".join(pos_words) if pos_words else ""
        else:
            _most_position_possession = ""
    else:
        _most_position_possession = most_pos_m.group(1).strip() if most_pos_m else ""

    # Player table (right side)
    player_words = page_words(page, x_min=725, y_min=100)
    player_rows = group_rows(player_words, y_tol=5)
    players = []
    for row in player_rows:
        num_words = [w for w in row if 725 <= w[0] < 743]
        name_words = [w for w in row if 743 <= w[0] < 900]
        val_words = [w for w in row if w[0] >= 900]
        if not num_words or not val_words:
            continue
        try:
            num = int(num_words[0][2])
        except ValueError:
            continue
        name = " ".join(w[2] for w in sorted(name_words, key=lambda t: t[0]))
        try:
            regains = int(val_words[0][2])
        except (ValueError, IndexError):
            regains = 0
        if name:
            players.append({"num": num, "name": name, "total_possession_regains": regains})

    return {
        "team": team,
        "forced_turnovers": forced or 0,
        "possession_regained": regained or 0,
        "interceptions": interceptions or 0,
        "tackles": tackles or 0,
        "possession_actions_per_defensive_action": ratio or 0,
        "blocks": _build_blocks(page, blocks_total or 0),
        "possession_contests": _build_contests(page, contests_total or 0),
        "most_possession_regains": {
            "count": int(most_count_m.group(1)) if most_count_m else 0,
            "player": most_player_m.group(1).strip() if most_player_m else "",
            "position": _most_position_possession,
        },
        "players": players,
    }


def parse_pages_25_26(doc, home_team, away_team, extra=0):
    p25 = _parse_defensive_actions(doc[24 + extra], home_team)
    p26 = _parse_defensive_actions(doc[25 + extra], away_team)
    return p25, p26


# ─── Pages 27/28: Defensive Line Height ──────────────────────────────────────

def parse_pages_27_28(doc, home_team, away_team, extra=0):
    secs = ["high_block_press", "mid_block", "low_block"]
    p27 = _parse_pitch_diagram_3blocks(doc[26 + extra], secs)
    p28 = _parse_pitch_diagram_3blocks(doc[27 + extra], secs)
    p27["team"] = home_team
    p28["team"] = away_team
    return p27, p28


# ─── Page 29: Defensive Pressure ─────────────────────────────────────────────

def parse_page29(page, home_team, away_team):
    words = page_words(page, y_min=100)
    rows = group_rows(words, y_tol=5)

    stats = []
    most = {"home_team": {}, "away_team": {}}

    for row in rows:
        wxs = [(w[0], w[2]) for w in row]
        left = [t for x, t in wxs if x < 410]
        center = [t for x, t in wxs if 410 <= x <= 580]
        right = [t for x, t in wxs if x > 580]
        if not center or not left or not right:
            continue
        stat_name = " ".join(center)
        lv = " ".join(left)
        rv = " ".join(right)

        # Skip "Most Direct Pressures" rows
        if "Most" in stat_name or "Most" in lv:
            continue
        if "DIRECTION" in stat_name or "Shown" in stat_name:
            continue

        home_v = to_num(re.sub(r'\s*s$', '', lv.strip()))
        away_v = to_num(re.sub(r'\s*s$', '', rv.strip()))
        if home_v is None:
            continue
        if "Duration" in stat_name and "(s)" not in stat_name:
            stat_name += " (s)"
        if "Recovery Time" in stat_name and "(s)" not in stat_name:
            stat_name += " (s)"
        stats.append({"stat": stat_name, "home_team": home_v, "away_team": away_v})

    # Most direct pressures — extract from word layer by position
    # Layout: "Most Direct / Pressures" label at y~Y, count at y~Y+25,
    #         player name at y~Y+38, position words at y~Y+51..+65
    # Home widget at x<500, away widget at x>500
    all_words = page_words(page)
    most_label_ys = [y for x, y, t in all_words if t == 'Most' and
                     any(abs(y - y2) < 6 and t2 == 'Direct'
                         for x2, y2, t2 in all_words)]
    if not most_label_ys:
        # fallback: find 'Pressures' near 'Most Direct' region
        most_label_ys = [y for x, y, t in all_words if t == 'Pressures' and x > 200 and x < 700]

    if most_label_ys:
        ref_y = min(most_label_ys)
        for side, x_min, x_max in [('home_team', 0, 500), ('away_team', 500, 950)]:
            # count: integer in y+20..y+40 in x_range
            cnt_words = [(x, y, t) for x, y, t in all_words
                         if x_min <= x < x_max and ref_y + 15 <= y <= ref_y + 45
                         and re.match(r'^\d+$', t)]
            if not cnt_words:
                continue
            cnt_words.sort(key=lambda w: w[1])
            count = int(cnt_words[0][2])
            count_y = cnt_words[0][1]
            # player: first distinct y level roughly 30-55 units below count
            candidate_words = [(x, y, t) for x, y, t in all_words
                               if x_min <= x < x_max and count_y + 25 <= y <= count_y + 60]
            if candidate_words:
                first_y = min(w[1] for w in candidate_words)
                player_words = [(x, y, t) for x, y, t in candidate_words if abs(y - first_y) < 5]
            else:
                player_words = []
            player = ' '.join(t for _, _, t in sorted(player_words, key=lambda w: w[0]))
            # position: words at y+50..y+80, letter-only tokens
            player_y = player_words[0][1] if player_words else count_y + 14
            pos_words = [(x, y, t) for x, y, t in all_words
                         if x_min <= x < x_max and player_y + 8 <= y <= player_y + 40
                         and re.match(r'^[A-Za-z]', t)
                         and t not in ('Shown', 'Outside', 'Inside', 'Neutral', 'From', 'Behind')]
            position = ' '.join(t for _, _, t in sorted(pos_words, key=lambda w: (w[1], w[0])))
            most[side] = {"count": count, "player": player, "position": position}

    return {"statistics": stats, "most_direct_pressures": most}


# ─── Page 31: Goalkeeping Involvement ────────────────────────────────────────

def parse_page31(page):
    text = page.get_text("text")
    h = re.search(r'(\d+)\s*\nTotal Involvements', text)
    nums = re.findall(r'(\d+)\s*\nTotal Involvements', text)
    return {
        "home_team": {"total_involvements": int(nums[0]) if nums else 0},
        "away_team": {"total_involvements": int(nums[1]) if len(nums) > 1 else 0},
    }


# ─── Pages 32/33: Goalkeeping Distribution ───────────────────────────────────

def _parse_gk_distribution(page, team, gk_name):
    text = page.get_text("text")
    words = page_words(page)

    # Total per category appears at y~477 at specific x-centers
    # kick_from_feet ≈ x=160, kick_from_hands ≈ x=406, throw ≈ x=643
    cat_words = [(x, int(t)) for x, y, t in words
                 if re.match(r'^\d+$', t) and 470 <= y <= 485 and x < 680]
    cat_sorted = sorted(cat_words, key=lambda t: t[0])
    feet_total = cat_sorted[0][1] if len(cat_sorted) > 0 else 0
    hands_total = cat_sorted[1][1] if len(cat_sorted) > 1 else 0
    throw_total = cat_sorted[2][1] if len(cat_sorted) > 2 else 0
    total_dist = feet_total + hands_total + throw_total

    # Goalkeeper line breaks
    lb_m = re.search(r'(\d+)\s*\nGoalkeeper Line Breaks', text)
    gk_lb = int(lb_m.group(1)) if lb_m else 0

    return {
        "team": team,
        "goalkeeper": gk_name,
        "kick_from_feet": {"total": feet_total},
        "kick_from_hands": {"total": hands_total},
        "throw_distribution": {"total": throw_total},
        "total_distributions": total_dist,
        "goalkeeper_line_breaks": gk_lb,
    }


def parse_pages_32_33(doc, home_team, away_team, home_gk, away_gk, extra=0):
    p32 = _parse_gk_distribution(doc[31 + extra], home_team, home_gk)
    p33 = _parse_gk_distribution(doc[32 + extra], away_team, away_gk)
    return p32, p33


# ─── Pages 34/35: Goal Prevention ────────────────────────────────────────────

def _parse_goal_prevention(page, team, gk_name):
    text = page.get_text("text")
    words = page_words(page)

    total_m = re.search(r'(\d+)\s*\nTotal Attempts on Goal Faced', text)
    save_pct_m = re.search(r'(\d+)\s*\nSave %', text)
    total_faced = int(total_m.group(1)) if total_m else 0
    save_pct = int(save_pct_m.group(1)) if save_pct_m else 0

    # Intervention breakdown table (at y~509)
    # Cols: total_faced, total_goal_interventions, save_and_retain, deflect_and_retain,
    #       save_and_deflect, save_attempt, no_save_attempt
    TABLE_X = {
        "total_faced": 506, "total_goal_interventions": 604,
        "save_and_retain": 675, "deflect_and_retain": 733,
        "save_and_deflect": 794, "save_attempt": 850, "no_save_attempt": 910,
    }
    breakdown = {k: 0 for k in TABLE_X}
    for x, y, t in words:
        if re.match(r'^\d+$', t) and 500 <= y <= 520:
            col = closest(x, TABLE_X, tol=25)
            if col:
                breakdown[col] = int(t)

    return {
        "team": team,
        "goalkeeper": gk_name,
        "total_attempts_faced": total_faced,
        "save_pct": save_pct,
        "intervention_breakdown": {
            "total_goal_interventions": breakdown["total_goal_interventions"],
            "save_and_retain": breakdown["save_and_retain"],
            "deflect_and_retain": breakdown["deflect_and_retain"],
            "save_and_deflect": breakdown["save_and_deflect"],
            "save_attempt": breakdown["save_attempt"],
            "no_save_attempt": breakdown["no_save_attempt"],
        },
        "intervention_body_type": {
            "head": None, "hands": None, "upper_body": None,
            "lower_body": None, "feet": None,
        },
    }


def parse_pages_34_35(doc, home_team, away_team, home_gk, away_gk, extra=0):
    p34 = _parse_goal_prevention(doc[33 + extra], home_team, home_gk)
    p35 = _parse_goal_prevention(doc[34 + extra], away_team, away_gk)
    return p34, p35


# ─── Pages 36/37: Aerial Control ─────────────────────────────────────────────

def _parse_aerial_control(page, team, gk_name):
    text = page.get_text("text")
    words = page_words(page)

    total_m = re.search(r'(\d+)\s*\nTotal Interventions', text)
    total_int = int(total_m.group(1)) if total_m else 0

    def parse_intervention(label):
        # e.g. "Punches" → complete / incomplete
        # Pattern: "(complete) (total) (label) (incomplete)" from word positions
        c_m = re.search(rf'(\d+)\s*\nComplete\s*\n(\d+)\s*\n{label}\s*\n(\d+)\s*\nIncomplete', text)
        if c_m:
            return {"complete": int(c_m.group(1)), "incomplete": int(c_m.group(3))}
        # Fallback from word positions: three numbers appear near label text
        return {"complete": 0, "incomplete": 0}

    punches = parse_intervention("Punches")
    claims = parse_intervention("Claims")
    tipped = parse_intervention(r"Tipped/Palmed")

    # Delivery types table (explicit row at y~512)
    TABLE_X = {
        "total": 524, "in_swing": 586, "out_swing": 647,
        "driven": 708, "lofted": 770, "cutback": 829, "push": 891,
    }
    delivery = {k: 0 for k in TABLE_X}
    for x, y, t in words:
        if re.match(r'^\d+$', t) and 505 <= y <= 520:
            col = closest(x, TABLE_X, tol=25)
            if col:
                delivery[col] = int(t)

    return {
        "team": team,
        "goalkeeper": gk_name,
        "total_interventions": total_int,
        "punches": punches,
        "claims": claims,
        "tipped_palmed": tipped,
        "crosses_faced_delivery_types": delivery,
    }


def parse_pages_36_37(doc, home_team, away_team, home_gk, away_gk, extra=0):
    p36 = _parse_aerial_control(doc[35 + extra], home_team, home_gk)
    p37 = _parse_aerial_control(doc[36 + extra], away_team, away_gk)
    return p36, p37


# ─── Pages 39/40: Set Plays ───────────────────────────────────────────────────

def _parse_set_plays(page, team):
    text = page.get_text("text")

    def g(pattern, cast=int):
        m = re.search(pattern, text)
        return cast(m.group(1)) if m else 0

    totals = {
        "set_plays": g(r'(\d+)\s*\nTotal Set Plays'),
        "free_kicks": g(r'(\d+)\s*\nTotal Free Kicks'),
        "penalties": g(r'(\d+)\s*\nTotal Penalties'),
        "corners": g(r'(\d+)\s*\nTotal Corners'),
        "throw_ins": g(r'(\d+)\s*\nTotal Throw Ins'),
    }
    direct_m = re.search(r'Direct\s*\n(\d+)\s*\n', text)
    indirect_m = re.search(r'Indirect\s*\n(\d+)', text)
    fk_direct = int(direct_m.group(1)) if direct_m else 0
    fk_indirect = int(indirect_m.group(1)) if indirect_m else 0
    # direct_on_target and direct_off_target are sub-fields only accessible visually
    free_kicks = {
        "direct": fk_direct,
        "direct_on_target": 0,
        "direct_off_target": 0,
        "indirect": fk_indirect,
    }

    # Corners by delivery type: use word positions to distinguish from_left/from_right/total.
    # Column x positions: From Left ~765, From Right ~837, Total ~909 (consistent across PDFs).
    _all_words = page_words(page)
    LABEL_ROWS = {"Direct to Area": None, "Short": None, "Edge of Penalty Area": None}
    for label in list(LABEL_ROWS):
        label_words = label.split()
        rows_candidate = group_rows(_all_words, y_tol=4)
        for row in rows_candidate:
            row_texts_list = [t for _, _, t in row]
            if row_texts_list[:len(label_words)] == label_words:
                LABEL_ROWS[label] = min(y for _, y, _ in row)
                break

    def corner_block(label):
        label_y = LABEL_ROWS.get(label)
        if label_y is None:
            return {"from_left": 0, "from_right": 0, "total": 0}
        row_words = [(x, y, t) for x, y, t in _all_words
                     if abs(y - label_y) < 8 and re.match(r'^\d+$', t)]
        fl = fr = tot = 0
        for x, y, t in row_words:
            v = int(t)
            if x < 800:
                fl = v
            elif x < 875:
                fr = v
            else:
                tot = v
        return {"from_left": fl, "from_right": fr, "total": tot}

    c_type = {
        "direct_to_area": corner_block("Direct to Area"),
        "short": corner_block(r"Short"),
        "edge_of_penalty_area": corner_block("Edge of Penalty Area"),
    }

    # Corners by delivery style: Inswing N / Outswing N / Driven N / Lofted N
    def style_val(label):
        # Require the number to be on its own line (followed by \n or end-of-string)
        # to avoid matching "13" from "13 June 2026" footer
        m = re.search(rf'{label}\s*\n(\d+)\s*\n', text)
        return int(m.group(1)) if m else 0

    c_style = {
        "inswing": style_val("Inswing"),
        "outswing": style_val("Outswing"),
        "driven": style_val("Driven"),
        "lofted": style_val("Lofted"),
    }

    return {
        "team": team,
        "totals": totals,
        "free_kicks": free_kicks,
        "corners_by_delivery_type": c_type,
        "corners_by_delivery_style": c_style,
    }


def parse_pages_39_40(doc, home_team, away_team, extra=0):
    p39 = _parse_set_plays(doc[38 + extra], home_team)
    p40 = _parse_set_plays(doc[39 + extra], away_team)
    return p39, p40


# ─── Pages 42/44: Distributions per player ───────────────────────────────────

_DIST_X = {
    "passes_attempted": 213, "passes_completed": 267, "pass_completion_pct": 319,
    "switches_of_play": 378, "crosses_attempted": 432, "crosses_completed": 486,
    "line_breaks_attempted": 539, "line_breaks_completed": 593,
    "line_break_completion_pct": 641, "ball_progressions": 703,
    "take_ons": 757, "step_ins": 811, "attempts_at_goal": 865, "goals": 919,
}


def _parse_distributions(page, team):
    words = page_words(page, y_min=108)
    rows = group_rows(words, y_tol=5)
    players = []
    for row in rows:
        num_words = [w for w in row if w[0] < 40]
        name_words = [w for w in row if 40 <= w[0] < 200]
        if not num_words or not name_words:
            continue
        try:
            num = int(num_words[0][2])
        except ValueError:
            continue
        name = " ".join(w[2] for w in sorted(name_words, key=lambda t: t[0]))
        if not name:
            continue
        p = {"num": num, "name": name}
        for col in _DIST_X:
            p[col] = 0
        for x, y, t in row:
            if x < 200:
                continue
            col = closest(x, _DIST_X, tol=25)
            if col:
                if "pct" in col:
                    p[col] = pct_int(t) if "%" in t else (to_num(t) or 0)
                else:
                    p[col] = to_num(t) or 0
        players.append(p)

    return {"team": team, "players": players}


def parse_pages_42_44(doc, home_team, away_team, extra=0):
    p42 = _parse_distributions(doc[41 + extra], home_team)
    p44 = _parse_distributions(doc[43 + extra], away_team)
    return p42, p44


# ─── Pages 43/45: Offers & Receptions per player ─────────────────────────────

_OFF_X = {
    "total_offers": 220, "in_front": 318, "in_between": 410,
    "out_to_in": 515, "in_to_out": 610, "in_behind": 703,
    "no_movement": 793, "offers_received": 895,
}


def _parse_offers_receptions(page, team):
    words = page_words(page, y_min=108)
    rows = group_rows(words, y_tol=5)
    players = []
    for row in rows:
        num_words = [w for w in row if w[0] < 40]
        name_words = [w for w in row if 40 <= w[0] < 200]
        if not num_words or not name_words:
            continue
        try:
            num = int(num_words[0][2])
        except ValueError:
            continue
        name = " ".join(w[2] for w in sorted(name_words, key=lambda t: t[0]))
        if not name:
            continue
        p = {"num": num, "name": name}
        for col in _OFF_X:
            p[col] = 0
        for x, y, t in row:
            if x < 200:
                continue
            col = closest(x, _OFF_X, tol=30)
            if col:
                p[col] = to_num(t) or 0
        players.append(p)
    return {"team": team, "players": players}


def parse_pages_43_45(doc, home_team, away_team, extra=0):
    p43 = _parse_offers_receptions(doc[42 + extra], home_team)
    p45 = _parse_offers_receptions(doc[44 + extra], away_team)
    return p43, p45


# ─── Pages 47/48: Out of Possession per player ───────────────────────────────

_OOP_X = {
    "tackles": 213,           # "X / Y" format parsed separately
    "blocks": 267,
    "interceptions": 316,
    "pressing_direct": 381,
    "pressing_indirect": 430,
    "duels_won_aerial": 484,
    "duels_won_physical": 538,
    "possession_contests_won": 592,
    "clearances": 646,
    "loose_ball_receptions": 700,
    "pushing_on": 754,
    "pushing_on_into_pressing": 808,
    "possession_regains": 862,
    "possession_interrupted": 916,
}


def _parse_oop(page, team):
    words = page_words(page, y_min=108)
    rows = group_rows(words, y_tol=5)
    players = []
    OOP_NOTE = "regains column validated against Defensive Actions page; interior sparse columns are best-effort."
    # Note: the note text is consistent across both home and away pages
    for row in rows:
        num_words = [w for w in row if w[0] < 40]
        name_words = [w for w in row if 40 <= w[0] < 200]
        if not num_words or not name_words:
            continue
        try:
            num = int(num_words[0][2])
        except ValueError:
            continue
        name = " ".join(w[2] for w in sorted(name_words, key=lambda t: t[0]))
        if not name:
            continue

        p = {"num": num, "name": name,
             "tackles_made": 0, "tackles_won": 0}
        for col in _OOP_X:
            if col != "tackles":
                p[col] = 0

        # Parse "/" for tackles and assign remaining by x
        data_words = sorted([w for w in row if w[0] >= 200], key=lambda t: t[0])
        i = 0
        while i < len(data_words):
            x, y, t = data_words[i]
            if t == "/" and i > 0 and i < len(data_words) - 1:
                # data_words[i-1] = made, data_words[i+1] = won
                try:
                    p["tackles_made"] = int(data_words[i-1][2])
                    p["tackles_won"] = int(data_words[i+1][2])
                except (ValueError, IndexError):
                    pass
                i += 2
                continue
            if re.match(r'^\d+$', t):
                col = closest(x, _OOP_X, tol=30)
                if col and col != "tackles":
                    p[col] = int(t)
            i += 1

        players.append(p)

    return {"team": team, "_note": OOP_NOTE, "players": players}


def parse_pages_47_48(doc, home_team, away_team, extra=0):
    p47 = _parse_oop(doc[46 + extra], home_team)
    p48 = _parse_oop(doc[47 + extra], away_team)
    return p47, p48


# ─── Pages 50/51: Physical Data ───────────────────────────────────────────────

_PHYS_X = {
    "total_distance_m": 285, "zone1_0_7_m": 362,
    "zone2_7_15_m": 442,    "zone3_15_20_m": 525,
    "zone4_20_25_m": 615,   "zone5_25plus_m": 690,
    "high_speed_runs_zone3": 770, "sprints_zone4_5": 845,
    "top_speed_kmh": 920,
}


def _parse_physical(page, team):
    words = page_words(page, y_min=108)
    rows = group_rows(words, y_tol=5)
    players = []
    for row in rows:
        num_words = [w for w in row if w[0] < 40]
        name_words = [w for w in row if 40 <= w[0] < 240]
        if not num_words or not name_words:
            continue
        try:
            num = int(num_words[0][2])
        except ValueError:
            continue
        name = " ".join(w[2] for w in sorted(name_words, key=lambda t: t[0]))
        if not name:
            continue
        p = {"num": num, "name": name}
        for col in _PHYS_X:
            p[col] = 0
        for x, y, t in row:
            if x < 265:
                continue
            col = closest(x, _PHYS_X, tol=30)
            if col:
                v = to_num(t) or 0
                # Count columns (runs, sprints) should be int, not float
                if isinstance(v, float) and v == int(v) and col in (
                        'high_speed_runs_zone3', 'sprints_zone4_5'):
                    v = int(v)
                p[col] = v
        players.append(p)
    return {"team": team, "players": players}


def parse_pages_50_51(doc, home_team, away_team, extra=0):
    p50 = _parse_physical(doc[49 + extra], home_team)
    p51 = _parse_physical(doc[50 + extra], away_team)
    return p50, p51


# ─── GK name helper ───────────────────────────────────────────────────────────

def find_gk(players_dict):
    """Find the starting goalkeeper name from a team's player dict."""
    for p in players_dict.get("starting", []):
        if p.get("position", "").upper() == "GK":
            return p["name"]
    return "Unknown"


# ─── Main assembler ───────────────────────────────────────────────────────────

def _count_extra_shot_log_pages(doc):
    """Return number of extra shot-log pages beyond the standard 52-page layout."""
    if len(doc) <= 52:
        return 0
    try:
        p = doc[17]
        words = p.get_text('words')
        minute_words = [w for w in words if w[0] < 100 and re.match(r'^\d{1,3}$', w[4])]
        if len(minute_words) >= 3:
            return 1
    except Exception:
        pass
    return 0


def extract(pdf_path: str, output_path: str):
    doc = fitz.open(pdf_path)
    extra = _count_extra_shot_log_pages(doc)
    pdf_filename = Path(pdf_path).name
    print(f"Parsing {pdf_filename} ({doc.page_count} pages)…")

    # ── Page 1: match metadata ──
    match = parse_page1(doc[0])
    home = match["home_team_name"]
    away = match["away_team_name"]
    score = match["score"]

    # ── Pre-parse shot logs (needed for lineup goal-minute lookup) ──
    p15_raw = _parse_shot_log(doc[14])
    if extra > 0:
        p17_raw = _parse_shot_log(doc[16]) + _parse_shot_log(doc[17])
    else:
        p17_raw = _parse_shot_log(doc[16])
    home_goals_map = {s["player"]: [] for s in p15_raw if "Goal" in s.get("outcome", "")}
    away_goals_map = {s["player"]: [] for s in p17_raw if "Goal" in s.get("outcome", "")}
    for s in p15_raw:
        if "Goal" in s.get("outcome", ""):
            home_goals_map.setdefault(s["player"], []).append(s["minute"])
    for s in p17_raw:
        if "Goal" in s.get("outcome", ""):
            away_goals_map.setdefault(s["player"], []).append(s["minute"])
    all_goals_map = {**home_goals_map, **away_goals_map}

    # ── Parse all pages ──
    p2_data = parse_page2(doc, home, away, p15_raw, p17_raw, score)
    home_gk = find_gk(p2_data["home_team"])
    away_gk = find_gk(p2_data["away_team"])

    p15_full, p17_full = parse_pages_15_17(doc, home, away, extra)
    p14, p16 = parse_pages_14_16(doc, home, away)
    p3 = parse_page3(doc[2])
    p4 = parse_page4(doc[3])
    p6, p7 = parse_pages_6_7(doc, home, away)
    p8, p9 = parse_pages_8_9(doc, home, away)
    p10, p11 = parse_pages_10_11(doc, home, away)
    p12, p13 = parse_pages_12_13(doc, home, away)
    p18, p19 = parse_pages_18_19(doc, home, away, extra)
    p20, p21 = parse_pages_20_21(doc, home, away, extra)
    p22, p23 = parse_pages_22_23(doc, home, away, extra)
    p25, p26 = parse_pages_25_26(doc, home, away, extra)
    p27, p28 = parse_pages_27_28(doc, home, away, extra)
    p29 = parse_page29(doc[28 + extra], home, away)
    p31 = parse_page31(doc[30 + extra])
    p32, p33 = parse_pages_32_33(doc, home, away, home_gk, away_gk, extra)
    p34, p35 = parse_pages_34_35(doc, home, away, home_gk, away_gk, extra)
    p36, p37 = parse_pages_36_37(doc, home, away, home_gk, away_gk, extra)
    p39, p40 = parse_pages_39_40(doc, home, away, extra)
    p42, p44 = parse_pages_42_44(doc, home, away, extra)
    p43, p45 = parse_pages_43_45(doc, home, away, extra)
    p47, p48 = parse_pages_47_48(doc, home, away, extra)
    p50, p51 = parse_pages_50_51(doc, home, away, extra)

    # ── Assemble pages dict ──
    pages = {
        "1":  {"title": "Cover / Metadata", "type": "title_page", "data": dict(match)},
        "2":  {"title": "Match Summary - Teams", "type": "lineups", "data": p2_data},
        "3":  {"title": "Match Summary - Key Statistics", "type": "team_comparison_table", "data": p3},
        "4":  {"title": "Phases of Play", "type": "team_comparison_table", "data": p4},
        "6":  {"title": "In Possession Line Height & Team Length - Home", "type": "pitch_diagram", "data": p6},
        "7":  {"title": "In Possession Line Height & Team Length - Away", "type": "pitch_diagram", "data": p7},
        "8":  {"title": "Line Breaks - Home", "type": "diagram_widgets", "data": p8},
        "9":  {"title": "Line Breaks - Away", "type": "diagram_widgets", "data": p9},
        "10": {"title": "Line Breaks (per player) - Home", "type": "player_table", "data": p10},
        "11": {"title": "Line Breaks (per player) - Away", "type": "player_table", "data": p11},
        "12": {"title": "Passing Networks - Home", "type": "matrix_plus_table", "data": p12},
        "13": {"title": "Passing Networks - Away", "type": "matrix_plus_table", "data": p13},
        "14": {"title": "Attempts at Goal (summary) - Home", "type": "shot_map_summary", "data": p14},
        "15": {"title": "Attempts at Goal (shot log) - Home", "type": "event_table", "data": p15_full},
        "16": {"title": "Attempts at Goal (summary) - Away", "type": "shot_map_summary", "data": p16},
        "17": {"title": "Attempts at Goal (shot log) - Away", "type": "event_table", "data": p17_full},
        "18": {"title": "Crosses (Open Play) - Home", "type": "diagram_plus_table", "data": p18},
        "19": {"title": "Crosses (Open Play) - Away", "type": "diagram_plus_table", "data": p19},
        "20": {"title": "Offering to Receive - Home", "type": "widgets_plus_table", "data": p20},
        "21": {"title": "Offering to Receive - Away", "type": "widgets_plus_table", "data": p21},
        "22": {"title": "Movement to Receive - Home", "type": "widgets_plus_charts", "data": p22},
        "23": {"title": "Movement to Receive - Away", "type": "widgets_plus_charts", "data": p23},
        "25": {"title": "Defensive Actions - Home", "type": "widgets_plus_table", "data": p25},
        "26": {"title": "Defensive Actions - Away", "type": "widgets_plus_table", "data": p26},
        "27": {"title": "Defensive Line Height & Team Length - Home", "type": "pitch_diagram", "data": p27},
        "28": {"title": "Defensive Line Height & Team Length - Away", "type": "pitch_diagram", "data": p28},
        "29": {"title": "Defensive Pressure", "type": "team_comparison_table", "data": p29},
        "31": {"title": "Goalkeeping Involvement", "type": "timeline_charts", "data": p31},
        "32": {"title": "Goalkeeping Distribution - Home", "type": "diagram_widgets", "data": p32},
        "33": {"title": "Goalkeeping Distribution - Away", "type": "diagram_widgets", "data": p33},
        "34": {"title": "Goal Prevention - Home", "type": "diagram_widgets", "data": p34},
        "35": {"title": "Goal Prevention - Away", "type": "diagram_widgets", "data": p35},
        "36": {"title": "Aerial Control - Home", "type": "diagram_widgets", "data": p36},
        "37": {"title": "Aerial Control - Away", "type": "diagram_widgets", "data": p37},
        "39": {"title": "Set Plays - Home", "type": "widgets_plus_tables", "data": p39},
        "40": {"title": "Set Plays - Away", "type": "widgets_plus_tables", "data": p40},
        "42": {"title": "In Possession - Distributions - Home", "type": "player_table", "data": p42},
        "43": {"title": "In Possession - Offers & Receptions - Home", "type": "player_table", "data": p43},
        "44": {"title": "In Possession - Distributions - Away", "type": "player_table", "data": p44},
        "45": {"title": "In Possession - Offers & Receptions - Away", "type": "player_table", "data": p45},
        "47": {"title": "Out of Possession - Home", "type": "player_table", "data": p47},
        "48": {"title": "Out of Possession - Away", "type": "player_table", "data": p48},
        "50": {"title": "Physical Data - Home", "type": "player_table", "data": p50},
        "51": {"title": "Physical Data - Away", "type": "player_table", "data": p51},
    }

    result = {
        "_meta": {
            "source_file": pdf_filename,
            "description": "Structured extraction of FIFA Post Match Summary Report",
            "skipped_pages": sorted(SKIP_PAGES_1IDX),
            "skipped_pages_reason": (
                "Section divider / title pages and the closing FIFA logo page (no data)."
            ),
            "pages_processed": PROCESSED_PAGES,
        },
        "match": match,
        "pages": pages,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size = Path(output_path).stat().st_size
    print(f"Wrote {output_path} ({size:,} bytes, {len(pages)} pages)")
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: parse_pmsr.py <pdf_path> [output.json]")
        sys.exit(1)
    pdf_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "result.json"
    if not Path(pdf_path).exists():
        print(f"Error: {pdf_path} not found")
        sys.exit(1)
    extract(pdf_path, output_path)


if __name__ == "__main__":
    main()
