## Android-Emulator Proxy:

# Set proxy:
adb shell settings put global http_proxy 127.0.0.1:8080

# Android to host ort fowarding:
adb reverse tcp:8080 tcp:8080

# Remove fowarding:
adb reverse --remove-all

# Remove proxy:
adb shell settings put global http_proxy :0
