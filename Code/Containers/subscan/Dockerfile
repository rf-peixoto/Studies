# Use the official Python slim image for a smaller footprint
FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Install system dependencies required to build native Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libssl-dev \
        libffi-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install the Python libraries used by subscan.py
RUN pip install --no-cache-dir \
        requests \
        beautifulsoup4 \
        dnspython \
        ipwhois

# Copy the application code and the subdomains file into the container
COPY . /app

# Default entrypoint: run the subscan.py script
CMD ["python", "subscan.py"]
