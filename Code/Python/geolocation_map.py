# pip install pandas geopy matplotlib basemap numpy
import pandas as pd
import requests
import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap
import numpy as np
import time
import sys

# Path to the file containing the list of IPs
FILE_PATH = sys.argv[1]
# Color of the points (examples: 'red', 'blue', 'green', 'yellow', etc.)
MAP_COLOR = 'red'
# Shape of the points (examples: '.', ',', 'o', 'v', '^', '<', '>', '1', '2', '3', '4', 's', 'p', '*', 'h', 'H', '+', 'x', 'D', 'd', '|', '_')
MARKER_SHAPE = '1'
# Size of the points
MARKER_SIZE = 100
# Transparency of the points (0 to 1)
MARKER_ALPHA = 0.8
# Map projection type (examples: 'cyl', 'merc', 'mill', 'cea', 'gall', 'ortho', 'geos', 'aeqd', 'gnom', 'cass', 'poly', 'npaeqd', 'spaeqd', 'npstere', 'spstere', 'vandg', 'mbtfpq', 'robin', 'eck4', 'kav7', 'hammer', 'moll', 'sinu', 'lambert', 'aea', 'tmerc', 'omerc', 'stere', 'eqdc')
MAP_PROJECTION = 'merc'
# Map resolution ('c' for crude, 'l' for low, 'i' for intermediate, 'h' for high, 'f' for full)
MAP_RESOLUTION = 'c'
# Figure size (width, height)
FIGURE_SIZE = (12, 8)
# Title of the map
TITLE = 'IP Geolocation Map'
# Time to sleep between API requests to avoid rate limiting
SLEEP_TIME = 1
# API URL for geolocation
API_URL = "http://ip-api.com/json/"

# Function to read IPs from a file
def read_ips(file_path):
    with open(file_path, 'r') as file:
        ips = file.readlines()
    return [ip.strip() for ip in ips]

# Function to get geolocation of an IP
def get_geolocation(ip):
    url = f"{API_URL}{ip}"
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
        time.sleep(SLEEP_TIME)
    return geolocations

# Function to plot heat map on a world map with customization options
def plot_heatmap(geolocations, color, marker, size, alpha, projection, resolution, figure_size, title):
    # Create a new figure
    plt.figure(figsize=figure_size)
    
    # Setup Basemap
    m = Basemap(projection=projection, llcrnrlat=-60, urcrnrlat=90, llcrnrlon=-180, urcrnrlon=180, resolution=resolution)
    m.drawcoastlines()
    m.drawcountries()
    
    # Convert geolocations to numpy array for plotting
    latitudes = np.array([loc[0] for loc in geolocations])
    longitudes = np.array([loc[1] for loc in geolocations])
    
    # Plot points on the map
    x, y = m(longitudes, latitudes)
    m.scatter(x, y, color=color, marker=marker, s=size, alpha=alpha, zorder=5)
    
    # Title
    plt.title(title)
    
    # Show plot
    plt.show()

# Main function
def main():
    ips = read_ips(FILE_PATH)
    geolocations = get_geolocations(ips)
    if not geolocations:
        print("No geolocations found.")
    else:
        plot_heatmap(geolocations, MAP_COLOR, MARKER_SHAPE, MARKER_SIZE, MARKER_ALPHA, MAP_PROJECTION, MAP_RESOLUTION, FIGURE_SIZE, TITLE)

# Run the main function
main()
