#!/bin/bash

# =============================================================================
# Script: manage_tor_nodes.sh
# Description: Manages Dockerized Tor relay nodes by checking their status,
#              monitoring Tor processes, reporting log sizes, and providing
#              options to stop or remove the containers and their images.
# =============================================================================

set -e  # Exit immediately if a command exits with a non-zero status

# ---------------------------- Configuration ----------------------------

# Directory where logs are stored
LOGS_DIR="$HOME/tor-monitoring/logs"

# Pattern to identify Tor node containers
CONTAINER_PATTERN="tor-node*"

# Output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ---------------------------- Helper Functions ----------------------------

# Function to display usage information
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -status       Check the status of all Tor node containers."
    echo "  -stop         Stop all Tor node containers."
    echo "  -remove       Stop and remove all Tor node containers and their images."
    echo "  -help         Display this help message."
    echo ""
    echo "Examples:"
    echo "  $0 -status"
    echo "  $0 -stop"
    echo "  $0 -remove"
    exit 1
}

# Function to check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null
    then
        echo -e "${RED}Docker is not installed. Please install Docker and try again.${NC}"
        exit 1
    fi
}

# Function to retrieve all Tor node container names
get_tor_nodes() {
    docker ps -a --filter "name=$CONTAINER_PATTERN" --format "{{.Names}}"
}

# Function to check if a container is running
is_running() {
    local container="$1"
    status=$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || echo "false")
    if [ "$status" == "true" ]; then
        echo "Running"
    else
        echo "Stopped"
    fi
}

# Function to check if Tor is running inside the container
is_tor_running() {
    local container="$1"
    if [ "$(is_running "$container")" == "Running" ]; then
        # Check if the Tor process is active
        if docker exec "$container" pgrep tor > /dev/null 2>&1; then
            echo "Active"
        else
            echo "Inactive"
        fi
    else
        echo "N/A"
    fi
}

# Function to get the size of the log file
get_log_size() {
    local container="$1"
    # Extract node identifier from container name (e.g., tor-node1 -> node1)
    node_id=$(echo "$container" | sed 's/tor-//')
    log_file="$LOGS_DIR/$node_id/notices.log"

    if [ -f "$log_file" ]; then
        du -h "$log_file" | awk '{print $1}'
    else
        echo "Not Found"
    fi
}

# Function to display status of all nodes
display_status() {
    local nodes=("$@")
    if [ ${#nodes[@]} -eq 0 ]; then
        echo -e "${YELLOW}No Tor node containers found.${NC}"
        exit 0
    fi

    # Print table header
    printf "%-15s %-10s %-15s %-15s\n" "Node Name" "Docker" "Tor Relay" "Log Size"
    printf "%-15s %-10s %-15s %-15s\n" "--------- " "------" "---------" "--------"

    for container in "${nodes[@]}"; do
        node_name="$container"
        docker_status=$(is_running "$container")
        tor_status=$(is_tor_running "$container")
        log_size=$(get_log_size "$container")

        # Color coding based on status
        if [ "$docker_status" == "Running" ]; then
            docker_color=$GREEN
        else
            docker_color=$RED
        fi

        if [ "$tor_status" == "Active" ]; then
            tor_color=$GREEN
        elif [ "$tor_status" == "Inactive" ]; then
            tor_color=$RED
        else
            tor_color=$YELLOW
        fi

        # Print the status row
        printf "%-15s ${docker_color}%-10s${NC} ${tor_color}%-15s${NC} %-15s\n" \
            "$node_name" "$docker_status" "$tor_status" "$log_size"
    done
}

# Function to stop all Tor node containers
stop_containers() {
    local nodes=("$@")
    if [ ${#nodes[@]} -eq 0 ]; then
        echo -e "${YELLOW}No Tor node containers to stop.${NC}"
        exit 0
    fi

    echo "Stopping Tor node containers..."
    for container in "${nodes[@]}"; do
        docker stop "$container" && echo "Stopped $container"
    done
    echo -e "${GREEN}All Tor node containers have been stopped.${NC}"
}

# Function to remove all Tor node containers and their images
remove_containers_and_images() {
    local nodes=("$@")
    if [ ${#nodes[@]} -eq 0 ]; then
        echo -e "${YELLOW}No Tor node containers to remove.${NC}"
        exit 0
    fi

    echo "Stopping Tor node containers before removal..."
    for container in "${nodes[@]}"; do
        docker stop "$container" && echo "Stopped $container"
    done

    echo "Removing Tor node containers..."
    for container in "${nodes[@]}"; do
        docker rm "$container" && echo "Removed $container"
    done

    echo "Removing Tor node Docker images..."
    for container in "${nodes[@]}"; do
        # Get the image used by the container
        image=$(docker inspect -f '{{.Config.Image}}' "$container" 2>/dev/null || echo "none")
        if [ "$image" != "none" ]; then
            docker rmi "$image" && echo "Removed image $image for container $container"
        else
            echo "No image found for container $container"
        fi
    done

    echo -e "${GREEN}All Tor node containers and their images have been removed.${NC}"
}

# ---------------------------- Main Script Logic ----------------------------

# Check if Docker is installed
check_docker

# Retrieve all Tor node containers
TOR_NODES=$(get_tor_nodes)

# Convert to array
readarray -t NODE_ARRAY <<< "$TOR_NODES"

# Parse command-line arguments
if [ $# -eq 0 ]; then
    # Default action: display status
    display_status "${NODE_ARRAY[@]}"
    exit 0
fi

case "$1" in
    -status)
        display_status "${NODE_ARRAY[@]}"
        ;;
    -stop)
        stop_containers "${NODE_ARRAY[@]}"
        ;;
    -remove)
        remove_containers_and_images "${NODE_ARRAY[@]}"
        ;;
    -help|--help)
        usage
        ;;
    *)
        echo -e "${RED}Invalid option: $1${NC}"
        usage
        ;;
esac
