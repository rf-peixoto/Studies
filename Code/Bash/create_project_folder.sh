#!/bin/bash

project_name=$1

# Create project:
mkdir -p $project_name/{build/,include/,results/{bin/,lib/},src/,tests/}

# Create files:
cd $project_name
touch README.md CMakeLists.txt
