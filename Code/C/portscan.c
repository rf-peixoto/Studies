#include <stdio.h>
#include <netdb.h>
#include <sys/socket.h>


int main(int argc, char *argv[]) {
	// Declare variables:
	int skt;
	int conn;
	// Create Structure:
	struct sockaddr_in target;
	// Create Socket:
	skt = socket(AF_INET, SOCK_STREAM, 0);
	// Loop
	for (int port = 0; port < 65535; port++) {
		target.sin_family = AF_INET;
		target.sin_port = htons(port);
		target.sin_addr.s_addr = inet_addr(argv[1]); //First arg: target IP.
		// Connect:
		conn = connect(skt, (struct sockaddr *)&target, sizeof target);
		// Check if was open:
		if (conn == 0) {
			printf("%d: Open\n", port);
			close(skt);
			close(conn);
		} else {
			//printf("Now on port %d\n", port); //Debug only!
			close(skt);
			close(conn);
		}
	}
	return 0;
}
