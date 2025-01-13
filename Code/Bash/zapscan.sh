#!/bin/bash

# Configuration
ZAP_HOST="127.0.0.1"
ZAP_PORT="8080"
ZAP_URL="http://$ZAP_HOST:$ZAP_PORT"
ZAP_API_KEY="YOUR_API_KEY"
SCAN_URL=$1
REPORT_FILE="zap_report.html"

if [[ -z "$SCAN_URL" ]]; then
  echo "Usage: $0 <url>"
  exit 1
fi

# Check if ZAP is running
if ! curl -s "$ZAP_URL" > /dev/null; then
  echo "ZAP is not running. Starting ZAP in daemon mode..."
  zap.sh -daemon -port "$ZAP_PORT" -host "$ZAP_HOST" -config api.key="$ZAP_API_KEY"
  sleep 10 # Allow ZAP some time to start
fi

# Start the scan
echo "Starting scan on URL: $SCAN_URL"
SCAN_ID=$(curl -s "$ZAP_URL/JSON/ascan/action/scan/" \
  --data-urlencode "url=$SCAN_URL" \
  --data-urlencode "recurse=true" \
  --data-urlencode "inScopeOnly=false" \
  --data-urlencode "apikey=$ZAP_API_KEY" \
  | jq -r '.scan')

if [[ "$SCAN_ID" == "null" || -z "$SCAN_ID" ]]; then
  echo "Failed to start scan. Exiting."
  exit 1
fi

# Monitor the scan progress
while :; do
  PROGRESS=$(curl -s "$ZAP_URL/JSON/ascan/view/status/" \
    --data-urlencode "apikey=$ZAP_API_KEY" \
    | jq -r '.status')
  echo "Scan progress: $PROGRESS%"
  
  if [[ "$PROGRESS" -eq 100 ]]; then
    echo "Scan completed."
    break
  fi
  
  sleep 5
done

# Export the report
echo "Exporting the report to $REPORT_FILE"
curl -s "$ZAP_URL/OTHER/core/other/htmlreport/" \
  --data-urlencode "apikey=$ZAP_API_KEY" \
  -o "$REPORT_FILE"

if [[ $? -eq 0 ]]; then
  echo "Report saved as $REPORT_FILE"
else
  echo "Failed to save report."
fi
