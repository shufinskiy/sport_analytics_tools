from string import ascii_lowercase
from pathlib import Path
from typing import Optional
from itertools import product

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

    def merge_double(self, merge_df: pd.DataFrame) -> pd.DataFrame:
        merge_double = (
            self.double_df
            .pipe(lambda df_: df_.loc[:, ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR"]])
            .astype({'FROM_YEAR': 'int', 'TO_YEAR': 'int'})
            .pipe(lambda df_: df_.merge(self.non_merge_bbref,
                                        how="left",
                                        left_on=["DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR"],
                                        right_on=["name", "from_year", "to_year"]
                                        ))
        )

        non_match = merge_double.loc[pd.isna(merge_double.name), ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR"]]
        self.full_coincidence_df = (
            merge_double
            .pipe(lambda df_: df_.merge((
                df_
                .groupby(["PERSON_ID"], as_index=False)["TO_YEAR"]
                .count()
                .pipe(lambda df_: df_.loc[df_.TO_YEAR > 1, "PERSON_ID"])
            ), how="inner", on="PERSON_ID"))
            .loc[:, ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR"]]
            .drop_duplicates()
            .reset_index(drop=True)
        )

        non_ids = non_match.PERSON_ID.to_list() + self.full_coincidence_df.PERSON_ID.to_list()

        merge_df = pd.concat([merge_df, merge_double.loc[~merge_double.PERSON_ID.isin(non_ids)]],
                             axis=0, ignore_index=True)
        self.upd_non_merge(merge_df)

        merge_non_match = non_match.merge(self.non_merge_bbref, how="left", left_on="DISPLAY_FIRST_LAST", right_on="name")
        merge_df = pd.concat([merge_df, merge_non_match], axis=0, ignore_index=True)

        self.upd_non_merge(merge_df)

        return merge_df

    def merge_non_english(self, merge_df: pd.DataFrame) -> pd.DataFrame:
        non_eng_idx = np.array([self._detect_non_english(x) for x in self.non_merge_bbref.name])
        non_eng = self.non_merge_bbref.iloc[non_eng_idx].reset_index(drop=True)
        non_eng["non_english_count"] = [self._count_non_english(x) for x in non_eng.name]
        non_eng["name_lower"] = [x.lower() for x in non_eng["name"]]

        check_non_eng = (
            self.non_merge_nbastats
            .pipe(lambda df_: df_.merge(non_eng, how="inner", left_on="DISPLAY_FIRST_LAST", right_on="name"))
            .loc[:, ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR",
                     "name", "url", "bbref_id", "from_year", "to_year"]]
        )

        if check_non_eng.shape[0] != 0:
            merge_df = pd.concat([merge_df, check_non_eng], axis=0, ignore_index=True)
            self.upd_non_merge(merge_df)

        transform_nbastats = (
            self.non_merge_nbastats
            .assign(
                name_lower=lambda df_: [x.lower() for x in df_.DISPLAY_FIRST_LAST],
            )
            .loc[:, ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR", "name_lower"]]
        )

        cnt_sym = np.sort(np.unique(non_eng.non_english_count))
        prod_dict = {key: list(product(*[list(ascii_lowercase) for _ in range(key)])) for key in cnt_sym}
        eng = np.hstack((np.arange(65, 91), np.arange(97, 123), np.array([32, 45, 46])))

        for i, row in enumerate(non_eng.itertuples()):
            n = np.array([ord(x) in eng for x in row.name_lower])
            if row.non_english_count == 1:
                replace_idx = np.where(n == False)[0]
            else:
                replace_idx = np.where(n == False)[0]
            for sym_cand in prod_dict[row.non_english_count]:
                name_ = list(row.name_lower)
                for pos in range(len(sym_cand)):
                    name_[replace_idx[pos]] = sym_cand[pos]
                    new_name = "".join(name_)
                check_idx = transform_nbastats.loc[transform_nbastats["name_lower"] == new_name].index
                if len(check_idx) == 0:
                    continue
                else:
                    non_eng.iloc[i, 6] = new_name
                    break

        merge_non_eng = (
            non_eng
            .pipe(lambda df_: df_.merge(transform_nbastats, how="inner", on="name_lower"))
            .loc[:, ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR",
                     "name", "url", "bbref_id", "from_year", "to_year"]]
        )
        merge_df = pd.concat([merge_df, merge_non_eng], axis=0, ignore_index=True)
        self.upd_non_merge(merge_df)

        return merge_df

    def merge_surname(self, merge_df: pd.DataFrame) -> pd.DataFrame:
        nbastats_surname = set(
            self.non_merge_nbastats
            .assign(
                CNT_PART = lambda df_: [len(x.split()) for x in df_.DISPLAY_FIRST_LAST],
                SURNAME=lambda df_: [x.split()[1] if y > 1 else None for x, y in zip(df_.DISPLAY_FIRST_LAST, df_.CNT_PART)]
            )
            .groupby("SURNAME", as_index=False)["PERSON_ID"].count()
            .pipe(lambda df_: df_.loc[df_.PERSON_ID == 1])
            .reset_index(drop=True)
            .iloc[:, 0]
            .to_list()
        )

        bbref_surname = (
            self.non_merge_bbref
            .assign(SURNAME=lambda df_: [x.split()[1] for x in df_.name])
            .groupby("SURNAME", as_index=False)["bbref_id"].count()
            .pipe(lambda df_: df_.loc[df_.bbref_id == 1])
            .reset_index(drop=True)
            .iloc[:, 0]
            .to_list()
        )
        surname_set = nbastats_surname.intersection(bbref_surname)

        comp_surname = (
            self.non_merge_nbastats
            .assign(SURNAME=lambda df_: [x.split()[1] for x in df_.DISPLAY_FIRST_LAST])
            .pipe(lambda df_: df_.loc[df_.SURNAME.isin(surname_set)])
            .reset_index(drop=True)
            .pipe(lambda df_: df_.merge(
                (
                    self.non_merge_bbref
                    .assign(SURNAME=lambda df_: [x.split()[1] for x in df_.name])
                    .pipe(lambda df_: df_.loc[df_.SURNAME.isin(surname_set)])
                    .reset_index(drop=True)
                ),
                how="inner",
                on="SURNAME"
            ))
            .pipe(lambda df_: df_.loc[:, ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR",
                                          "name", "url", "bbref_id", "from_year", "to_year"]])
        )

        merge_df = pd.concat([merge_df, comp_surname], axis=0, ignore_index=True)

        self.upd_non_merge(merge_df)

        nbastats_surname_year = (
            self.non_merge_nbastats
            .assign(
                CNT_PART = lambda df_: [len(x.split()) for x in df_.DISPLAY_FIRST_LAST],
                SURNAME=lambda df_: [x.split()[1] if y > 1 else None for x, y in zip(df_.DISPLAY_FIRST_LAST, df_.CNT_PART)]
            )
            .drop(columns="CNT_PART")
        )

        bbref_surname_year = (
            self.non_merge_bbref
            .assign(
                CNT_PART=lambda df_: [len(x.split()) for x in df_.name],
                SURNAME=lambda df_: [x.split()[1] if y > 1 else None for x, y in
                                     zip(df_.name, df_.CNT_PART)]
            )
            .drop(columns="CNT_PART")
        )

        comp_surname_year = (
            nbastats_surname_year
            .astype({'FROM_YEAR': 'int', 'TO_YEAR': 'int'})
            .pipe(lambda df_: df_.merge(
                bbref_surname_year,
                how="inner",
                left_on=["SURNAME", "FROM_YEAR", "TO_YEAR"],
                right_on=["SURNAME", "from_year", "to_year"]
            ))
            .pipe(lambda df_: df_.loc[~df_.PERSON_ID.isin([203183, 203502]),
            ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR",
             "name", "url", "bbref_id", "from_year", "to_year"]])
            .reset_index(drop=True)
        )

        merge_df = pd.concat([merge_df, comp_surname_year], axis=0, ignore_index=True)

        self.upd_non_merge(merge_df)

        return merge_df

    def merge_wo_punctuation(self, merge_df: pd.DataFrame) -> pd.DataFrame:
        nba_letters = (
            self.non_merge_nbastats
            .assign(
                ONLY_LETTER=lambda df_: [re.sub(r'[^a-zA-Z]', "", re.sub(" I$| II$| III$| IV$| V$", "", x)).lower() for
                                         x in df_.DISPLAY_FIRST_LAST])
        )

        bbref_letters = (
            self.non_merge_bbref
            .assign(only_letter=lambda df_: [re.sub(r'[^a-zA-Z]', '', x).lower() for x in df_.name])
        )

        comp_letter = (
            nba_letters
            .pipe(lambda df_: df_.loc[:, ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR", "ONLY_LETTER"]])
            .pipe(lambda df_: df_.merge(bbref_letters, how="inner", left_on="ONLY_LETTER", right_on="only_letter"))
            .pipe(lambda df_: df_.loc[~df_["PERSON_ID"].isin([203183, 203502])])
            .reset_index(drop=True)
        )

        merge_df = pd.concat([merge_df, comp_letter.drop(columns=["ONLY_LETTER", "only_letter"])], axis=0, ignore_index=True)

        self.upd_non_merge(merge_df)

        bbref_letters = (
            bbref_letters
            .pipe(lambda df_: df_.loc[~df_.bbref_id.isin(comp_letter.bbref_id)])
            .reset_index(drop=True)
        )

        nba_letters = (
            nba_letters
            .pipe(lambda df_: df_.loc[~df_.PERSON_ID.isin(comp_letter.PERSON_ID)])
            .reset_index(drop=True)
        )

        list_nba_names = nba_letters.ONLY_LETTER.to_list()
        list_bbref_names = bbref_letters.only_letter.to_list()

        best = []
        idx_best = []
        for player in list_nba_names:
            min_dist = 10000
            second_min_dist = 10000
            idx = 0
            for idx_comp, player_comp in enumerate(list_bbref_names):
                dist = distance(player, player_comp)
                if dist <= min_dist:
                    min_dist = dist
                    idx = idx_comp
                elif dist < second_min_dist:
                    second_min_dist = dist
                else:
                    pass
            best.append(min_dist)
            idx_best.append(idx)

        comp_lev = (
            nba_letters
            .pipe(lambda df_: df_.loc[:, ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR", "ONLY_LETTER"]])
            .assign(
                LEN_LETTER=lambda df_: [len(x) for x in df_.ONLY_LETTER],
                BEST_LEV=best,
                BEST_IDX=idx_best
            )
            .pipe(lambda df_: df_.loc[(df_.BEST_LEV <= 2) & (~df_.PERSON_ID.isin([203183, 203502])),
            ["PERSON_ID", "DISPLAY_FIRST_LAST",
             "FROM_YEAR", "TO_YEAR", "BEST_IDX"]])
            .reset_index(drop=True)
            .pipe(lambda df_: df_.merge(
                bbref_letters.assign(IDX=lambda df_: df_.index),
                how="inner",
                left_on="BEST_IDX", right_on="IDX"
            ))
            .drop(columns=["BEST_IDX", "only_letter", "IDX"])
        )

        merge_df = pd.concat([merge_df, comp_lev], axis=0, ignore_index=True)

        self.upd_non_merge(merge_df)

        return merge_df

    def merge_from_dict(self, merge_df: pd.DataFrame) -> pd.DataFrame:

        comp_dict = (
            self.non_merge_nbastats
            .assign(bbref_id = lambda df_: [self._mapping_dict(x) for x in df_.PERSON_ID])
            .pipe(lambda df_: df_.merge(self.non_merge_bbref, how="left", on="bbref_id"))
            .pipe(lambda df_: df_.loc[:, ["PERSON_ID", "DISPLAY_FIRST_LAST", "FROM_YEAR", "TO_YEAR", "name", "url",
                                          "bbref_id", "from_year", "to_year"]])
            .assign(
                url=lambda df_: [
                    "/".join(["https://www.basketball-reference.com/players", x[0], x + ".html"])
                    if isinstance(x, str) else None
                    for x in df_.bbref_id
                ]
            )
        )

        merge_df = pd.concat([merge_df, comp_dict], axis=0, ignore_index=True)

        self.upd_non_merge(merge_df)

        return merge_df.drop(columns=["FROM_YEAR", "TO_YEAR", "from_year", "to_year"])

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

    @staticmethod
    def _detect_non_english(names: str) -> bool:
        ord_name = not all([ord(x) in ENGLISH for x in names])
        return ord_name

    @staticmethod
    def _count_non_english(names: str) -> int:
        return np.sum([ord(x) not in ENGLISH for x in names])
