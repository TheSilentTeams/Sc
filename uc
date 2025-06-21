import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def get_links(url: str) -> list:
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--headless=new')

    driver = uc.Chrome(options=options)
    links_found = []

    try:
        driver.get(url)
        print("[*] Loaded page")
        time.sleep(5)

        wait = WebDriverWait(driver, 20)

        # Step 1: Click the "Generate Direct Download Link" button
        button = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(text(), 'Generate Direct Download Link')]")
        ))
        print(f"[*] Found button: {button.text.strip()}")
        button.click()

        # Step 2: Wait for redirection to a new host (e.g., gamerxyt or similar)
        print("[*] Step 2: Waiting for redirection...")
        time.sleep(6)
        final_url = driver.current_url
        print(f"[+] Redirected to: {final_url}")

        # Step 3: Wait and scan for buttons/links
        wait.until(EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
        buttons = driver.find_elements(By.TAG_NAME, "a")

        for btn in buttons:
            text = btn.text.strip().lower()
            href = btn.get_attribute("href")

            if not href:
                continue

            if "download" in text or href.endswith((".mkv", ".mp4", ".zip")):
                links_found.append(href)

    except Exception as e:
        print(f"[!] Error: {e}")
    finally:
        driver.quit()

    return links_found


# For standalone testing (optional)
if __name__ == "__main__":
    test_url = "https://hubcloud.one/drive/uznt4rtd4yz4lgz"
    results = get_links(test_url)

    print("\n🎯 Final Video Link(s):")
    for link in results:
        print(f"• {link}")
