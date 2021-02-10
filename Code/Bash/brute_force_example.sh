#!/bin/bash

for user in $(cat userlist.txt):
do:
  for pass in $(cat passlist.txt):
  do:
    [PROTOCOL] $user $pass;
  done;
done;
