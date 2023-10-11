#!/bin/zsh

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
$filename = basename($_FILES["fileToUpload"]["name"]);
$file_extension = pathinfo($filename, PATHINFO_EXTENSION);

// Check if the file is a PHP file
if (strtolower($file_extension) === "php") {
    $target_file = $target_dir . pathinfo($filename, PATHINFO_FILENAME) . ".txt";
    
    if (move_uploaded_file($_FILES["fileToUpload"]["tmp_name"], $target_file)) {
        echo "The file ". basename($_FILES["fileToUpload"]["name"]). " has been uploaded: /intranet/uploads/.";
    } else {
        echo "Sorry, there was an error uploading your file.";
    }
} else {
    echo "Only PHP files are allowed.";
}
?>' > /var/www/html/intranet/upload.php

# Change ownership and permissions
sudo chown -R www-data:www-data /var/www/html/intranet
sudo chmod -R 777 /var/www/html/intranet/uploads

# Restart Apache
sudo systemctl restart apache2

echo "Honeypot setup complete. Visit http://localhost/intranet/upload.html to upload files."
