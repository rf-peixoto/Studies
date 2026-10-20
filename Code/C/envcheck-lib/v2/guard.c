/* guard.c  —  enforcement example for the envcheck library.
 *
 * This is the "policy" layer that sits on top of the inspect-only library:
 * it runs the checks, and if the COMBINED score (vm_score + analysis_score)
 * reaches a threshold, it DELETES ITS OWN EXECUTABLE and stops immediately.
 * Otherwise it continues into whatever your real program does.
 *
 * This is a destructive self-protection pattern (standard anti-tamper): on a
 * tripped check the program erases its own binary so an analyst can't keep
 * poking at it, then exits. It only ever deletes its OWN executable image —
 * never any other file.
 *
 * ================== READ THIS BEFORE SHIPPING ==================
 *  * The threshold below (7) is DELIBERATELY the value you asked for, but it
 *    is LOW. Ordinary virtual machines, cloud instances, CI runners and
 *    VirtualBox desktops routinely score well above 7 (a plain KVM guest
 *    scores ~11-13 with no debugger present at all). With this threshold the
 *    binary will self-delete on many legitimate users' machines.
 *  * Self-deletion is irreversible and user-hostile on a false positive. Tune
 *    GUARD_THRESHOLD against real measurements from your target fleet, and
 *    strongly consider gating on analysis_score (active debugging) rather than
 *    vm_score (merely virtualized), since being in a VM is not, by itself, an
 *    attack.
 *  * Test with GUARD_DRY_RUN=1 in the environment first — it reports what it
 *    WOULD do without deleting anything.
 * ===============================================================
 *
 * Build:  cc -O2 guard.c envcheck.c -o guard          (Linux)
 *         cl /O2 guard.c envcheck.c                    (Windows, MSVC)
 */
#include "envcheck.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The combined-score threshold at which the binary self-destructs. */
#ifndef GUARD_THRESHOLD
#define GUARD_THRESHOLD 7
#endif

#if defined(_WIN32)
#  include <windows.h>
#  include <shellapi.h>
#  pragma comment(lib, "shell32.lib")
#else
#  include <unistd.h>
#endif

/* Resolve this process's own executable path. */
static int self_path(char *out, size_t n){
#if defined(_WIN32)
    DWORD r = GetModuleFileNameA(NULL, out, (DWORD)n);
    return (r>0 && r<n) ? 0 : -1;
#else
    ssize_t r = readlink("/proc/self/exe", out, n-1);
    if (r <= 0) return -1;
    out[r] = '\0';
    /* If the file is already gone, the kernel appends " (deleted)". */
    char *tag = strstr(out, " (deleted)");
    if (tag) *tag = '\0';
    return 0;
#endif
}

/* Delete this process's own executable. Returns 0 on success/scheduled. */
static int self_destruct(const char *path){
#if defined(_WIN32)
    /* A running image can't be unlinked directly on Windows, so hand the
       delete to a detached cmd that waits for us to exit, then removes it. */
    char cmd[1024];
    snprintf(cmd, sizeof(cmd),
             "/c ping 127.0.0.1 -n 2 >nul & del /f /q \"%s\"", path);
    HINSTANCE h = ShellExecuteA(NULL, "open", "cmd.exe", cmd, NULL, SW_HIDE);
    return ((INT_PTR)h > 32) ? 0 : -1;
#else
    return unlink(path);   /* removes the on-disk binary; we keep running until exit */
#endif
}

int main(void){
    int dry = 0;
    { const char *e = getenv("GUARD_DRY_RUN"); if (e && *e && *e!='0') dry = 1; }

    env_report_t r = env_inspect(NULL);
    int total = r.vm_score + r.analysis_score;

    if (total >= GUARD_THRESHOLD){
        char path[4096];
        int havep = (self_path(path, sizeof(path)) == 0);

        if (dry){
            fprintf(stderr,
                "[guard] DRY RUN: combined score %d >= %d — WOULD delete \"%s\" and exit.\n",
                total, GUARD_THRESHOLD, havep ? path : "(unknown path)");
            return 3;   /* dry-run signals the trip without acting */
        }

        /* Live: erase our own binary, then halt immediately. No report, no
           hint to the analyst about which check tripped. */
        if (havep) self_destruct(path);

#if defined(_WIN32)
        ExitProcess(1);
#else
        _exit(1);
#endif
    }

    /* ---- Environment considered clean: your real program starts here. ---- */
    printf("environment OK (combined score %d < %d) — continuing.\n",
           total, GUARD_THRESHOLD);
    /* ... real application logic ... */
    return 0;
}
