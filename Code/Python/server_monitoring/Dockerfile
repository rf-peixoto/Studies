FROM python:3.12-slim

# Dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd -ms /bin/bash appuser

# Dir
WORKDIR /app

# Copy code
COPY server_monitor.py /app/server_monitor.py

# Install psutil
RUN pip install --no-cache-dir psutil

# Check permissions
RUN chown -R appuser:appuser /app
USER appuser

# Avoid buffering
ENV PYTHONUNBUFFERED=1

# Default command:
CMD ["python", "server_monitor.py"]
