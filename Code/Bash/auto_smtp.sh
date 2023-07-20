sudo apt-get install postfix
sudo postconf -e "smtpd_port = 25"
sudo postconf -e "smtpd_relayhost = localhost"
sudo touch /etc/mail/virtual/domains
echo "@$1 mail exchanger = 1 localhost" >> /etc/mail/virtual/domains
sudo touch /etc/postfix/sieve/main.cf
echo "smtpd_recipient_restrictions = permit_mynetworks, permit_sasl_authenticated, reject_unauth_destination, check_policy_service unix:private/policy-spf" >> /etc/postfix/sieve/main.cf
sudo touch /etc/postfix/dmarc.conf
echo "dmarc_policy = quarantine" >> /etc/postfix/dmarc.conf
sudo touch /etc/postfix/dkim.conf
echo "dkim_selector = default" >> /etc/postfix/dkim.conf
echo "dkim_domain = $1" >> /etc/postfix/dkim.conf
echo "dkim_private_key = /etc/postfix/dkim.private" >> /etc/postfix/dkim.conf
echo "dkim_key_length = 4096" >> /etc/postfix/dkim.conf
echo "dkim_sign_policy = strict" >> /etc/postfix/dkim.conf
sudo postconf -e "dkim_genkey = yes"
sudo service postfix restart
