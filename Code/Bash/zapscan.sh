#!/bin/bash

# Configuration
ZAP_HOST="127.0.0.1"
ZAP_PORT="8080"
ZAP_URL="http://$ZAP_HOST:$ZAP_PORT"
ZAP_API_KEY="YOUR_API_KEY"
DEFAULT_REPORT_FORMAT="html"
SCAN_DELAY=2  # Delay in seconds between status checks
VERBOSE=true  # Enable verbose output

# Colors for output
GREEN="\e[32m"
RED="\e[31m"
YELLOW="\e[33m"
RESET="\e[0m"

# Usage instructions
function usage() {
    echo -e "${YELLOW}Usage: $0 -u <url> [-m <scan_mode>] [-r <report_format>] [-d <scan_delay>] [--no-recurse] [--in-scope]${RESET}"
    echo "  -u, --url          Target URL to scan"
    echo "  -m, --mode         Scan mode: 'passive' or 'aggressive' (default: aggressive)"
    echo "  -r, --report       Report format: 'html' (default) or 'json'"
    echo "  -d, --delay        Time (in seconds) between progress updates (default: 2)"
    echo "  --no-recurse       Disable recursive scanning"
    echo "  --in-scope         Only scan items in the current scope"
    echo "  -v, --verbose      Enable verbose output"
    echo "  -h, --help         Display this help message"
}

# Default settings
SCAN_MODE="aggressive"
RECURSE=true
IN_SCOPE=false
REPORT_FORMAT="$DEFAULT_REPORT_FORMAT"

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -u|--url) SCAN_URL="$2"; shift ;;
        -m|--mode) SCAN_MODE="$2"; shift ;;
        -r|--report) REPORT_FORMAT="$2"; shift ;;
        -d|--delay) SCAN_DELAY="$2"; shift ;;
        --no-recurse) RECURSE=false ;;
        --in-scope) IN_SCOPE=true ;;
        -v|--verbose) VERBOSE=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo -e "${RED}Unknown option: $1${RESET}"; usage; exit 1 ;;
    esac
    shift
done

# Validate inputs
if [[ -z "$SCAN_URL" ]]; then
    echo -e "${RED}Error: Target URL is required.${RESET}"
    usage
    exit 1
fi

if ! [[ "$SCAN_MODE" =~ ^(passive|aggressive)$ ]]; then
    echo -e "${RED}Error: Invalid scan mode. Use 'passive' or 'aggressive'.${RESET}"
    exit 1
fi

if ! [[ "$REPORT_FORMAT" =~ ^(html|json)$ ]]; then
    echo -e "${RED}Error: Invalid report format. Use 'html' or 'json'.${RESET}"
    exit 1
fi

# Check if ZAP is running
if ! curl -s "$ZAP_URL" &>/dev/null; then
    echo -e "${YELLOW}ZAP is not running. Starting ZAP in daemon mode...${RESET}"
    zap.sh -daemon -nostdout -port "$ZAP_PORT" -config api.key="$ZAP_API_KEY"
    sleep 10  # Allow ZAP some time to start
fi

echo -e "${GREEN}Target URL: $SCAN_URL${RESET}"

# Start the scan
if [[ "$SCAN_MODE" == "passive" ]]; then
    echo -e "${GREEN}Starting spider (passive mode) on URL: $SCAN_URL${RESET}"
    SPIDER_ID=$(curl -s "$ZAP_URL/JSON/spider/action/scan/" \
      --data-urlencode "url=$SCAN_URL" \
      --data-urlencode "recurse=$RECURSE" \
      --data-urlencode "apikey=$ZAP_API_KEY" \
      | jq -r '.scan')

    if [[ "$SPIDER_ID" == "null" || -z "$SPIDER_ID" ]]; then
        echo -e "${RED}Failed to start spider scan. Exiting.${RESET}"
        exit 1
    fi

    echo -e "${GREEN}Spider started (ID: $SPIDER_ID). Monitoring progress...${RESET}"
    while :; do
        SPIDER_PROGRESS=$(curl -s "$ZAP_URL/JSON/spider/view/status/" \
          --data-urlencode "scanId=$SPIDER_ID" \
          --data-urlencode "apikey=$ZAP_API_KEY" \
          | jq -r '.status')

        echo -ne "Spider progress: ${SPIDER_PROGRESS}%\r"

        if [[ "$SPIDER_PROGRESS" -eq 100 ]]; then
            echo -e "\n${GREEN}Spider scan completed.${RESET}"
            break
        fi
        sleep "$SCAN_DELAY"
    done

    echo -e "${YELLOW}Passive scanning is performed automatically by ZAP on discovered URLs.${RESET}"
else
    echo -e "${GREEN}Starting aggressive scan on URL: $SCAN_URL${RESET}"
    SCAN_ID=$(curl -s "$ZAP_URL/JSON/ascan/action/scan/" \
      --data-urlencode "url=$SCAN_URL" \
      --data-urlencode "recurse=$RECURSE" \
      --data-urlencode "inScopeOnly=$IN_SCOPE" \
      --data-urlencode "apikey=$ZAP_API_KEY" \
      | jq -r '.scan')

    if [[ "$SCAN_ID" == "null" || -z "$SCAN_ID" ]]; then
        echo -e "${RED}Failed to start aggressive scan. Exiting.${RESET}"
        exit 1
    fi

    echo -e "${GREEN}Active scan started (ID: $SCAN_ID). Monitoring progress...${RESET}"
    while :; do
        PROGRESS=$(curl -s "$ZAP_URL/JSON/ascan/view/status/" \
          --data-urlencode "scanId=$SCAN_ID" \
          --data-urlencode "apikey=$ZAP_API_KEY" \
          | jq -r '.status')

        ALERTS=$(curl -s "$ZAP_URL/JSON/core/view/alertsSummary/" \
          --data-urlencode "baseurl=$SCAN_URL" \
          --data-urlencode "apikey=$ZAP_API_KEY" \
          | jq -r '.high | . + " High, " + (.medium | tostring) + " Medium, " + (.low | tostring) + " Low Alerts"')

        echo -ne "Scan progress: ${PROGRESS}% - Alerts: ${ALERTS}\r"

        if [[ "$PROGRESS" -eq 100 ]]; then
            echo -e "\n${GREEN}Aggressive scan completed.${RESET}"
            break
        fi

        sleep "$SCAN_DELAY"
    done
fi

# Export the report
REPORT_FILE="zap_report.$REPORT_FORMAT"
echo -e "${GREEN}Exporting the report to $REPORT_FILE${RESET}"

if [[ "$REPORT_FORMAT" == "html" ]]; then
    curl -s "$ZAP_URL/OTHER/core/other/htmlreport/" \
      --data-urlencode "apikey=$ZAP_API_KEY" \
      -o "$REPORT_FILE"
else
    curl -s "$ZAP_URL/JSON/core/view/alerts/" \
      --data-urlencode "apikey=$ZAP_API_KEY" \
      --data-urlencode "baseurl=$SCAN_URL" \
      -o "$REPORT_FILE"
fi

if [[ $? -eq 0 ]]; then
    echo -e "${GREEN}Report saved: $REPORT_FILE${RESET}"
else
    echo -e "${RED}Failed to save the report.${RESET}"
fi
