#!/bin/bash

# Replace these variables with appropriate values
directory_to_compress="/path/to/directory"  # Replace with the directory you want to compress
compressed_filename="compressed_directory.tar.gz"
recipient_email="recipient@example.com"
sender_email="sender@example.com"
email_subject="Compressed Directory"

# Step 1: Compress the directory
tar -czf "$compressed_filename" "$directory_to_compress"

# Step 2: Send the compressed file via email
if [ -f "$compressed_filename" ]; then
    echo "Sending the compressed file via email..."
    echo "Please find the compressed directory attached." | mail -s "$email_subject" -a "$compressed_filename" -r "$sender_email" "$recipient_email"
    echo "Email sent successfully."
else
    echo "Compression failed. Please check if the directory exists and try again."
fi

# Step 3: Clean up (optional, uncomment the line below if you want to remove the compressed file after sending the email)
# rm "$compressed_filename"
