<p align="center">
  <img src="https://github.com/shufinskiy/sport_analytics_tools/blob/main/sat_logo.jpeg"/>
</p>

<h1 align="center">Sport Analytics Tools</h1>

**Sport Analytics Tools** is a project dedicated to publishing information (code, tutorials, media) to help data scientists and sports enthusiasts work with sports data effectively.

## Motivation

- I believe that open-source solutions are superior to proprietary technologies.  
- I believe that if you've solved a problem or possess valuable knowledge, you should share it.  

## Objective

The goal of this project is to assist people interested in sports data science in tackling data analysis tasks. 

- I've developed **nba_data**, a repository of NBA data that can be accessed in seconds instead of hours via the NBA API.  
- I am the author of the **nba-on-court** library, which simplifies working with NBA data.  
- I am a contributor to well-known sports libraries such as **nba_api**, **hoopR**, and **worldfootballR**.  

Through this project, I aim to create a comprehensive knowledge base of tools and resources to enhance the workflow with sports data.

## Project Table

|Name|Description|
|------|---------|
|[NBA Player ID Mapping Tool](https://github.com/shufinskiy/sport_analytics_tools/tree/main/mapping_nba_ids)| Code automating the process of mapping ID from the NBA website and basketball-reference|
|[whoscored_light](https://github.com/shufinskiy/sport_analytics_tools/tree/main/whoscored_light)| A lightweight Python module for quickly retrieving football match event data from [WhoScored.com](https://whoscored.com) using a provided `match_id`.|

## List of Projects

### 1. NBA Player ID Mapping Tool 🏀
Tool for mapping player IDs between NBA Stats API and Basketball Reference.

#### Features
- Automated ID mapping between different basketball data sources
- Multiple matching algorithms for high accuracy
- Handles special cases and non-English names
- Easy-to-use Python interface

#### Requirements
- Python 3.8+
- Core dependencies: beautifulsoup4, numpy, pandas, requests, nba_api, python-Levenshtein

[Learn more about NBA Player ID Mapping Tool →](https://github.com/shufinskiy/sport_analytics_tools/tree/main/mapping_nba_ids)

### 2. whoscored_light ⚽️
A lightweight Python module for quickly retrieving football match event data from [WhoScored.com](https://whoscored.com) using a provided `match_id`. Supports direct export to multiple formats:
- `event`
- `spadl`
- `atomic-spadl`

#### Features
- Fast, direct event retrieval by `match_id` (no schedule/tournament setup needed)
- Outputs in multiple formats for downstream analysis
- In-memory conversion to SPADL/atomic-SPADL (no disk I/O)
- Works for matches outside major European leagues and one-off games

#### When to Use
- Quick analysis of individual matches (especially outside Big Five leagues)
- Immediate access to event data in SPADL/atomic-SPADL formats

#### Limitations
- Manual entry of `match_id` required
- Not intended for bulk downloads or production systems

[Learn more about whoscored_light →](https://github.com/shufinskiy/sport_analytics_tools/tree/main/whoscored_light)

## Installation

```bash
# Clone the repository
git clone https://github.com/shufinskiy/sport_analytics_tools.git
cd sport_analytics_tools

```

## Contributing 🤝
Contributions are welcome! Please feel free to submit pull requests, particularly for:

- Adding new tools for sports analytics
- Improving existing functionality
- Adding documentation and tutorials
- Bug fixes and optimizations

## License 📄
Apache License 2.0

## Contact 📫

<div id="header" align="center">
  <div id="badges">
    <a href="https://www.linkedin.com/in/vladislav-shufinskiy/">
      <img src="https://img.shields.io/badge/LinkedIn-blue?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn Badge"/>
    </a>
    <a href="https://t.me/brains14482">
      <img src="https://img.shields.io/badge/Telegram-blue?style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram Badge"/>
    </a>
    <a href="https://twitter.com/vshufinskiy">
      <img src="https://img.shields.io/badge/Twitter-blue?style=for-the-badge&logo=twitter&logoColor=white" alt="Twitter Badge"/>
    </a>
  </div>
</div>
