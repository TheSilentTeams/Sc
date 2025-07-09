
import os
import json
import logging
import asyncio
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pyrogram import Client, idle,utils
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait
import nest_asyncio
from collections import defaultdict
import re
import urllib3

# --- Environment Setup ---
nest_asyncio.apply()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_ID     = int(os.environ.get("API_ID", "25833520"))
API_HASH   = os.environ.get("API_HASH", "7d012a6cbfabc2d0436d7a09d8362af7")
BOT_TOKEN  = os.environ.get("FF_BOT_TOKEN", "8091169950:AAHfUE1W6GJYeH5rnX235AUNkjDyfeIFrgM")
CHANNEL_ID = int(os.environ.get("FF_CHANNEL_ID", "-1002557597877"))
OWNER_ID   = int(os.environ.get("FF_OWNER_ID", "921365334"))
filmy_FILE = "filmy.json"
utils.get_peer_type = lambda peer_id: "channel" if str(peer_id).startswith("-100") else "user"
BASE_URL = "https://filmyfly.loan/"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FilmyFlyBot")

# --- Pyrogram Client ---
app = Client("filmyfly-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- filmy Movie Tracker ---
def load_filmy():
    if os.path.exists(filmy_FILE):
        with open(filmy_FILE) as f:
            return set(json.load(f))
    return set()

def save_filmy(filmy):
    with open(filmy_FILE, "w") as f:
        json.dump(list(filmy), f, indent=2)

# --- Scraper Functions ---
def get_latest_movie_links():
    logger.info("Fetching homepage")
    r = requests.get(BASE_URL, headers=HEADERS, verify=False)
    soup = BeautifulSoup(r.text, "html.parser")
    blocks = soup.find_all("div", class_="A10")
    links = [urljoin(BASE_URL, a["href"].strip()) for b in blocks if (a := b.find("a", href=True))]
    return list(dict.fromkeys(links))

def get_quality_links(movie_url):
    r = requests.get(movie_url, headers=HEADERS, verify=False)
    soup = BeautifulSoup(r.text, "html.parser")
    qlinks = defaultdict(list)
    for a in soup.find_all("a", href=True, string=True):
        text = a.get_text().strip()
        if text.lower().startswith("download") and "/view/" in a["href"]:
            qual = re.search(r"\{(.+?)\}", text)
            quality = qual.group(1) if qual else "Other"
            full = urljoin(BASE_URL, a["href"])
            qlinks[quality].append(full)
    return dict(qlinks)

def get_intermediate_links(quality_page_url):
    r = requests.get(quality_page_url, headers=HEADERS, verify=False)
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for tag in soup.find_all(["a", "button"]):
        href = tag.get("href") or tag.get("data-href")
        label = tag.get_text(strip=True)
        if href and label and href.startswith("http") and not any(x in label.lower() for x in ["login", "signup"]):
            links.append((label, href))
    return links

def extract_final_links(cloud_url):
    r = requests.get(cloud_url, headers=HEADERS, verify=False)
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    for tag in soup.find_all(["a", "button"]):
        href = tag.get("href") or tag.get("data-href")
        label = tag.get_text(strip=True)
        if href and label and href.startswith("http"):
            links.append((label, href))
    for form in soup.find_all("form"):
        action = form.get("action")
        label = form.get_text(strip=True)
        if action and action.startswith("http"):
            links.append((label, action))
    return links

def get_title_from_intermediate(url):
    try:
        r = requests.get(url, headers=HEADERS, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.find("title")
        return title.text.strip() if title else "Untitled"
    except:
        return "Untitled"

def clean(text):
    return re.sub(r"[\[\]_`*]", "", text)

# --- Telegram Messaging ---
async def send_quality_message(title, quality, provider, links):
    msg = f"🎬 `{clean(title)}`\n\n"
    msg += f"🔗 **Quality**: `{provider}`\n\n"
    for label, url in links:
        msg += f"• [{clean(label)}]({url})\n"
    msg += "\n🌐 Scraped from [FilmyFly](https://telegram.me/Silent_Bots)"
    try:
        await app.send_message(
            chat_id=CHANNEL_ID,
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await send_quality_message(title, quality, provider, links)
    except Exception as e:
        logger.error(f"Send error: {e}")

# --- Main Monitor ---
async def monitor():
    filmy = load_filmy()
    logger.info(f"Loaded {len(filmy)} filmy entries")
    while True:
        try:
            movies = await asyncio.to_thread(get_latest_movie_links)
            new = [m for m in movies if m not in filmy]
            logger.info(f"Found {len(new)} new movies")
            for movie_url in new:
                logger.info(f"Processing: {movie_url}")
                qlinks = await asyncio.to_thread(get_quality_links, movie_url)
                for quality, view_urls in qlinks.items():
                    for view_url in view_urls:
                        intermediate_links = await asyncio.to_thread(get_intermediate_links, view_url)
                        for provider, link in intermediate_links:
                            finals = await asyncio.to_thread(extract_final_links, link)
                            if finals:
                                title = await asyncio.to_thread(get_title_from_intermediate, link)
                                await send_quality_message(title, quality, provider, finals)
                filmy.add(movie_url)
                save_filmy(filmy)
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        await asyncio.sleep(300)

# --- Start Bot ---
async def start_filmyfly():
    await app.start()
    asyncio.create_task(monitor())
    await idle()
    await app.stop()

# For deployment or direct run
if __name__ == "__main__":
    asyncio.run(main())
