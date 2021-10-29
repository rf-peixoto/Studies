# Ref: https://www.hackingarticles.in/rce-with-lfi-and-ssh-log-poisoning/
<?php
   $file = $_GET['file'];
   if(isset($file)) {
       include("$file");
   } else {
       include("index.php");
   }
?>
