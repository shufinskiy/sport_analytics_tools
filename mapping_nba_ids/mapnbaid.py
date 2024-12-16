from string import ascii_lowercase
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup
import numpy as np
import pandas as pd


ENGLISH = np.hstack((np.arange(65, 91),np.arange(97, 123), np.array([32, 45, 46])))

MAPPING_DICT = {
    202392: 'blakema01',
    1629129: 'bluietr01',
    1642486: 'buiebo01',
    202221: 'butchbr01',
    1642382: 'carlsbr01',
    1642269: 'cartede02',
    1642353: 'chrisca02',
    1642384: 'crawfis01',
    1642368: 'nfalyda01',
    76521: 'davisdw01',
    1642399: 'edwarje01',
    1642348: 'edwarju01',
    203543: 'favervi01',
    1642280: 'flowetr01',
    202070: 'gaffnto01',
    1641945: 'galloja01',
    1619: 'garriki01',
    2775: 'seungha01',
    202238: 'hasbrke01',
    1641747: 'holmeda01',
    1630258: 'homesca01',
    77082: 'hundlho01',
    201998: 'jerrecu01',
    1642352: 'johnske10',
    77199: 'joneswa01',
    1641752: 'klintbo01',
    1630249: 'krejcvi01',
    986: 'mannma01',
    1641970: 'pereima01',
    77510: 'mcclate01',
    1641755: 'mcculke01',
    203183: 'mitchto03',
    203502: 'mitchto02',
    1642439: 'olivaqu01',
    1629341: 'phillta01',
    1642366: 'postqu01',
    202375: 'rollema01',
    202067: 'simpsdi01',
    1630569: 'stewadj01',
    1630597: 'stewadj02',
    78302: 'taylofa01',
    1642260: 'topicni01',
    201987: 'vadenro01',
    78409: 'vaughch01',
    1630492: 'vildolu01',
    202358: 'whitete01',
    78539: 'williar01',
    1629624: 'wooteke01',
    1642385: 'cuiyo01'
}


class PlayerDataBBref(object):

    def __init__(self,
                 base_url: str="https://www.basketball-reference.com/players",
                 letters: str=ascii_lowercase,
                 verbose: bool=False) -> None:
        self.base_url = base_url
        self.letters = letters
        self.verbose = verbose
        self.bbref_players: list[dict[str: str|int]] = []

    def bbref_player_data(self) -> pd.DataFrame:
        for letter in self.letters:
            self.scrape_player_data(letter)
            if self.verbose:
                print(f"Letter: {letter} finished")
        return pd.DataFrame(self.bbref_players)

    def scrape_player_data(self, letter: str) -> None:
        url = f"{self.base_url}/{letter}/"
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'lxml')
        table = soup.find('table', {'id': 'players'})
        if table:
            rows = table.find('tbody').find_all('tr')

            if len(rows) != 0:
                for row in rows:
                    player_name = row.find('th').get_text()
                    player_url = row.find('th').find('a')['href'] if row.find('th').find('a') else None
                    from_year = row.find("td", {"data-stat": "year_min"}).get_text() if row.find("td", {"data-stat": "year_min"}) else None
                    to_year = row.find("td", {"data-stat": "year_max"}).get_text() if row.find("td", {"data-stat": "year_max"}) else None

                    self.bbref_players.append({
                        'name': player_name.replace("*", ""),
                        'url': f"https://www.basketball-reference.com{player_url}" if player_url else None,
                        'bbref_id': Path(player_url).stem if player_url else None,
                        'from_year': int(from_year) - 1,
                        'to_year': int(to_year) - 1
                })
        else:
            raise ValueError(f"On page {url} there is no information about the players")


class MergePlayerID(object):

    def __init__(self,
                 nbastats: pd.DataFrame,
                 bbref: pd.DataFrame) -> None:
        self.nbastats = (
            nbastats
            .assign(FIRST_LETTER = lambda df_: [x[:1].lower() for x in df_.DISPLAY_LAST_COMMA_FIRST])
        )
        self.bbref = bbref
        self.zero_df: Optional[pd.DataFrame] = None
        self.double_df: Optional[pd.DataFrame] = None
        self.non_merge_bbref: Optional[pd.DataFrame] = None
        self.non_merge_nbastats: Optional[pd.DataFrame] = None
        self.full_coincidence_df: Optional[pd.DataFrame] = None

    def merge_by_name(self) -> pd.DataFrame:
        merge_index = []
        zero_index = []
        double_index = []
        for idx, nba_name in enumerate(self.nbastats.loc[:, "DISPLAY_FIRST_LAST"]):
            tmp_df = self.bbref.loc[self.bbref["name"] == nba_name]
            if tmp_df.shape[0] == 1:
                merge_index.append(idx)
            elif tmp_df.shape[0] == 0:
                zero_index.append(idx)
            elif tmp_df.shape[0] > 1:
                double_index.append(idx)
            else:
                raise ValueError("Error")

        self.zero_df = self.nbastats.iloc[zero_index].reset_index(drop=True)
        self.double_df = self.nbastats.iloc[double_index].reset_index(drop=True)

        merge_df = (
            self.nbastats
            .iloc[merge_index]
            .reset_index(drop=True)
            .pipe(lambda df_: df_.loc[:, ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR"]])
            .pipe(lambda df_: df_.merge(self.bbref, how="inner", left_on="DISPLAY_FIRST_LAST", right_on="name"))
        )

        self.upd_non_merge(merge_df)

        return merge_df

    def upd_non_merge(self, merge_df: pd.DataFrame) -> None:
        merge_bbref_id = merge_df.bbref_id
        merge_person_id = merge_df.PERSON_ID

        if self.non_merge_bbref is not None:
            self.non_merge_bbref = self.non_merge_bbref[~self.non_merge_bbref.bbref_id.isin(merge_bbref_id)].reset_index(drop=True)
        else:
            self.non_merge_bbref = self.bbref.loc[~self.bbref.bbref_id.isin(merge_bbref_id)].reset_index(drop=True)

        if self.non_merge_nbastats is not None:
            self.non_merge_nbastats = self.non_merge_nbastats[~self.non_merge_nbastats.PERSON_ID.isin(merge_person_id)].reset_index(drop=True)
        else:
            self.non_merge_nbastats = self.nbastats.loc[~self.nbastats.PERSON_ID.isin(merge_person_id)].reset_index(drop=True)
