// Created by ChatGPT (openai.com )
// Both atexit and _exit can be used to terminate a program, but atexit
// allows you to register functions that will be called before the
// program terminates, while _exit terminates the program immediately
// without calling any registered functions.

// ATEXIT

#include <stdlib.h>
#include <stdio.h>

void clean_up(void) {
  printf("Cleaning up before exit...\n");
}

int main(int argc, char* argv[]) {
  // Register the clean_up function to be called when the program exits
  atexit(clean_up);

  // Do some work here...

  // Terminate the program with a success code
  exit(EXIT_SUCCESS);
}

// _EXIT

#include <stdlib.h>
#include <stdio.h>

int main(int argc, char* argv[]) {
  // Do some work here...

  // Terminate the program immediately, without calling any registered
  // atexit functions or flushing any open streams
  _exit(EXIT_SUCCESS);
}
