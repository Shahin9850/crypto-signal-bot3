"""
Fair Value Gap (FVG) / imbalance detection using the classic 3-candle pattern:

Bullish FVG at candle i (needs i-1, i, i+1):
    low[i+1] > high[i-1]   -> gap between candle i-1's high and candle i+1's low
Bearish FVG at candle i:
    high[i+1] < low[i-1]

The gap zone is [high[i-1], low[i+1]] for bullish, [high[i+1], low[i-1]] for bearish.
"""
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

import config


@dataclass
class FVGZone:
    direction: str   # 'bullish' or 'bearish'
    index: int         # index of the middle candle (i)
    top: float
    bottom: float


def find_fvgs(df: pd.DataFrame) -> List[FVGZone]:
    zones = []
    highs = df["high"].values
    lows = df["low"].values

    for i in range(1, len(df) - 1):
        prev_high, prev_low = highs[i - 1], lows[i - 1]
        next_high, next_low = highs[i + 1], lows[i + 1]

        if next_low > prev_high:
            gap = next_low - prev_high
            if gap >= config.FVG_MIN_GAP_RATIO * (highs[i] - lows[i] + 1e-9):
                zones.append(FVGZone(direction="bullish", index=i, top=next_low, bottom=prev_high))

        if next_high < prev_low:
            gap = prev_low - next_high
            if gap >= config.FVG_MIN_GAP_RATIO * (highs[i] - lows[i] + 1e-9):
                zones.append(FVGZone(direction="bearish", index=i, top=prev_low, bottom=next_high))

    return zones


def find_fvg_after(df: pd.DataFrame, after_index: int, direction: str) -> Optional[FVGZone]:
    """First FVG of the given direction formed at or after `after_index`."""
    for zone in find_fvgs(df):
        if zone.index >= after_index and zone.direction == direction:
            return zone
    return None


def price_in_zone(price: float, zone: FVGZone) -> bool:
    return zone.bottom <= price <= zone.top
