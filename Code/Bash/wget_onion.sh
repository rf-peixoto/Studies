#!/bin/bash

# Function to check if a service is running
check_service_status() {
    if systemctl is-active --quiet "$1"; then
        echo "$1 is active."
        return 0
    else
        echo "$1 is not active."
        return 1
    fi
}

# Start or restart Tor service
restart_tor() {
    echo "Restarting Tor service..."
    sudo systemctl restart tor
    sleep 5
    if check_service_status tor; then
        echo "Tor service restarted successfully."
    else
        echo "Failed to restart Tor service. Exiting."
        exit 1
    fi
}

# Test if Tor is working
test_tor() {
    echo "Testing Tor connection..."
    if curl --socks5 127.0.0.1:9050 --socks5-hostname 127.0.0.1:9050 -s https://check.torproject.org | grep -q "Congratulations. This browser is configured to use Tor."; then
        echo "Tor is working correctly."
    else
        echo "Tor is not working. Exiting."
        exit 1
    fi
}

# Use proxychains with wget to access onion URL
download_with_proxychains() {
    ONION_URL="$1"
    if [[ -z "$ONION_URL" ]]; then
        echo "No onion URL provided. Exiting."
        exit 1
    fi

    LOG_FILE="wget_log.txt"
    echo "Using proxychains to run wget on $ONION_URL..."
    proxychains wget -r "$ONION_URL" -o "$LOG_FILE"
    if [ $? -eq 0 ]; then
        echo "Download successful."
    else
        echo "Download completed with errors. Checking log for failed files..."
        extract_and_retry_errors "$LOG_FILE"
    fi
}

# Extract failed URLs from wget log and retry them
extract_and_retry_errors() {
    LOG_FILE="$1"
    FAILED_URLS="failed_urls.txt"

    # Extract failed URLs from wget log
    grep "ERROR" "$LOG_FILE" | awk '{print $NF}' | sed 's/://g' > "$FAILED_URLS"
    
    if [[ -s "$FAILED_URLS" ]]; then
        echo "Retrying failed downloads..."
        while read -r url; do
            echo "Retrying $url..."
            proxychains wget "$url"
            if [ $? -eq 0 ]; then
                echo "Retry successful for $url."
            else
                echo "Retry failed for $url. Check connection or URL validity."
            fi
        done < "$FAILED_URLS"
    else
        echo "No failed URLs found in the log."
    fi

    # Cleanup
    rm -f "$FAILED_URLS"
}

# Main script execution
restart_tor
test_tor
download_with_proxychains "$1"
