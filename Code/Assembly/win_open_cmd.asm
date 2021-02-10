extern system ; Using external function.
global _main
section .text

_main:
	PUSH 0x00657865 ; 00.exe
	PUSH 0x2e646d63 ; .cmd
	PUSH ESP
	POP EAX
	PUSH EAX
	MOV EBX, 0x7653dc0 ; system(), on msvcrt.dll
	CALL EBX