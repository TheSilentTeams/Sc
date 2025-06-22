import os
import json
import time
import re
import logging
import asyncio
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from pyrogram import Client, filters, utils

# --- Config ---
API_ID     = int(os.environ.get("API_ID", "25833520"))
API_HASH   = os.environ.get("API_HASH", "7d012a6cbfabc2d0436d7a09d8362af7")
BOT_TOKEN  = os.environ.get("BOT_TOKEN", "7422084781:AAEyqYJBAepuCeXgnZcNVxa_Z7aMDcIiK1s")
OWNER_ID   = int(os.environ.get("OWNER_ID", "921365334"))
CHANNEL_ID = -1002739509521

CONFIG_FILE = "config.json"
SEEN_FILE   = "seen.json"
LOG_FILE    = "bot.log"
CHECK_INTERVAL = 300  # seconds

# --- Logging Setup ---
logger = logging.getLogger("movie_bot")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s — %(levelname)s — %(message)s")

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

# File handler
fh = logging.FileHandler(LOG_FILE)
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
logger.addHandler(fh)

# --- Patch peer type ---
def get_peer_type_new(peer_id: int) -> str:
    peer_str = str(peer_id)
    if not peer_str.startswith("-"):
        return "user"
    elif peer_str.startswith("-100"):
        return "channel"
    return "chat"

utils.get_peer_type = get_peer_type_new

# --- Pyrogram Client ---
app = Client("movie-monitor",
             api_id=API_ID,
             api_hash=API_HASH,
             bot_token=BOT_TOKEN)

# --- Config Loader / Saver ---
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"BASE_URL": "https://skymovieshd.dance"}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

config = load_config()
BASE_URL = config.get("BASE_URL", "https://skymovieshd.dance")

# --- Seen Tracking ---
def load_seen():
    try:
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f, indent=2)

# --- Scraper Functions ---
def get_latest_movie_links():
    logger.debug("Fetching homepage: %s", BASE_URL)
    resp = requests.get(BASE_URL, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/movie/" in href and href.endswith(".html"):
            full = urljoin(BASE_URL, href)
            links.append(full)

    unique = sorted(set(links), reverse=True)[:15]
    logger.info("Found %d movie links", len(unique))
    return unique

def get_server_links(movie_url):
    logger.debug("Fetching movie page: %s", movie_url)
    resp = requests.get(movie_url, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    servers = []
    for a in soup.find_all("a", href=True):
        if "howblogs.xyz" in a["href"] or "server" in a.get_text().lower():
            servers.append(a["href"])
    logger.debug("  → %d server link(s)", len(servers))
    return servers

def extract_final_links(redirector_url):
    try:
        logger.debug("Resolving redirector: %s", redirector_url)
        resp = requests.get(redirector_url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        raw = BeautifulSoup(resp.text, "html.parser").get_text()
        found = re.findall(r"https?://[^\s\"']+", raw)
        logger.debug("    → %d final link(s)", len(found))
        return found
    except Exception as e:
        logger.error("Failed to extract from %s: %s", redirector_url, e)
        return []

def clean_links(links):
    cleaned = sorted({link.strip() for link in links if link.startswith("http")})
    logger.debug("  → %d unique cleaned link(s)", len(cleaned))
    return cleaned

def get_title_and_size(movie_url):
    try:
        logger.debug("Extracting title/size from: %s", movie_url)
        resp = requests.get(movie_url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text()

        # Title candidates
        candidates = [
            getattr(soup.find("h1"), "text", None),
            getattr(soup.title, "text", None),
            soup.find("meta", property="og:title") and soup.find("meta", property="og:title")["content"],
            soup.find("meta", {"name": "title"}) and soup.find("meta", {"name": "title"})["content"]
        ]
        title = next((t for t in candidates if t and t.strip()), None)
        if not title:
            # fallback to URL
            title = movie_url.rstrip("/").split("/")[-1].replace("-", " ").replace(".html", "").title()

        # Size
        size_match = re.search(r"\b(\d+(?:\.\d+)?\s*(?:MB|GB))\b", text, re.I)
        size = size_match.group(0) if size_match else "Unknown Size"

        logger.info("Parsed → Title: %s | Size: %s", title.strip(), size)
        return title.strip(), size
    except Exception as e:
        logger.error("Error parsing title/size for %s: %s", movie_url, e)
        # fallback
        name = movie_url.rstrip("/").split("/")[-1].replace("-", " ").replace(".html", "").title()
        return name, "Unknown Size"

async def send_to_channel(title, size, links):
    logger.info("Sending to channel → %s [%s links]", title, len(links))
    msg = f"🎬 **{title}**\n📦 Size: `{size}`\n\n🎯 **Links:**\n"
    for link in links:
        domain = re.sub(r"^https?://(www\.)?", "", link).split("/")[0]
        label = domain.split(".")[0][:10]
        msg += f"👍🏻**{label}** - {link}\n"
    await app.send_message(CHANNEL_ID, msg)

# --- /up command for owner to change BASE_URL ---
@app.on_message(filters.command("up") & filters.user(OWNER_ID))
async def update_url(client, message):
    global BASE_URL
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.reply("❌ Usage: `/up https://newdomain.xyz`", quote=True)
        return

    new_url = parts[1].strip()
    BASE_URL = new_url
    config["BASE_URL"] = new_url
    save_config(config)
    logger.warning("BASE_URL updated by owner → %s", new_url)
    await message.reply(f"✅ BASE_URL updated to: {new_url}")

# --- Monitoring Loop ---
async def monitor():
    seen = load_seen()
    logger.info("Starting monitor loop; %d items in seen list", len(seen))
    while True:
        try:
            latest = get_latest_movie_links()
            new_items = [u for u in latest if u not in seen]
            if new_items:
                logger.info("Found %d new item(s)", len(new_items))

            for url in new_items:
                title, size = get_title_and_size(url)
                servers = get_server_links(url)
                all_links = []
                for srv in servers:
                    all_links.extend(extract_final_links(srv))
                final = clean_links(all_links)
                if final:
                    await send_to_channel(title, size, final)
                seen.add(url)
                save_seen(seen)

        except Exception as e:
            logger.exception("Error in monitor loop: %s", e)

        logger.debug("Sleeping for %d seconds", CHECK_INTERVAL)
        await asyncio.sleep(CHECK_INTERVAL)

# --- Run ---
if __name__ == "__main__":
    async def main():
        await app.start()
        logger.info("Bot started")
        await monitor()
    asyncio.run(main())
