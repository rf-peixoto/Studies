#pyinstaller --onefile --name output --key $1 --noconsole $2

# pip install nuitka nuitka3
# Use --standalone or --onefile
# --onefile requires --linux-onefile-icon=/usr/share/icons/hicolor/scalable/apps/org.gnome.Shell.Extensions.svg
python -m nuitka --remove-output --standalone --assume-yes-for-downloads --follow-stdlib --follow-imports $1
# Options:
# --enable-plugin=tk-inter
