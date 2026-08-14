"""
Central configuration loaded from environment variables (.env file).
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

EXCHANGE_ID = os.getenv("EXCHANGE_ID", "binance")

SYMBOLS = [s.strip() for s in os.getenv("SYMBOLS", "BTC/USDT").split(",") if s.strip()]

# --- Auto symbol discovery (scan the whole market instead of a fixed list) ---
SYMBOL_MODE = os.getenv("SYMBOL_MODE", "static")  # 'static' uses SYMBOLS above, 'auto' scans top-volume market
AUTO_QUOTE_CURRENCY = os.getenv("AUTO_QUOTE_CURRENCY", "USDT")
AUTO_TOP_N = int(os.getenv("AUTO_TOP_N", "30"))
SYMBOL_REFRESH_SECONDS = int(os.getenv("SYMBOL_REFRESH_SECONDS", "900"))  # how often to re-rank by volume
# substrings to exclude (leveraged/synthetic tokens that behave badly technically)
EXCLUDE_SYMBOL_KEYWORDS = [
    s.strip().upper() for s in os.getenv(
        "EXCLUDE_SYMBOL_KEYWORDS", "UP/,DOWN/,BULL/,BEAR/,3L/,3S/,5L/,5S/"
    ).split(",") if s.strip()
]

HTF = os.getenv("HTF", "4h")            # bias / structure timeframe
LTF = os.getenv("LTF", "15m")           # entry timeframe
MICRO_TF = os.getenv("MICRO_TF", "1m")  # used to approximate volume profile / POC

RISK_REWARD = float(os.getenv("RISK_REWARD", "2.0"))

# --- Position sizing / leverage suggestion ---
# Every signal targets a FIXED dollar profit and risks a FIXED dollar amount
# (profit = risk * RISK_REWARD, so with RISK_REWARD=2.0 a $1.5 risk always
# targets $3 profit) -- regardless of how close the stop-loss is to entry.
# Position size and leverage are derived to make that true for each signal.
FIXED_RISK_USD = float(os.getenv("FIXED_RISK_USD", "1.5"))
MARGIN_PER_TRADE_USD = float(os.getenv("MARGIN_PER_TRADE_USD", "50"))   # how much margin you put up per trade
MAX_LEVERAGE = float(os.getenv("MAX_LEVERAGE", "10"))

SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "300"))
MONITOR_INTERVAL_SECONDS = int(os.getenv("MONITOR_INTERVAL_SECONDS", "60"))

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))

DB_PATH = os.getenv("DB_PATH", "signals.db")

# --- Strategy tuning knobs ---
SWING_LOOKBACK = 3          # bars each side to confirm a swing high/low (fractal)
POC_ZONE_RATIO = 0.33       # top/bottom third of the candle counts as "near the edge"
FVG_MIN_GAP_RATIO = 0.0     # minimum gap size as ratio of candle range (0 = any gap)
MAX_LOOKBACK_CANDLES_HTF = 300
MAX_LOOKBACK_CANDLES_LTF = 500
