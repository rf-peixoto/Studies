#!/bin/bash

# Grep most interesting findings from nuclei raw output:
grep -r '\[low\]\|\[medium\]\|\[high\]\|\[critical\]\|\[cve\]' $1
