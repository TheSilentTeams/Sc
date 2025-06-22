import os
import json
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

# --- Logging ---
logger = logging.getLogger("movie_bot")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s — %(levelname)s — %(message)s")

ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

fh = logging.FileHandler(LOG_FILE)
fh.setFormatter(formatter)
logger.addHandler(fh)

# --- Patch Pyrogram Peer Type ---
def get_peer_type_new(peer_id: int) -> str:
    peer_id_str = str(peer_id)
    if not peer_id_str.startswith("-"):
        return "user"
    elif peer_id_str.startswith("-100"):
        return "channel"
    return "chat"

utils.get_peer_type = get_peer_type_new

# --- Pyrogram App ---
app = Client("movie-monitor", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Load/Save Config ---
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

# --- Load/Save Seen ---
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
# [Full trimmed script with focus on get_latest_movie_links]

def get_latest_movie_links():
    logger.debug("Fetching homepage: %s", BASE_URL)
    res = requests.get(BASE_URL, headers={"User-Agent": "Mozilla/5.0"})
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    # Find the heading "Latest Updated Movies" and its list entries
    header = soup.find(lambda tag: tag.name in ["h2","h3","div"] and "Latest Updated Movies" in tag.text)
    if not header:
        logger.warning("Could not locate 'Latest Updated Movies' header, fallback to homepage")
        return []

    # Usually the movie links are in the next sibling (like a ul or div)
    container = header.find_next_sibling()
    if not container:
        logger.warning("No container after header, fallback")
        return []

    links = []
    for a in container.find_all("a", href=True):
        href = a["href"]
        if "/movie/" in href and href.endswith(".html"):
            links.append(urljoin(BASE_URL, href))

    unique = sorted(set(links), reverse=True)[:15]
    logger.info("Found %d latest updated movie links", len(unique))
    return unique


def get_server_links(movie_url):
    logger.debug("Fetching movie page: %s", movie_url)
    res = requests.get(movie_url, headers={"User-Agent": "Mozilla/5.0"})
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    servers = []
    for a in soup.find_all("a", href=True):
        if "howblogs" in a["href"] or "server" in a.get_text().lower():
            servers.append(a["href"])
    return servers

def extract_final_links(redirector_url):
    try:
        res = requests.get(redirector_url, headers={"User-Agent": "Mozilla/5.0"})
        res.raise_for_status()
        raw = BeautifulSoup(res.text, "html.parser").get_text()
        found = re.findall(r"https?://[^\s\"']+", raw)
        return found
    except Exception as e:
        logger.error("Error extracting final links: %s", e)
        return []

def clean_links(links):
    allowed_domains = ["gofile", "hubcloud", "hubdrive", "gdflix", "gdtot"]
    filtered = []
    for link in links:
        for domain in allowed_domains:
            if domain in link:
                filtered.append(link.strip())
                break
    unique = sorted(set(filtered))
    logger.debug("Filtered to %d final download links", len(unique))
    return unique

def get_title(movie_url):
    try:
        res = requests.get(movie_url, headers={"User-Agent": "Mozilla/5.0"})
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        candidates = [
            getattr(soup.find("h1"), "text", None),
            getattr(soup.title, "text", None),
            soup.find("meta", property="og:title") and soup.find("meta", property="og:title")["content"],
            soup.find("meta", {"name": "title"}) and soup.find("meta", {"name": "title"})["content"]
        ]
        for c in candidates:
            if c and c.strip():
                return c.strip()
        return movie_url.split("/")[-1].replace("-", " ").replace(".html", "").title()
    except Exception as e:
        logger.error("Failed to get title from %s: %s", movie_url, e)
        return movie_url.split("/")[-1].replace("-", " ").replace(".html", "").title()

async def send_to_channel(title, links):
    logger.info("Sending: %s with %d links", title, len(links))
    msg = f"🎬 **{title}**\n\n🎯 **Links:**\n"
    for link in links:
        domain = re.sub(r"^https?://(www\.)?", "", link).split("/")[0]
        label = domain.split(".")[0][:10]
        msg += f"🔗 **{label}** - {link}\n"
    await app.send_message(CHANNEL_ID, msg)

# --- /up command ---
@app.on_message(filters.command("up") & filters.user(OWNER_ID))
async def update_url(client, message):
    global BASE_URL
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.reply("❌ Usage: `/up https://newdomain.xyz`")
        return
    new_url = parts[1].strip()
    BASE_URL = new_url
    config["BASE_URL"] = new_url
    save_config(config)
    logger.warning("BASE_URL updated to %s", new_url)
    await message.reply(f"✅ BASE_URL updated to: {new_url}")

# --- Monitor Loop ---
async def monitor():
    seen = load_seen()
    logger.info("Starting monitor with %d seen entries", len(seen))

    while True:
        try:
            latest = get_latest_movie_links()
            new_items = [u for u in latest if u not in seen]

            if new_items:
                logger.info("Found %d new item(s)", len(new_items))

            for url in new_items:
                title = get_title(url)
                server_links = get_server_links(url)

                all_links = []
                for s in server_links:
                    all_links.extend(extract_final_links(s))

                final_links = clean_links(all_links)
                if final_links:
                    await send_to_channel(title, final_links)

                seen.add(url)
                save_seen(seen)

        except Exception as e:
            logger.exception("Error in monitor: %s", e)

        await asyncio.sleep(CHECK_INTERVAL)

# --- Run ---
if __name__ == "__main__":
    async def main():
        await app.start()
        logger.info("Bot started and monitoring.")
        await monitor()
    asyncio.run(main())
