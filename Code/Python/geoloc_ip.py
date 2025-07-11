#!/usr/bin/env python3
"""
Advanced IP Geolocation Inspector - Educational Tool
Combines multiple data sources for comprehensive analysis
"""

import sys
import os
import argparse
import ipaddress
import requests
import json
import socket
import time
import math
from collections import defaultdict
import subprocess
import re

# API Configuration
API_CONFIG = {
    "geolocation_apis": {
        "ipinfo": "https://ipinfo.io/{}/json",
        "ipapi": "https://ipapi.co/{}/json/",
        "ipgeolocation": "https://api.ipgeolocation.io/ipgeo?apiKey={}&ip={}"
    },
    "asn_api": "https://api.asrank.caida.org/v2/restful/asns/{}",
    "privacy_api": "https://vpnapi.io/api/{}",
    "historical_api": "https://api.viewdns.info/iphistory/?ip={}&apikey={}&output=json"
}

# API Keys (set your own in environment variables)
API_KEYS = {
    "ipgeolocation": os.getenv("IPGEOLOCATION_API_KEY", "free"),
    "viewdns": os.getenv("VIEWDNS_API_KEY", "demo")
}

# Visualization characters
MAP_CHARS = {
    "target": "★",
    "hop": "•",
    "line": "─",
    "node": "┼",
    "space": " ",
    "header": "▰"
}

def validate_ip(ip):
    """Validate IP address format"""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def get_ip_version(ip):
    """Get IP version (4 or 6)"""
    return 4 if '.' in ip else 6

def api_request(url, max_retries=3, timeout=5):
    """Robust API request with error handling and retries"""
    retry_delays = [1, 3, 5]  # Seconds between retries
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delays[attempt])
                continue
            return {"error": f"API request failed: {str(e)}"}
    return {"error": "Max retries exceeded"}

def get_geolocation_data(ip):
    """Get geolocation from multiple sources"""
    results = {}
    apis = API_CONFIG["geolocation_apis"]
    
    # Query all geolocation APIs
    for service, url_template in apis.items():
        if service == "ipgeolocation":
            url = url_template.format(API_KEYS["ipgeolocation"], ip)
        else:
            url = url_template.format(ip)
        
        data = api_request(url)
        if "error" not in data:
            results[service] = data
    
    return results

def get_asn_data(asn):
    """Get detailed ASN information"""
    if not asn.startswith("AS"):
        asn = f"AS{asn}"
    
    url = API_CONFIG["asn_api"].format(asn)
    data = api_request(url)
    
    if "error" in data:
        return {"error": data["error"]}
    
    # Extract relevant ASN information
    asn_data = data.get("data", {}).get("asn", {})
    return {
        "asn": asn_data.get("asn", "Unknown"),
        "name": asn_data.get("organization", {}).get("orgName", "Unknown"),
        "description": asn_data.get("organization", {}).get("comment", "Unknown"),
        "country": asn_data.get("country", {}).get("iso", "Unknown"),
        "rank": asn_data.get("rank", {}).get("rank", "Unknown"),
        "type": asn_data.get("cone", {}).get("numberAsns", "Unknown"),
        "ipv4_prefixes": asn_data.get("cone", {}).get("numberPrefixes", "Unknown")
    }

def get_reverse_dns(ip):
    """Perform reverse DNS lookup"""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror):
        return "Not found"
    except Exception as e:
        return f"Error: {str(e)}"

def analyze_hostname(hostname):
    """Extract geographic clues from hostname"""
    if "not found" in hostname.lower() or "error" in hostname.lower():
        return {}
    
    # Common geographic indicators in hostnames
    indicators = {
        "city": r"\b(nyc|sfo|lax|lon|par|fra|ams|tok|syd|sin|dub|mow|vie)\b",
        "country": r"\b(us|uk|de|fr|nl|jp|au|sg|ru|ca|br)\b",
        "airport": r"\b(jfk|sfo|lax|cdg|fra|ams|nrt|syd|sin|dub|svo)\b",
        "region": r"\b(west|east|north|south|central|emea|apac|namer|samer|europe|asia)\b"
    }
    
    clues = {}
    hostname_lower = hostname.lower()
    
    for clue_type, pattern in indicators.items():
        match = re.search(pattern, hostname_lower)
        if match:
            clues[clue_type] = match.group(0).upper()
    
    return clues

def perform_traceroute(ip, max_hops=8):
    """Perform traceroute to target IP"""
    try:
        # Determine OS and appropriate traceroute command
        command = ["tracert", "-d", "-h", str(max_hops), ip] if os.name == "nt" else ["traceroute", "-n", "-m", str(max_hops), ip]
        
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate()
        
        if error:
            return {"error": error.decode().strip()}
        
        return parse_traceroute(output.decode(), ip)
    except Exception as e:
        return {"error": f"Traceroute failed: {str(e)}"}

def parse_traceroute(output, target_ip):
    """Parse traceroute output into structured data"""
    hops = []
    ip_pattern = r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
    hop_pattern = r"^\s*(\d+)\s+(.*?)\s+ms\s+.*?ms\s+.*?ms\s+([\w\.]+)"
    
    for line in output.splitlines():
        # Match hop lines
        hop_match = re.match(hop_pattern, line)
        if hop_match:
            hop_num = int(hop_match.group(1))
            hop_ip = hop_match.group(3)
            
            # Skip if IP not found
            if not re.match(ip_pattern, hop_ip):
                continue
                
            hops.append({
                "hop": hop_num,
                "ip": hop_ip,
                "hostname": get_reverse_dns(hop_ip),
                "location": get_geolocation_data(hop_ip).get("ipinfo", {})
            })
        
        # Match target line
        target_match = re.search(f"^\\s*\\d+\\s+.*?({target_ip})", line)
        if target_match:
            hops.append({
                "hop": hop_num + 1 if hops else 1,
                "ip": target_ip,
                "hostname": get_reverse_dns(target_ip),
                "location": get_geolocation_data(target_ip).get("ipinfo", {}),
                "target": True
            })
            break
    
    return hops

def detect_privacy_services(ip):
    """Detect VPN, proxy, or TOR usage"""
    url = API_CONFIG["privacy_api"].format(ip)
    data = api_request(url)
    
    if "error" in data:
        return {"error": data["error"]}
    
    return {
        "vpn": data.get("security", {}).get("vpn", False),
        "proxy": data.get("security", {}).get("proxy", False),
        "tor": data.get("security", {}).get("tor", False),
        "relay": data.get("security", {}).get("relay", False),
        "service": data.get("security", {}).get("service", "Clean")
    }

def get_historical_data(ip):
    """Get historical IP information"""
    url = API_CONFIG["historical_api"].format(ip, API_KEYS["viewdns"])
    data = api_request(url)
    
    if "error" in data:
        return {"error": data["error"]}
    
    # Parse historical data
    history = []
    response = data.get("response", {})
    if "history" in response:
        for record in response["history"]:
            history.append({
                "ip": record.get("ip", "Unknown"),
                "owner": record.get("owner", "Unknown"),
                "last_seen": record.get("lastseen", "Unknown"),
                "country": record.get("country", "Unknown")
            })
    
    return history

def calculate_accuracy(geo_data):
    """Calculate confidence score for geolocation data"""
    scores = []
    indicators = []
    
    # Check for consistency between sources
    sources = list(geo_data.keys())
    if len(sources) > 1:
        country_match = 0
        city_match = 0
        
        countries = set()
        cities = set()
        
        for source, data in geo_data.items():
            country = data.get("country", "")
            city = data.get("city", "")
            
            if country:
                countries.add(country)
                country_match += 1
            
            if city:
                cities.add(city)
                city_match += 1
        
        # Calculate consistency scores
        country_consistency = len(countries) == 1
        city_consistency = len(cities) == 1
        
        if country_consistency:
            scores.append(25)
            indicators.append("Country consistent across sources")
        else:
            scores.append(5)
            indicators.append(f"Country mismatch: {', '.join(countries)}")
        
        if city_consistency:
            scores.append(30)
            indicators.append("City consistent across sources")
        else:
            scores.append(10)
            indicators.append(f"City mismatch: {', '.join(cities)}")
    else:
        indicators.append("Single source - lower confidence")
        scores.append(20)
    
    # Check for ISP data
    for source, data in geo_data.items():
        if "org" in data or "asn" in data:
            scores.append(15)
            indicators.append("ISP data available")
            break
    
    # Check for coordinates
    for source, data in geo_data.items():
        if "loc" in data:
            scores.append(20)
            indicators.append("Coordinates available")
            break
    
    # Check for privacy services
    if "privacy" in geo_data:
        if not any([
            geo_data["privacy"]["vpn"],
            geo_data["privacy"]["proxy"],
            geo_data["privacy"]["tor"]
        ]):
            scores.append(10)
            indicators.append("No privacy services detected")
        else:
            scores.append(2)
            indicators.append("Privacy services detected - lower confidence")
    
    # Calculate total score (max 100)
    total_score = min(sum(scores), 100)
    
    # Determine confidence level
    if total_score >= 80:
        confidence = "High"
    elif total_score >= 60:
        confidence = "Medium"
    elif total_score >= 40:
        confidence = "Low"
    else:
        confidence = "Very Low"
    
    return {
        "score": total_score,
        "confidence": confidence,
        "indicators": indicators
    }

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates (Haversine formula)"""
    R = 6371  # Earth radius in km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = (math.sin(dlat/2) * math.sin(dlat/2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlon/2) * math.sin(dlon/2))
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def create_visualization(traceroute_data, geo_data):
    """Create ASCII visualization of network path"""
    if not traceroute_data or "error" in traceroute_data:
        return "Visualization unavailable"
    
    # Get target coordinates
    target_ip = traceroute_data[-1]["ip"]
    target_geo = geo_data.get("ipinfo", {})
    
    if "loc" not in target_geo:
        return "Target coordinates unavailable"
    
    target_lat, target_lon = map(float, target_geo["loc"].split(","))
    
    # Create coordinate list
    points = []
    for hop in traceroute_data:
        if "location" in hop and "loc" in hop["location"]:
            lat, lon = map(float, hop["location"]["loc"].split(","))
            points.append({
                "type": "target" if hop.get("target") else "hop",
                "lat": lat,
                "lon": lon,
                "label": f"Hop {hop['hop']}"
            })
    
    if not points:
        return "No geolocated hops for visualization"
    
    # Calculate bounds
    min_lat = min(p["lat"] for p in points)
    max_lat = max(p["lat"] for p in points)
    min_lon = min(p["lon"] for p in points)
    max_lon = max(p["lon"] for p in points)
    
    # Normalize coordinates to grid
    GRID_WIDTH = 60
    GRID_HEIGHT = 20
    
    def normalize(value, min_val, max_val, size):
        return int((value - min_val) / (max_val - min_val) * size)
    
    grid = [[' ' for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
    
    # Plot points
    for point in points:
        x = normalize(point["lon"], min_lon, max_lon, GRID_WIDTH-1)
        y = normalize(point["lat"], min_lat, max_lat, GRID_HEIGHT-1)
        
        # Flip y-axis for proper orientation
        y = GRID_HEIGHT - 1 - y
        
        if 0 <= x < GRID_WIDTH and 0 <= y < GRID_HEIGHT:
            grid[y][x] = MAP_CHARS["target"] if point["type"] == "target" else MAP_CHARS["hop"]
    
    # Draw connections between points
    prev_x, prev_y = None, None
    for point in points:
        x = normalize(point["lon"], min_lon, max_lon, GRID_WIDTH-1)
        y = normalize(point["lat"], min_lat, max_lat, GRID_HEIGHT-1)
        y = GRID_HEIGHT - 1 - y
        
        if prev_x is not None:
            # Draw line between previous and current point
            dx = x - prev_x
            dy = y - prev_y
            steps = max(abs(dx), abs(dy))
            
            for i in range(1, steps):
                inter_x = int(prev_x + dx * i / steps)
                inter_y = int(prev_y + dy * i / steps)
                
                if 0 <= inter_x < GRID_WIDTH and 0 <= inter_y < GRID_HEIGHT:
                    if grid[inter_y][inter_x] == ' ':
                        grid[inter_y][inter_x] = MAP_CHARS["line"]
        
        prev_x, prev_y = x, y
    
    # Create header
    header = f"Network Path Visualization ({len(points)} hops)"
    header_line = MAP_CHARS["header"] * len(header)
    
    # Convert grid to string
    grid_str = "\n".join("".join(row) for row in grid)
    
    # Add legend
    legend = (
        f"\nLegend: {MAP_CHARS['target']} = Target | {MAP_CHARS['hop']} = Hop | "
        f"{MAP_CHARS['line']} = Path"
    )
    
    return f"{header}\n{header_line}\n{grid_str}{legend}"

def print_comparison(geo_data):
    """Display comparison of geolocation sources"""
    if not geo_data:
        print("No geolocation data available for comparison")
        return
    
    print("\n\033[1;36m=== GEOLOCATION SOURCE COMPARISON ===\033[0m")
    print(f"{'Source':<15} {'Country':<10} {'Region':<15} {'City':<15} {'Coordinates':<20} {'ISP':<25}")
    print("-" * 95)
    
    for source, data in geo_data.items():
        country = data.get("country", "N/A")
        region = data.get("region", "N/A")
        city = data.get("city", "N/A")
        loc = data.get("loc", "N/A")
        isp = data.get("org", data.get("asn", "N/A")).split("AS")[0][:25]
        
        print(f"{source:<15} {country:<10} {region:<15} {city:<15} {loc:<20} {isp:<25}")

def print_asn_info(asn_data):
    """Display detailed ASN information"""
    if not asn_data or "error" in asn_data:
        print("\nASN information unavailable")
        return
    
    print("\n\033[1;36m=== ASN DETAILS ===\033[0m")
    print(f"AS Number:      {asn_data.get('asn', 'N/A')}")
    print(f"Organization:   {asn_data.get('name', 'N/A')}")
    print(f"Description:    {asn_data.get('description', 'N/A')}")
    print(f"Country:        {asn_data.get('country', 'N/A')}")
    print(f"Global Rank:    #{asn_data.get('rank', 'N/A')}")
    print(f"Network Size:   {asn_data.get('type', 'N/A')} ASNs")
    print(f"IPv4 Prefixes:  {asn_data.get('ipv4_prefixes', 'N/A')}")

def print_privacy_info(privacy_data):
    """Display privacy service detection results"""
    if not privacy_data or "error" in privacy_data:
        print("\nPrivacy detection unavailable")
        return
    
    print("\n\033[1;36m=== PRIVACY DETECTION ===\033[0m")
    status = "Clean"
    if privacy_data["vpn"]:
        status = "VPN Detected"
    elif privacy_data["proxy"]:
        status = "Proxy Detected"
    elif privacy_data["tor"]:
        status = "TOR Exit Node"
    elif privacy_data["relay"]:
        status = "Cloud Relay"
    
    print(f"Status:         {status}")
    print(f"Service:        {privacy_data.get('service', 'Unknown')}")
    print(f"VPN:            {'Yes' if privacy_data['vpn'] else 'No'}")
    print(f"Proxy:          {'Yes' if privacy_data['proxy'] else 'No'}")
    print(f"TOR:            {'Yes' if privacy_data['tor'] else 'No'}")
    print(f"Cloud Relay:    {'Yes' if privacy_data['relay'] else 'No'}")

def print_accuracy_assessment(accuracy):
    """Display accuracy assessment"""
    if not accuracy:
        print("\nAccuracy assessment unavailable")
        return
    
    print("\n\033[1;36m=== ACCURACY ASSESSMENT ===\033[0m")
    print(f"Confidence Score: {accuracy['score']}/100 ({accuracy['confidence']} Confidence)")
    print("\nKey Indicators:")
    for indicator in accuracy["indicators"]:
        print(f"  - {indicator}")

def main():
    parser = argparse.ArgumentParser(description="Advanced IP Geolocation Inspector")
    parser.add_argument("ip", help="IP address to analyze")
    parser.add_argument("--history", action="store_true", help="Show historical data")
    parser.add_argument("--map", action="store_true", help="Generate network path visualization")
    args = parser.parse_args()
    
    # Validate IP
    if not validate_ip(args.ip):
        print(f"Error: Invalid IP address - {args.ip}")
        sys.exit(1)
    
    print(f"\n\033[1;35m=== ADVANCED IP GEOLOCATION ANALYSIS ===\033[0m")
    print(f"Target IP: \033[1;32m{args.ip}\033[0m ({'IPv4' if get_ip_version(args.ip) == 4 else 'IPv6'})\n")
    
    # Start analysis
    print("\033[1;34m[1/6] Gathering geolocation data from multiple sources...\033[0m")
    geo_data = get_geolocation_data(args.ip)
    
    # Get ASN information
    asn = geo_data.get("ipinfo", {}).get("org", "").split("-")[0] if "ipinfo" in geo_data else None
    asn_data = get_asn_data(asn) if asn else {}
    
    # Reverse DNS analysis
    print("\033[1;34m[2/6] Performing reverse DNS analysis...\033[0m")
    hostname = get_reverse_dns(args.ip)
    hostname_clues = analyze_hostname(hostname)
    
    # Traceroute
    print("\033[1;34m[3/6] Performing traceroute (limited to 8 hops)...\033[0m")
    traceroute_data = perform_traceroute(args.ip)
    
    # Privacy detection
    print("\033[1;34m[4/6] Checking for privacy services...\033[0m")
    privacy_data = detect_privacy_services(args.ip)
    
    # Historical data
    historical_data = None
    if args.history:
        print("\033[1;34m[5/6] Retrieving historical data...\033[0m")
        historical_data = get_historical_data(args.ip)
    
    # Accuracy assessment
    print("\033[1;34m[6/6] Calculating accuracy assessment...\033[0m")
    accuracy = calculate_accuracy(geo_data)
    
    # Generate visualization if requested
    visualization = ""
    if args.map:
        visualization = create_visualization(traceroute_data, geo_data)
    
    # Print results
    print("\n\033[1;35m=== ANALYSIS RESULTS ===\033[0m")
    
    # Geolocation comparison
    print_comparison(geo_data)
    
    # ASN information
    print_asn_info(asn_data)
    
    # Reverse DNS results
    print("\n\033[1;36m=== REVERSE DNS ANALYSIS ===\033[0m")
    print(f"Hostname:       {hostname}")
    if hostname_clues:
        print("Geographic Clues Found:")
        for clue, value in hostname_clues.items():
            print(f"  - {clue.capitalize()}: {value}")
    else:
        print("No geographic clues found in hostname")
    
    # Privacy detection
    print_privacy_info(privacy_data)
    
    # Accuracy assessment
    print_accuracy_assessment(accuracy)
    
    # Historical data
    if args.history and historical_data and not historical_data.get("error"):
        print("\n\033[1;36m=== HISTORICAL INFORMATION ===\033[0m")
        print(f"{'IP':<16} {'Owner':<30} {'Last Seen':<12} {'Country':<10}")
        print("-" * 70)
        for record in historical_data:
            print(f"{record['ip']:<16} {record['owner'][:28]:<30} {record['last_seen']:<12} {record['country']:<10}")
    
    # Traceroute results
    if traceroute_data and not traceroute_data.get("error"):
        print("\n\033[1;36m=== TRACEROUTE RESULTS ===\033[0m")
        print(f"{'Hop':<4} {'IP':<16} {'Hostname':<35} {'Location':<25} {'ASN':<10}")
        print("-" * 90)
        for hop in traceroute_data:
            location = ""
            if "location" in hop and "city" in hop["location"] and "country" in hop["location"]:
                location = f"{hop['location']['city']}, {hop['location']['country']}"
            
            asn = hop.get("location", {}).get("org", "N/A").split("-")[0][:10]
            
            print(f"{hop['hop']:<4} {hop['ip']:<16} {hop['hostname'][:34]:<35} {location[:24]:<25} {asn:<10}")
    
    # Visualization
    if visualization:
        print(f"\n\033[1;36m=== NETWORK PATH VISUALIZATION ===\033[0m")
        print(visualization)
    
    print("\n\033[1;35mAnalysis complete!\033[0m")

if __name__ == "__main__":
    main()
