extern _MessageBoxA ; Using external function from User32.dll
global _main

section .data
	MESSAGE	DB "This is a message.", 0
	TITL DB "Title", 0 ; ,0 = Quebra de Linha

section .text
_main:
	PUSH 0
	PUSH TITL
	PUSH MESSAGE
	PUSH 0 ; -> NULL
	CALL _MessageBoxA