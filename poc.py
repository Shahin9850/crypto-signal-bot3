"""
Approximate volume-profile / Point of Control (POC) for a single higher-timeframe
candle, built from smaller ("micro") candles inside its time range.

True footprint/orderflow POC needs tick-level bid/ask data that free exchange
APIs don't expose. This is an approximation: we take every micro-candle (e.g.
1m) inside the target candle's time window, use its typical price
((high+low+close)/3) as the traded price, bucket typical prices into a fixed
number of price bins across the candle's high-low range, and sum the
micro-candle volume into each bin. The bin with the most volume is the POC.

This is good enough to answer the question the strategy actually needs:
"is most of the volume concentrated near the top, the middle, or the bottom
of this candle?" -- it is not a substitute for real footprint data.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

import config
import data_fetcher


@dataclass
class POCResult:
    poc_price: float
    zone: str  # 'upper', 'middle', 'lower'


def _classify_zone(poc_price: float, candle_high: float, candle_low: float) -> str:
    rng = candle_high - candle_low
    if rng <= 0:
        return "middle"
    pos = (poc_price - candle_low) / rng  # 0 = at low, 1 = at high
    if pos >= 1 - config.POC_ZONE_RATIO:
        return "upper"
    if pos <= config.POC_ZONE_RATIO:
        return "lower"
    return "middle"


def calculate_poc_for_candle(symbol: str, candle_start_ts, candle_end_ts,
                              candle_high: float, candle_low: float,
                              n_bins: int = 24) -> POCResult:
    """candle_start_ts / candle_end_ts: pandas Timestamps (UTC) marking the
    open/close boundary of the higher-timeframe candle being analyzed."""
    start_ms = int(candle_start_ts.timestamp() * 1000)
    end_ms = int(candle_end_ts.timestamp() * 1000)

    micro = data_fetcher.fetch_ohlcv_between(symbol, config.MICRO_TF, start_ms, end_ms)

    if micro.empty or candle_high <= candle_low:
        mid = (candle_high + candle_low) / 2
        return POCResult(poc_price=mid, zone="middle")

    typical_price = (micro["high"] + micro["low"] + micro["close"]) / 3.0
    bins = np.linspace(candle_low, candle_high, n_bins + 1)
    bin_idx = np.clip(np.digitize(typical_price, bins) - 1, 0, n_bins - 1)

    volume_per_bin = np.zeros(n_bins)
    for idx, vol in zip(bin_idx, micro["volume"].values):
        volume_per_bin[idx] += vol

    max_bin = int(np.argmax(volume_per_bin))
    poc_price = (bins[max_bin] + bins[max_bin + 1]) / 2

    return POCResult(poc_price=poc_price, zone=_classify_zone(poc_price, candle_high, candle_low))


def get_candle_end_ts(df: pd.DataFrame, timeframe: str, index: int) -> pd.Timestamp:
    """The next candle's open time == this candle's close time. For the last
    candle in the frame (still forming), fall back to now."""
    if index + 1 < len(df):
        return df.index[index + 1]
    tf_ms = data_fetcher.timeframe_to_ms(timeframe)
    return df.index[index] + pd.Timedelta(milliseconds=tf_ms)
