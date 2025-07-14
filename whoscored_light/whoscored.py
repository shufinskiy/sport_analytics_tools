import json
import io

import seleniumbase as sb
import pandas as pd


def whoscored_read_event(
        match_id: int,
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
    df_events = pd.DataFrame(game_events)
    df_events["game_id"] = match_id
    events[match_id] = df_events

    from soccerdata._common import standardize_colnames
    from soccerdata.whoscored import COLS_EVENTS

    df = (
        pd.concat(events.values())
        .pipe(standardize_colnames)
        .assign(
            player=lambda x: x.player_id.replace(player_names),
            team=lambda x: x.team_id.replace(team_names)  # .replace(TEAMNAME_REPLACEMENTS),
        )
    )

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
    df = whoscored_read_event(1916923)
    print(df.shape)
