import os
import asyncio
import json
from threading import Thread
from typing import Callable
import logging
import traceback

from fastapi import FastAPI
import uvicorn
from pyrogram import Client, filters, utils
from pyrogram.enums import ParseMode
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", mode="a", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# --- Configuration ---
API_ID = int(os.environ.get("API_ID", "25833520"))
API_HASH = os.environ.get("API_HASH", "7d012a6cbfabc2d0436d7a09d8362af7")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7422084781:AAEyqYJBAepuCeXgnZcNVxa_Z7aMDcIiK1s")
OWNER_ID = int(os.environ.get("OWNER_ID", "921365334"))
CHANNEL_ID = -1002739509521
CONFIG_FILE = "config.json"
SEEN_FILE = "seen.json"

# Patch Pyrogram get_peer_type
utils.get_peer_type = lambda peer_id: "channel" if str(peer_id).startswith("-100") else ("chat" if str(peer_id).startswith("-") else "user")

# --- FastAPI Web App ---
web_app = FastAPI()

@web_app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is alive!"}

# --- Telegram Bot ---
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Selenium link extractor ---
def get_real_download_links(url: str, update_callback: Callable[[str], None] = None) -> list:
    def send_update(text: str):
        if update_callback:
            update_callback(text)
        logger.info(text)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=options)
    logger.info(f"Selenium browser launched for: {url}")

    try:
        send_update("\U0001F310 Opening URL...")
        driver.get(url)
        wait = WebDriverWait(driver, 15)
        send_update("\U0001F50D Looking for download generator button...")
        button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Generate Direct Download Link')]")))
        button.click()
        send_update("\u23F3 Waiting for redirection...")
        wait.until(lambda d: "hubcloud" not in d.current_url)
        send_update("\U0001F50E Scanning for final links...")
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
        buttons = driver.find_elements(By.TAG_NAME, "a")
        return [btn.get_attribute("href") for btn in buttons if btn.get_attribute("href") and ("download" in (btn.text or "").lower() or btn.get_attribute("href").endswith((".mp4", ".mkv", ".zip", ".rar")))]
    except Exception as e:
        logger.error(f"❌ Failed: {e}")
        logger.error(traceback.format_exc())
        return []
    finally:
        driver.quit()
        logger.info("Selenium browser closed.")

@bot.on_message(filters.command("hub"))
async def link_handler(client, message):
    if len(message.command) < 2:
        await message.reply("❌ Usage: /hub <url>")
        return

    url = message.command[1]
    status_msg = await message.reply("🔄 Starting processing...")
    logger.info(f"Received /hub command: {url} from user {message.from_user.id}")
    loop = asyncio.get_running_loop()

    def update_callback(text: str):
        async def coro():
            try:
                if status_msg.text != text:
                    await status_msg.edit_text(text)
            except Exception as e:
                logger.warning(f"Failed to update message text: {e}")
        asyncio.run_coroutine_threadsafe(coro(), loop)

    try:
        links = await asyncio.to_thread(get_real_download_links, url, update_callback)
        if links:
            await status_msg.edit_text("🎯 Final Video Link(s):\n" + "\n".join(f"• {link}" for link in links))
        else:
            await status_msg.edit_text("⚠️ No valid links found.")
    except Exception as e:
        logger.error(traceback.format_exc())
        await status_msg.edit_text(f"❌ Error occurred:\n`{e}`")

# --- SkymoviesHD Monitor ---
def load_seen():
    try:
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def get_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return {"base_url": "https://skymovieshd.dance"}

def get_latest_movies(base_url):
    res = requests.get(base_url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    return sorted(set(urljoin(base_url, a['href']) for a in soup.find_all("a", href=True) if "/movie/" in a['href'] and a['href'].endswith(".html")), reverse=True)[:10]

def get_server_links(page_url):
    res = requests.get(page_url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    return [a['href'] for a in soup.find_all('a', href=True) if 'howblogs' in a['href'] or 'server' in a.text.lower()]

def extract_final_links(redirector_url):
    try:
        res = requests.get(redirector_url, headers={'User-Agent': 'Mozilla/5.0'})
        return re.findall(r'https?://[^\s"\']+', res.text)
    except:
        return []

def clean_links(links):
    return sorted(set(l.strip() for l in links if l.startswith("http")))

def parse_movie_info(url):
    title = url.split("/")[-1].replace("-", " ").replace(".html", "").strip()
    match = re.search(r'(\[\d+(?:\.\d+)?GB\])', title, re.IGNORECASE)
    return title, match.group(1) if match else "Unknown Size"

async def monitor_skymovies():
    seen = load_seen()
    while True:
        config = get_config()
        latest = get_latest_movies(config["base_url"])
        new_movies = [url for url in latest if url not in seen]
        for url in new_movies:
            server_links = get_server_links(url)
            all_links = sum([extract_final_links(link) for link in server_links], [])
            final_links = clean_links(all_links)
            if not final_links:
                continue
            title, size = parse_movie_info(url)
            message = f"🎬 **{title}**\n📦 **Size:** {size}\n\n" + "\n".join([f"[Server {i+1}](<{l}>)" for i, l in enumerate(final_links)])
            try:
                await bot.send_message(CHANNEL_ID, message, parse_mode=ParseMode.MARKDOWN)
                seen.add(url)
                save_seen(seen)
            except Exception as e:
                logger.error(f"❌ Failed to send message: {e}")
        await asyncio.sleep(300)

@bot.on_message(filters.command("up") & filters.user(OWNER_ID))
async def update_domain(client, message):
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("Usage: /up <new base URL>")
        return
    with open(CONFIG_FILE, "w") as f:
        json.dump({"base_url": parts[1]}, f)
    await message.reply(f"✅ Domain updated to: {parts[1]}")

# --- Entrypoint ---
if __name__ == "__main__":
    Thread(target=lambda: uvicorn.run(web_app, host="0.0.0.0", port=8000)).start()

    async def main():
        await bot.start()
        logger.info("🔍 Bot started. Testing message send...")
        try:
            await bot.send_message(CHANNEL_ID, "✅ Bot successfully connected.")
        except Exception as e:
            logger.error(f"Send test failed: {e}")
        asyncio.create_task(monitor_skymovies())
        await bot.idle()

    asyncio.run(main())
