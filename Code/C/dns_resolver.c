#include <stdio.h>
#include <netdb.h>
#include <arpa/inet.h>

int main(int argc, char *argv[]){

	if (argc <= 1){
		printf("Usage: ./dns_resolver website.com\n");
		return 0;
	} else {
		struct hostent *target = gethostbyname(argv[1]);
		if (target == NULL) {
			printf("Error. Check your argument.");
			return 0;
		}
		printf("Target IP: %s\n", inet_ntoa(*((struct in_addr *)target->h_addr)));
		return 0;
	}
}
