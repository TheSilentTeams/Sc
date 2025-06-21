import os
import asyncio
from threading import Thread
from typing import Callable

from fastapi import FastAPI
import uvicorn
from pyrogram import Client, filters

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Configuration ---
API_ID = int(os.environ.get("API_ID", "25833520"))
API_HASH = os.environ.get("API_HASH", "7d012a6cbfabc2d0436d7a09d8362af7")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7422084781:AAGkwQECl0cSFAfx89_vncmgbuKQ0uHxjSs")

# --- Web App using FastAPI ---
web_app = FastAPI()

@web_app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is alive!"}

# --- Telegram Bot ---
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def get_real_download_links(url: str, update_callback: Callable[[str], None] = None) -> list:
    def send_update(text: str):
        if update_callback:
            update_callback(text)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=options)

    try:
        send_update("🌐 Opening URL...")
        driver.get(url)

        wait = WebDriverWait(driver, 15)
        send_update("🔍 Looking for download generator button...")

        button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Generate Direct Download Link')]")))
        button.click()

        send_update("⏳ Waiting for redirection...")
        wait.until(lambda d: "hubcloud" not in d.current_url)

        send_update("🔎 Scanning for final links...")
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
        buttons = driver.find_elements(By.TAG_NAME, "a")

        download_links = []
        for btn in buttons:
            href = btn.get_attribute("href")
            text = (btn.text or "").strip().lower()

            if href and ("download" in text or href.endswith((".mp4", ".mkv", ".zip", ".rar"))):
                download_links.append(href)

        send_update(f"✅ Found {len(download_links)} links.")
        return download_links

    except Exception as e:
        send_update(f"❌ Failed: {e}")
        return []

    finally:
        driver.quit()

@bot.on_message(filters.command("link"))
async def link_handler(client, message):
    if len(message.command) < 2:
        await message.reply("❌ Usage: /link <url>")
        return

    url = message.command[1]
    status_msg = await message.reply("🔄 Starting processing...")

    def update_callback(text: str):
        asyncio.run_coroutine_threadsafe(status_msg.edit_text(text), asyncio.get_event_loop())

    try:
        links = await asyncio.to_thread(get_real_download_links, url, update_callback)

        if links:
            reply = "\n".join(f"• {link}" for link in links)
            await status_msg.edit_text(f"🎯 Final Video Link(s):\n{reply}")
        else:
            await status_msg.edit_text("⚠️ No valid links found.")
    except Exception as e:
        await status_msg.edit_text(f"❌ Error occurred:\n`{e}`")

# --- Run FastAPI in background ---
def run_fastapi():
    config = uvicorn.Config(web_app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())

# --- Main entry point ---
if __name__ == "__main__":
    Thread(target=run_fastapi).start()
    bot.run()
