from datetime import datetime
import sqlite3

# Connect to Database:
db = sqlite3.connect("log.db")
cursor = db.cursor()

# Get timestamp:
def get_time_stamp():
    stamp = datetime.now()
    time = "{0}:{1}".format(str(stamp.hour).zfill(2), str(stamp.minute).zfill(2))
    date = "{0}{1}{2}".format(str(stamp.month).zfill(2), str(stamp.day).zfill(2), str(stamp.year).zfill(2))
    return "{0} - {1}".format(date, time)

# Insert data on DB:
def insert(username: str, action: str):
    command = "INSERT INTO action_log (time, user, action) VALUES('{0}', '{1}', '{2}')".format(get_time_stamp(), username, action)
    try:
        cursor.execute(command)
    except Exception as error:
        print(error)

# Test:
insert("test_1", "initialize")
insert("test_1", "do some stuff")
insert("test_2", "quit")
db.commit()
db.close()
