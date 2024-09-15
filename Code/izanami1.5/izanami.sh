#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# ------------------------------------------------------- #
# Author: https://www.linkedin.com/in/rf-peixoto/
# a.k.a Corvo
# ------------------------------------------------------- #

VERSION="v1.5.0"

# ------------------------------------------------------- #
# Load Configuration
# ------------------------------------------------------- #
CONFIG_FILE="./config.cfg"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo -e "${RED}Error:${CLEAR} Configuration file 'config.cfg' not found."
  exit 1
fi

# Load configuration variables
source "$CONFIG_FILE"

# ------------------------------------------------------- #
# Setup colors:
# ------------------------------------------------------- #
CLEAR='\033[0m'
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'

# ------------------------------------------------------- #
# Dependencies
# ------------------------------------------------------- #
#DEPENDENCIES=(./assetfinder ./subfinder ./nuclei ./rustscan ./naabu ./nmap ./katana ./sslyze ./sqlmap ./zap-cli jq notify-send 7z)

#for cmd in "${DEPENDENCIES[@]}"; do
#  if [[ ! -x "$cmd" ]]; then
#    echo -e "${RED}Error:${CLEAR} Dependency '$cmd' is not executable or not found. Please ensure it is present and has execute permissions."
#    exit 1
#  fi
#done

# ------------------------------------------------------- #
# Usage:
# ------------------------------------------------------- #
usage() {
  cat <<EOF
izanami ${VERSION}
Usage: ${0##*/} domain

Options:
  -h, --help        Show this help message and exit

Example:
  ${0##*/} domain.com

Scans Performed:
  * Subdomain Enumeration using assetfinder and subfinder
  * Web Asset Scanning with nuclei
  * Port Scanning with rustscan
  * Port Scanning Fallback with naabu and nmap
  * Link Collection with katana
  * SSL/TLS Analysis with sslyze
  * SQL Injection Testing with sqlmap
  * Web Scanning with OWASP ZAP
  * Result Compression with 7z

Ensure all dependencies are installed and configured before running the script.
EOF
}

# ------------------------------------------------------- #
# Check Arguments:
# ------------------------------------------------------- #
if [[ $# -lt 1 || "$1" =~ ^(-h|--help)$ ]]; then
  usage
  exit $(( $# ? 0 : 1 ))
fi

DOMAIN_INPUT="$1"

# Validate domain format
if ! [[ "$DOMAIN_INPUT" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo -e "${RED}Error:${CLEAR} Invalid domain format."
  exit 1
fi

DOMAIN="$DOMAIN_INPUT"

# ------------------------------------------------------- #
# Banner:
# ------------------------------------------------------- #
banner() {
  clear
  echo -e "${GREEN}"
  echo -e "                                          イザナミ"
  echo -e " _____ ______ _______ __   _ _______ _______ _____"
  echo -e "   |    ____/ |_____| | \\  | |_____| |  |  |   |"
  echo -e " __|__ /_____ |     | |  \\_| |     | |  |  | __|__"
  echo -e "    ${VERSION}"
  echo -e "${CLEAR}"
}

# ------------------------------------------------------- #
# Enumerate Subdomains
# ------------------------------------------------------- #
enumerate_subdomains() {
  echo -e "[${BLUE}*${CLEAR}] Preparing output directory for ${GREEN}$DOMAIN${CLEAR}"
  OUTPUT_DIR="${DOMAIN}_$(date +"$OUTPUT_TIMESTAMP_FORMAT")"
  mkdir -p "$OUTPUT_DIR"

  echo -e "[${BLUE}*${CLEAR}] Looking for subdomains."
  echo "$DOMAIN" > "$OUTPUT_DIR/subdomains.txt"

  if [[ "$ENABLE_SUBDOMAIN_ENUMERATION" == "true" ]]; then
    echo -e "[${BLUE}*${CLEAR}] Running assetfinder and subfinder."

    # Run assetfinder and subfinder in parallel
    assetfinder "$DOMAIN" | sort -u > "$OUTPUT_DIR/assetfinder.txt" &
    ASSETFINDER_PID=$!

    ./subfinder -silent -all -dL "$OUTPUT_DIR/assetfinder.txt" > "$OUTPUT_DIR/subfinder.txt" &
    SUBFINDER_PID=$!

    # Wait for both processes to complete
    wait "$ASSETFINDER_PID" "$SUBFINDER_PID"

    # Combine and sort unique subdomains
    cat "$OUTPUT_DIR/assetfinder.txt" "$OUTPUT_DIR/subfinder.txt" | sort -u >> "$OUTPUT_DIR/subdomains.txt"

    # Count the number of unique subdomains
    SUBDOMAIN_COUNT=$(wc -l < "$OUTPUT_DIR/subdomains.txt")
    echo -e "    Found ${BLUE}$SUBDOMAIN_COUNT${CLEAR} targets."
  else
    echo -e "[${YELLOW}*${CLEAR}] Subdomain enumeration is disabled."
  fi
}

# ------------------------------------------------------- #
# Scan Web Assets with Nuclei
# ------------------------------------------------------- #
scan_web_assets() {
  if [[ "$ENABLE_WEB_ASSET_SCAN" != "true" ]]; then
    echo -e "[${YELLOW}*${CLEAR}] Web asset scanning is disabled."
    return
  fi

  echo -e "[${BLUE}*${CLEAR}] Scanning web assets with nuclei."
  ./nuclei $NUCLEI_OPTS -l "$OUTPUT_DIR/subdomains.txt" -o "$OUTPUT_DIR/nuclei.txt"
  echo -e "    Nuclei scan completed. Results saved to ${GREEN}$OUTPUT_DIR/nuclei.txt${CLEAR}."
}

# ------------------------------------------------------- #
# Port Scanning with Rustscan
# ------------------------------------------------------- #
port_scan() {
  if [[ "$ENABLE_PORT_SCAN" != "true" ]]; then
    echo -e "[${YELLOW}*${CLEAR}] Port scanning is disabled."
    return
  fi

  echo -e "[${BLUE}*${CLEAR}] Fetching InternetDB information."
  MAIN_IP=$(host "$DOMAIN" | head -n 1 | awk '{print $4}')
  if [[ -z "$MAIN_IP" ]]; then
    echo -e "${RED}Error:${CLEAR} Unable to resolve IP for $DOMAIN."
    return
  fi
  curl -s "https://internetdb.shodan.io/$MAIN_IP" | jq '.' > "$OUTPUT_DIR/internetdb.json"
  echo -e "    InternetDB data saved to ${GREEN}$OUTPUT_DIR/internetdb.json${CLEAR}."

  echo -e "[${BLUE}*${CLEAR}] Scanning ports with rustscan."
  ./rustscan $RUSTSCAN_OPTS -a "$OUTPUT_DIR/subdomains.txt" -o "$OUTPUT_DIR/rustscan.txt"
  echo -e "    Rustscan completed. Results saved to ${GREEN}$OUTPUT_DIR/rustscan.txt${CLEAR}."
}

# ------------------------------------------------------- #
# Port Scanning Fallback with Naabu and Nmap
# ------------------------------------------------------- #
port_scan_fallback() {
  if [[ "$ENABLE_PORT_SCAN_FALLBACK" != "true" ]]; then
    echo -e "[${YELLOW}*${CLEAR}] Port scan fallback is disabled."
    return
  fi

  echo -e "[${BLUE}*${CLEAR}] Running naabu as a fallback port scanner."
  ./naabu $NAABU_OPTS -l "$OUTPUT_DIR/subdomains.txt" > "$OUTPUT_DIR/naabu.txt"
  echo -e "    Naabu scan completed. Results saved to ${GREEN}$OUTPUT_DIR/naabu.txt${CLEAR}."

  echo -e "[${BLUE}*${CLEAR}] Running nmap as a fallback port scanner."
  nmap $NMAP_OPTS "$OUTPUT_DIR/nmap.txt" -iL "$OUTPUT_DIR/subdomains.txt"
  echo -e "    Nmap scan completed. Results saved to ${GREEN}$OUTPUT_DIR/nmap.txt${CLEAR}."
}

# ------------------------------------------------------- #
# Collect Links with Katana
# ------------------------------------------------------- #
collect_links() {
  if [[ "$ENABLE_LINK_COLLECTION" != "true" ]]; then
    echo -e "[${YELLOW}*${CLEAR}] Link collection is disabled."
    return
  fi

  echo -e "[${BLUE}*${CLEAR}] Collecting visible links with katana."
  ./katana $KATANA_OPTS -u "http://$DOMAIN" > "$OUTPUT_DIR/katana.txt"
  LINK_COUNT=$(wc -l < "$OUTPUT_DIR/katana.txt")
  echo -e "    Found ${BLUE}$LINK_COUNT${CLEAR} links."
}

# ------------------------------------------------------- #
# Analyze SSL/TLS with sslyze
# ------------------------------------------------------- #
analyze_ssl_tls() {
  if [[ "$ENABLE_SSL_TLS_ANALYSIS" != "true" ]]; then
    echo -e "[${YELLOW}*${CLEAR}] SSL/TLS analysis is disabled."
    return
  fi

  echo -e "[${BLUE}*${CLEAR}] Analyzing SSL/TLS with sslyze."
  ./sslyze $SSLYZE_OPTS "$OUTPUT_DIR/subdomains.txt" > "$OUTPUT_DIR/sslyze.json" 2>/dev/null
  echo -e "    SSL/TLS analysis completed. Results saved to ${GREEN}$OUTPUT_DIR/sslyze.json${CLEAR}."
}

# ------------------------------------------------------- #
# SQL Injection Testing with sqlmap
# ------------------------------------------------------- #
sql_injection_testing() {
  if [[ "$ENABLE_SQL_INJECTION_TESTING" != "true" ]]; then
    echo -e "[${YELLOW}*${CLEAR}] SQL injection testing is disabled."
    return
  fi

  echo -e "[${BLUE}*${CLEAR}] Testing for SQL injection with sqlmap."

  # Ensure katana output exists
  if [[ ! -f "$OUTPUT_DIR/katana.txt" ]]; then
    echo -e "${RED}Error:${CLEAR} katana.txt not found. Skipping SQL injection testing."
    return
  fi

  while IFS= read -r url; do
    # Generate a safe filename by hashing the URL
    SAFE_URL=$(echo "$url" | md5sum | awk '{print $1}')
    ./sqlmap -u "$url" $SQLMAP_OPTS -o "$OUTPUT_DIR/sqlmap_$SAFE_URL.txt" &
  done < "$OUTPUT_DIR/katana.txt"

  wait
  echo -e "    SQL injection testing completed. Results saved to ${GREEN}$OUTPUT_DIR/sqlmap_*.txt${CLEAR}."
}

# ------------------------------------------------------- #
# Web Scanning with OWASP ZAP
# ------------------------------------------------------- #
webscan_zap() {
  if [[ "$ENABLE_WEBSCAN_ZAP" != "true" ]]; then
    echo -e "[${YELLOW}*${CLEAR}] Web scanning with OWASP ZAP is disabled."
    return
  fi

  echo -e "[${BLUE}*${CLEAR}] Starting scan on OWASP ZAP."
  ./zap-cli --zap-url http://localhost:8080 --api-key "$ZAP_API_KEY" quick-scan "$DOMAIN" >/dev/null 2>&1
  echo -e "    OWASP ZAP scan initiated."

  echo -e "[${BLUE}*${CLEAR}] Retrieving alerts from OWASP ZAP."
  ./zap-cli --zap-url http://localhost:8080 --api-key "$ZAP_API_KEY" alerts -l 10 > "$OUTPUT_DIR/zap_alerts.json" >/dev/null 2>&1
  echo -e "    ZAP alerts saved to ${GREEN}$OUTPUT_DIR/zap_alerts.json${CLEAR}."
}

# ------------------------------------------------------- #
# Compressing Results with 7z
# ------------------------------------------------------- #
compress_results() {
  if [[ "$ENABLE_RESULT_COMPRESSION" != "true" ]]; then
    echo -e "[${YELLOW}*${CLEAR}] Result compression is disabled."
    return
  fi

  echo -e "[${BLUE}*${CLEAR}] Compressing results with 7z."
  7z $COMPRESS_OPTS "$OUTPUT_DIR.7z" "$OUTPUT_DIR" >/dev/null 2>&1
  echo -e "    Results compressed to ${GREEN}$OUTPUT_DIR.7z${CLEAR}."
}

# ------------------------------------------------------- #
# Cleanup Temporary Files
# ------------------------------------------------------- #
cleanup() {
  echo -e "[${BLUE}*${CLEAR}] Cleaning up temporary files."
  rm -f "$OUTPUT_DIR/assetfinder.txt" "$OUTPUT_DIR/subfinder.txt" "$OUTPUT_DIR/naabu.txt" "$OUTPUT_DIR/nmap.txt" >/dev/null 2>&1 || true
  echo -e "    Temporary files removed."
}

# ------------------------------------------------------- #
# Send Notification
# ------------------------------------------------------- #
send_notification() {
  if [[ "${NOTIFY_ENABLED}" == "true" ]]; then
    notify-send "izanami" "Finished scan on $DOMAIN"
  fi
}

# ------------------------------------------------------- #
# Logging
# ------------------------------------------------------- #
start_logging() {
  exec > >(tee -i "$LOG_FILE") 2>&1
  echo "izanami scan started at $(date)"
}

end_logging() {
  echo "izanami scan completed at $(date)"
}

# ------------------------------------------------------- #
# Main Execution Flow
# ------------------------------------------------------- #
main() {
  start_logging
  banner
  enumerate_subdomains
  scan_web_assets
  port_scan
  port_scan_fallback
  collect_links
  analyze_ssl_tls
  sql_injection_testing
  webscan_zap
  compress_results
  cleanup
  echo ""
  echo -e "[${BLUE}*${CLEAR}] Finished."
  send_notification
  end_logging
}

# Invoke main function
main
