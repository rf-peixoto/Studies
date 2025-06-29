# Use the official Python 3.12 slim image
FROM python:3.12-slim

# Prevent Python from writing .pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
# Ensure that stdout/stderr is flushed immediately
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install pip dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the escavator script into the container
COPY escavator.py .

# Default command: run escavator.py
ENTRYPOINT ["python", "escavator.py"]
