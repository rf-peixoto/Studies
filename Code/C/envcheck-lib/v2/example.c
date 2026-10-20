/* example.c  —  optional demo driver for the envcheck library.
 *
 * Build:
 *   Linux:   cc -O2 example.c envcheck.c -o envcheck
 *   Windows: cl /O2 example.c envcheck.c
 *
 * Prints the environment report as JSON and exits. Takes no other action.
 */
#include "envcheck.h"
#include <stdio.h>

int main(void){
    env_options_t opts = env_default_options();
    opts.run_sleep_skew = 1;          /* enable the time-acceleration probe */

    env_report_t r = env_inspect(&opts);
    env_layout_matches(&r, "pt", 0x0416 /* pt-BR; adjust to your market */);

    char buf[8192];
    env_report_to_json(&r, buf, sizeof(buf));
    fputs(buf, stdout);
    return 0;
}
