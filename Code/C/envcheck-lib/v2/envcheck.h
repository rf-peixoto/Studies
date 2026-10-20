/* envcheck.h  —  environment inspection library (public API)
 *
 * Software-protection / anti-reversing environment inspector.
 *
 * DESIGN CONTRACT
 *   Every check INSPECTS and REPORTS into env_report_t. Nothing here kills the
 *   process, branches your logic, wipes data, phones home, or hides its own
 *   activity. The caller reads the struct and decides what (if anything) to do.
 *   Nothing is obfuscated. A handful of probes deliberately raise-and-catch a
 *   CPU fault/exception internally, or (opt-in) change thread/process state;
 *   each is flagged in env_options_t and in the source. They only record a
 *   boolean — your program's behaviour is unchanged.
 *
 * REALITY CHECK
 *   A speed bump, not a wall. It raises the cost of casual analysis and defeats
 *   many automated sandboxes. A skilled analyst on bare metal, or one who
 *   patches the checks out, gets through. Several signals also fire on
 *   legitimate hosts (cloud dev boxes, WSL, containers, CI runners, low-spec
 *   laptops). Weigh the aggregate scores; never treat one hit as proof.
 *
 * USAGE
 *     #include "envcheck.h"
 *     env_report_t r = env_inspect(NULL);            // NULL => default options
 *     env_layout_matches(&r, "pt", 0x0416);          // optional market check
 *     if (r.analysis_score >= 6 || r.vm_score >= 8) { ...your policy... }
 *
 *     // or emit JSON:
 *     char buf[8192];
 *     env_report_to_json(&r, buf, sizeof(buf));
 *     fputs(buf, stdout);
 *
 * BUILD (into your project)
 *     Linux:   cc -O2 -c envcheck.c
 *     Windows: cl /O2 /c envcheck.c           (MSVC recommended)
 */
#ifndef ENVCHECK_H
#define ENVCHECK_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    /* ---- VM / hypervisor ---- */
    int  hypervisor_bit;            char hypervisor_vendor[13];
    int  vm_cpu_brand;              /* CPUID brand string looks virtual     */
    int  vm_mac_prefix;
    int  vm_dmi_string;
    int  vm_artifact_present;
    int  vm_vmware_backdoor;        /* VMware I/O backdoor port responded    */
    int  cpuinfo_hypervisor;        /* Linux /proc/cpuinfo hypervisor flag   */
    int  wine_present;              /* running under Wine                    */
    int  wsl_present;               /* running under WSL                     */
    int  fw_vm_table;               char fw_vm_hit[16];   /* ACPI/SMBIOS firmware tables name a VM */
    int  pci_vm_device;             char pci_vm_id[24];   /* PCI vendor id belongs to a VM vendor  */
    int  disk_vm_model;             /* disk model string looks virtual       */
    int  gpu_vm_model;              char gpu_name[64];    /* GPU/display adapter looks virtual      */
    int  no_thermal_sensor;         /* no thermal sensors (VMs usually lack)  */
    int  no_battery;                /* no battery present (reported, unscored)*/
    int  vm_named_pipe;             /* Windows VM/sandbox named pipe present  */
    int  seccomp_active;            /* Linux seccomp filter installed         */
    int  unusual_namespace;         /* Linux: in a non-init PID namespace     */
    int  yama_ptrace_scope;         /* Linux Yama ptrace_scope value (reported)*/

    /* ---- Debugger / tracer ---- */
    int  debugger_present;
    int  tracer_pid;
    int  ptrace_self_blocked;
    int  peb_being_debugged;
    int  peb_ntglobalflag;
    int  hw_breakpoints;
    int  debug_port_set;
    int  ld_preload_set;
    int  ld_audit_set;              /* Linux LD_AUDIT present (hooking vector)*/
    int  seh_int3_debugger;
    int  closehandle_debugger;
    int  kernel_debugger;           /* bare-metal/kernel debugger enabled    */

    /* ---- Analysis tooling / hooks / instrumentation / parent ---- */
    int  analysis_tool_found;       char analysis_tool_name[64];   /* running  */
    int  analysis_tool_installed;   char analysis_tool_inst_name[64]; /* on disk/PATH */
    int  analysis_dll_loaded;       char analysis_dll_name[64];
    int  instrumentation_found;     char instrumentation_name[64]; /* Frida/Pin/... */
    int  parent_process_suspicious; char parent_name[64];

    /* ---- Containers ---- */
    int  container_detected;        char container_type[32];

    /* ---- Sandbox resource / behavioral heuristics ---- */
    unsigned int       cpu_count;   int low_cpu_count;
    unsigned long long ram_mb;      int low_ram;
    unsigned long long disk_gb;     int small_disk;
    unsigned long long uptime_sec;  int short_uptime;
    int  suspicious_identity;
    int  small_screen;              /* default sandbox resolution            */
    unsigned long long input_idle_sec; int no_user_input; /* no human present */
    long sleep_skew_ms;             int sleep_skew_suspicious; /* time accel.  */

    /* ---- Timing ---- */
    uint64_t cpuid_cycles;          int timing_suspicious;

    /* ---- Keyboard layout / market ---- */
    unsigned int primary_langid;    char layout_name[32];
    int  layout_matches_target;

    /* ---- Aggregate ---- */
    int  vm_score;
    int  analysis_score;
} env_report_t;

/* Controls for the probes that are slow or that change state. */
typedef struct {
    int run_ptrace_self;   /* Linux PTRACE_TRACEME probe (changes+restores state). Default 1. */
    int run_io_backdoor;   /* VMware backdoor port probe (raises+catches a CPU fault). Default 1. */
    int run_sleep_skew;    /* sleep ~200ms and measure (adds latency). Default 0. */
} env_options_t;

/* Sensible defaults: ptrace-self and backdoor on, sleep-skew off. */
env_options_t env_default_options(void);

/* Run every inspection. Pass NULL for env_default_options(). */
env_report_t  env_inspect(const env_options_t *opts);

/* Coarse market check. Pass the layout/language substring you expect for your
   intended audience (e.g. "pt"), and/or a Windows LANGID (e.g. 0x0416 pt-BR).
   Records and returns 1 on match, 0 otherwise. */
int env_layout_matches(env_report_t *r, const char *expect_substr,
                       unsigned int expect_langid);

/* Serialize the report as a JSON object into out[0..n). Returns the number of
   bytes that would be written (snprintf semantics). */
int env_report_to_json(const env_report_t *r, char *out, size_t n);

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* ENVCHECK_H */
