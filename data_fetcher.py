"""
Thin wrapper around ccxt for fetching OHLCV candles as pandas DataFrames.
Works with any ccxt-supported spot exchange (default: binance), no API key
needed for public market data.
"""
import ccxt
import pandas as pd

import config

_exchange = None


def get_exchange():
    global _exchange
    if _exchange is None:
        exchange_class = getattr(ccxt, config.EXCHANGE_ID)
        _exchange = exchange_class({"enableRateLimit": True})
    return _exchange


def fetch_ohlcv_df(symbol: str, timeframe: str, limit: int = 300, since: int = None) -> pd.DataFrame:
    """Fetch OHLCV candles and return as a DataFrame indexed by open time (UTC)."""
    ex = get_exchange()
    raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit, since=since)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    return df


def fetch_ohlcv_between(symbol: str, timeframe: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Fetch all candles of `timeframe` between start_ms and end_ms (inclusive-ish).
    Used to build an approximate volume profile for a single higher-timeframe candle
    out of many smaller candles (e.g. 1m candles inside one 4h candle)."""
    ex = get_exchange()
    all_rows = []
    since = start_ms
    # ccxt returns at most `limit` candles per call; loop until we pass end_ms
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=1000)
        if not batch:
            break
        all_rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts >= end_ms or len(batch) < 2:
            break
        since = last_ts + 1

    if not all_rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df[(df["timestamp"] >= start_ms) & (df["timestamp"] <= end_ms)]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    return df


def fetch_last_price(symbol: str) -> float:
    ex = get_exchange()
    ticker = ex.fetch_ticker(symbol)
    return float(ticker["last"])


def timeframe_to_ms(timeframe: str) -> int:
    ex = get_exchange()
    return ex.parse_timeframe(timeframe) * 1000
