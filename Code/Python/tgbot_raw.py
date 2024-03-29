import requests
import os

class SimpleTelegramBot:
    def __init__(self, token):
        self.api_url = f"https://api.telegram.org/bot{token}/"
        self.token = token

    def send_message(self, chat_id, text):
        method = 'sendMessage'
        data = {'chat_id': chat_id, 'text': text}
        response = requests.post(self.api_url + method, data=data)
        return response.json()

    def send_file(self, chat_id, file_path):
        method = 'sendDocument'
        with open(file_path, 'rb') as file:
            files = {'document': file}
            data = {'chat_id': chat_id}
            response = requests.post(self.api_url + method, files=files, data=data)
        return response.json()

    def get_chat_info(self, chat_id):
        method = 'getChat'
        data = {'chat_id': chat_id}
        response = requests.post(self.api_url + method, data=data)
        return response.json()

    def get_chat_member_info(self, chat_id, user_id):
        method = 'getChatMember'
        data = {'chat_id': chat_id, 'user_id': user_id}
        response = requests.post(self.api_url + method, data=data)
        return response.json()

    def get_updates(self, offset=None, timeout=30):
        method = 'getUpdates'
        params = {'timeout': timeout, 'offset': offset}
        response = requests.get(self.api_url + method, params=params)
        return response.json()

    def restrict_chat_member(self, chat_id, user_id, permissions):
        method = 'restrictChatMember'
        data = {
            'chat_id': chat_id,
            'user_id': user_id,
            'permissions': permissions
        }
        response = requests.post(self.api_url + method, data=data)
        return response.json()

    def ban_chat_member(self, chat_id, user_id):
        method = 'banChatMember'
        data = {'chat_id': chat_id, 'user_id': user_id}
        response = requests.post(self.api_url + method, data=data)
        return response.json()

    def unban_chat_member(self, chat_id, user_id):
        method = 'unbanChatMember'
        data = {'chat_id': chat_id, 'user_id': user_id}
        response = requests.post(self.api_url + method, data=data)
        return response.json()
