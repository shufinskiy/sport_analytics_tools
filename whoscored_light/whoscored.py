import json
import io
from datetime import datetime, timedelta
from typing import Any

import seleniumbase as sb
import pandas as pd
from soccerdata._common import standardize_colnames


def whoscored_read_event(
        match_id: int,
        output_fmt: str = "events",
        path_to_browser: str = "/usr/bin/google-chrome",
        headless: bool = True
) -> pd.DataFrame:
    driver = sb.Driver(
        uc=True,
        headless=headless,
        binary_location=path_to_browser,
    )

    driver.get(f"https://www.whoscored.com/matches/{match_id}/live")

    response = json.dumps(driver.execute_script("return " + "require.config.params['args'].matchCentreData")).encode(
        "utf-8")
    driver.close()

    reader = io.BytesIO(response)
    reader.seek(0)

    json_data = json.load(reader)

    events = {}
    player_names = {}
    team_names = {}

    player_names.update(
        {int(k): v for k, v in json_data["playerIdNameDictionary"].items()}
    )
    team_names.update(
        {
            int(json_data[side]["teamId"]): json_data[side]["name"]
            for side in ["home", "away"]
        }
    )
    game_events = json_data["events"]
    if output_fmt == "events":
        df_events = pd.DataFrame(game_events)
        df_events["game_id"] = match_id
        events[match_id] = df_events
    elif output_fmt in ["spadl", "atomic-spadl"]:
        try:
            from socceraction.data.opta.parsers.base import assertget, _get_end_x, _get_end_y
            from socceraction.data.opta.loader import _eventtypesdf
            from socceraction.spadl.opta import convert_to_actions
            from socceraction.atomic.spadl.base import convert_to_atomic
        except ImportError:
            raise ImportError(
                "The socceraction package is required to use the 'spadl' "
                "or 'atomic-spadl' output format. "
                "Please install it with `pip install socceraction`."
            )

        def _get_period_id(event: dict[str, Any]) -> int:
            period = assertget(event, "period")
            period_id = int(assertget(period, "value"))
            return period_id

        time_start_str = assertget(json_data, "startTime")
        time_start = datetime.strptime(time_start_str, "%Y-%m-%dT%H:%M:%S")

        events_action = {}
        for attr in json_data["events"]:
            event_id = int(assertget(attr, "id" if "id" in attr else "eventId"))
            eventtype = attr.get("type", {})
            start_x = float(assertget(attr, "x"))
            start_y = float(assertget(attr, "y"))
            minute = int(assertget(attr, "expandedMinute"))
            second = int(attr.get("second", 0))
            qualifiers = {
                int(q["type"]["value"]): q.get("value", True) for q in attr.get("qualifiers", [])
            }
            end_x = attr.get("endX", _get_end_x(qualifiers))
            end_y = attr.get("endY", _get_end_y(qualifiers))
            events_action[(match_id, event_id)] = {
                # Fields required by the base schema
                "game_id": match_id,
                "event_id": event_id,
                "period_id": _get_period_id(attr),
                "team_id": int(assertget(attr, "teamId")),
                "player_id": int(attr.get("playerId")) if "playerId" in attr else None,
                "type_id": int(assertget(eventtype, "value")),
                # type_name=assertget(eventtype, "displayName"),  # added in the opta loader
                # Fields required by the opta schema
                # Timestamp is not availe in the data stream. The returned
                # timestamp  is not accurate, but sufficient for camptability
                # with the other Opta data streams.
                "timestamp": (time_start + timedelta(seconds=(minute * 60 + second))),
                "minute": minute,
                "second": second,
                "outcome": bool(attr["outcomeType"].get("value"))
                if "outcomeType" in attr
                else None,
                "start_x": start_x,
                "start_y": start_y,
                "end_x": end_x if end_x is not None else start_x,
                "end_y": end_y if end_y is not None else start_y,
                "qualifiers": qualifiers,
                # Optional fields
                "related_player_id": int(attr.get("relatedPlayerId"))
                if "relatedPlayerId" in attr
                else None,
                "touch": bool(attr.get("isTouch", False)),
                "goal": bool(attr.get("isGoal", False)),
                "shot": bool(attr.get("isShot", False)),
                # assist=bool(attr.get('assist')) if "assist" in attr else None,
                # keypass=bool(attr.get('keypass')) if "keypass" in attr else None,
            }

        df_events = (
            pd.DataFrame.from_dict(events_action, orient="index")
            .merge(_eventtypesdf, on="type_id", how="left")
            .reset_index(drop=True)
        )

        df_actions = convert_to_actions(
            df_events, home_team_id=int(json_data["home"]["teamId"])
        )

        if output_fmt == "spadl":
            events[match_id] = df_actions
        else:
            events[match_id] = convert_to_atomic(df_actions)

    df = (
        pd.concat(events.values())
        .pipe(standardize_colnames)
        .assign(
            player=lambda x: x.player_id.replace(player_names),
            team=lambda x: x.team_id.replace(team_names)  # .replace(TEAMNAME_REPLACEMENTS),
        )
    )

    if output_fmt == "events":

        from soccerdata.whoscored import COLS_EVENTS

        # add missing columns
        for col, default in COLS_EVENTS.items():
            if col not in df.columns:
                df[col] = default

        df["outcome_type"] = df["outcome_type"].apply(
            lambda x: x.get("displayName") if pd.notnull(x) else x
        )
        df["card_type"] = df["card_type"].apply(
            lambda x: x.get("displayName") if pd.notnull(x) else x
        )
        df["type"] = df["type"].apply(lambda x: x.get("displayName") if pd.notnull(x) else x)
        df["period"] = df["period"].apply(
            lambda x: x.get("displayName") if pd.notnull(x) else x
        )

        df = df[list(COLS_EVENTS.keys())]

    return df


if __name__ == "__main__":
    events = whoscored_read_event(1916923)
    events_spadl = whoscored_read_event(1916923, output_fmt="spadl")
    events_atomic = whoscored_read_event(1916923, output_fmt="atomic-spadl")

    assert events.shape == (1514, 26)
    assert events_spadl.shape == (1530, 16)
    assert events_atomic.shape == (2622, 15)
