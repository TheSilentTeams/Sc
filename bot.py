import os
import json
import re
import logging
import asyncio
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fastapi import FastAPI
import threading
import uvicorn
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import undetected_chromedriver as uc
from pyrogram import idle
from pyrogram import Client, filters, utils
import nest_asyncio
nest_asyncio.apply()

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


web_app = FastAPI()

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


@web_app.get("/")
def read_root():
    return {"status": "running", "message": "Movie bot monitor is active"}

def run_web():
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(web_app, host="0.0.0.0", port=port)


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
    try:
        res = requests.get(BASE_URL, headers={"User-Agent": "Mozilla/5.0"})
        res.raise_for_status()
    except Exception as e:
        logger.error("Failed to fetch BASE_URL: %s", e)
        return []

    soup = BeautifulSoup(res.text, "html.parser")

    # Try to find all divs with class "Fmvideo" (this is where movies are listed)
    movie_divs = soup.find_all("div", class_=lambda x: x and "Fmvideo" in x)
    if not movie_divs:
        logger.warning("No movie divs found with class Fmvideo")
        return []

    links = []
    for div in movie_divs:
        a = div.find("a", href=True)
        if a:
            href = a["href"]
            if "movie" in href and href.endswith(".html"):
                full_url = urljoin(BASE_URL, href)
                links.append(full_url)

    unique = sorted(set(links), reverse=True)[:15]
    logger.info("Found %d latest updated movie links", len(unique))
    return unique

def bypass_hubcloud(url):
    from selenium.webdriver.chrome.service import Service

    options = Options()
    options.add_argument("--headless=new")  # Use new headless mode
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # IMPORTANT: set binary location if you're on Render or custom path
    options.binary_location = "/usr/bin/chromium"

    service = Service("/usr/bin/chromedriver")  # use full path to chromedriver if needed

    driver = webdriver.Chrome(service=service, options=options)
    logger.info(f"🌐 Bypassing HubCloud: {url}")
    links = []

    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)

        button = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(text(), 'Generate Direct Download Link')]")))
        button.click()

        wait.until(lambda d: "hubcloud" not in d.current_url)
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))

        for a in driver.find_elements(By.TAG_NAME, "a"):
            href = a.get_attribute("href")
            if href and ("download" in (a.text or "").lower() or href.endswith((".mp4", ".mkv", ".zip", ".rar"))):
                links.append(href.strip())
    except Exception as e:
        logger.warning(f"HubCloud bypass failed: {e}")
    finally:
        driver.quit()

    logger.info(f"✅ HubCloud bypassed: {len(links)} links found")
    return links


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
    logger.info("Preparing to send: %s with %d links", title, len(links))

    msg = f"🎬 **{title}**\n\n🎯 **Links:**\n"
    hubcloud_scraped = []

    for link in links:
        domain = re.sub(r"^https?://(www\.)?", "", link).split("/")[0]
        label = domain.split(".")[0][:10]

        msg += f"🔗 **{label}** - {link}\n"

        if "hubcloud" in link:
            scraped = await asyncio.to_thread(bypass_hubcloud, link)
            if scraped:
                hubcloud_scraped.extend(scraped)

    if hubcloud_scraped:
        msg += "\n🚀 **HubCloud Scraped Links** 🚀\n"
        for link in hubcloud_scraped:
            msg += f"• {link}\n"

    await app.send_message(CHANNEL_ID, msg)

@app.on_message(filters.command("up") & filters.user(OWNER_ID))
async def update_url(client, message):
    logger.info(f"Triggered /up by {message.from_user.id} with text: {message.text}")
    
    if len(message.command) < 2:
        await message.reply("❌ Usage: /up <https://newdomain.xyz>")
        return

    new_url = message.command[1].strip()

    if not new_url.startswith("http"):
        await message.reply("❌ That doesn't look like a valid URL.")
        return

    try:
        global BASE_URL
        BASE_URL = new_url
        config["BASE_URL"] = new_url
        save_config(config)

        logger.info(f"✅ BASE_URL updated to: {new_url}")
        await message.reply(f"✅ BASE_URL updated to:\n`{new_url}`")
    except Exception as e:
        logger.error(f"Error in /up: {e}")
        await message.reply(f"❌ Failed to update BASE_URL.\n`{e}`")


@app.on_message(filters.command("hub"))
async def hubcloud_bypass(client, message):
    logger.info(f"Triggered /hub by {message.from_user.id} with text: {message.text}")
    
    if len(message.command) < 2:
        await message.reply("❌ Usage: /hub <hubcloud_link>")
        return

    url = message.command[1]
    if "hubcloud" not in url:
        await message.reply("❌ That doesn't look like a valid HubCloud link.")
        return

    status_msg = await message.reply("⏳ Bypassing HubCloud link, please wait...")

    try:
        loop = asyncio.get_running_loop()
        links = await asyncio.to_thread(bypass_hubcloud, url)

        if not links:
            await status_msg.edit_text("❌ Failed to bypass the HubCloud link.")
            return

        reply = "\n".join(f"• {l}" for l in links)
        await status_msg.edit_text(f"🚀 **Bypassed Links:**\n{reply}")
    except Exception as e:
        logger.error(f"Error in /hub: {e}")
        await status_msg.edit_text(f"❌ Error: {e}")


# --- Monitor Loop ---
async def monitor():
    seen = load_seen()
    logger.info("Starting monitor with %d seen entries", len(seen))

    while True:
        try:
            latest = await asyncio.to_thread(get_latest_movie_links)
            new_items = [u for u in latest if u not in seen]

            if new_items:
                logger.info("Found %d new item(s)", len(new_items))

            for url in new_items:
                title = await asyncio.to_thread(get_title, url)
                server_links = await asyncio.to_thread(get_server_links, url)

                all_links = []
                for s in server_links:
                    extracted = await asyncio.to_thread(extract_final_links, s)
                    all_links.extend(extracted)

                final_links = clean_links(all_links)
                if final_links:
                    await send_to_channel(title, final_links)

                seen.add(url)
                save_seen(seen)

        except Exception as e:
            logger.exception("Error in monitor: %s", e)

        await asyncio.sleep(CHECK_INTERVAL)


async def run_web_async():
    import uvicorn
    config = uvicorn.Config(web_app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    await app.start()
    asyncio.create_task(monitor())  # starts the monitor loop
    await idle()  # keeps the bot running
    await app.stop()

async def run_all():
    await asyncio.gather(
        run_web_async(),
        main()
    )

if __name__ == "__main__":
    asyncio.run(run_all())
