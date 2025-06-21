from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def get_real_download_links(url):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        time.sleep(5)

        wait = WebDriverWait(driver, 20)
        button = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(text(), 'Generate Direct Download Link')]")))
        button.click()

        time.sleep(6)
        final_url = driver.current_url

        download_links = []

        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
        buttons = driver.find_elements(By.TAG_NAME, "a")

        for btn in buttons:
            try:
                text = btn.text.strip().lower()
                href = btn.get_attribute("href")
                if text and "download" in text or (href and any(href.endswith(ext) for ext in [".mkv", ".mp4", ".zip"])):
                    download_links.append(href)
            except Exception:
                continue

        return download_links

    except Exception as e:
        return []

    finally:
        driver.quit()
