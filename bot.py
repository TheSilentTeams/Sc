import os
import json
import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from pyrogram import Client, filters, utils
from pyrogram.enums import ChatAction

# --- Config ---
API_ID = int(os.environ.get("API_ID", "25833520"))
API_HASH = os.environ.get("API_HASH", "7d012a6cbfabc2d0436d7a09d8362af7"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7422084781:AAEyqYJBAepuCeXgnZcNVxa_Z7aMDcIiK1s")
OWNER_ID = int(os.environ.get("OWNER_ID", "921365334"))
CHANNEL_ID = -1002739509521

CONFIG_FILE = "config.json"
SEEN_FILE = "seen.json"

# --- Patch peer type ---
def get_peer_type_new(peer_id: int) -> str:
    peer_id_str = str(peer_id)
    if not peer_id_str.startswith("-"):
        return "user"
    elif peer_id_str.startswith("-100"):
        return "channel"
    else:
        return "chat"

utils.get_peer_type = get_peer_type_new

# --- Pyrogram Client ---
app = Client("movie-monitor", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- Config Loader ---
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"BASE_URL": "https://skymovieshd.dance"}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f)

config = load_config()
BASE_URL = config["BASE_URL"]
CHECK_INTERVAL = 300

# --- Seen Tracking ---
def load_seen():
    try:
        with open(SEEN_FILE, 'r') as f:
            return set(json.load(f))
    except:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, 'w') as f:
        json.dump(list(seen), f)

# --- Scraper Functions ---
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

def get_server_links(movie_url):
    res = requests.get(movie_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    servers = []
    for a in soup.find_all('a', href=True):
        if 'howblogs.xyz' in a['href'] or 'server' in a.text.lower():
            servers.append(a['href'])
    return servers

def extract_final_links(redirector_url):
    try:
        res = requests.get(redirector_url, headers={'User-Agent': 'Mozilla/5.0'})
        raw = BeautifulSoup(res.text, 'html.parser').get_text()
        return re.findall(r'https?://[^\s"\']+', raw)
    except:
        return []

def clean_links(links):
    return sorted(list(set(link.strip() for link in links if link.startswith("http"))))

def get_title_and_size(movie_url):
    try:
        res = requests.get(movie_url)
        soup = BeautifulSoup(res.text, 'html.parser')
        title = soup.find("h1")
        size_match = re.search(r'\b(\d+(?:\.\d+)?\s*(?:MB|GB))\b', soup.get_text(), re.I)
        return title.text.strip() if title else "Unknown Title", size_match.group(0) if size_match else "Unknown Size"
    except:
        return "Unknown Title", "Unknown Size"

async def send_to_channel(title, size, links):
    msg = f"🎬 **{title}**\n📦 Size: `{size}`\n\n🎯 **Links:**\n"
    for link in links:
        domain = re.sub(r'^https?://(www\.)?', '', link).split('/')[0]
        domain_label = domain.split('.')[0][:10]  # limit to 10 chars
        msg += f"👍🏻**{domain_label}** - {link}\n"
    await app.send_message(CHANNEL_ID, msg)

# --- Updater Command ---
@app.on_message(filters.command("up") & filters.user(OWNER_ID))
async def update_url(client, message):
    global BASE_URL
    parts = message.text.split()
    if len(parts) != 2:
        await message.reply("❌ Usage: `/up https://newdomain.xyz`", quote=True)
        return

    BASE_URL = parts[1]
    config["BASE_URL"] = BASE_URL
    save_config(config)
    await message.reply(f"✅ BASE_URL updated to: {BASE_URL}")

# --- Monitoring Loop ---
async def monitor():
    seen = load_seen()
    while True:
        print("🔍 Checking for updates...")
        try:
            latest = get_latest_movie_links()
            new_entries = [url for url in latest if url not in seen]

            for url in new_entries:
                title, size = get_title_and_size(url)
                print(f"🎥 Found New: {title}")
                server_links = get_server_links(url)

                all_links = []
                for s in server_links:
                    all_links.extend(extract_final_links(s))

                final_links = clean_links(all_links)
                if final_links:
                    await send_to_channel(title, size, final_links)

                seen.add(url)
                save_seen(seen)

        except Exception as e:
            print("❌ Error during check:", e)

        await asyncio.sleep(CHECK_INTERVAL)

# --- Main ---
import asyncio

if __name__ == "__main__":
    async def main():
        await app.start()
        await monitor()

    asyncio.run(main())
