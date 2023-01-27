#!/bin/bash

ctrl_c() {
  echo "You cannot kill me."
}

# Trap signal:
trap ctrl_c SIGINT SIGTERM

while true; do
  # Put your code here.
done
