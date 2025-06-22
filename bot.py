import os
import json
import time
import asyncio
import logging
import traceback
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from fastapi import FastAPI
from threading import Thread
import uvicorn

# --- Config ---
API_ID = int(os.environ.get("API_ID", "25833520"))
API_HASH = os.environ.get("API_HASH", "7d012a6cbfabc2d0436d7a09d8362af7")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7422084781:AAEyqYJBAepuCeXgnZcNVxa_Z7aMDcIiK1s")
OWNER_ID = int(os.environ.get("OWNER_ID", "921365334"))
CHANNEL_ID = -1002739509521

CONFIG_FILE = "config.json"
SEEN_FILE = "seen.json"
CHECK_INTERVAL = 300  # seconds

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Web App ---
web_app = FastAPI()

@web_app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is alive!"}

# --- Load config ---
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"BASE_URL": "https://skymovieshd.dance"}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

config = load_config()
BASE_URL = config["BASE_URL"]

# --- Seen Management ---
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

# --- Scraping Logic ---
def get_latest_movie_links():
    res = requests.get(BASE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    links = []
    for a in soup.find_all("a", href=True):
        href = a['href']
        if "/movie/" in href and href.endswith('.html'):
            full_url = urljoin(BASE_URL, href)
            links.append(full_url)
    return sorted(set(links), reverse=True)[:15]

def get_server_links(skymovies_url):
    res = requests.get(skymovies_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    servers = []
    for a in soup.find_all('a', href=True):
        if 'howblogs.xyz' in a['href'] or 'server' in a.text.lower():
            servers.append(a['href'])
    return servers

def extract_final_links(redirector_url):
    try:
        res = requests.get(redirector_url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        raw_text = soup.get_text()
        links = re.findall(r'https?://[^\s"\']+', raw_text)
        return links
    except:
        return []

def clean_links(links):
    cleaned = [link.strip() for link in links if link.startswith("http")]
    return sorted(set(cleaned))

# --- Telegram Bot ---
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

async def notify_to_channel(movie_url, links):
    name = movie_url.split("/")[-1].replace("-", " ").replace(".html", "").title()
    text = f"🆕 New Movie: [{name}]({movie_url})\n"
    for link in links:
        label = link.split("//")[1].split("/")[0].split(".")[0]
        text += f"👍🏻 **{label}** - {link}\n"

    await bot.send_message(CHANNEL_ID, text, parse_mode=ParseMode.MARKDOWN)

async def monitor_loop():
    seen = load_seen()
    while True:
        logger.info("🔍 Checking for new content...")
        latest = get_latest_movie_links()
        new_links = [url for url in latest if url not in seen]

        for url in new_links:
            logger.info(f"📥 New Detected: {url}")
            server_links = get_server_links(url)
            all_links = []
            for server in server_links:
                all_links.extend(extract_final_links(server))
            final_links = clean_links(all_links)

            if final_links:
                await notify_to_channel(url, final_links)
                seen.add(url)
                save_seen(seen)

        logger.info(f"⏳ Sleeping {CHECK_INTERVAL} seconds...\n")
        await asyncio.sleep(CHECK_INTERVAL)

@bot.on_message(filters.command("up") & filters.user(OWNER_ID))
async def update_base(client, message):
    global BASE_URL, config
    if len(message.command) < 2:
        await message.reply("❌ Usage: /up <new_url>")
        return
    new_url = message.command[1]
    config["BASE_URL"] = new_url
    BASE_URL = new_url
    save_config(config)
    await message.reply(f"✅ BASE_URL updated to:\n{new_url}")

# --- Launch Background Services ---
def run_fastapi():
    uvicorn.run(web_app, host="0.0.0.0", port=8000)

# --- Main ---
if __name__ == "__main__":
    Thread(target=run_fastapi, daemon=True).start()

    async def main():
        await bot.start()
        await monitor_loop()

    asyncio.run(main())
