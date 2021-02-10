//PHP URL Phish

<html>
<title>Teste</title>
<body>
<form name="form" action="" method="GET">
Username: <input type="text" name="username">
Password: <input type="password" name="password">
<input type="submit" name="botton" value="Send">
</body>
<?php
$user = $_GET["username"];
$passwd = $_GET["password"];
print $user;
print $passwd;
?>
</html>
