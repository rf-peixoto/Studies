// #include libs.h Ex:
#include <stdio.h>
#include <stdlib.h>

// Main funcion (with args):
int main(int argc, char *argv[]) {
	// Check args. 2 is our example number.
	if (argc < 2) {
		printf("Usage %s [instructions]\n", argv[0]);
	} else {
		// Your code goes here.
		printf("Do your thing.\n");
	}
	// Close program.
	return 0;
} // End.
