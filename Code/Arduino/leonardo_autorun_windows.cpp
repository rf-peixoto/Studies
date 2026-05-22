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

    // Your backup command here
    Keyboard.print("echo Arduino test > %USERPROFILE%\\Downloads\\arduino_test.txt && exit");
    Keyboard.write(KEY_RETURN);

    // Stop keyboard emulation
    Keyboard.end();
}

void loop() {
    // Nothing here
}
