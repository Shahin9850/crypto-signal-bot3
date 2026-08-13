"""
Entry point. Runs a Telegram bot that:
  - every SCAN_INTERVAL_SECONDS scans all configured symbols for a new signal
    with the 4H-bias / 15M-entry POC strategy and sends it to the chat.
  - every MONITOR_INTERVAL_SECONDS checks open signals against TP/SL.
  - responds to the text "وضعیت" (or /status) with full-history TP/SL stats.
  - automatically posts a stats summary every BATCH_SIZE signals sent.

Run with:  python bot.py
Requires a .env file (see .env.example).
"""
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import config
import database
import signal_manager
import symbol_universe

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_symbols = context.bot_data.get("symbols", config.SYMBOLS)
    mode_label = (
        f"خودکار (تاپ {config.AUTO_TOP_N} نماد پرحجم {config.AUTO_QUOTE_CURRENCY}, "
        f"هر {config.SYMBOL_REFRESH_SECONDS // 60} دقیقه بروزرسانی)"
        if config.SYMBOL_MODE == "auto" else "ثابت (از .env)"
    )
    await update.message.reply_text(
        "ربات سیگنال فعاله ✅\n"
        f"حالت نماد: {mode_label}\n"
        f"تعداد نماد در حال رصد: {len(current_symbols)}\n"
        f"تحلیل: {config.HTF} | ورود: {config.LTF}\n\n"
        "برای دیدن وضعیت سیگنال‌ها بنویس: وضعیت"
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(signal_manager.format_status_message())


async def status_text_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text in ("وضعیت", "وضعیت؟", "status"):
        await update.message.reply_text(signal_manager.format_status_message())


async def refresh_symbols_job(context: ContextTypes.DEFAULT_TYPE):
    if config.SYMBOL_MODE != "auto":
        return
    try:
        top = symbol_universe.get_top_symbols()
        if top:
            context.bot_data["symbols"] = top
            logger.info("Watch-list refreshed: %d symbols", len(top))
    except Exception:
        logger.exception("Failed to refresh top-volume symbol list")


async def scan_job(context: ContextTypes.DEFAULT_TYPE):
    symbols = context.bot_data.get("symbols", config.SYMBOLS)
    await signal_manager.scan_for_signals(context.bot, symbols=symbols)


async def monitor_job(context: ContextTypes.DEFAULT_TYPE):
    await signal_manager.monitor_open_signals(context.bot)


def main():
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID رو تو فایل .env تنظیم کن (به .env.example نگاه کن)."
        )

    database.init_db()

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.bot_data["symbols"] = config.SYMBOLS  # default until first auto-refresh (if enabled)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, status_text_trigger))

    job_queue = app.job_queue
    if config.SYMBOL_MODE == "auto":
        job_queue.run_repeating(refresh_symbols_job, interval=config.SYMBOL_REFRESH_SECONDS, first=0)
        # give the first refresh a moment to populate bot_data["symbols"] before the first scan
        job_queue.run_repeating(scan_job, interval=config.SCAN_INTERVAL_SECONDS, first=15)
    else:
        job_queue.run_repeating(scan_job, interval=config.SCAN_INTERVAL_SECONDS, first=5)
    job_queue.run_repeating(monitor_job, interval=config.MONITOR_INTERVAL_SECONDS, first=10)

    logger.info("Bot starting... mode=%s htf=%s ltf=%s", config.SYMBOL_MODE, config.HTF, config.LTF)
    app.run_polling()


if __name__ == "__main__":
    main()
