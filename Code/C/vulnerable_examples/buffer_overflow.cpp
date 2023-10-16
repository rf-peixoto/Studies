using namespace std;

#include <iostream>
#include <cstring>

int main() {
	char buffer[8];
	cout << "Random question to your input: ";
	cin >> buffer;
	cout << buffer <<endl;
	return 0;
}

/*
Exploitation example: buffer_overflow 123456789
*/
