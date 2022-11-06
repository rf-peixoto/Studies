// https://stackoverflow.com/questions/60984946/how-to-hash-the-contents-of-a-file-in-c

#include <openssl/md5.h>
#include <openssl/sha.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void main() {
    unsigned char sha256_digest[SHA256_DIGEST_LENGTH];
    unsigned char md5_digest[MD5_DIGEST_LENGTH];
    unsigned char *buffer = "Hello World!";
    int i;

    SHA256(buffer, strlen(buffer), sha256_digest);
    MD5(buffer, strlen(buffer), md5_digest);


    for (i = 0; i < SHA256_DIGEST_LENGTH; i++) {
        printf("%02x", sha256_digest[i]);
    }
    printf("\n");
    for (i = 0; i < MD5_DIGEST_LENGTH; i++) {
        printf("%02x", md5_digest[i]);
    }

}
