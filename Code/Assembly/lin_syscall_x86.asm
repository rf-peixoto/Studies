global _main
section .data
	TXT	"This is a text", 0xa
section .text
_main:
	MOV	RAX, 1
	MOV	RDI, 1
	MOV	RSI, TXT
	MOV	RDX, 15
	SYSCALL

	MOV	RAX, 60
	MOV RDI, 0
	SYSCALL