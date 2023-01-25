#!/bin/bash

var="Something here"
# Print if it was defined:
echo ${var:-not found}

unset var
echo ${something:-not found}

# Define it was not defined before:

echo ${var:=Works}
echo ${var:-not found}

# Show parts of string:
echo ${var:2:4}
echo ${var:2:-1}
echo ${var: -5}
echo ${var: -1: 1}

# Arrays:
array=(uno dos tres)
echo ${array[1]}
echo ${array}

# Count characteres:
echo ${#array[0]}

# Using wildchars:
# ! = prefix
# * = anything:
varD="Second variable"
echo ${!var*}

# Cut value similar to sed:
vT="Terminal"
echo ${vT#Ter}
echo ${vT%nal}

# Replace:
echo ${vT/min/lololo}
# Replace all:
vQ="abaCadae"
echo ${vQ//a/lololo}

# Change case:
echo ${vQ~}
echo ${vQ~~}
echo ${vQ^}
echo ${vQ^^}
echo ${vQ,}
echo ${vQ,,}

# See value:
echo ${vQ@A}
echo ${vQ@Q}

echo ${vT}s
