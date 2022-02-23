#!/bin/bash
# Usage: ./create_project_folder.sh project_name

# Create project:
mkdir -p $1/{build/,include/,results/{bin/,lib/},src/,tests/}

# Create files:
cd $1
touch README.md CMakeLists.txt
