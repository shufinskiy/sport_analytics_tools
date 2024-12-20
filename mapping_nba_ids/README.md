# NBA Player ID Mapping Tool 🏀

A Python tool for mapping player IDs between NBA Stats API and Basketball Reference. This tool helps solve the common challenge of matching player data across different basketball data sources.

## Why This Tool? 🤔

When working with basketball data, analysts often need to combine data from multiple sources. Two of the most popular sources are:
- NBA Stats API (official NBA statistics)
- Basketball Reference (comprehensive historical data)

However, these sources use different ID systems for players, making it difficult to merge data. This tool creates a mapping between these IDs, allowing for seamless data integration.

## How It Works 🛠️

The tool uses a multi-step matching algorithm to ensure the highest possible accuracy:

1. **Exact Name Matching** 📋
   - First attempts to match players by their exact names
   - Separates cases with no matches and multiple matches for further processing

2. **Multiple Match Resolution** 🔄
   - For players with multiple potential matches, uses additional criteria like active years
   - Creates separate handling for special cases

3. **Non-English Character Handling** 🌐
   - Processes names containing non-English characters
   - Attempts various transliterations to find matches

4. **Surname-Based Matching** 👥
   - Matches players using surnames when full names don't match
   - Includes additional verification using career years

5. **Fuzzy Matching** 🔍
   - Removes punctuation and special characters
   - Uses Levenshtein distance for approximate string matching

6. **Manual Dictionary Mapping** 📘
   - Falls back to a pre-defined mapping for special cases
   - Handles edge cases that automated matching can't resolve

## Usage 💻

```python
from mapping_nba_ids import mapping_nba_id

# Basic usage with default parameters
mapped_players = mapping_nba_id()

# Advanced usage with custom parameters
mapped_players = mapping_nba_id(
    verbose=True,  # Print progress information
    letters='abcde',  # Only process players whose names start with these letters
    base_url='https://www.basketball-reference.com/players'  # Custom base URL
)
```

## Requirements 📦

### Python Version
- Python 3.8 or higher

### Required Libraries
```txt
nba_api>=1.4.0
numpy>=1.22.2,<2.0.0
pandas>=2.0.0
Levenshtein==0.26.1
beautifulsoup4>=4.10.0
requests>=2.31.0
lxml>=5.2.0
```

## Output 📊
The tool returns a pandas DataFrame containing:

- NBA Stats API Player ID
- Player Name
- Basketball Reference ID
- Basketball Reference URL

**ID mapping table is located in mapping_nba_ids.csv file and will be updated periodically. You can run the code locally or just download this file.**
  
## Contributing 🤝
Contributions are welcome! Here's how you can help:

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Author ✍️
shufinskiy - [GitHub Profile](https://github.com/shufinskiy)

- 📫 How to reach me: Create an issue in this repository
- 🌟 If you find this tool useful, please consider giving it a star!

