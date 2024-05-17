#!/bin/bash

# Input file containing the list of domains
INPUT_FILE="domains.txt"

# Output CSV file
OUTPUT_FILE="domain_ips.csv"

# Function to get the IP of a domain
get_ip() {
  domain=$1
  ip=$(dig +short $domain | tail -n 1)
  echo $ip
}

# Create or clear the output file
echo "Domain,IP" > $OUTPUT_FILE

# Check if input file exists
if [[ ! -f $INPUT_FILE ]]; then
  echo "Input file $INPUT_FILE does not exist."
  exit 1
fi

# Read domains from the input file and get their IPs
while IFS= read -r domain; do
  ip=$(get_ip $domain)
  echo "$domain,$ip" >> $OUTPUT_FILE
done < "$INPUT_FILE"

echo "IP addresses saved to $OUTPUT_FILE"
