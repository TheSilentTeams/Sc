import os
import asyncio
from fastapi import FastAPI
from pyrogram import Client, filters

API_ID = int(os.environ.get("API_ID", "25833520"))  # Get this from https://my.telegram.org
API_HASH = os.environ.get("API_HASH", "7d012a6cbfabc2d0436d7a09d8362af7")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7422084781:AAGkwQECl0cSFAfx89_vncmgbuKQ0uHxjSs")

# Set up FastAPI app
web_app = FastAPI()

@web_app.get("/")
async def root():
    return {"status": "online", "message": "Bot is alive!"}

# Set up Pyrogram client
bot = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# /link handler
@bot.on_message(filters.command("link") & filters.private)
async def link_handler(client, message):
    if len(message.command) < 2:
        await message.reply("❌ Usage: /link <url>")
        return

    url = message.command[1]
    await message.reply("🔄 Processing your link...")

    try:
        from uc import get_real_download_links
        links = get_real_download_links(url)

        if links:
            reply = "\n".join(f"• {link}" for link in links)
            await message.reply(f"🎯 Final Video Link(s):\n{reply}")
        else:
            await message.reply("⚠️ No links found.")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

# Entry point
if __name__ == "__main__":
    import uvicorn
    async def main():
        await bot.start()
        print("🤖 Bot started!")
        # Start FastAPI server
        uvicorn.run(web_app, host="0.0.0.0", port=8000)

    asyncio.run(main())
