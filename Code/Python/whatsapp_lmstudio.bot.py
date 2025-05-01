from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import time
import requests

# Set up WhatsApp Web
driver = webdriver.Chrome()  # Use your preferred browser
driver.get('https://web.whatsapp.com/')
input('Scan the QR code and press Enter')

# DeepSeek API endpoint
deepseek_api_endpoint = 'YOUR_DEEPSEEK_API_ENDPOINT'

def process_message(message):
    try:
        response = requests.post(deepseek_api_endpoint, json={'prompt': message})
        deepseek_response = response.json()
        return deepseek_response['response']  # Adjust based on actual API response format
    except Exception as e:
        print(f"Error: {e}")
        return "Error processing your request."

def send_message(chat_name, message):
    try:
        chat = driver.find_element(By.XPATH, f"//span[@title='{chat_name}']")
        chat.click()
        message_box = driver.find_element(By.XPATH, "//div[@contenteditable='true']")
        message_box.send_keys(message)
        message_box.send_keys(Keys.RETURN)
    except Exception as e:
        print(f"Error sending message: {e}")

def get_unread_messages():
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        unread_chats = soup.find_all('span', {'class': '_23LrM'})
        for chat in unread_chats:
            chat_name = chat.find_previous('span', {'class': '_3ko75 _5h6Y_ _3Whw5'}).text
            send_message(chat_name, process_message("example message"))  # You'll need to fetch the actual message
    except Exception as e:
        print(f"Error fetching messages: {e}")

while True:
    get_unread_messages()
    time.sleep(5)
