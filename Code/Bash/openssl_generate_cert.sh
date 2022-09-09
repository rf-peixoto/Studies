openssl req -new -x509 -keyout cert.pem -out cert.pem -days 365 -nodes
openssl req -newkey rsa:2048 -nodes -keyout key.pem -x509 -days 365 -out certificate.pem
