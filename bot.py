import os
import asyncio
from pyrogram import Client, filters
from uc import get_real_download_links

# Replace these or set them via environment variables on Render
API_ID = int(os.environ.get("API_ID", "25833520"))  # Get this from https://my.telegram.org
API_HASH = os.environ.get("API_HASH", "7d012a6cbfabc2d0436d7a09d8362af7")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7422084781:AAGkwQECl0cSFAfx89_vncmgbuKQ0uHxjSs")

bot = Client(
    "dlbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

@bot.on_message(filters.command("link") & filters.private | filters.group)
async def link_handler(client, message):
    if len(message.command) < 2:
        await message.reply("❌ Usage: `/link <url>`", quote=True)
        return

    url = message.command[1]
    await message.reply("🔄 Processing your link...")

    try:
        links = get_real_download_links(url)
        if links:
            text = "🎯 Final Video Link(s):\n" + "\n".join(f"• {link}" for link in links)
        else:
            text = "⚠️ No links found."

        await message.reply(text, quote=True)
    except Exception as e:
        await message.reply(f"❌ Error: `{e}`", quote=True)

bot.run()
