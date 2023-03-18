#!/bin/bash

# Exec each line of .sh file in parallel:
cat $1 | parallel -u
