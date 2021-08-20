import urllib.parse
import sys

# ------------------------------------------------------------------- #
tag = ['<scr', '</scr', '<script>', '</script>', 'ipt>']


def url_encode(payload):
    temp_str = (tag[0] * 2) + tag[2] + (tag[4] * 2)
    temp_str += payload + (tag[1] * 2) + tag[3] + (tag[4] * 2)
    return urllib.parse.quote(temp_str, safe='')

def normal_encode(payload):
    # You can also use quote_plus to convert blank spaces into '+' signs.
    # Ex: Test abc = Test+abc
    return urllib.parse.quote_plus(payload, safe='') # quote or quote_plus

print(normal_encode(sys.argv[1]))
