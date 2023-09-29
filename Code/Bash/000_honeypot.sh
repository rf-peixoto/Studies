#!/bin/bash

# Configuration
CONFIG_FILE="./000_honeypot_config.cfg"
source $CONFIG_FILE

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "Please install 'jq' to run this script."
    exit 1
fi

echo "[*] Starting honeypot on port $HONEYPOT_PORT..."

while :
do
    RANDOM_RESPONSE=${RESPONSES[$RANDOM % ${#RESPONSES[@]}]}
    echo -e "$RANDOM_RESPONSE" | nc -l -p $HONEYPOT_PORT -q 1 -n -w 3 | while IFS= read -r line; do
        TIMESTAMP=$(date '+%Y-%m-%dT%H:%M:%S')

        if [[ "$line" =~ ^Host: ]]; then
            headers["source_ip"]=$(echo $line | awk '{print $2}')
        fi

        # Capture all browser-related headers
        if [[ "$line" =~ ^(User-Agent|Accept|Referer|Accept-Language|Cookie): ]]; then
            key=$(echo $line | awk -F': ' '{print $1}' | tr '-' '_')
            value=$(echo $line | awk -F': ' '{print $2}')
            headers["$key"]="$value"
        fi

        # If we have collected the data and reached the end of headers, save to the log file
        if [[ -z "$line" && -n "${headers[source_ip]}" ]]; then
            log_entry=$(echo "{}" | jq --arg ts "$TIMESTAMP" '.timestamp=$ts' | jq --arg ip "${headers[source_ip]}" '.source_ip=$ip')

            for header in "${!headers[@]}"; do
                if [[ $header != "source_ip" ]]; then
                    log_entry=$(echo $log_entry | jq --arg key "$header" --arg value "${headers[$header]}" '.[$key]=$value')
                fi
            done

            echo $log_entry >> $LOGFILE
            unset headers
            declare -A headers
        fi

    done
done
