#pyinstaller --onefile --name output --key $1 --noconsole $2
nuitka3 --verbose --standalone --assume-yes-for-downloads --follow-stdlib --follow-imports $1
