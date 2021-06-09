from secrets import token_urlsafe
import configparser

config = configparser.ConfigParser()
config['DEFAULT'] = {'AUTOCONNECT': str(False),
                     'PUBLIC_ACC': str(False)}

config['USER'] = {}
config['USER']['USERNAME'] = 'username'
config['USER']['IS_PAID'] = str(False)

config['CONNECTION'] = {}
config['CONNECTION']['IP'] = '127.0.0.1'

with open('setup.ini', 'w') as config_file:
    config.write(config_file)
