#!/bin/bash

# Work in progress:
lynx --dump https://crt.sh/?q=%25.$1 # | grep -E '(?:http[s]?:\/\/)?(?:www\.)?([^/\n\r\s]+\.[^/\n\r\s]+)(?:/)?(\w+)?'
