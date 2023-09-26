lsection .data
    syscall_names db 'Unknown syscall',0
    syscall_names_len equ $ - syscall_names

section .text
    global print_syscall_name
    print_syscall_name:
        ; Argument: syscall ID in rdi

        ; Check if the syscall ID is valid (0-335).
        cmp rdi, 336
        jae invalid_syscall

        ; Array of syscall names (indexed by syscall number).
        mov rax, rdi
        mov rdi, syscall_names
        add rdi, rax

        ; Call the syscall to write the name to stdout.
        mov rax, 1         ; syscall number for write
        mov rdi, 1         ; file descriptor 1 (stdout)
        mov rsi, rdi       ; pointer to the syscall name
        mov rdx, syscall_names_len   ; length of the name
        syscall

        ret

    invalid_syscall:
        mov rax, 1         ; syscall number for write
        mov rdi, 1         ; file descriptor 1 (stdout)
        mov rsi, invalid_msg  ; pointer to the error message
        mov rdx, invalid_msg_len   ; length of the error message
        syscall

        ret

section .data
    invalid_msg db 'Invalid syscall ID',0
    invalid_msg_len equ $ - invalid_msg
