global _main

section .data
	TEXT DB 'HELLO WORLD', 0xa	; 0xA = \n

section .text
_main :
	MOV	EAX, 4		;_ASM_X86_UNISTD_32H > __NR_write 4
	MOV	EBX, 1		; 0 = STDIN | 1 = STDOUT | 2 = STDERR
	MOV	ECX, TEXT	; STRING TO PRINT
	MOV EDX, 12 	; STRING SIZE
	INT 0x80

	MOV	EAX, 1		; syscall exit
	MOV	EBX, 0
	INT	0x80

