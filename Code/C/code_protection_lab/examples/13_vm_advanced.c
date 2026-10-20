#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

/*
 * Register machine:
 * ADDI r, imm ; ADD dst, src ; SUBI r, imm ;
 * JNZ r, target ; HALT r
 * All instruction operands are uint32_t words.
 */
enum { ADDI=1, ADD, SUBI, JNZ, HALT };
typedef struct {
    uint32_t r[4];
    size_t pc;
    size_t steps;
} VM;
static int execute(const uint32_t *code, size_t length,
                   size_t budget, uint32_t *out) {
    VM vm = {{0},0,0};
    while (vm.pc < length && vm.steps++ < budget) {
        uint32_t op = code[vm.pc++];
        if (op == ADDI || op == SUBI || op == ADD || op == JNZ) {
            if (length - vm.pc < 2) return -1;
            uint32_t a = code[vm.pc++], b = code[vm.pc++];
            if (a >= 4) return -1;
            if (op == ADDI) vm.r[a] += b;
            if (op == SUBI) vm.r[a] -= b;
            if (op == ADD) {
                if (b >= 4) return -1;
                vm.r[a] += vm.r[b];
            }
            if (op == JNZ && vm.r[a] != 0) {
                if (b >= length) return -1;
                vm.pc = b;
            }
        } else if (op == HALT) {
            if (vm.pc >= length || code[vm.pc] >= 4) return -1;
            *out = vm.r[code[vm.pc]];
            return 0;
        } else return -1;
    }
    return -1;
}
int main(void) {
    /*
       r0=0; r1=5; loop: r0+=r1; r1-=1; if (r1) loop;
       return r0 => 15
       pc offsets index words, not instructions.
    */
    const uint32_t program[] = {
        ADDI,1,5,       /* pc 0 */
        ADD,0,1,        /* pc 3 */
        SUBI,1,1,       /* pc 6 */
        JNZ,1,3,        /* pc 9 */
        HALT,0          /* pc 12 */
    };
    uint32_t result = 0;
    if (execute(program,sizeof program/sizeof *program,1000,&result))
        return 1;
    printf("register VM: %u\n", (unsigned)result);
    return result == 15u ? 0 : 1;
}
