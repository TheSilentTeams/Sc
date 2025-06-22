import os
import asyncio
import json
import re
from threading import Thread
from typing import Callable
import logging
import traceback

from fastapi import FastAPI
import uvicorn
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Config ---
API_ID = int(os.environ.get("API_ID", "25833520"))
API_HASH = os.environ.get("API_HASH", "7d012a6cbfabc2d0436d7a09d8362af7")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7422084781:AAEyqYJBAepuCeXgnZcNVxa_Z7aMDcIiK1s")
OWNER_ID = int(os.environ.get("OWNER_ID", "921365334"))
CHANNEL_ID = -1002739509521

BASE_URL = "https://skymovieshd.dance"
CONFIG_FILE = "config.json"
SEEN_FILE = "seen.json"

# --- Web ---
web_app = FastAPI()

@web_app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is alive!"}

# --- Bot ---
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Utility ---
def load_seen():
    try:
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def extract_host_name(url):
    try:
        return re.sub(r'^www\.', '', url.split('/')[2].split('.')[0])
    except:
        return "unknown"

def parse_movie_info(url):
    title = url.split("/")[-1].replace("-", " ").replace(".html", "").strip()
    size_match = re.search(r'(\d+(?:\.\d+)?\s?(?:GB|MB))', title, re.IGNORECASE)
    size = size_match.group(1) if size_match else "Unknown Size"
    return title.title(), size

def get_latest_movies():
    res = requests.get(BASE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    return sorted(set(
        urljoin(BASE_URL, a['href']) for a in soup.find_all("a", href=True)
        if "/movie/" in a['href'] and a['href'].endswith(".html")
    ), reverse=True)[:15]

def get_server_links(page_url):
    res = requests.get(page_url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    return [a['href'] for a in soup.find_all('a', href=True)
            if 'howblogs' in a['href'] or 'server' in a.text.lower()]

def extract_final_links(redirector_url):
    try:
        res = requests.get(redirector_url, headers={'User-Agent': 'Mozilla/5.0'})
        text = BeautifulSoup(res.text, 'html.parser').get_text()
        return re.findall(r'https?://[^\s"\']+', text)
    except:
        return []

def clean_links(links):
    return sorted(set(l.strip() for l in links if l.startswith("http")))

# --- Monitor ---
async def monitor_skymovies():
    seen = load_seen()
    while True:
        try:
            logger.info("🔍 Checking for new movies...")
            latest = get_latest_movies()
            new_movies = [url for url in latest if url not in seen]

            for url in new_movies:
                logger.info(f"🎬 New movie: {url}")
                server_links = get_server_links(url)
                all_links = []
                for server in server_links:
                    all_links.extend(extract_final_links(server))
                final_links = clean_links(all_links)
                if not final_links:
                    continue

                title, size = parse_movie_info(url)
                message = f"🎬 **{title}**\n📦 **Size:** {size}\n\n" + "\n".join([
                    f"👍🏻 **{extract_host_name(link)}** - [Link]({link})"
                    for link in final_links
                ])

                await bot.send_message(CHANNEL_ID, message, parse_mode=ParseMode.MARKDOWN)
                seen.add(url)
                save_seen(seen)
        except Exception as e:
            logger.error(f"Monitor error: {e}\n{traceback.format_exc()}")
        await asyncio.sleep(300)

# --- Bot Commands ---
@bot.on_message(filters.command("start"))
async def start_handler(client, message):
    await message.reply("👋 Bot is running!")

@bot.on_message(filters.command("up") & filters.user(OWNER_ID))
async def update_domain(client, message):
    await message.reply("✋ This command is disabled in this version.")

@bot.on_message(filters.text & ~filters.command(["start", "up"]))
async def fallback(client, message):
    await message.reply("🤖 Waiting for new movies! No commands needed.")

# --- Run ---
if __name__ == "__main__":
    # Start FastAPI server
    Thread(target=lambda: uvicorn.run(web_app, host="0.0.0.0", port=8000)).start()

    async def main():
        await bot.start()

        # 🐒 Monkey patch: Resolve peer ID by caching channel manually
        try:
            await bot.get_chat(CHANNEL_ID)
            logger.info("✅ Channel peer resolved.")
        except Exception as e:
            logger.warning(f"⚠️ Cannot resolve channel peer yet: {e}")

        logger.info("✅ Bot started and connected.")
        asyncio.create_task(monitor_skymovies())

        # 💤 No idle() – use wait forever method
        await asyncio.Event().wait()

    asyncio.run(main())
