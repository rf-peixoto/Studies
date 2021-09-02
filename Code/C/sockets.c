#include <stdio.h>
#include <sys/socket.h>
#include <netdb.h>

int main(void) {
	int s;
	int connection;

	struct sockaddr_in target;
	s = socket(AF_INET, SOCK_STREAM, 0); // s = Socket
	target.sin_family = AF_INET;	// AF_INET : TCP
	target.sin_port = htons(80);	// Port
	target.sin_addr.s_addr = inet_addr("192.168.0.1"); // inet_addr translate address.

	connection = connect(s, (struct sockaddr *)&target, sizeof target); // Connection

	if (connection == 0) {
		printf("Connected.\n");
		close(s);
		close(connection);
	}
	return 0;
}
