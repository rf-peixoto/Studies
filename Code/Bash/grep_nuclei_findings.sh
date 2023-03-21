#!/bin/bash

# Grep most interesting findings from nuclei raw output:
grep --color='auto' -r '\[low\]\|\[medium\]\|\[high\]\|\[critical\]\|\[cve\]' $1
