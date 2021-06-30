# ======================================================== #
# TimeKey
# ======================================================== #
from secrets import token_urlsafe
from datetime import datetime
from hashlib import md5

# ======================================================== #
# Class
# ======================================================== #
class TimeKey:
    def __init__(self, password: str, hardness: int):
        """ Generate your client
        :param str password: Your password.
        :param int hardness: How hard will be your code"""
        self.password = md5(password.encode()).hexdigest()
        self.hardness = 3 + hardness # minimum: 3
        self.salt = token_urlsafe(64)

    def split_hash(self, string: str) -> str:
        a = string[0:8]
        b = string[8:16]
        c = string[16:24]
        d = string[24:32]
        return "{0}-{1}-{2}-{3}".format(a, b, c, d)

    def verify_user(self, password: str) -> str:
        """ Verify user password """
        if md5(password.encode()).hexdigest() == self.password:
            return True
        else:
            return False

    def generate_key(self, password: str) -> str:
        """ Generate key """
        if not self.verify_user(password):
            return
        else:
            now = datetime.now()
            day = str(now.day).zfill(self.hardness)
            month = str(now.month).zfill(self.hardness)
            year = str(now.year).zfill(self.hardness)
            hour = str(now.hour).zfill(self.hardness)
            minute = str(now.minute).zfill(self.hardness)
            hashed = md5(str(self.salt + day + month + year + hour + minute).encode()).hexdigest().upper()
            return self.split_hash(hashed)
