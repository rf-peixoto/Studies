#!/bin/bash

# Schedule a job to write "Hello, world!" into a file at 12:45 PM
echo "echo 'Hello, world!' > /tmp/test.txt" | at 12:45 pm

# Schedule a script to run at 9:30 AM on the next Friday
echo "/path/to/script.sh" | at 9:30 AM Fri

# View scheduled jobs
atq

# Example: You need to know job numbers to use atrm, uncomment the next line after checking atq
# atrm <job_number>

# Schedule a job with interactive input at 11:00 PM today (uncomment to use interactively)
# at 11:00 PM today

# Schedule a job to copy a file in one hour from the current time
echo "cp /files/data.txt /backup/" | at now + 1 hour

# Schedule a command to create a tar.gz archive at midnight tomorrow
echo "tar -czf /backup/my_files.tar.gz /home/user/Documents" | at midnight tomorrow

