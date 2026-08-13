"""
Basic price-action market structure tools:
  - swing highs/lows (fractal pivots)
  - Break of Structure (BOS): a close beyond the last swing point in the
    direction of the prevailing trend -> trend continuation / confirmation
  - Change of Character (CHoCH): a close beyond the last swing point AGAINST
    the prevailing trend -> possible reversal (used here as the minor entry
    trigger on the lower timeframe)
"""
from dataclasses import dataclass
from typing import Optional

import pandas as pd

import config


@dataclass
class StructureEvent:
    kind: str          # 'BOS' or 'CHoCH'
    direction: str      # 'bullish' or 'bearish'
    index: int           # integer position in the dataframe of the breaking candle
    broken_level: float


def find_swing_points(df: pd.DataFrame, lookback: int = None):
    """Return two boolean Series (swing_high, swing_low) marking fractal pivots:
    a bar whose high is the highest of `lookback` bars on each side is a swing
    high; symmetric for swing lows."""
    lookback = lookback or config.SWING_LOOKBACK
    highs = df["high"]
    lows = df["low"]

    swing_high = pd.Series(False, index=df.index)
    swing_low = pd.Series(False, index=df.index)

    for i in range(lookback, len(df) - lookback):
        window_high = highs.iloc[i - lookback: i + lookback + 1]
        window_low = lows.iloc[i - lookback: i + lookback + 1]
        if highs.iloc[i] == window_high.max():
            swing_high.iloc[i] = True
        if lows.iloc[i] == window_low.min():
            swing_low.iloc[i] = True

    return swing_high, swing_low


def _last_swing_before(series_bool: pd.Series, values: pd.Series, before_index: int) -> Optional[tuple]:
    for i in range(before_index - 1, -1, -1):
        if series_bool.iloc[i]:
            return i, values.iloc[i]
    return None


def detect_latest_structure_break(df: pd.DataFrame, lookback: int = None) -> Optional[StructureEvent]:
    """Scan forward through the dataframe and return the most recent moment
    where price closed beyond the prior confirmed swing high (bullish break)
    or swing low (bearish break). Does not yet label BOS vs CHoCH -- that
    requires knowing the prevailing trend, done by the caller."""
    swing_high, swing_low = find_swing_points(df, lookback)

    last_event = None
    for i in range(len(df)):
        prior_high = _last_swing_before(swing_high, df["high"], i)
        prior_low = _last_swing_before(swing_low, df["low"], i)

        close = df["close"].iloc[i]

        if prior_high and close > prior_high[1]:
            last_event = StructureEvent(kind="BREAK", direction="bullish", index=i, broken_level=prior_high[1])
        if prior_low and close < prior_low[1]:
            last_event = StructureEvent(kind="BREAK", direction="bearish", index=i, broken_level=prior_low[1])

    return last_event


def get_bias_from_htf(df: pd.DataFrame, lookback: int = None) -> Optional[StructureEvent]:
    """Simple bias definition: the direction of the most recent structure
    break on the higher timeframe. Labelled as BOS since on the HTF we treat
    it as the trend-defining event."""
    event = detect_latest_structure_break(df, lookback)
    if event:
        event.kind = "BOS"
    return event


def detect_minor_choch(df: pd.DataFrame, bias_direction: str, lookback: int = None) -> Optional[StructureEvent]:
    """On the lower timeframe, look for the most recent break that goes
    AGAINST the immediately preceding minor trend but back IN the direction
    of `bias_direction`. In practice: the latest structure break in the
    dataframe, only accepted if it matches bias_direction."""
    event = detect_latest_structure_break(df, lookback)
    if event and event.direction == bias_direction:
        event.kind = "CHoCH"
        return event
    return None
