#include <Windows.h>

int main() {
	ShellExecute(0, "open", "cmd", "/c calc.exe", 0, 0);
	return 0;
}