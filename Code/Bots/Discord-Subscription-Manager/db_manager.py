import sqlite3
from datetime import datetime

class DBManager:
    # Initialize:
    def __init__(self):
        try:
            self.db = sqlite3.connect("database.db")
            self.cursor = self.db.cursor()
        except Exception as error:
            print("Error while connecting to the database: {0}".format(error))

    # Get actual datetime.now():
    def get_datetime(self):
        date = datetime.now()
        day = date.day
        month = date.month
        year = date.year
        # Update one month:
        if month == 12:
            return '{0}//{1}/{2}'.format(1, day, year + 1)
        else:
            return '{0}/{1}/{2}'.format(month + 1, day, year)

    # Create user:
    def create_user(self, userid: str):
        # 0 means NOT SUBSCRIBER
        create_user = "INSERT INTO users VALUES('{0}', 0, '{1}')".format(userid, self.get_datetime())
        try:
            self.cursor.execute(create_user)
            return True
        except Exception as error:
            print("Error while creating user {0}: {1}".format(userid, error))

    # Get data:
    def get_data(self, userid: str):
        try:
            self.cursor.execute("SELECT * FROM users WHERE userid='{0}'".format(userid))
            return self.cursor.fetchone()
        except Exception as error:
            print("Error on query: {0} : {1}".format(userid, error))

    # Check subscription:
    def check_sub(self, userid):
        try:
            self.cursor.execute("SELECT * FROM users WHERE userid='{0}'".format(userid))
            result = self.cursor.fetchone()[1]
            if result == 1:
                return True
            else:
                return False
        except Exception as error:
            print("Error while checking subscription: {0}".format(error))

    # Change subscription:
    def subscribe_user(self, userid: str):
        # 1 means SUBSCRIBER
        update_sub = "UPDATE users SET subscriber=1 WHERE userid='{0}'".format(userid)
        update_valid_date = "UPDATE users SET valid_until='{0}' WHERE userid='{1}'".format(self.get_datetime(), userid)
        try:
            self.cursor.execute(update_sub)
            self.cursor.execute(update_valid_date)
            return True
        except Exception as error:
            print("Error while trying to subscribe {0}: {1}".format(userid, error))

    # Unsubscribe user:
    def unsubscribe_user(self, userid: str):
        # 0 means NOT SUBSCRIBER
        update_sub = "UPDATE users SET subscriber=0 WHERE userid='{0}'".format(userid)
        update_valid_date = "UPDATE users SET valid_until='{0}' WHERE userid='{1}'".format(self.get_datetime(), userid)
        try:
            self.cursor.execute(update_sub)
            self.cursor.execute(update_valid_date)
            return True
        except Exception as error:
            print("Error while trying to unsubscribe {0}: {1}".format(userid, error))

    # Save changes:
    def save_changes(self):
        try:
            self.db.commit()
            return True
        except Exception as error:
            print("Error while saving: {0}".format(error))

