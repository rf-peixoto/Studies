#!/bin/bash

echo "Stopping docker images..."
docker stop $(docker ps -a -q)

echo "Removing docker images..."
docker rm $(docker ps -a -q)

echo "Read to shutdown..."
sleep 3
shutdown now
