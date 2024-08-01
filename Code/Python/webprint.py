from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import os
import time

# Function to set up the Chrome WebDriver with options
def setup_driver(user_agent, cookies):
    options = Options()
    options.add_argument(f"user-agent={user_agent}")
    options.add_argument("--headless")  # Run in headless mode for faster performance
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    driver.delete_all_cookies()
    
    if cookies:  # Add cookies only if they are provided
        for cookie in cookies:
            driver.add_cookie(cookie)
    
    return driver

# Function to take screenshot of a URL
def capture_screenshot(url, driver, output_folder):
    driver.get(url)
    
    # Wait for redirects and page to load completely
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    
    # Capture screenshot
    screenshot_name = url.replace('https://', '').replace('http://', '').replace('/', '_') + ".png"
    screenshot_path = os.path.join(output_folder, screenshot_name)
    driver.save_screenshot(screenshot_path)
    print(f"Screenshot saved as {screenshot_path}")

# Main function to process the list of URLs
def main():
    # Read URLs from a file
    with open('urls.txt', 'r') as file:
        urls = [line.strip() for line in file.readlines()]
    
    # Ensure URLs are correctly formatted
    formatted_urls = ["http://" + url if not (url.startswith("http://") or url.startswith("https://")) else url for url in urls]
    
    # Define user agent and cookies
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36"
    cookies = [
        # Example cookie
        # {'name': 'cookie_name', 'value': 'cookie_value', 'domain': 'domain.com'},
        # Add more cookies if needed, or leave the list empty
    ]
    
    # Create output folder if it doesn't exist
    output_folder = 'img'
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    driver = setup_driver(user_agent, cookies)
    
    for url in formatted_urls:
        try:
            capture_screenshot(url, driver, output_folder)
            time.sleep(1)  # Delay between requests to avoid being flagged as a bot
        except Exception as e:
            print(f"Failed to capture screenshot for {url}: {e}")
    
    driver.quit()

if __name__ == "__main__":
    main()
