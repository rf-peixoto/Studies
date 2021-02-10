#!/bin/bash

# Form Parser v.1.0.0

# Identifica formul[arios em arquivos HTML


if [ "$1" == ""  ]
then
    echo "Modo de uso: $0 file.html."
else
   cat "$1" | grep 'method="post"'
fi
