import pandas as pd
import folium
import sys

def generate_ip_map(csv_file, output_file="ip_geolocation_map.html"):
    # Load the CSV file
    df = pd.read_csv(csv_file)
    
    # Ensure necessary columns exist
    required_columns = {"Latitude", "Longitude", "IP", "Provider", "City", "Malicious"}
    if not required_columns.issubset(df.columns):
        raise ValueError(f"Missing required columns in CSV. Expected: {required_columns}")
    
    # Define the center of the map based on the average latitude and longitude
    map_center = [df["Latitude"].mean(), df["Longitude"].mean()]
    ip_map = folium.Map(location=map_center, zoom_start=4)
    
    # Add IP locations as markers
    for _, row in df.iterrows():
        folium.Marker(
            location=[row["Latitude"], row["Longitude"]],
            popup=f'IP: {row["IP"]}<br>Provider: {row["Provider"]}<br>City: {row["City"]}',
            icon=folium.Icon(color="red" if row["Malicious"] == "Yes" else "blue")
        ).add_to(ip_map)
    
    # Save the map to an HTML file
    ip_map.save(output_file)
    print(f"Map successfully created: {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_ip_map.py <csv_file> [output_file]")
    else:
        csv_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else "ip_geolocation_map.html"
        generate_ip_map(csv_file, output_file)
