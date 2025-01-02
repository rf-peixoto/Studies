#!/usr/bin/env python3

# DO NOT USE FOR COMMERCIAL PURPOSES!!!

import os
import sys
import time
import base64
import requests
from colorama import init, Fore, Style
from datetime import datetime

# Initialize colorama for colored output.
init(autoreset=True)

# Wigle.net credentials. Replace with valid data or load from secure storage.
WIGLE_API_NAME = "api name"
WIGLE_API_TOKEN = "api token"

# Base URL for the Wigle.net API.
WIGLE_API_URL = "https://api.wigle.net/api/v2/network/search"

def build_query_params(device_type, query):
    """
    Build query parameters for the Wigle.net API request.
    device_type can be wifi, cell, or bluetooth.
    The 'query' can be an SSID, partial name, BSSID, or other relevant string.
    """
    # Approximate bounding box for Brazil.
    brazil_params = {
        "latrange1": -33.7500,
        "latrange2":  5.2672,
        "longrange1": -73.9828,
        "longrange2": -32.3928,
    }
    
    # Base parameters (applied to all device types).
    query_params = {
        "onlymine":       "false",
        "freenet":        "false",
        "paynet":         "false",
        "lastupdt":       "",      # (Optional) Filter by date
        "resultsPerPage": 10,      # Each page returns up to 50 records
        "searchAfter":    None,
        "variance":       "0.010", # Adjust if needed
    }
    
    query_params.update(brazil_params)

    # Set the device type.
    if device_type.lower() == "wifi":
        # Wi-Fi networks
        query_params["type"] = "WIFI"
        # You can search by SSID or BSSID (netid). Here, we default to SSID:
        query_params["ssid"] = query

    elif device_type.lower() == "cell":
        # Cellular networks
        query_params["type"] = "CELL"
        # For cell, Wigle often uses 'ssid' in the search param as well, 
        # but you can consider 'carrier' or 'netid' if needed:
        query_params["ssid"] = query

    elif device_type.lower() == "bluetooth":
        # Bluetooth devices
        query_params["type"] = "BLUETOOTH"
        # Wigle's param 'ssid' can still be used for partial name matching:
        query_params["ssid"] = query

    else:
        print(Fore.RED + "Invalid device type. Must be one of: wifi, cell, bluetooth.")
        sys.exit(1)

    return query_params

def parse_lasttime(entry):
    """
    Convert the 'lasttime' field into a datetime object for sorting.
    If invalid or missing, return datetime.min so the sort will place these at the end.
    """
    lasttime_str = entry.get("lasttime")
    if not lasttime_str:
        return datetime.min
    try:
        # Typically 'YYYY-MM-DD HH:MM:SS'
        return datetime.strptime(lasttime_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.min

def query_wigle_api(device_type, query, max_results):
    """
    Make a search request to Wigle.net for the specified device_type, limited to Brazil.
    Returns up to 'max_results' items sorted by last-seen time.
    """
    # Prepare basic-auth header.
    credentials = f"{WIGLE_API_NAME}:{WIGLE_API_TOKEN}"
    credentials_b64 = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {credentials_b64}",
        "Accept": "application/json"
    }
    
    params = build_query_params(device_type, query)
    results = []
    total_pages = 1
    current_page = 1

    while current_page <= total_pages:
        response = requests.get(WIGLE_API_URL, headers=headers, params=params, timeout=30)
        
        if response.status_code != 200:
            print(Fore.RED + "Error: Received non-200 response from Wigle.net API.")
            print(Fore.YELLOW + f"Response code: {response.status_code}")
            print(Fore.YELLOW + f"Response body: {response.text}")
            sys.exit(1)
        
        data = response.json()
        
        if not data.get("success"):
            print(Fore.RED + "Error: Unsuccessful response from Wigle.net.")
            print(Fore.YELLOW + str(data))
            sys.exit(1)
        
        page_results = data.get("results", [])
        results.extend(page_results)

        # If we already have enough, stop early to avoid extra requests.
        if len(results) >= max_results:
            break
        
        total_pages = data.get("totalPages", 1)
        search_after = data.get("search_after")

        # If there's no 'search_after' token or we're on the last page, stop.
        if not search_after or current_page == total_pages:
            break

        params["searchAfter"] = search_after
        current_page += 1

        # Sleep to respect Wigle.net API usage limits.
        time.sleep(2)

    # Sort all retrieved results by last-seen time in descending order.
    results.sort(key=parse_lasttime, reverse=True)

    # Return only up to the requested maximum.
    return results[:max_results]

def print_results(results, device_type):
    """
    Display the retrieved data in a clear, color-coded manner.
    Omits fields that are missing or empty.
    Shows common fields for Wi-Fi, cell, or Bluetooth results:
      - For Wi-Fi, fields like encryption, channel, address, etc.
      - For cell, fields like userfound, comment, address, etc.
      - For bluetooth, similarly userfound, address, encryption (though often empty).
    """
    if not results:
        print(Fore.RED + "No results found for the specified criteria.")
        return
    
    print(Fore.GREEN + f"Total results in memory: {len(results)}")
    print(Style.DIM + f"Device type: {device_type.upper()}")
    
    for index, entry in enumerate(results, start=1):
        # The script prints out these fields if they exist:
        details = {
            "Type":         entry.get("type"),
            "SSID/Name":    entry.get("ssid"),
            "NETID/BSSID":  entry.get("netid"),
            "Comment":      entry.get("comment"),
            "Userfound":    entry.get("userfound"),
            "Encryption":   entry.get("encryption"),
            "Address":      entry.get("address"),
            "Channel":      entry.get("channel"),
            "Latitude":     entry.get("trilat"),
            "Longitude":    entry.get("trilong"),
            "Last Seen":    entry.get("lasttime"),
            "First Seen":   entry.get("firsttime"),
            "City":         entry.get("city"),
            "Region":       entry.get("region"),
            "Country":      entry.get("country"),
            # For cell towers specifically, you may also find "carrier", "cellid", "radio", etc.
            "Carrier":      entry.get("carrier"),
            "CellID":       entry.get("cellid"),
            "Radio":        entry.get("radio"),
            # For Bluetooth, you might see partial names or addresses. 
            # Wigle uses similar fields for device name, so it's stored under 'ssid' above.
        }
        
        print(f"{Fore.CYAN}Result {index}:")
        for field_name, field_value in details.items():
            # If the field has a valid (non-empty) value, print it.
            if field_value is not None and str(field_value).strip():
                print(f"{Fore.WHITE}  {field_name}: {field_value}")
        
        print(Style.DIM + "-" * 40)

def main():
    """
    Usage:
      python wigle_search.py <device_type> <search_query> [max_results]

    Examples:
      python wigle_search.py wifi MyNetwork
      python wigle_search.py cell Vivo
      python wigle_search.py bluetooth MyBTDevice 20

    device_type can be one of:
      - wifi
      - cell
      - bluetooth

    search_query is typically an SSID, partial network name, or other text.

    max_results is optional; defaults to 10 if not specified.
    """
    if len(sys.argv) < 3:
        print(Fore.YELLOW + "Usage: python wigle_search.py <device_type> <search_query> [max_results]")
        print(Fore.YELLOW + "Example: python wigle_search.py wifi MyNetwork 10")
        sys.exit(1)
    
    device_type = sys.argv[1]
    query = sys.argv[2]
    
    # Default to 30 if the user does not specify max_results.
    max_results = 10
    if len(sys.argv) >= 4:
        try:
            max_results = int(sys.argv[3])
        except ValueError:
            print(Fore.RED + "Invalid max_results value. Must be an integer.")
            sys.exit(1)
    
    print(Fore.WHITE + f"Initiating search on Wigle.net for device type {device_type.upper()}, query: {query}")
    print(Fore.WHITE + f"Will show up to {max_results} results in descending last-seen order.\n")
    
    results = query_wigle_api(device_type, query, max_results)
    print_results(results, device_type)

if __name__ == "__main__":
    main()
