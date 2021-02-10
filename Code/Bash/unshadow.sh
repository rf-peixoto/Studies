#!/bin/bash

# Formatar arquivo 'shadow': 
unshadow /etc/passwd /etc/shadow > shadow_hashes.txt
john shadow_hashes.txt
