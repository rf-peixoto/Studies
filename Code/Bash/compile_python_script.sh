#pyinstaller --onefile --name output --key $1 --noconsole $2
nuitka3 --standalone --assume-yes-for-downloads $1
