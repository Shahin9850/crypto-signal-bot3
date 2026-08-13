"""
Orchestrates the whole pipeline:
  - scan_for_signals(): run the strategy on every configured symbol, store
    and send any new signal, and trigger a batch report every BATCH_SIZE
    signals.
  - monitor_open_signals(): check current price of every open signal against
    its TP/SL and close it out when hit.
  - build_status_report(): full-history stats used by the "وضعیت" command.
"""
import logging

import config
import data_fetcher
import database
import strategy

logger = logging.getLogger(__name__)


def format_signal_message(signal: strategy.Signal) -> str:
    arrow = "🟢 LONG" if signal.direction == "long" else "🔴 SHORT"
    return (
        f"{arrow}  |  {signal.symbol}\n\n"
        f"Entry: {signal.entry:.6g}\n"
        f"Stop Loss: {signal.stop_loss:.6g}\n"
        f"Take Profit: {signal.take_profit:.6g}\n"
        f"R:R = 1:{config.RISK_REWARD:g}\n\n"
        f"HTF bias: {config.HTF} | Entry TF: {config.LTF}"
    )


def format_batch_message(rows, batch_number: int) -> str:
    tp = sum(1 for r in rows if r["status"] == "tp")
    sl = sum(1 for r in rows if r["status"] == "sl")
    pending = sum(1 for r in rows if r["status"] == "open")
    total = len(rows)
    return (
        f"📊 گزارش دسته سیگنال شماره {batch_number} (آخرین {total} سیگنال)\n\n"
        f"✅ تیک‌پرافیت خورده: {tp}\n"
        f"❌ استاپ خورده: {sl}\n"
        f"⏳ هنوز باز: {pending}"
    )


def format_status_message() -> str:
    rows = database.get_all_signals()
    total = len(rows)
    if total == 0:
        return "هنوز هیچ سیگنالی ارسال نشده."

    tp = sum(1 for r in rows if r["status"] == "tp")
    sl = sum(1 for r in rows if r["status"] == "sl")
    pending = sum(1 for r in rows if r["status"] == "open")
    closed = tp + sl
    winrate = (tp / closed * 100) if closed else 0.0

    return (
        f"📈 وضعیت کلی سیگنال‌ها\n\n"
        f"تعداد کل سیگنال‌ها: {total}\n"
        f"✅ تیک‌پرافیت: {tp}\n"
        f"❌ استاپ: {sl}\n"
        f"⏳ باز (هنوز نتیجه مشخص نشده): {pending}\n"
        f"🎯 وین‌ریت (از بسته‌شده‌ها): {winrate:.1f}%"
    )


async def scan_for_signals(bot, symbols=None):
    """Run once per SCAN_INTERVAL_SECONDS. Returns list of sent signal ids.
    `symbols` overrides config.SYMBOLS -- used when SYMBOL_MODE=auto to scan
    the current top-volume watch-list instead of a fixed list."""
    symbols = symbols if symbols is not None else config.SYMBOLS
    sent_ids = []
    for symbol in symbols:
        try:
            if database.has_open_signal_for_symbol(symbol):
                continue  # avoid duplicate/overlapping signals on the same symbol
            signal = strategy.find_signal_for_symbol(symbol)
            if signal is None:
                continue

            signal_id = database.insert_signal(
                symbol=signal.symbol,
                direction=signal.direction,
                entry_price=signal.entry,
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
            )
            sent_ids.append(signal_id)

            await bot.send_message(chat_id=config.TELEGRAM_CHAT_ID, text=format_signal_message(signal))
            await _maybe_send_batch_report(bot)

        except Exception:
            logger.exception("Error scanning symbol %s", symbol)

    return sent_ids


async def _maybe_send_batch_report(bot):
    unbatched = database.get_unbatched_signals(config.BATCH_SIZE)
    if len(unbatched) < config.BATCH_SIZE:
        return

    total_signals = database.count_total_signals()
    batch_number = (total_signals - 1) // config.BATCH_SIZE + 1

    await bot.send_message(
        chat_id=config.TELEGRAM_CHAT_ID,
        text=format_batch_message(unbatched, batch_number),
    )
    database.mark_batch_notified([r["id"] for r in unbatched])


async def monitor_open_signals(bot):
    open_signals = database.get_open_signals()
    for sig in open_signals:
        try:
            price = data_fetcher.fetch_last_price(sig["symbol"])
        except Exception:
            logger.exception("Error fetching price for %s", sig["symbol"])
            continue

        hit = None
        if sig["direction"] == "long":
            if price >= sig["take_profit"]:
                hit = "tp"
            elif price <= sig["stop_loss"]:
                hit = "sl"
        else:
            if price <= sig["take_profit"]:
                hit = "tp"
            elif price >= sig["stop_loss"]:
                hit = "sl"

        if hit:
            database.close_signal(sig["id"], hit)
            emoji = "✅" if hit == "tp" else "❌"
            label = "تیک‌پرافیت خورد" if hit == "tp" else "استاپ خورد"
            await bot.send_message(
                chat_id=config.TELEGRAM_CHAT_ID,
                text=f"{emoji} سیگنال {sig['symbol']} ({sig['direction']}) {label}\nقیمت: {price:.6g}",
            )
