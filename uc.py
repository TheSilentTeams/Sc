from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_real_download_links(url, status_msg=None):
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    import asyncio

    def send_update(text):
        if status_msg:
            asyncio.run_coroutine_threadsafe(status_msg.edit_text(text), asyncio.get_event_loop())

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

