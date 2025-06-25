#!/usr/bin/env bash
set -e

# 1️⃣ Build the image
docker build -t subscan-image .

# 2️⃣ Run it, mounting only the subdomains file and mapping
#    your local `output/` into container:/app/output so you keep
#    /app intact
docker run --rm \
  -v "$(pwd)/subdomains.txt:/app/subdomains.txt:ro" \
  -v "$(pwd)/output:/app/output" \
  subscan-image
