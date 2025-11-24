### Build:
docker build -t server-monitor .

### First run:
docker run --rm -it -v $(pwd)/config:/app server-monitor

### Bot started on /app and config json created at ./config/server_monitor.json. Edit credentials, them:
docker run -d --name server-monitor -v $(pwd)/config:/app --restart=unless-stopped server-monitor
