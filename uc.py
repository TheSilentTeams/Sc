from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_real_download_links(url):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--blink-settings=imagesEnabled=false")  # 🖼️ Disable images
    options.add_argument("--disable-blink-features=AutomationControlled")  # 🚫 Less bot detection

    driver = webdriver.Chrome(options=options)

    try:
        driver.set_page_load_timeout(20)
        driver.get(url)

        wait = WebDriverWait(driver, 15)

        # Wait for the download generator button
        button = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(text(), 'Generate Direct Download Link')]")))
        button.click()

        # Wait for redirect to complete
        wait.until(lambda d: "hubcloud" not in d.current_url)

        # Gather all <a> elements
        links = wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))

        download_links = []
        for link in links:
            href = link.get_attribute("href")
            text = (link.text or "").strip().lower()

            if href and (
                "download" in text or
                any(href.endswith(ext) for ext in [".mp4", ".mkv", ".zip", ".rar"])
            ):
                download_links.append(href)

        return download_links

    except Exception as e:
        print(f"[!] Error: {e}")
        return []

    finally:
        driver.quit()
