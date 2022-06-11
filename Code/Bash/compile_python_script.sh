#pyinstaller --onefile --name output --key $1 --noconsole $2
# Use --standalone or --onefile
nuitka3 --remove-output --standalone --assume-yes-for-downloads --follow-stdlib --follow-imports $1
