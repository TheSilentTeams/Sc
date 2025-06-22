import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

SEEN_FILE = "seen.json"
CONFIG_FILE = "config.json"

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
    links = []
    for a in soup.find_all("a", href=True):
        if "/movie/" in a['href'] and a['href'].endswith(".html"):
            links.append(urljoin(base_url, a['href']))
    return sorted(set(links), reverse=True)[:10]

def get_server_links(page_url):
    res = requests.get(page_url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'html.parser')
    servers = []
    for a in soup.find_all('a', href=True):
        if 'howblogs' in a['href'] or 'server' in a.text.lower():
            servers.append(a['href'])
    return servers

def extract_final_links(redirector_url):
    try:
        res = requests.get(redirector_url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        return re.findall(r'https?://[^\s"\']+', text)
    except:
        return []

def clean_links(links):
    return sorted(set([l.strip() for l in links if l.startswith("http")]))

def parse_movie_info(url):
    title = url.split("/")[-1].replace("-", " ").replace(".html", "").strip()
    match = re.search(r'(\[\d+(?:\.\d+)?GB\])', title, re.IGNORECASE)
    size = match.group(1) if match else "Unknown Size"
    return title, size

async def monitor_site(app, channel_id):
    seen = load_seen()
    config = get_config()
    latest = get_latest_movies(config["base_url"])

    new_movies = [url for url in latest if url not in seen]

    for url in new_movies:
        server_links = get_server_links(url)
        all_links = []
        for server in server_links:
            all_links.extend(extract_final_links(server))

        final_links = clean_links(all_links)
        if not final_links:
            continue

        title, size = parse_movie_info(url)
        link_text = "\n".join([f"[Server {i+1}](<{l}>)" for i, l in enumerate(final_links)])
        message = f"🎬 **{title}**\n📦 **Size:** {size}\n\n{link_text}"

        try:
            await app.send_message(channel_id, message, parse_mode=ParseMode.MARKDOWN)
            seen.add(url)
            save_seen(seen)
        except Exception as e:
            print(f"❌ Failed to send message: {e}")
