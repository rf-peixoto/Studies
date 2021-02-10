extern _ShellExecuteA ; Using external function from Shell32.dll
global _main

section .data
	TP	DB "open", 0
	FL	DB	"cmd", 0
	ARG	DB "/c notepad.exe",0

section .text
_main:
	PUSH 0 ; Window type: 0 -> SW_Hide
	PUSH 0
	PUSH ARG
	PUSH FL
	PUSH TP
	PUSH 0
	CALL _ShellExecuteA
