section .text
global _start

_start:
  xor rdx, rdx
  push rdx
  mov rax, 0x68732f2f6e69622f ; /bin/sh in little endian: "hs//nib/"
  push rax
  mov rdi, rsp

  push rdx
  push rdi
  mov rsi, rsp
  xor rax, rax
  mov al, 0x3b ; syscall execve (59) in hex
