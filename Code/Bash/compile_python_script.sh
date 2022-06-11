#pyinstaller --onefile --name output --key $1 --noconsole $2
# Use --standalone or --onefile
# --onefile requires --linux-onefile-icon=/usr/share/icons/hicolor/scalable/apps/org.gnome.Shell.Extensions.svg
nuitka3 --remove-output --standalone --assume-yes-for-downloads --follow-stdlib --follow-imports $1
# Options:
# --enable-plugin=tk-inter
