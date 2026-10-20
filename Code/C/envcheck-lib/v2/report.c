/* report.c  —  test harness for the envcheck library.
 *
 * Runs env_inspect(), prints a per-signal breakdown with the points each
 * contributes, the VM and analysis subtotals, a combined total, and a
 * heuristic percentage of "running in a VM / controlled environment".
 *
 * Build:  ./build.sh        (or see that script for the raw cc line)
 * Run:    ./report           [--json] [--no-ptrace] [--no-backdoor] [--sleep-skew]
 *
 * NOTE ON THE PERCENTAGE
 *   The weights are a heuristic, and several signals are platform-specific or
 *   mutually exclusive, so no single run can light up every flag. The percentage
 *   is score / theoretical-maximum, shown as a confidence-style indicator with
 *   interpretation bands — NOT a calibrated probability. Trust the breakdown and
 *   the bands more than the exact number.
 */
#include "envcheck.h"
#include <stdio.h>
#include <string.h>

/* One row of the breakdown: a human label, whether it fired, and its weight.
   The weights MUST mirror env_inspect() in envcheck.c. If you retune the
   library's scoring, update these to match. */
typedef struct { const char *label; int fired; int weight; } row_t;

static int print_section(const char *title, const row_t *rows, int n,
                         int *out_score, int *out_max){
    int score=0, max=0;
    printf("  %s\n", title);
    printf("  %-34s %6s %7s\n", "signal", "points", "fired");
    printf("  ------------------------------------ ------ -------\n");
    for (int i=0;i<n;i++){
        max += rows[i].weight;
        int pts = rows[i].fired ? rows[i].weight : 0;
        score += pts;
        printf("  %-34s %6d %7s\n",
               rows[i].label, pts, rows[i].fired ? "yes" : "-");
    }
    printf("  ------------------------------------ ------ -------\n");
    printf("  %-34s %6d  / %d\n\n", "subtotal", score, max);
    *out_score=score; *out_max=max;
    return score;
}

static const char *band(double pct){
    if (pct >= 60.0) return "VERY HIGH  — almost certainly a VM / analysis host";
    if (pct >= 35.0) return "HIGH       — likely a controlled environment";
    if (pct >= 18.0) return "MODERATE   — some signals; could be cloud/CI/low-spec HW";
    if (pct >   0.0) return "LOW        — a few weak signals, probably benign";
    return               "NONE       — no signals fired";
}

int main(int argc, char **argv){
    env_options_t o = env_default_options();
    int want_json = 0;

    for (int i=1;i<argc;i++){
        if      (!strcmp(argv[i],"--json"))       want_json=1;
        else if (!strcmp(argv[i],"--no-ptrace"))  o.run_ptrace_self=0;
        else if (!strcmp(argv[i],"--no-backdoor"))o.run_io_backdoor=0;
        else if (!strcmp(argv[i],"--sleep-skew")) o.run_sleep_skew=1;
        else if (!strcmp(argv[i],"--help")){
            printf("usage: %s [--json] [--no-ptrace] [--no-backdoor] [--sleep-skew]\n", argv[0]);
            return 0;
        }
    }

    env_report_t r = env_inspect(&o);
    env_layout_matches(&r, "pt", 0x0416 /* pt-BR; change to your market */);

    if (want_json){
        char buf[8192];
        env_report_to_json(&r, buf, sizeof(buf));
        fputs(buf, stdout);
        return 0;
    }

    /* ---- VM / environment signals (mirror env_inspect weights) ---- */
    row_t vm[] = {
        {"hypervisor_bit",            r.hypervisor_bit,        1},
        {"hypervisor_vendor",         r.hypervisor_vendor[0]!=0,2},
        {"cpu_brand_virtual",         r.vm_cpu_brand,          2},
        {"mac_prefix",                r.vm_mac_prefix,         2},
        {"dmi_string",                r.vm_dmi_string,         3},
        {"artifact_present",          r.vm_artifact_present,   3},
        {"vmware_backdoor",           r.vm_vmware_backdoor,    3},
        {"cpuinfo_hypervisor",        r.cpuinfo_hypervisor,    1},
        {"wine",                      r.wine_present,          2},
        {"wsl",                       r.wsl_present,           1},
        {"container",                 r.container_detected,    2},
        {"timing_suspicious",         r.timing_suspicious,     1},
        {"low_cpu_count",             r.low_cpu_count,         1},
        {"low_ram",                   r.low_ram,               1},
        {"small_disk",                r.small_disk,            1},
        {"short_uptime",              r.short_uptime,          1},
        {"suspicious_identity",       r.suspicious_identity,   2},
        {"small_screen",              r.small_screen,          1},
        {"no_user_input",             r.no_user_input,         1},
        {"sleep_skew_suspicious",     r.sleep_skew_suspicious, 2},
        {"firmware_table",            r.fw_vm_table,           3},
        {"pci_vm_device",             r.pci_vm_device,         3},
        {"disk_vm_model",             r.disk_vm_model,         2},
        {"gpu_vm_model",              r.gpu_vm_model,          2},
        {"no_thermal_sensor",         r.no_thermal_sensor,     1},
        {"vm_named_pipe",             r.vm_named_pipe,         2},
        {"seccomp_active",            r.seccomp_active,        2},
        {"unusual_namespace",         r.unusual_namespace,     1},
        {"no_battery (unscored)",     r.no_battery,            0},
    };
    /* ---- Analysis / debugging signals (mirror env_inspect weights) ---- */
    row_t an[] = {
        {"debugger_present",          r.debugger_present,         3},
        {"kernel_debugger",           r.kernel_debugger,          3},
        {"analysis_tool_running",     r.analysis_tool_found,      3},
        {"analysis_tool_installed",   r.analysis_tool_installed,  2},
        {"hook_dll_loaded",           r.analysis_dll_loaded,      3},
        {"instrumentation",           r.instrumentation_found,    3},
        {"parent_suspicious",         r.parent_process_suspicious,3},
        {"hw_breakpoints",            r.hw_breakpoints,           2},
        {"peb_ntglobalflag",          r.peb_ntglobalflag,         1},
        {"ld_preload_set",            r.ld_preload_set,           1},
        {"ld_audit_set",              r.ld_audit_set,             1},
        {"ptrace_self_blocked",       r.ptrace_self_blocked,      2},
        {"seh_int3",                  r.seh_int3_debugger,        3},
        {"closehandle",               r.closehandle_debugger,     3},
    };

    printf("============================================================\n");
    printf(" envcheck environment report\n");
    printf("============================================================\n\n");

    int vm_score, vm_max, an_score, an_max;
    print_section("[VM / controlled-environment signals]", vm,
                  (int)(sizeof(vm)/sizeof(vm[0])), &vm_score, &vm_max);
    print_section("[Analysis / debugging signals]", an,
                  (int)(sizeof(an)/sizeof(an[0])), &an_score, &an_max);

    /* Sanity: our recomputed subtotals should equal the library's own. */
    if (vm_score != r.vm_score || an_score != r.analysis_score)
        printf("  (note: recomputed %d/%d vs library %d/%d — weights drifted)\n\n",
               vm_score, an_score, r.vm_score, r.analysis_score);

    int total     = vm_score + an_score;
    int total_max = vm_max + an_max;
    double pct     = total_max ? (100.0 * total / total_max) : 0.0;
    double vm_pct  = vm_max    ? (100.0 * vm_score / vm_max) : 0.0;
    double an_pct  = an_max    ? (100.0 * an_score / an_max) : 0.0;

    printf("------------------------------------------------------------\n");
    printf("  VM score          : %3d / %-3d  (%.0f%%)\n", vm_score, vm_max, vm_pct);
    printf("  Analysis score    : %3d / %-3d  (%.0f%%)\n", an_score, an_max, an_pct);
    printf("  TOTAL score       : %3d / %-3d\n", total, total_max);
    printf("------------------------------------------------------------\n");
    printf("  VM / controlled-env likelihood : %.0f%%\n", pct);
    printf("  Assessment : %s\n", band(pct));
    printf("------------------------------------------------------------\n");
    printf("  Context: hypervisor=\"%s\" parent=\"%s\"",
           r.hypervisor_vendor[0]?r.hypervisor_vendor:"-",
           r.parent_name[0]?r.parent_name:"-");
    if (r.analysis_tool_found)     printf(" tool_running=\"%s\"", r.analysis_tool_name);
    if (r.analysis_tool_installed) printf(" tool_installed=\"%s\"", r.analysis_tool_inst_name);
    if (r.instrumentation_found)   printf(" instrumentation=\"%s\"", r.instrumentation_name);
    if (r.fw_vm_table)             printf(" firmware=\"%s\"", r.fw_vm_hit);
    if (r.pci_vm_device)           printf(" pci=\"%s\"", r.pci_vm_id);
    if (r.gpu_vm_model)            printf(" gpu=\"%s\"", r.gpu_name);
    printf("\n");
    printf("  (heuristic indicator, not a calibrated probability — see README)\n");

    return 0;
}
