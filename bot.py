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
from pyrogram import idle
from pyrogram import Client, filters, utils
from playwright.async_api import async_playwright
import nest_asyncio
nest_asyncio.apply()
import tempfile
import time
from pyrogram.errors import FloodWait
from typing import Dict, List

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

async def bypass_hubcloud(raw_url: str) -> Dict[str, str]:
    collected_links = {}
    final_links = {}
    url = raw_url.split("Views")[0].strip()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            print(f"🌐 Visiting HubCloud URL: {url}")
            await page.goto(url, timeout=45000)
            await page.wait_for_load_state("domcontentloaded")

            # Click "Generate" button
            generate_btn = page.locator("a, button").filter(has_text=re.compile("generate", re.I))
            if await generate_btn.count() == 0:
                print("❌ No 'Generate' button found.")
                return {}

            print("⚙️ Clicking 'Generate' button...")
            await generate_btn.nth(0).click()
            await page.wait_for_timeout(2000)

            # Click "Generate Direct Download Link"
            direct_btn = page.locator("a, button").filter(
                has_text=re.compile("Generate Direct Download Link", re.I)
            )
            if await direct_btn.count() == 0:
                print("❌ 'Generate Direct Download Link' not found.")
                return {}

            gamerxyt_url = await direct_btn.nth(0).get_attribute("href")
            if gamerxyt_url:
                print(f"➡️ Visiting GamerXyt link: {gamerxyt_url}")
                await page.goto(gamerxyt_url, timeout=45000)
            else:
                print("➡️ Clicking fallback Direct Download button...")
                await direct_btn.nth(0).click()

            await page.wait_for_load_state("domcontentloaded")

            # Filter relevant download buttons (not junk)
            print("🔍 Scanning for download buttons...")
            buttons = await page.locator("a, button").all()

            for btn in buttons:
                text = (await btn.inner_text() or "").strip()
                href = await btn.get_attribute("href")

                # Avoid noise buttons
                if not href or not text:
                    continue
                if re.search(r'vpn|idm|ida|telegram|login|how\s?\?|tutorial', text, re.I):
                    continue
                if not re.search(r'download', text, re.I):
                    continue

                collected_links[text] = href

            # Now handle 10Gbps link visit
            for text, href in collected_links.items():
                if "10gbps" in text.lower():
                    print(f"🕵️ Visiting intermediate link for '{text}'...")
                    sub_page = await context.new_page()
                    try:
                        await sub_page.goto(href, timeout=45000)
                        await sub_page.wait_for_load_state("domcontentloaded")

                        print("🔬 [10Gbps] Inspecting buttons and DOM inside...")
                        sub_buttons = await sub_page.locator("a, button").all()

                        for sb in sub_buttons:
                            label = (await sb.inner_text() or "").strip()
                            final_href = await sb.get_attribute("href")
                            print(f"    ├── Button: {label} → {final_href}")
                            if final_href and "download" in label.lower():
                                print(f"✅ Direct download link found: {final_href}")
                                final_links[text] = final_href
                                break
                        else:
                            print("⚠️ No clear download button found, keeping original.")
                            final_links[text] = href
                    except Exception as err:
                        print(f"❌ Error in 10Gbps page: {err}")
                        final_links[text] = href
                    finally:
                        await sub_page.close()
                else:
                    final_links[text] = href

    except Exception as e:
        print(f"❌ Error during extraction: {e}")
    return final_links


async def notify_debug_failure(url, error, files):
    try:
        caption = f"❌ **HubCloud Bypass Failed**\nURL: `{url}`\nError: `{error}`"
        await app.send_message(OWNER_ID, caption)
        for path in files:
            if os.path.exists(path):
                if path.endswith(".png"):
                    await app.send_photo(OWNER_ID, path)
                else:
                    await app.send_document(OWNER_ID, path)
    except FloodWait as fw:
        logger.warning(f"Flood wait: sleeping for {fw.value} seconds")
        await asyncio.sleep(fw.value)
        await notify_debug_failure(url, error, files)
    except Exception as e:
        logger.error(f"Failed to send debug files to OWNER_ID: {e}")



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
    msg = f"🎬 `{title}`\n\n🎯 **Links:**\n"
    hubcloud_scraped = []

    for link in links:
        domain = re.sub(r"^https?://(www\.)?", "", link).split("/")[0]
        label = domain.split(".")[0][:10]

        msg += f"[{label}]({link})\n"

        if "hubcloud" in link:
            scraped = await bypass_hubcloud(link)
            if scraped:
                hubcloud_scraped.extend(scraped)

    if hubcloud_scraped:
        msg += "\n🚀 **HubCloud Scraped Links** 🚀\n"
        for item in hubcloud_scraped:
            # Support both raw links or tuples (label, link)
            if isinstance(item, tuple) and len(item) == 2:
                label, link = item
                msg += f"[{label}]({link})\n"
            else:
                domain = re.sub(r"^https?://(www\.)?", "", item).split("/")[0]
                label = domain.split(".")[0][:10]
                msg += f"[{label}]({item})\n"

    # Footer
    msg += "\n> 🌐 Scraped from [SkyMoviesHD](https://telegram.me/Silent_Bots)"

    await app.send_message(
        CHANNEL_ID,
        msg,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


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
        links = await bypass_hubcloud(url)

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
