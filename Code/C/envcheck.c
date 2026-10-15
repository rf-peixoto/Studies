/* envcheck.c
 *
 * Environment inspection module for software-protection purposes.
 *
 * DESIGN CONTRACT
 *   - Every function only INSPECTS and REPORTS. No function kills the process,
 *     alters behaviour, wipes data, or hides its own activity. The caller reads
 *     the result struct and decides what (if anything) to do.
 *   - Nothing here is obfuscated or stealthy. The checks are plainly named and
 *     plainly commented so you (and auditors) can see exactly what runs.
 *
 * SCOPE
 *   - Hypervisor / VM / sandbox heuristics
 *   - Debugger / tracer presence
 *   - Coarse keyboard-layout check (intended-market signal, NOT geolocation)
 *   - Crude timing artifact
 *
 * CAVEAT (be realistic)
 *   None of this stops a determined reverse engineer. VM/debugger detection is
 *   a speed bump: it raises the cost of casual analysis and automated sandboxes.
 *   A skilled analyst on bare metal, or one who patches these checks out, will
 *   get past them. Treat the output as a risk signal, not a verdict.
 *
 * BUILD
 *   Linux:   cc -O2 -DENVCHECK_DEMO envcheck.c -o envcheck
 *   Windows: cl /O2 /DENVCHECK_DEMO envcheck.c   (links to standard libs)
 */

#include <stdint.h>
#include <string.h>
#include <stdio.h>

/* ------------------------------------------------------------------ */
/* Platform detection                                                  */
/* ------------------------------------------------------------------ */
#if defined(_WIN32)
#  define ENV_WINDOWS 1
#  include <windows.h>
#  include <intrin.h>
#  include <iphlpapi.h>
#  pragma comment(lib, "iphlpapi.lib")
#elif defined(__linux__)
#  define ENV_LINUX 1
#  include <stdlib.h>
#  include <unistd.h>
#  include <fcntl.h>
#  include <sys/stat.h>
#  include <sys/ptrace.h>
#  include <sys/ioctl.h>
#  include <net/if.h>
#  include <sys/socket.h>
#  include <dirent.h>
#  if defined(__i386__) || defined(__x86_64__)
#    include <cpuid.h>
#  endif
#endif

/* ------------------------------------------------------------------ */
/* Result structure                                                    */
/* ------------------------------------------------------------------ */

typedef struct {
    /* Hypervisor / VM */
    int   hypervisor_bit;          /* CPUID.1:ECX[31] set                 */
    char  hypervisor_vendor[13];   /* CPUID 0x40000000 vendor string      */
    int   vm_mac_prefix;           /* NIC MAC matches a known VM OUI       */
    int   vm_dmi_string;           /* DMI/product strings look virtual     */
    int   vm_artifact_present;     /* known guest-tool file/device found   */

    /* Debugger / tracer */
    int   debugger_present;        /* a debugger/tracer is attached        */
    int   tracer_pid;              /* Linux TracerPid value (0 if none)    */

    /* Timing */
    uint64_t cpuid_cycles;         /* cycles around a serialising CPUID    */
    int   timing_suspicious;       /* above a rough threshold              */

    /* Keyboard layout / intended market */
    unsigned int primary_langid;   /* low word of primary layout langid    */
    char  layout_name[32];         /* best-effort human-readable layout    */
    int   layout_matches_target;   /* set by env_layout_matches()          */

    /* Aggregate */
    int   vm_score;                /* 0..N, higher = more VM-like          */
} env_report_t;

/* ------------------------------------------------------------------ */
/* Low-level helpers                                                   */
/* ------------------------------------------------------------------ */

#if defined(__i386__) || defined(__x86_64__) || defined(_M_IX86) || defined(_M_X64)
#  define ENV_X86 1
static void env_cpuid(uint32_t leaf, uint32_t subleaf, uint32_t out[4]) {
#  if defined(ENV_WINDOWS)
    int regs[4];
    __cpuidex(regs, (int)leaf, (int)subleaf);
    out[0]=(uint32_t)regs[0]; out[1]=(uint32_t)regs[1];
    out[2]=(uint32_t)regs[2]; out[3]=(uint32_t)regs[3];
#  else
    __cpuid_count(leaf, subleaf, out[0], out[1], out[2], out[3]);
#  endif
}
static uint64_t env_rdtsc(void) {
#  if defined(ENV_WINDOWS)
    return __rdtsc();
#  else
    uint32_t lo, hi;
    __asm__ __volatile__("rdtsc" : "=a"(lo), "=d"(hi));
    return ((uint64_t)hi << 32) | lo;
#  endif
}
#endif

/* ------------------------------------------------------------------ */
/* 1. Hypervisor bit + vendor string (CPUID)                           */
/* ------------------------------------------------------------------ */

static void check_cpuid_hypervisor(env_report_t *r) {
    r->hypervisor_bit = 0;
    r->hypervisor_vendor[0] = '\0';
#if defined(ENV_X86)
    uint32_t regs[4];

    /* CPUID.1:ECX bit 31 — set on every mainstream hypervisor. */
    env_cpuid(1, 0, regs);
    r->hypervisor_bit = (regs[2] >> 31) & 1;

    /* CPUID 0x40000000 — hypervisors return a 12-byte vendor ID in EBX:ECX:EDX.
       Examples: "VMwareVMware", "KVMKVMKVM\0\0\0", "Microsoft Hv",
       "XenVMMXenVMM", "VBoxVBoxVBox", "TCGTCGTCGTCG" (QEMU/TCG),
       "prl hyperv  " (Parallels). */
    if (r->hypervisor_bit) {
        env_cpuid(0x40000000, 0, regs);
        memcpy(r->hypervisor_vendor + 0, &regs[1], 4);
        memcpy(r->hypervisor_vendor + 4, &regs[2], 4);
        memcpy(r->hypervisor_vendor + 8, &regs[3], 4);
        r->hypervisor_vendor[12] = '\0';
    }
#endif
}

/* ------------------------------------------------------------------ */
/* 2. Timing artifact (VM exits make serialising instructions slow)    */
/* ------------------------------------------------------------------ */

static void check_timing(env_report_t *r) {
    r->cpuid_cycles = 0;
    r->timing_suspicious = 0;
#if defined(ENV_X86)
    uint32_t regs[4];
    uint64_t best = (uint64_t)-1;
    /* Take the minimum over several runs to filter scheduling noise.
       CPUID forces a VM exit under many hypervisors, inflating the delta. */
    for (int i = 0; i < 16; ++i) {
        uint64_t t0 = env_rdtsc();
        env_cpuid(0, 0, regs);
        uint64_t t1 = env_rdtsc();
        uint64_t d = t1 - t0;
        if (d < best) best = d;
    }
    r->cpuid_cycles = best;
    /* Bare metal is typically well under a few hundred cycles for CPUID.
       This threshold is deliberately loose and will have false positives;
       tune it for your hardware or drop it entirely. */
    r->timing_suspicious = (best > 1000);
#endif
}

/* ------------------------------------------------------------------ */
/* 3. NIC MAC address vs known virtual OUIs                            */
/* ------------------------------------------------------------------ */

/* First 3 bytes (OUI) assigned to virtualization vendors. */
static int mac_is_virtual(const unsigned char m[6]) {
    static const unsigned char ouis[][3] = {
        {0x00,0x05,0x69}, {0x00,0x0C,0x29}, {0x00,0x1C,0x14}, {0x00,0x50,0x56}, /* VMware */
        {0x08,0x00,0x27},                                                       /* VirtualBox */
        {0x00,0x15,0x5D},                                                       /* Hyper-V */
        {0x00,0x16,0x3E},                                                       /* Xen */
        {0x00,0x1C,0x42},                                                       /* Parallels */
        {0x52,0x54,0x00},                                                       /* QEMU/KVM */
    };
    for (size_t i = 0; i < sizeof(ouis)/sizeof(ouis[0]); ++i)
        if (m[0]==ouis[i][0] && m[1]==ouis[i][1] && m[2]==ouis[i][2])
            return 1;
    return 0;
}

static void check_mac(env_report_t *r) {
    r->vm_mac_prefix = 0;
#if defined(ENV_WINDOWS)
    IP_ADAPTER_INFO info[32];
    ULONG len = sizeof(info);
    if (GetAdaptersInfo(info, &len) == ERROR_SUCCESS) {
        for (IP_ADAPTER_INFO *a = info; a; a = a->Next) {
            if (a->AddressLength == 6 && mac_is_virtual(a->Address)) {
                r->vm_mac_prefix = 1; break;
            }
        }
    }
#elif defined(ENV_LINUX)
    struct if_nameindex *ifs = if_nameindex();
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (ifs && fd >= 0) {
        for (struct if_nameindex *p = ifs; p->if_name; ++p) {
            struct ifreq req; memset(&req, 0, sizeof(req));
            strncpy(req.ifr_name, p->if_name, IFNAMSIZ-1);
            if (ioctl(fd, SIOCGIFHWADDR, &req) == 0) {
                unsigned char *m = (unsigned char*)req.ifr_hwaddr.sa_data;
                if (mac_is_virtual(m)) { r->vm_mac_prefix = 1; break; }
            }
        }
    }
    if (fd >= 0) close(fd);
    if (ifs) if_freenameindex(ifs);
#endif
}

/* ------------------------------------------------------------------ */
/* 4. DMI / product strings + guest-tool artifacts                     */
/* ------------------------------------------------------------------ */

static int str_has_vm_keyword(const char *s) {
    static const char *kw[] = {
        "vmware","virtualbox","vbox","qemu","kvm","xen","bochs",
        "parallels","hyper-v","microsoft corporation virtual","innotek"
    };
    char low[256]; size_t i;
    for (i = 0; s[i] && i < sizeof(low)-1; ++i)
        low[i] = (char)((s[i]>='A'&&s[i]<='Z') ? s[i]+32 : s[i]);
    low[i] = '\0';
    for (size_t k = 0; k < sizeof(kw)/sizeof(kw[0]); ++k)
        if (strstr(low, kw[k])) return 1;
    return 0;
}

static void check_dmi_and_artifacts(env_report_t *r) {
    r->vm_dmi_string = 0;
    r->vm_artifact_present = 0;
#if defined(ENV_LINUX)
    /* DMI strings exposed by the kernel; virtual firmware advertises itself. */
    const char *dmi[] = {
        "/sys/class/dmi/id/product_name",
        "/sys/class/dmi/id/sys_vendor",
        "/sys/class/dmi/id/board_vendor",
        "/sys/class/dmi/id/bios_vendor",
    };
    for (size_t i = 0; i < sizeof(dmi)/sizeof(dmi[0]); ++i) {
        int fd = open(dmi[i], O_RDONLY);
        if (fd >= 0) {
            char buf[256]; ssize_t n = read(fd, buf, sizeof(buf)-1);
            close(fd);
            if (n > 0) { buf[n] = '\0'; if (str_has_vm_keyword(buf)) r->vm_dmi_string = 1; }
        }
    }
    /* Guest-tool device nodes / modules that normal hosts don't have. */
    const char *artifacts[] = {
        "/dev/vboxguest", "/dev/vboxuser", "/dev/vmci",
        "/proc/scsi/scsi",  /* often lists VBOX/VMware model strings */
        "/sys/bus/pci/drivers/vmw_pvscsi",
    };
    for (size_t i = 0; i < sizeof(artifacts)/sizeof(artifacts[0]); ++i) {
        struct stat st;
        if (stat(artifacts[i], &st) == 0) { r->vm_artifact_present = 1; break; }
    }
#elif defined(ENV_WINDOWS)
    /* System manufacturer/model from the registry. */
    HKEY h; char buf[256]; DWORD sz = sizeof(buf);
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,
            "HARDWARE\\DESCRIPTION\\System\\BIOS", 0, KEY_READ, &h) == ERROR_SUCCESS) {
        sz = sizeof(buf);
        if (RegQueryValueExA(h, "SystemManufacturer", 0, 0, (LPBYTE)buf, &sz) == ERROR_SUCCESS)
            if (str_has_vm_keyword(buf)) r->vm_dmi_string = 1;
        sz = sizeof(buf);
        if (RegQueryValueExA(h, "SystemProductName", 0, 0, (LPBYTE)buf, &sz) == ERROR_SUCCESS)
            if (str_has_vm_keyword(buf)) r->vm_dmi_string = 1;
        RegCloseKey(h);
    }
    /* Guest-tool driver files commonly present inside VMs. */
    const char *files[] = {
        "C:\\Windows\\System32\\drivers\\vmmouse.sys",
        "C:\\Windows\\System32\\drivers\\vmhgfs.sys",
        "C:\\Windows\\System32\\drivers\\VBoxMouse.sys",
        "C:\\Windows\\System32\\drivers\\VBoxGuest.sys",
        "C:\\Windows\\System32\\vboxdisp.dll",
    };
    for (size_t i = 0; i < sizeof(files)/sizeof(files[0]); ++i) {
        if (GetFileAttributesA(files[i]) != INVALID_FILE_ATTRIBUTES) {
            r->vm_artifact_present = 1; break;
        }
    }
#endif
}

/* ------------------------------------------------------------------ */
/* 5. Debugger / tracer presence                                       */
/* ------------------------------------------------------------------ */

static void check_debugger(env_report_t *r) {
    r->debugger_present = 0;
    r->tracer_pid = 0;
#if defined(ENV_WINDOWS)
    if (IsDebuggerPresent()) r->debugger_present = 1;
    BOOL remote = FALSE;
    if (CheckRemoteDebuggerPresent(GetCurrentProcess(), &remote) && remote)
        r->debugger_present = 1;
#elif defined(ENV_LINUX)
    /* /proc/self/status reports the PID of any tracer (0 = none). */
    int fd = open("/proc/self/status", O_RDONLY);
    if (fd >= 0) {
        char buf[4096]; ssize_t n = read(fd, buf, sizeof(buf)-1);
        close(fd);
        if (n > 0) {
            buf[n] = '\0';
            char *p = strstr(buf, "TracerPid:");
            if (p) {
                r->tracer_pid = atoi(p + 10);
                if (r->tracer_pid != 0) r->debugger_present = 1;
            }
        }
    }
    /* Note: a PTRACE_TRACEME probe is also common, but it CHANGES state
       (it attaches the caller as its own tracer), so it is intentionally
       omitted here to honour the "inspect only, take no action" contract. */
#endif
}

/* ------------------------------------------------------------------ */
/* 6. Keyboard layout — coarse intended-market signal                  */
/*    This reads the active layout's language id. It is a locale hint,  */
/*    nothing more: it does not locate the user.                        */
/* ------------------------------------------------------------------ */

static void check_keyboard_layout(env_report_t *r) {
    r->primary_langid = 0;
    r->layout_name[0] = '\0';
    r->layout_matches_target = -1;   /* -1 = not evaluated yet */
#if defined(ENV_WINDOWS)
    HKL hkl = GetKeyboardLayout(0);
    /* Low word of the HKL is the input language identifier (LANGID). */
    r->primary_langid = (unsigned int)(LOWORD((DWORD_PTR)hkl));
    /* Human-readable name via the locale. */
    LCID lcid = MAKELCID(r->primary_langid, SORT_DEFAULT);
    GetLocaleInfoA(lcid, LOCALE_SISO639LANGNAME, r->layout_name, sizeof(r->layout_name));
#elif defined(ENV_LINUX)
    /* On the console there is no "keyboard layout" API comparable to Windows.
       Under X11 you'd query XkbGetState + the layout group names; under
       Wayland it depends on the compositor. As a portable, dependency-free
       fallback we read the locale environment, which usually tracks the
       language the user configured. */
    const char *env = getenv("LC_ALL");
    if (!env || !*env) env = getenv("LC_CTYPE");
    if (!env || !*env) env = getenv("LANG");
    if (env && *env) {
        strncpy(r->layout_name, env, sizeof(r->layout_name)-1);
        r->layout_name[sizeof(r->layout_name)-1] = '\0';
    }
    /* r->primary_langid stays 0 on Linux; compare layout_name instead. */
#endif
}

/* Caller-supplied comparison. Pass the layout/language substring you expect
   for your intended market (e.g. "pt" for Portuguese, "de" for German, or a
   Windows LANGID). Returns 1 on match, 0 otherwise, and records it. */
static int env_layout_matches(env_report_t *r, const char *expect_substr,
                              unsigned int expect_langid) {
    int match = 0;
    if (expect_langid && r->primary_langid == expect_langid) match = 1;
    if (!match && expect_substr && r->layout_name[0]) {
        /* case-insensitive substring */
        char a[64], b[64]; size_t i;
        for (i = 0; r->layout_name[i] && i < sizeof(a)-1; ++i)
            a[i] = (char)((r->layout_name[i]>='A'&&r->layout_name[i]<='Z')?r->layout_name[i]+32:r->layout_name[i]);
        a[i]='\0';
        for (i = 0; expect_substr[i] && i < sizeof(b)-1; ++i)
            b[i] = (char)((expect_substr[i]>='A'&&expect_substr[i]<='Z')?expect_substr[i]+32:expect_substr[i]);
        b[i]='\0';
        if (strstr(a, b)) match = 1;
    }
    r->layout_matches_target = match;
    return match;
}

/* ------------------------------------------------------------------ */
/* Orchestrator — runs every inspection, computes an aggregate score   */
/* ------------------------------------------------------------------ */

static env_report_t env_inspect(void) {
    env_report_t r;
    memset(&r, 0, sizeof(r));

    check_cpuid_hypervisor(&r);
    check_timing(&r);
    check_mac(&r);
    check_dmi_and_artifacts(&r);
    check_debugger(&r);
    check_keyboard_layout(&r);

    /* Weighted sum. These are signals, not proof — the hypervisor bit alone
       is normal on many legitimate hosts (nested virt, WSL2, cloud dev boxes),
       so one hit should never be treated as conclusive. */
    r.vm_score  = 0;
    r.vm_score += r.hypervisor_bit;
    r.vm_score += (r.hypervisor_vendor[0] != '\0') ? 2 : 0;
    r.vm_score += r.vm_mac_prefix        ? 2 : 0;
    r.vm_score += r.vm_dmi_string        ? 3 : 0;
    r.vm_score += r.vm_artifact_present  ? 3 : 0;
    r.vm_score += r.timing_suspicious    ? 1 : 0;

    return r;
}

/* ------------------------------------------------------------------ */
/* Demo / self-test — prints findings, takes no other action           */
/* ------------------------------------------------------------------ */
#ifdef ENVCHECK_DEMO
int main(void) {
    env_report_t r = env_inspect();

    /* Example market check: expect Portuguese. Adjust to your audience. */
    env_layout_matches(&r, "pt", 0x0416 /* pt-BR LANGID, ignored on Linux */);

    printf("== Environment report ==\n");
    printf("hypervisor_bit      : %d\n", r.hypervisor_bit);
    printf("hypervisor_vendor   : %s\n", r.hypervisor_vendor[0] ? r.hypervisor_vendor : "(none)");
    printf("vm_mac_prefix       : %d\n", r.vm_mac_prefix);
    printf("vm_dmi_string       : %d\n", r.vm_dmi_string);
    printf("vm_artifact_present : %d\n", r.vm_artifact_present);
    printf("debugger_present    : %d\n", r.debugger_present);
    printf("tracer_pid          : %d\n", r.tracer_pid);
    printf("cpuid_cycles (min)  : %llu\n", (unsigned long long)r.cpuid_cycles);
    printf("timing_suspicious   : %d\n", r.timing_suspicious);
    printf("primary_langid      : 0x%04x\n", r.primary_langid);
    printf("layout_name         : %s\n", r.layout_name[0] ? r.layout_name : "(unknown)");
    printf("layout_matches      : %d\n", r.layout_matches_target);
    printf("-----------------------\n");
    printf("vm_score            : %d  (higher = more VM-like)\n", r.vm_score);

    /* NOTE: we only printed. The module never decides on your behalf. */
    return 0;
}
#endif
