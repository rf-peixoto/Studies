#!/usr/bin/env bash
set -euo pipefail

# 1. Stop all running containers
running_containers=$(docker ps -q)
if [ -n "$running_containers" ]; then
  echo "Stopping running containers..."
  docker stop $running_containers
fi

# 2. Remove all containers (stopped or running)
all_containers=$(docker ps -aq)
if [ -n "$all_containers" ]; then
  echo "Removing all containers..."
  docker rm -f $all_containers
fi

# 3. Remove all images
all_images=$(docker images -aq)
if [ -n "$all_images" ]; then
  echo "Removing all images..."
  docker rmi -f $all_images
fi

# 4. (Optional) Remove unused volumes and networks
# Uncomment the lines below if you also want to clean up volumes and networks
# echo "Pruning unused volumes..."
# docker volume prune -f
# echo "Pruning unused networks..."
# docker network prune -f

echo "Docker environment is now clean."
