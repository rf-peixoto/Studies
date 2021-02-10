#include <netdb.h>
#include <stdio.h>
#include <sys/socket.h>
#include <arpa/inet.h>

int main (int arc, char *argv[]) {

	if (argc <= 1) {
		printf("No arguments were passed. Enter the domain:");
		char[] domain;
		fgets(domain, 32, stdin);
		printf("IP: %s\n", inet_ntoa(domain));

		return 0;
	} else {
		struct hostent *target = gethostbyname(argv[1]);
		if (target == NULL) {
			printf("An error ocurred!\n");
		} else {
			printf("IP: %s\n", inet_ntoa(*((struct in_addr *) target -> h_addr)));
			return 0;
		}
	}
}
/*
int main (int argc, char *argv[]) {

	if (argc <= 1) {
		printf("Erro. Modo de uso: sdos domain.com");
	} else {
		// Declarando variáveis:
		int socket;
		int connection;
		struct sockaddr_n target;
		
		// Configurando:
		socket = sock(AF_INET, SOCK_STREAM, 0);
		target.sin.family = AF_INET;
		target.sin.port = htons(20);

		// Conectando:
		connection = connect(socket, (struct sockaddr *) & target, sizeoftarget);
		if (connection == 0) {
			printf("Sucesso");
		}

	}

}
*/
