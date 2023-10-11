#!/bin/bash

# Install Apache and PHP if not installed
if ! dpkg -l | grep -q apache2; then
  sudo apt update
  sudo apt install -y apache2
fi

if ! dpkg -l | grep -q php; then
  sudo apt install -y php libapache2-mod-php
fi

# Create directories and files
mkdir -p /var/www/html/intranet/uploads

# Create upload.html
echo '<!DOCTYPE html>
<html>
<body>

<form action="upload.php" method="post" enctype="multipart/form-data">
  Select PHP file to upload:
  <input type="file" name="fileToUpload" id="fileToUpload">
  <input type="submit" value="Upload File" name="submit">
</form>

</body>
</html>' > /var/www/html/intranet/upload.html

# Create upload.php
echo '<?php
$target_dir = "uploads/";
$target_file = $target_dir . basename($_FILES["fileToUpload"]["name"]);

if (move_uploaded_file($_FILES["fileToUpload"]["tmp_name"], $target_file)) {
    echo "The file ". basename($_FILES["fileToUpload"]["name"]). " has been uploaded.";
} else {
    echo "Sorry, there was an error uploading your file.";
}
?>' > /var/www/html/intranet/upload.php

# Create .htaccess in uploads/ to disable PHP execution
echo 'php_flag engine off' > /var/www/html/intranet/uploads/.htaccess

# Change ownership and permissions
sudo chown -R www-data:www-data /var/www/html/intranet
sudo chmod -R 755 /var/www/html/intranet

# Enable .htaccess usage and restart Apache
sudo a2enmod rewrite

# Update Apache configuration
echo '<Directory /var/www/html/intranet>
  <FilesMatch ".*">
    Require all denied
  </FilesMatch>
  <FilesMatch "upload\.html|upload\.php">
    Require all granted
  </FilesMatch>
</Directory>

<Directory /var/www/html/intranet/uploads>
  AllowOverride All
  <FilesMatch ".*\.php">
    ForceType text/plain
  </FilesMatch>
</Directory>' | sudo tee -a /etc/apache2/apache2.conf > /dev/null

# Restart Apache
sudo systemctl restart apache2

echo "Honeypot setup complete. Visit http://localhost/intranet/upload.html to upload files."
