# whoscored_light

**whoscored_light** is a lightweight Python module for quickly retrieving football match event data from [WhoScored.com](https://whoscored.com) using a provided `match_id`. The tool supports exporting data in four formats:  
- **raw**
- **event**
- **spadl**
- **atomic-spadl**

>Note: Unlike soccerdata.Whoscored.read_events(fmt="raw"), which returns only event data from the JSON response in dictionary format, output_fmt = "raw" in the whoscored_read_event function returns the full JSON response from whoscored.com with additional meta information.

Unlike the `WhoScored.read_events` method from the [soccerdata](https://github.com/voetbalai/soccerdata) library, `whoscored_light` does **not** require a game schedule or tournament configuration. This means you can get event data much faster for individual matches, especially for non-BigFive championships. Additionally, you can instantly convert and output data in `spadl` and `atomic-spadl` formats without saving intermediate JSON files to disk.

## Features

- **Fast retrieval:** Directly fetch events for a match using its `match_id`- no schedule or tournament setup required.
- **Flexible formats:** Output data in `raw`, `event`, `spadl`, or `atomic-spadl` formats for downstream analysis.
- **In-memory conversion:** Convert to SPADL and atomic-SPADL without writing or reading JSON files from disk.
- **Works for non-BigFive matches:** Useful for matches outside the major European leagues, or for one-off games.

## When to Use

- **Recommended:**  
  - You want to quickly analyze one or a few matches, especially from leagues or tournaments not covered by soccerdata's default schedule.
  - You need immediate access to event data in `spadl` or `atomic-spadl` format.

- **Not Recommended:**  
  - For production systems or bulk downloads of many matches.
  - If you require automated schedule or tournament management.

## Usage

```python
from whoscored_light import whoscored_read_event

# Example: Fetch events for a specific match_id
match_id = '1916923' # PSG - Real Madrid FIFA CLub World Cup 2025
event_data = whoscored_read_event(match_id, format='event')
match_json = whoscored_read_event(match_id, format='raw')
spadl_data = whoscored_read_event(match_id, format='spadl')
atomic_spadl_data = whoscored_read_event(match_id, format='atomic-spadl')
```

### Arguments

- `match_id` (str): The WhoScored.com match identifier (you must enter this manually).
- `format` (str): One of `raw`, `'event'`, `'spadl'`, `'atomic-spadl'`.

### Output

Returns the requested data format as a Python object (e.g., pandas DataFrame).

## Limitations

- You must manually specify the `match_id` for each match.
- Not suitable for large-scale or automated data collection tasks.
- Designed for fast, simple access - not for robust production use.

## Installation

Place the `whoscored_light` folder inside your Python project or install via pip if available.

```bash
pip install -e .
```

## License

**Apache License 2.0**

See [LICENSE](../LICENSE) for details.

## Credits

Inspired by [soccerdata](https://github.com/probberechts/soccerdata) and [socceraction](https://github.com/ML-KULeuven/socceraction).

---
For questions or contributions, please open an issue or pull request.