#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

enum { PUSH=1, ADD, MUL, XOR, HALT };
typedef struct { uint32_t values[32]; size_t top; } Stack;
static int push(Stack *s, uint32_t v) {
    if (s->top == 32) return -1;
    s->values[s->top++] = v;
    return 0;
}
static int pop(Stack *s, uint32_t *v) {
    if (!s->top) return -1;
    *v = s->values[--s->top];
    return 0;
}
static int execute(const uint32_t *code, size_t length, uint32_t *out) {
    Stack s = {{0},0};
    size_t pc = 0;
    while (pc < length) {
        uint32_t a,b, instruction = code[pc++];
        if (instruction == PUSH) {
            if (pc >= length || push(&s, code[pc++])) return -1;
        } else if (instruction == HALT) {
            return s.top == 1 ? pop(&s, out) : -1;
        } else if (instruction == ADD || instruction == MUL ||
                   instruction == XOR) {
            if (pop(&s,&b) || pop(&s,&a)) return -1;
            uint32_t result = instruction == ADD ? a+b :
                              instruction == MUL ? a*b : a^b;
            if (push(&s,result)) return -1;
        } else return -1;
    }
    return -1;
}
int main(void) {
    /* ((10+20)*3)^0x55 = 15 */
    const uint32_t program[] = {
        PUSH,10,PUSH,20,ADD,PUSH,3,MUL,PUSH,0x55,XOR,HALT
    };
    uint32_t result;
    if (execute(program, sizeof program / sizeof *program, &result)) return 1;
    printf("stack VM: %u\n", (unsigned)result);
    return result == 15u ? 0 : 1;
}
