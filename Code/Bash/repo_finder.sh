#!/bin/bash

# Directory to search for git repositories
base_dir="/home/user/

# Output file to store repository URLs
output_file="/home/user/repo_urls.txt"
#touch $output_file

# Find all .git/config files and extract the repository URLs
find "$base_dir" -type f -name "config" -path "*/.git/*" -exec grep -Po "(?<=url = ).*" {} \; > "$output_file"

echo "Repository URLs exported to $output_file"
