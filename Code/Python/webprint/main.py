import json
import logging
import os
import time
import chardet
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from colorama import Fore, Style
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup logging
logging.basicConfig(filename='script.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Function to set up the Chrome WebDriver with options
def setup_driver(user_agent, cookies):
    options = Options()
    options.add_argument(f"user-agent={user_agent}")
    options.add_argument("--headless")  # Run in headless mode for faster performance
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920x1080")
    options.add_argument("--log-level=3")  # Suppress driver output

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
    print(Fore.GREEN + f"Screenshot saved as {screenshot_path}" + Style.RESET_ALL)
    logging.info(f"Screenshot saved as {screenshot_path}")

# Function to process a single URL
def process_url(url, user_agent, cookies, output_folder):
    driver = setup_driver(user_agent, cookies)
    try:
        capture_screenshot(url, driver, output_folder)
    except Exception as e:
        logging.error(f"Failed to capture screenshot for {url}: {e}", exc_info=True)
        failed_message = f"Screenshot failed at {url}"
        print(Fore.RED + failed_message + Style.RESET_ALL)
        with open('failed_urls.txt', 'a') as f:
            f.write(url + '\n')
    finally:
        driver.quit()

# Function to detect file encoding
def detect_encoding(file_path):
    with open(file_path, 'rb') as file:
        raw_data = file.read()
    result = chardet.detect(raw_data)
    return result['encoding']

# Main function to process the list of URLs
def main():
    # Read configuration from a file
    with open('config.json', 'r') as file:
        config = json.load(file)

    # Detect encoding of the URLs file
    urls_file_path = 'urls.txt'
    encoding = detect_encoding(urls_file_path)
    
    # Read URLs from the file with the detected encoding
    with open(urls_file_path, 'r', encoding=encoding) as file:
        urls = [line.strip() for line in file.readlines()]
    
    # Ensure URLs are correctly formatted
    formatted_urls = ["http://" + url if not (url.startswith("http://") or url.startswith("https://")) else url for url in urls]
    
    # Create output folder if it doesn't exist
    output_folder = 'img'
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    user_agent = config['user_agent']
    cookies = config['cookies']
    delay = config.get('delay', 1)
    max_workers = config.get('max_workers', 4)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_url, url, user_agent, cookies, output_folder) for url in formatted_urls]
        for future in as_completed(futures):
            future.result()  # Ensure exceptions are raised
    
    time.sleep(delay)  # Delay between batches

if __name__ == "__main__":
    main()
