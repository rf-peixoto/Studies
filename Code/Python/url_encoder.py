import urllib.parse
import sys

# ------------------------------------------------------------------- #
tag = ['<scr', '</scr', '<script>', '</script>', 'ipt>']


def url_encode(payload):
    temp_str = (tag[0] * 2) + tag[2] + (tag[4] * 2)
    temp_str += payload + (tag[1] * 2) + tag[3] + (tag[4] * 2)
    return urllib.parse.quote(temp_str, safe='')

def normal_encode(payload):
    return urllib.parse.quote(payload, safe='')

print(normal_encode(sys.argv[1]))
