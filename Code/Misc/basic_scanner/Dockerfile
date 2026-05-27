FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GOTOOLCHAIN=auto \
    VIRTUAL_ENV=/opt/scanner-venv \
    PATH="/opt/scanner-venv/bin:/root/go/bin:/usr/local/go/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        golang-go \
        build-essential \
        dnsutils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY scan.py /app/scan.py
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN python -m venv "$VIRTUAL_ENV" \
    && python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt \
    && go install github.com/tomnomnom/assetfinder@latest \
    && go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest \
    && go install github.com/projectdiscovery/httpx/cmd/httpx@latest \
    && go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

VOLUME ["/data", "/output"]

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["/data/domains.txt", "--output-dir", "/output"]
