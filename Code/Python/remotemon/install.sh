sudo install -m 0755 remotemon.py /opt/remotemon.py
sudo systemctl daemon-reload
sudo systemctl enable --now server-monitor.service
sudo systemctl status server-monitor.service
