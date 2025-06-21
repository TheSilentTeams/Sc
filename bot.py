import os
import asyncio
from fastapi import FastAPI
from pyrogram import Client, filters
import uvicorn
from threading import Thread

API_ID = int(os.environ.get("API_ID", "25833520"))  # Get this from https://my.telegram.org
API_HASH = os.environ.get("API_HASH", "7d012a6cbfabc2d0436d7a09d8362af7")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7422084781:AAGkwQECl0cSFAfx89_vncmgbuKQ0uHxjSs")

# --- FastAPI app ---
web_app = FastAPI()

@web_app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is alive!"}

# --- Pyrogram bot ---
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@bot.on_message(filters.command("link"))
async def link_handler(client, message):
    if len(message.command) < 2:
        await message.reply("❌ Usage: /link <url>")
        return

    url = message.command[1]
    status_msg = await message.reply("🔄 Starting processing...")

    try:
        from uc import get_real_download_links

        await status_msg.edit_text("⚙️ Launching browser & loading page...")
        links = get_real_download_links(url)

        if links:
            reply = "\n".join(f"• {link}" for link in links)
            await status_msg.edit_text(f"🎯 Final Video Link(s):\n{reply}")
        else:
            await status_msg.edit_text("⚠️ No valid links found.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Error occurred:\n`{e}`")


# --- Start FastAPI in background ---
def run_fastapi():
    config = uvicorn.Config(web_app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())

if __name__ == "__main__":
    Thread(target=run_fastapi).start()  # Start web server in background
    bot.run()  # Start Telegram bot
