#!/bin/bash

# Specify the disk partition, e.g., /dev/sda1 or simply /
partition="/"

# Get disk usage and extract the use percentage
disk_usage=$(df -h $partition | awk 'NR==2 {print $5}')

echo "Disk usage for $partition: $disk_usage"
