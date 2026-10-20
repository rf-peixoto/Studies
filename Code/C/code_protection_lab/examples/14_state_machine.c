#include <stddef.h>
#include <stdio.h>

/*
 * Accept strings matching: one or more uppercase ASCII letters,
 * followed by a colon, followed by one or more digits.
 * Table-driven DFA, states: 0=start, 1=letters, 2=colon,
 * 3=digits, 4=reject.
 */
enum { LETTER=0, DIGIT, COLON, OTHER };
static const unsigned char transitions[5][4] = {
    {1,4,4,4},
    {1,4,2,4},
    {4,3,4,4},
    {4,3,4,4},
    {4,4,4,4}
};
static unsigned classify(unsigned char c) {
    if (c >= 'A' && c <= 'Z') return LETTER;
    if (c >= '0' && c <= '9') return DIGIT;
    if (c == ':') return COLON;
    return OTHER;
}
static int valid(const char *s) {
    unsigned state = 0;
    for (; *s; ++s) state = transitions[state][classify((unsigned char)*s)];
    return state == 3;
}
int main(void) {
    static const char *samples[] = {"ABC:123","A:7","ABC:",":123","abc:3","HI:22X"};
    static const int expected[] = {1,1,0,0,0,0};
    for (size_t i=0;i<sizeof samples/sizeof *samples;i++) {
        int actual = valid(samples[i]);
        printf("%s => %s\n", samples[i], actual ? "accepted" : "rejected");
        if (actual != expected[i]) return 1;
    }
    return 0;
}
