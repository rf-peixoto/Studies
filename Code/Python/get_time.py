from datetime import datetime

class GetTime:
    def __init__(self):
        return

    def get_string(self):
        time = datetime.now()
        return "{0}/{1}/{2} {3}:{4}".format(time.day, time.month, time.year, time.hour, time.minute)
