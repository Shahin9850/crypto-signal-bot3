"""
Single-run entry point, meant to be triggered on a schedule (GitHub Actions
cron every 15 minutes) rather than run as a long-lived process:

  1. Poll Telegram once for any new messages since the last run (handles
     "وضعیت"/"/status" and "/start").
  2. Scan the current symbol watch-list for a new strategy signal.
  3. Check open signals against TP/SL.
  4. Exit. State (signals, Telegram update offset) persists in signals.db,
     which the workflow commits back to the repo after each run.

Run with:  python run_once.py
Requires the same environment variables as bot.py (see .env.example) --
in GitHub Actions these come from repository secrets/variables instead of
a local .env file.
"""
import logging

import config
import database
import signal_manager
import symbol_universe
from telegram_client import TelegramClient

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

STATUS_TRIGGERS = {"وضعیت", "وضعیت؟", "status", "/status"}
START_TRIGGERS = {"/start", "start"}


def get_current_symbols():
    if config.SYMBOL_MODE == "auto":
        try:
            top = symbol_universe.get_top_symbols()
            if top:
                return top
        except Exception:
            logger.exception("Auto symbol discovery failed, falling back to SYMBOLS")
    return config.SYMBOLS


def handle_incoming_messages(client: TelegramClient, symbols):
    offset_str = database.get_meta("telegram_offset")
    offset = int(offset_str) + 1 if offset_str else None

    try:
        updates = client.get_updates(offset=offset, timeout=0)
    except Exception:
        logger.exception("Failed to fetch Telegram updates")
        return

    last_update_id = None
    for update in updates:
        last_update_id = update["update_id"]
        message = update.get("message") or update.get("edited_message")
        if not message:
            continue

        text = (message.get("text") or "").strip()
        chat_id = message["chat"]["id"]

        if text in STATUS_TRIGGERS:
            client.send_message(chat_id, signal_manager.format_status_message())
        elif text in START_TRIGGERS:
            mode_label = (
                f"خودکار (تاپ {config.AUTO_TOP_N} نماد پرحجم {config.AUTO_QUOTE_CURRENCY})"
                if config.SYMBOL_MODE == "auto" else "ثابت (از تنظیمات)"
            )
            client.send_message(
                chat_id,
                "ربات سیگنال فعاله ✅\n"
                f"حالت نماد: {mode_label}\n"
                f"تعداد نماد در حال رصد: {len(symbols)}\n"
                f"تحلیل: {config.HTF} | ورود: {config.LTF}\n"
                f"هر اجرا هر {config.SCAN_INTERVAL_SECONDS // 60} دقیقه (GitHub Actions)\n\n"
                "برای دیدن وضعیت سیگنال‌ها بنویس: وضعیت"
            )

    if last_update_id is not None:
        database.set_meta("telegram_offset", str(last_update_id))


def main():
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN و TELEGRAM_CHAT_ID تنظیم نشدن (به‌عنوان secret تو GitHub Actions اضافه‌شون کن)."
        )

    database.init_db()
    client = TelegramClient(config.TELEGRAM_BOT_TOKEN)

    symbols = get_current_symbols()
    logger.info("Watching %d symbols (mode=%s)", len(symbols), config.SYMBOL_MODE)

    handle_incoming_messages(client, symbols)
    new_ids = signal_manager.scan_for_signals(client, symbols=symbols)
    signal_manager.monitor_open_signals(client, exclude_ids=new_ids)

    logger.info("Run complete.")


if __name__ == "__main__":
    main()
