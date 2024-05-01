#include <stdio.h>
#include <stdbool.h>

// Function to set a bit at a given position
void setBit(int *num, int position) {
    *num |= 1 << position;
}

// Function to clear a bit at a given position
void clearBit(int *num, int position) {
    *num &= ~(1 << position);
}

// Function to toggle a bit at a given position
void toggleBit(int *num, int position) {
    *num ^= 1 << position;
}

// Function to check if a bit at a given position is set
bool checkBit(int num, int position) {
    return (num & (1 << position)) != 0;
}

int main() {
    int flags = 0; // Initialize all bits to 0

    // Set bits at position 0, 1, and 2
    setBit(&flags, 0);
    setBit(&flags, 1);
    setBit(&flags, 2);

    // Check if bits are set
    printf("Bit 0 is %s\n", checkBit(flags, 0) ? "set" : "not set");
    printf("Bit 1 is %s\n", checkBit(flags, 1) ? "set" : "not set");
    printf("Bit 2 is %s\n", checkBit(flags, 2) ? "set" : "not set");

    // Clear bit at position 1
    clearBit(&flags, 1);

    // Check again
    printf("After clearing, Bit 1 is %s\n", checkBit(flags, 1) ? "set" : "not set");

    // Toggle bit at position 0
    toggleBit(&flags, 0);

    // Check again
    printf("After toggling, Bit 0 is %s\n", checkBit(flags, 0) ? "set" : "not set");

    return 0;
}
