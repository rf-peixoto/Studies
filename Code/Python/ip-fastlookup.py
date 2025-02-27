import requests
import csv
import time

def get_ip_info(ip):
    """
    Retrieves geolocation and provider information for the given IP using ip-api.
    """
    url = f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,lat,lon,isp,org"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        if data.get("status") == "success":
            return data
        else:
            return {"error": data.get("message", "Unknown error")}
    except Exception as e:
        return {"error": str(e)}

def get_vt_info(ip, api_key):
    """
    Retrieves reputation data for the given IP from VirusTotal.
    The API returns analysis stats including the count of malicious detections.
    """
    url = f"https://www.virustotal.com/api/v3/ip_addresses/{ip}"
    headers = {
        "x-apikey": api_key
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # Extract analysis statistics from the response.
            analysis_stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            return analysis_stats
        else:
            return {"error": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def main():
    # Replace with your actual VirusTotal API key.
    vt_api_key = "VTAPI"
    input_file = "ips.txt"   # File containing IP addresses (one per line)
    output_file = "results.csv"
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            ips = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print("Error reading input file:", e)
        return

    total_ips = len(ips)
    print(f"Processing {total_ips} IP address{'es' if total_ips != 1 else ''}.")

    try:
        with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = ["IP", "Provider", "Country", "Region", "City", "Latitude", "Longitude", "Malicious Count", "Malicious"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for idx, ip in enumerate(ips, start=1):
                print(f"[{idx}/{total_ips}] Processing IP: {ip}")
                
                ip_info = get_ip_info(ip)
                if "error" in ip_info:
                    print(f"Error retrieving info for IP {ip}: {ip_info['error']}")
                    continue
                
                vt_stats = get_vt_info(ip, vt_api_key)
                if "error" in vt_stats:
                    malicious_count = "N/A"
                    malicious_flag = "No"
                    print(f"Error retrieving VirusTotal info for IP {ip}: {vt_stats['error']}")
                else:
                    malicious_count = vt_stats.get("malicious", 0)
                    malicious_flag = "Yes" if isinstance(malicious_count, int) and malicious_count > 0 else "No"
                
                row = {
                    "IP": ip,
                    "Provider": ip_info.get("org", ip_info.get("isp", "N/A")),
                    "Country": ip_info.get("country", "N/A"),
                    "Region": ip_info.get("regionName", "N/A"),
                    "City": ip_info.get("city", "N/A"),
                    "Latitude": ip_info.get("lat", "N/A"),
                    "Longitude": ip_info.get("lon", "N/A"),
                    "Malicious Count": malicious_count,
                    "Malicious": malicious_flag
                }
                writer.writerow(row)
                # Pause to respect rate limits.
                time.sleep(1)
    except Exception as e:
        print("Error writing to output file:", e)
        return

    print("Processing complete. Results saved to", output_file)

if __name__ == "__main__":
    main()
