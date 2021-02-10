#!bin/bash

for i in $cat(password-list.txt)
do
    echo -n $i " ";
    echo -n $i | (Algorítimo*);
done;

# Ou

for i in $cat(password-list.txt); do echo -n $i " "; echo -n $i | (Algorítimo*); > rainbow_tables

Algorítimo* = md5sum, sha256sum, sha384sum, sha512sum...