import json
from typing import IO

import pandas as pd

from brasa.engine import CacheManager, CacheMetadata, MarketDataReader
from brasa.parsers.b3.bvbg028 import BVBG028Parser
from brasa.parsers.b3.bvbg086 import BVBG086Parser
from brasa.parsers.b3.cdi import CDIParser
from brasa.parsers.b3.cotahist import COTAHISTParser
from brasa.parsers.b3.futures_settlement_prices import future_settlement_prices_parser


def read_json(reader: MarketDataReader, fname: IO | str) -> pd.DataFrame:
    if isinstance(fname, str):
        with open(fname, "r", encoding=reader.encoding) as f:
            data = json.load(f)
    else:
        data = json.load(fname)
    return pd.DataFrame(data, index=[0], columns=reader.fields.names)


def read_csv(reader: MarketDataReader, fname: IO | str) -> pd.DataFrame:
    converters = {n:str for n in reader.fields.names}
    return pd.read_csv(fname,
                       encoding=reader.encoding,
                       header=None,
                       skiprows=reader.skip,
                       sep=reader.separator,
                       converters=converters,
                       names=reader.fields.names,)


def read_b3_cotahist(meta: CacheMetadata) -> pd.DataFrame:
    fname = meta.downloaded_files[0]
    man = CacheManager()
    parser = COTAHISTParser(man.cache_path(fname))
    return parser._data._tables["data"]


def read_b3_bvbg028(meta: CacheMetadata) -> dict[str, pd.DataFrame]:
    paths = meta.downloaded_files
    paths.sort()
    fname = paths[-1]
    man = CacheManager()
    parser = BVBG028Parser(man.cache_path(fname))
    return parser.data


def read_b3_bvbg086(meta: CacheMetadata) -> pd.DataFrame:
    paths = meta.downloaded_files
    paths.sort()
    fname = paths[-1]
    man = CacheManager()
    parser = BVBG086Parser(man.cache_path(fname))
    df = parser.data
    df["refdate"] = pd.to_datetime(df["refdate"])
    df["creation_date"] = pd.to_datetime(df["creation_date"])
    df["security_id"] = pd.to_numeric(df["security_id"])
    df["security_proprietary"] = pd.to_numeric(df["security_proprietary"])
    df["open_interest"] = pd.to_numeric(df["open_interest"])
    df["trade_quantity"] = pd.to_numeric(df["trade_quantity"])
    df["volume"] = pd.to_numeric(df["volume"])
    df["traded_contracts"] = pd.to_numeric(df["traded_contracts"])
    df["best_ask_price"] = pd.to_numeric(df["best_ask_price"])
    df["best_bid_price"] = pd.to_numeric(df["best_bid_price"])
    df["open"] = pd.to_numeric(df["open"])
    df["low"] = pd.to_numeric(df["low"])
    df["high"] = pd.to_numeric(df["high"])
    df["average"] = pd.to_numeric(df["average"])
    df["close"] = pd.to_numeric(df["close"])
    df["regular_transactions_quantity"] = pd.to_numeric(df["regular_transactions_quantity"])
    df["regular_traded_contracts"] = pd.to_numeric(df["regular_traded_contracts"])
    df["regular_volume"] = pd.to_numeric(df["regular_volume"])
    df["oscillation_percentage"] = pd.to_numeric(df["oscillation_percentage"])
    df["adjusted_quote"] = pd.to_numeric(df["adjusted_quote"])
    df["adjusted_tax"] = pd.to_numeric(df["adjusted_tax"])
    df["previous_adjusted_quote"] = pd.to_numeric(df["previous_adjusted_quote"])
    df["previous_adjusted_tax"] = pd.to_numeric(df["previous_adjusted_tax"])
    df["variation_points"] = pd.to_numeric(df["variation_points"])
    df["adjusted_value_contract"] = pd.to_numeric(df["adjusted_value_contract"])
    df["nonregular_transactions_quantity"] = pd.to_numeric(df["nonregular_transactions_quantity"])
    df["nonregular_traded_contracts"] = pd.to_numeric(df["nonregular_traded_contracts"])
    df["nonregular_volume"] = pd.to_numeric(df["nonregular_volume"])

    return parser.data


def read_b3_cdi(meta: CacheMetadata) -> pd.DataFrame:
    man = CacheManager()
    parser = CDIParser(man.cache_path(meta.downloaded_files[0]))
    return parser.data


def read_b3_futures_settlement_prices(meta: CacheMetadata) -> pd.DataFrame:
    fname = meta.downloaded_files[0]
    man = CacheManager()
    df = future_settlement_prices_parser(man.cache_path(fname))
    return df