"""Main module for Tonkkabot — Telegram bot tracking Helsinki-Vantaa temperature."""

import datetime
import logging
import os
import time
from typing import Optional

from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

import data
import plots

BOT_INFO = (
    "This bot tracks the temperature at Helsinki-Vantaa (EFHK). Use command /history to plot"
    " the temperature of last 24h, command \n/temperature to plot current temperature and "
    "command /forecast to plot the forecast of next 48h."
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.WARNING
)
logger = logging.getLogger(__name__)


async def _parse_hours(
    update: Update, context: ContextTypes.DEFAULT_TYPE, lo: int, hi: int, default: int
) -> int:
    """Parse the first command arg as an int in [lo, hi]; fall back to default and warn."""
    arg = next(iter(context.args), None)
    if arg is None:
        return default
    try:
        hours = int(arg)
    except ValueError:
        await update.message.reply_text(
            "Please send an integer argument to change the plotting range."
        )
        return default
    if not lo <= hours <= hi:
        await update.message.reply_text(f"Argument must be between {lo} and {hi}.")
        return default
    return hours


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — reply with the bot description."""
    await update.message.reply_text(BOT_INFO)


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /history [hours] — reply with a temperature history plot."""
    hours = await _parse_hours(update, context, lo=2, hi=24, default=24)
    bio = plots.history(hours)
    bio.seek(0)

    tonks = data.check_history()
    if tonks:
        caption = f'Tönkkä aukesi {tonks["time"]}'
    else:
        caption = "Oli vielä vähän liian kylmää :("
    await update.message.reply_photo(photo=bio, caption=caption)


async def temperature(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /temperature — reply with the most recent observation."""
    temp, timestamp = data.temperature()
    if temp is None or timestamp is None:
        await update.message.reply_text(
            "Ei lämpötilatietoja saatavilla tällä hetkellä."
        )
        return

    await update.message.reply_text(
        f"{temp}\N{DEGREE SIGN}C (at {timestamp.hour:02d}:{timestamp.minute:02d})"
    )


async def forecast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /forecast [hours] — reply with a temperature forecast plot."""
    hours = await _parse_hours(update, context, lo=2, hi=48, default=48)
    bio = plots.forecast(hours)
    bio.seek(0)
    await update.message.reply_photo(photo=bio, caption="Onhan tönkkä jo ostettu? ;)")


async def check_history_job(_: ContextTypes.DEFAULT_TYPE) -> None:
    """Daily job — refresh the tönkkä record for the current year."""
    data.check_history()


async def error(update: Optional[object], context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors that reach the dispatcher so they don't disappear silently."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


async def flush_messages(bot: Bot) -> None:
    """Drop any updates queued during downtime so the bot doesn't spam on reconnect."""
    updates = await bot.get_updates()
    while updates:
        time.sleep(1)
        updates = await bot.get_updates(updates[-1].update_id + 1)


async def post_init(app: Application) -> None:
    """Register handlers and the daily job after the Application is built."""
    await flush_messages(app.bot)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("temperature", temperature))
    app.add_handler(CommandHandler("forecast", forecast))

    app.job_queue.run_daily(
        check_history_job,
        time=datetime.time(0, 0, 0),
        name="Check year",
    )

    app.add_error_handler(error)


def main() -> None:
    """Build the Application from BOT_TOKEN and start long-polling."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set")

    app = (
        Application.builder()
        .token(token)
        .concurrent_updates(False)
        .post_init(post_init)
        .build()
    )
    app.run_polling()


if __name__ == "__main__":
    main()
