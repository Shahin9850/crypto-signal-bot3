"""
Multi-timeframe POC + structure + FVG strategy.

4H (HTF): defines bias
  1. Find latest structure break (BOS) -> bullish or bearish bias.
  2. Approximate the POC of the breaking candle. The break is only accepted
     if POC sits in the "confirming" zone (upper zone for a bullish break,
     lower zone for a bearish break) -- exactly the filter described in the
     source strategy.
  3. The FVG created by that breaking candle (or the closest one after it)
     becomes the Point of Interest (POI) to wait for a pullback into.

15M (LTF): defines entry
  1. Wait for price to trade into the HTF POI.
  2. Inside the POI, look for a minor CHoCH in the direction of the HTF bias.
  3. Confirm with the POC of the CHoCH candle (must sit in the confirming
     zone, same logic as above).
  4. Entry = edge of the LTF FVG formed by that CHoCH (or the POI edge if no
     LTF FVG forms). Stop-loss = beyond the swing that the CHoCH broke.
     Take-profit = entry +/- RISK_REWARD * risk (fixed R:R, e.g. 1:2).
"""
from dataclasses import dataclass
from typing import Optional

import config
import data_fetcher
import fvg
import poc
import structure


@dataclass
class Bias:
    direction: str          # 'bullish' or 'bearish'
    poi_top: float
    poi_bottom: float
    break_index: int


@dataclass
class Signal:
    symbol: str
    direction: str    # 'long' or 'short'
    entry: float
    stop_loss: float
    take_profit: float


def _confirming_zone(direction: str) -> str:
    return "upper" if direction == "bullish" else "lower"


def get_htf_bias(symbol: str) -> Optional[Bias]:
    df = data_fetcher.fetch_ohlcv_df(symbol, config.HTF, limit=config.MAX_LOOKBACK_CANDLES_HTF)
    if len(df) < 2 * config.SWING_LOOKBACK + 5:
        return None

    event = structure.get_bias_from_htf(df)
    if event is None:
        return None

    i = event.index
    candle_start = df.index[i]
    candle_end = poc.get_candle_end_ts(df, config.HTF, i)
    poc_result = poc.calculate_poc_for_candle(
        symbol, candle_start, candle_end, df["high"].iloc[i], df["low"].iloc[i]
    )

    if poc_result.zone != _confirming_zone(event.direction):
        return None  # POC filter rejects this break -> no bias yet

    zone = fvg.find_fvg_after(df, i - 1, event.direction)
    if zone is None:
        return None  # no POI to trade towards

    return Bias(direction=event.direction, poi_top=zone.top, poi_bottom=zone.bottom, break_index=i)


def check_ltf_entry(symbol: str, bias: Bias) -> Optional[Signal]:
    df = data_fetcher.fetch_ohlcv_df(symbol, config.LTF, limit=config.MAX_LOOKBACK_CANDLES_LTF)
    if df.empty:
        return None

    last_price = df["close"].iloc[-1]
    price_reached_poi = bias.poi_bottom <= last_price <= bias.poi_top or (
        df["low"].tail(20).min() <= bias.poi_top and df["high"].tail(20).max() >= bias.poi_bottom
    )
    if not price_reached_poi:
        return None

    choch = structure.detect_minor_choch(df, bias.direction)
    if choch is None:
        return None

    i = choch.index
    candle_start = df.index[i]
    candle_end = poc.get_candle_end_ts(df, config.LTF, i)
    poc_result = poc.calculate_poc_for_candle(
        symbol, candle_start, candle_end, df["high"].iloc[i], df["low"].iloc[i]
    )
    if poc_result.zone != _confirming_zone(bias.direction):
        return None

    ltf_zone = fvg.find_fvg_after(df, i - 1, bias.direction)

    if bias.direction == "bullish":
        entry = ltf_zone.top if ltf_zone else df["low"].iloc[i]
        stop_loss = min(df["low"].iloc[max(0, i - config.SWING_LOOKBACK):i + 1])
        risk = entry - stop_loss
        if risk <= 0:
            return None
        take_profit = entry + config.RISK_REWARD * risk
        direction = "long"
    else:
        entry = ltf_zone.bottom if ltf_zone else df["high"].iloc[i]
        stop_loss = max(df["high"].iloc[max(0, i - config.SWING_LOOKBACK):i + 1])
        risk = stop_loss - entry
        if risk <= 0:
            return None
        take_profit = entry - config.RISK_REWARD * risk
        direction = "short"

    return Signal(symbol=symbol, direction=direction, entry=entry, stop_loss=stop_loss, take_profit=take_profit)


def find_signal_for_symbol(symbol: str) -> Optional[Signal]:
    bias = get_htf_bias(symbol)
    if bias is None:
        return None
    return check_ltf_entry(symbol, bias)
