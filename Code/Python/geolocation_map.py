# pip install pandas geopy matplotlib basemap numpy

import pandas as pd
import requests
import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap
import numpy as np

# Function to read IPs from a file
def read_ips(file_path):
    with open(file_path, 'r') as file:
        ips = file.readlines()
    return [ip.strip() for ip in ips]

# Function to get geolocation of an IP
def get_geolocation(ip):
    url = f"http://ip-api.com/json/{ip}"
    try:
        response = requests.get(url)
        data = response.json()
        if data['status'] == 'success':
            return data['lat'], data['lon']
    except requests.RequestException:
        return None
    return None

# Function to get geolocations for a list of IPs
def get_geolocations(ips):
    geolocations = []
    for ip in ips:
        location = get_geolocation(ip)
        if location:
            geolocations.append(location)
    return geolocations

# Function to plot heat map on a world map
def plot_heatmap(geolocations):
    # Create a new figure
    plt.figure(figsize=(12, 8))
    
    # Setup Basemap
    m = Basemap(projection='mill', llcrnrlat=-60, urcrnrlat=90, llcrnrlon=-180, urcrnrlon=180, resolution='c')
    m.drawcoastlines()
    m.drawcountries()
    
    # Convert geolocations to numpy array for plotting
    latitudes = np.array([loc[0] for loc in geolocations])
    longitudes = np.array([loc[1] for loc in geolocations])
    
    # Plot points on the map
    x, y = m(longitudes, latitudes)
    m.scatter(x, y, color='red', marker='o', s=50, alpha=0.5, zorder=5)
    
    # Title
    plt.title('IP Geolocation Map')
    
    # Show plot
    plt.show()

# Main function
def main(file_path):
    ips = read_ips(file_path)
    geolocations = get_geolocations(ips)
    if not geolocations:
        print("No geolocations found.")
    else:
        plot_heatmap(geolocations)

# Replace 'ips.txt' with your file containing the list of IPs
main('ips.txt')
