import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from uc import get_links  # this is your function

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /link <url>")
        return

    url = context.args[0]
    await update.message.reply_text("🔄 Processing your link...")

    try:
        links = get_links(url)
        if links:
            reply = "\n".join(f"• {link}" for link in links)
            await update.message.reply_text(f"🎯 Final Video Link(s):\n{reply}")
        else:
            await update.message.reply_text("⚠️ No links found.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("link", link_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
