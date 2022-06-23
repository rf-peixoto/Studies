from datetime import datetime
from time import sleep
import pywhatkit

class WhatBot:
    def __init__(self):
        self.numbers = []
        self.msg_delay = 1

    def add_number(self, number: str):
        self.numbers.append(number)

    def remove_number(self, number: str):
        try:
            self.numbers.remove(number)
        except Exception as error:
            print(error)

    def get_time(self) -> dict:
        time = datetime.now()
        tmp = {'hour':0, 'min':0}
        if time.minute = 59:
            tmp['hour'] = time.hour += 1
            tmp['minute'] = 0
        else:
            tmp['hour'] = time.hour
            tmp['minute'] = time.minute += 1

    def send_msg(self, msg: str):
        tmp = self.get_time()
        for n in self.numbers:
            pywhatkit.sendwhatsmsg(n, msg, tmp['hour'], tmp['minute'], tab_close=True, close_time=2)
            sleep(self.msg_delay)

    def send_img(self, img_path: str):
        tmp = self.get_time()
        for n in self.numbers:
            pywhatkit.sendwhats_image(n, img_path, tmp['hour'], tmp['minute'], tab_close=True, close_time=2)
            sleep(self.msg_delay)
