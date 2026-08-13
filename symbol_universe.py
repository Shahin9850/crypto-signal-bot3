"""
Discovers which symbols to scan when SYMBOL_MODE=auto: instead of a fixed
list, pull every spot market quoted in AUTO_QUOTE_CURRENCY (e.g. all
X/USDT pairs) from the exchange, rank by 24h quote volume, drop leveraged /
synthetic tokens, and keep the top AUTO_TOP_N. This is re-run every
SYMBOL_REFRESH_SECONDS so the watch-list tracks where the market's volume
actually is instead of a hardcoded list going stale.

Practical note: scanning literally every listed pair (often 500+) on every
cycle would blow through exchange rate limits very fast, especially since
the strategy fetches 1-minute candles per HTF/LTF candle for the POC
approximation. Restricting to the top-N by volume is the practical way to
"watch the whole market" without getting rate-limited or banned.
"""
import logging

import config
import data_fetcher

logger = logging.getLogger(__name__)


def _is_excluded(symbol: str) -> bool:
    upper = symbol.upper()
    return any(keyword in upper for keyword in config.EXCLUDE_SYMBOL_KEYWORDS)


def get_top_symbols(quote: str = None, top_n: int = None) -> list:
    """Return up to `top_n` symbols quoted in `quote`, sorted by 24h quote
    volume descending, excluding leveraged/synthetic tokens."""
    quote = quote or config.AUTO_QUOTE_CURRENCY
    top_n = top_n or config.AUTO_TOP_N

    ex = data_fetcher.get_exchange()
    markets = ex.load_markets()

    candidates = [
        symbol for symbol, m in markets.items()
        if m.get("quote") == quote
        and m.get("spot", True)
        and m.get("active", True)
        and not _is_excluded(symbol)
    ]

    if not candidates:
        logger.warning("No active spot markets found for quote currency %s", quote)
        return []

    try:
        tickers = ex.fetch_tickers(candidates)
    except Exception:
        logger.exception("fetch_tickers failed, falling back to per-symbol fetch skipped; returning unranked list")
        return candidates[:top_n]

    ranked = sorted(
        candidates,
        key=lambda s: (tickers.get(s, {}) or {}).get("quoteVolume") or 0,
        reverse=True,
    )

    top = ranked[:top_n]
    logger.info("Auto symbol discovery: %d/%d %s markets kept (top by volume)", len(top), len(candidates), quote)
    return top
