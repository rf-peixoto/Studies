#!/bin/bash

ctrl_c() {
  echo "You cannot kill me."
}

# Trap signal:
trap ctrl_c SIGINT SIGTERM

while true; do
  # Put your code here.
done


# Ignore interruption signals:
nohup while true; do
  # Do stuff

  # Do not interrupt this download:
  nohup wget https://sample.com/large_stuff &
done;
