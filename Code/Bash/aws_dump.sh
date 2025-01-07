#!/bin/bash

# Check if the user provided an S3 bucket URL
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <s3-bucket-url>"
    exit 1
fi

# Get the S3 bucket URL from the argument
s3_url="$1"

# Extract the bucket name from the S3 URL
bucket_name=$(echo "$s3_url" | sed -E 's#s3://([^/]+).*#\1#')

# Check if bucket_name was extracted correctly
if [ -z "$bucket_name" ]; then
    echo "Error: Unable to extract bucket name from the URL."
    exit 1
fi

# Create a folder named after the bucket
output_folder="$bucket_name-backup"
mkdir -p "$output_folder"

# Sync the bucket to the folder
echo "Syncing S3 bucket '$bucket_name' to folder '$output_folder'..."
aws s3 sync "$s3_url" "$output_folder" --no-sign-request

# Check if the sync was successful
if [ $? -eq 0 ]; then
    echo "Backup completed successfully."
else
    echo "Backup failed."
    exit 1
fi
