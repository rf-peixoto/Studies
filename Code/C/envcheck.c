/* envcheck.c  —  comprehensive edition
 *
 * Environment inspection module for software-protection purposes.
 *
 * BUILD
 *   Linux:   cc -O2 -DENVCHECK_DEMO envcheck.c -o envcheck
 *   Windows: cl /O2 /DENVCHECK_DEMO envcheck.c
 */

#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

/* ------------------------------------------------------------------ */
/* Platform detection                                                  */
/* ------------------------------------------------------------------ */
#if defined(_WIN32)
#  define ENV_WINDOWS 1
#  include <windows.h>
#  include <intrin.h>
#  include <iphlpapi.h>
#  include <tlhelp32.h>
#  pragma comment(lib, "iphlpapi.lib")
#elif defined(__linux__)
#  define ENV_LINUX 1
#  include <unistd.h>
#  include <fcntl.h>
#  include <sys/stat.h>
#  include <sys/ptrace.h>
#  include <sys/ioctl.h>
#  include <sys/sysinfo.h>
#  include <sys/statvfs.h>
#  include <net/if.h>
#  include <sys/socket.h>
#  include <dirent.h>
#  if defined(__i386__) || defined(__x86_64__)
#    include <cpuid.h>
#  endif
#endif

#if defined(__i386__) || defined(__x86_64__) || defined(_M_IX86) || defined(_M_X64)
#  define ENV_X86 1
#endif

/* ------------------------------------------------------------------ */
/* Result structure                                                    */
/* ------------------------------------------------------------------ */

typedef struct {
    /* --- Hypervisor / VM --- */
    int   hypervisor_bit;
    char  hypervisor_vendor[13];
    int   vm_mac_prefix;
    int   vm_dmi_string;
    int   vm_artifact_present;

    /* --- Debugger / tracer --- */
    int   debugger_present;        /* any debugger/tracer signal          */
    int   tracer_pid;              /* Linux TracerPid                      */
    int   ptrace_self_blocked;     /* PTRACE_TRACEME failed => already traced */
    int   peb_being_debugged;      /* Windows PEB.BeingDebugged            */
    int   peb_ntglobalflag;        /* Windows PEB.NtGlobalFlag debug bits  */
    int   hw_breakpoints;          /* Windows Dr0-Dr3/Dr7 set              */
    int   debug_port_set;          /* Windows NtQueryInformationProcess    */
    int   ld_preload_set;          /* Linux LD_PRELOAD present             */

    /* --- Analysis tooling --- */
    int   analysis_tool_found;
    char  analysis_tool_name[64];

    /* --- Sandbox resource heuristics --- */
    unsigned int cpu_count;        int low_cpu_count;
    unsigned long long ram_mb;     int low_ram;
    unsigned long long disk_gb;    int small_disk;
    unsigned long long uptime_sec; int short_uptime;
    int   suspicious_identity;     /* host/user name looks like a sandbox  */

    /* --- Timing --- */
    uint64_t cpuid_cycles;         int timing_suspicious;

    /* --- Keyboard layout / market --- */
    unsigned int primary_langid;
    char  layout_name[32];
    int   layout_matches_target;

    /* --- Aggregate --- */
    int   vm_score;
    int   analysis_score;
} env_report_t;

/* ------------------------------------------------------------------ */
/* Low-level helpers                                                   */
/* ------------------------------------------------------------------ */
#if defined(ENV_X86)
static void env_cpuid(uint32_t leaf, uint32_t sub, uint32_t o[4]) {
#  if defined(ENV_WINDOWS)
    int r[4]; __cpuidex(r,(int)leaf,(int)sub);
    o[0]=(uint32_t)r[0];o[1]=(uint32_t)r[1];o[2]=(uint32_t)r[2];o[3]=(uint32_t)r[3];
#  else
    __cpuid_count(leaf,sub,o[0],o[1],o[2],o[3]);
#  endif
}
static uint64_t env_rdtsc(void) {
#  if defined(ENV_WINDOWS)
    return __rdtsc();
#  else
    uint32_t lo,hi; __asm__ __volatile__("rdtsc":"=a"(lo),"=d"(hi));
    return ((uint64_t)hi<<32)|lo;
#  endif
}
#endif

/* case-insensitive substring, returns 1 if needle in haystack */
static int ci_contains(const char *hay, const char *needle) {
    char a[512], b[128]; size_t i;
    for (i=0; hay[i] && i<sizeof(a)-1; ++i)
        a[i]=(char)((hay[i]>='A'&&hay[i]<='Z')?hay[i]+32:hay[i]);
    a[i]='\0';
    for (i=0; needle[i] && i<sizeof(b)-1; ++i)
        b[i]=(char)((needle[i]>='A'&&needle[i]<='Z')?needle[i]+32:needle[i]);
    b[i]='\0';
    return strstr(a,b) != NULL;
}

/* ------------------------------------------------------------------ */
/* 1. Hypervisor bit + vendor string                                   */
/* ------------------------------------------------------------------ */
static void check_cpuid_hypervisor(env_report_t *r) {
#if defined(ENV_X86)
    uint32_t g[4];
    env_cpuid(1,0,g);
    r->hypervisor_bit = (g[2]>>31)&1;
    if (r->hypervisor_bit) {
        env_cpuid(0x40000000,0,g);
        memcpy(r->hypervisor_vendor+0,&g[1],4);
        memcpy(r->hypervisor_vendor+4,&g[2],4);
        memcpy(r->hypervisor_vendor+8,&g[3],4);
        r->hypervisor_vendor[12]='\0';
    }
#endif
}

/* ------------------------------------------------------------------ */
/* 2. Timing artifact                                                  */
/* ------------------------------------------------------------------ */
static void check_timing(env_report_t *r) {
#if defined(ENV_X86)
    uint32_t g[4]; uint64_t best=(uint64_t)-1;
    for (int i=0;i<16;++i){
        uint64_t t0=env_rdtsc(); env_cpuid(0,0,g); uint64_t t1=env_rdtsc();
        if (t1-t0<best) best=t1-t0;
    }
    r->cpuid_cycles=best;
    r->timing_suspicious=(best>1000); /* loose; tune per hardware */
#endif
}

/* ------------------------------------------------------------------ */
/* 3. NIC MAC vs known virtual OUIs                                    */
/* ------------------------------------------------------------------ */
static int mac_is_virtual(const unsigned char m[6]) {
    static const unsigned char o[][3]={
        {0x00,0x05,0x69},{0x00,0x0C,0x29},{0x00,0x1C,0x14},{0x00,0x50,0x56}, /* VMware */
        {0x08,0x00,0x27},                                                    /* VirtualBox */
        {0x00,0x15,0x5D},                                                    /* Hyper-V */
        {0x00,0x16,0x3E},                                                    /* Xen */
        {0x00,0x1C,0x42},                                                    /* Parallels */
        {0x52,0x54,0x00},                                                    /* QEMU/KVM */
    };
    for (size_t i=0;i<sizeof(o)/sizeof(o[0]);++i)
        if (m[0]==o[i][0]&&m[1]==o[i][1]&&m[2]==o[i][2]) return 1;
    return 0;
}
static void check_mac(env_report_t *r) {
#if defined(ENV_WINDOWS)
    IP_ADAPTER_INFO info[32]; ULONG len=sizeof(info);
    if (GetAdaptersInfo(info,&len)==ERROR_SUCCESS)
        for (IP_ADAPTER_INFO *a=info;a;a=a->Next)
            if (a->AddressLength==6 && mac_is_virtual(a->Address)){r->vm_mac_prefix=1;break;}
#elif defined(ENV_LINUX)
    struct if_nameindex *ifs=if_nameindex(); int fd=socket(AF_INET,SOCK_DGRAM,0);
    if (ifs&&fd>=0)
        for (struct if_nameindex *p=ifs;p->if_name;++p){
            struct ifreq q; memset(&q,0,sizeof(q));
            strncpy(q.ifr_name,p->if_name,IFNAMSIZ-1);
            if (ioctl(fd,SIOCGIFHWADDR,&q)==0 &&
                mac_is_virtual((unsigned char*)q.ifr_hwaddr.sa_data)){r->vm_mac_prefix=1;break;}
        }
    if (fd>=0) close(fd);
    if (ifs) if_freenameindex(ifs);
#endif
}

/* ------------------------------------------------------------------ */
/* 4. DMI / registry strings + guest-tool artifacts                    */
/* ------------------------------------------------------------------ */
static int str_has_vm_keyword(const char *s){
    static const char *kw[]={"vmware","virtualbox","vbox","qemu","kvm","xen",
        "bochs","parallels","hyper-v","virtual machine","innotek"};
    for (size_t k=0;k<sizeof(kw)/sizeof(kw[0]);++k) if (ci_contains(s,kw[k])) return 1;
    return 0;
}
static void check_dmi_and_artifacts(env_report_t *r){
#if defined(ENV_LINUX)
    const char *dmi[]={"/sys/class/dmi/id/product_name","/sys/class/dmi/id/sys_vendor",
        "/sys/class/dmi/id/board_vendor","/sys/class/dmi/id/bios_vendor"};
    for (size_t i=0;i<sizeof(dmi)/sizeof(dmi[0]);++i){
        int fd=open(dmi[i],O_RDONLY);
        if (fd>=0){char b[256];ssize_t n=read(fd,b,sizeof(b)-1);close(fd);
            if (n>0){b[n]='\0'; if (str_has_vm_keyword(b)) r->vm_dmi_string=1;}}
    }
    const char *art[]={"/dev/vboxguest","/dev/vboxuser","/dev/vmci",
        "/sys/bus/pci/drivers/vmw_pvscsi","/proc/scsi/scsi"};
    for (size_t i=0;i<sizeof(art)/sizeof(art[0]);++i){
        struct stat st; if (stat(art[i],&st)==0){r->vm_artifact_present=1;break;}
    }
#elif defined(ENV_WINDOWS)
    HKEY h; char b[256]; DWORD sz;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,"HARDWARE\\DESCRIPTION\\System\\BIOS",
            0,KEY_READ,&h)==ERROR_SUCCESS){
        sz=sizeof(b); if (RegQueryValueExA(h,"SystemManufacturer",0,0,(LPBYTE)b,&sz)==ERROR_SUCCESS)
            if (str_has_vm_keyword(b)) r->vm_dmi_string=1;
        sz=sizeof(b); if (RegQueryValueExA(h,"SystemProductName",0,0,(LPBYTE)b,&sz)==ERROR_SUCCESS)
            if (str_has_vm_keyword(b)) r->vm_dmi_string=1;
        RegCloseKey(h);
    }
    const char *f[]={
        "C:\\Windows\\System32\\drivers\\vmmouse.sys",
        "C:\\Windows\\System32\\drivers\\vmhgfs.sys",
        "C:\\Windows\\System32\\drivers\\VBoxMouse.sys",
        "C:\\Windows\\System32\\drivers\\VBoxGuest.sys",
        "C:\\Windows\\System32\\vboxdisp.dll",
        "C:\\Windows\\System32\\drivers\\vmci.sys"};
    for (size_t i=0;i<sizeof(f)/sizeof(f[0]);++i)
        if (GetFileAttributesA(f[i])!=INVALID_FILE_ATTRIBUTES){r->vm_artifact_present=1;break;}
    /* Sandboxie module loaded in-process */
    if (GetModuleHandleA("SbieDll.dll")) r->vm_artifact_present=1;
#endif
}

/* ------------------------------------------------------------------ */
/* 5. Debugger / tracer presence                                       */
/* ------------------------------------------------------------------ */
static void check_debugger(env_report_t *r){
#if defined(ENV_WINDOWS)
    if (IsDebuggerPresent()) r->debugger_present=1;
    BOOL rem=FALSE;
    if (CheckRemoteDebuggerPresent(GetCurrentProcess(),&rem)&&rem) r->debugger_present=1;

    /* Read the PEB directly (documented offsets). */
#  if defined(_M_X64) || defined(__x86_64__)
    unsigned char *peb=(unsigned char*)__readgsqword(0x60);
    if (peb){
        r->peb_being_debugged = peb[0x02] ? 1 : 0;
        unsigned int ngf=*(unsigned int*)(peb+0xBC);
        r->peb_ntglobalflag = (ngf & 0x70) ? 1 : 0; /* heap debug flags */
    }
#  elif defined(_M_IX86) || defined(__i386__)
    unsigned char *peb=(unsigned char*)__readfsdword(0x30);
    if (peb){
        r->peb_being_debugged = peb[0x02] ? 1 : 0;
        unsigned int ngf=*(unsigned int*)(peb+0x68);
        r->peb_ntglobalflag = (ngf & 0x70) ? 1 : 0;
    }
#  endif
    if (r->peb_being_debugged || r->peb_ntglobalflag) r->debugger_present=1;

    /* Hardware breakpoints: inspect this thread's debug registers. */
    CONTEXT ctx; memset(&ctx,0,sizeof(ctx));
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;
    if (GetThreadContext(GetCurrentThread(),&ctx)){
        if (ctx.Dr0||ctx.Dr1||ctx.Dr2||ctx.Dr3||ctx.Dr7) r->hw_breakpoints=1;
    }

    /* NtQueryInformationProcess: ProcessDebugPort(7) / DebugObjectHandle(30). */
    typedef LONG (WINAPI *NtQIP)(HANDLE,UINT,PVOID,ULONG,PULONG);
    HMODULE nt=GetModuleHandleA("ntdll.dll");
    if (nt){
        NtQIP f=(NtQIP)GetProcAddress(nt,"NtQueryInformationProcess");
        if (f){
            DWORD_PTR port=0;
            if (f(GetCurrentProcess(),7,&port,sizeof(port),0)==0 && port) r->debug_port_set=1;
            HANDLE dobj=0;
            if (f(GetCurrentProcess(),30,&dobj,sizeof(dobj),0)==0 && dobj) r->debug_port_set=1;
        }
    }
    if (r->hw_breakpoints || r->debug_port_set) r->debugger_present=1;

#elif defined(ENV_LINUX)
    int fd=open("/proc/self/status",O_RDONLY);
    if (fd>=0){char b[4096];ssize_t n=read(fd,b,sizeof(b)-1);close(fd);
        if (n>0){b[n]='\0';char *p=strstr(b,"TracerPid:");
            if (p){r->tracer_pid=atoi(p+10); if (r->tracer_pid) r->debugger_present=1;}}}
    /* LD_PRELOAD is a classic hooking/instrumentation vector. */
    const char *pre=getenv("LD_PRELOAD");
    if (pre && *pre){r->ld_preload_set=1;}
#endif
}

/* Opt-in self-trace probe. CHANGES STATE: on success the caller becomes its
   own tracer, so a real debugger can no longer attach; on failure a debugger
   is already attached. Run once, deliberately. */
static void check_ptrace_self(env_report_t *r){
#if defined(ENV_LINUX)
    long rc = ptrace(PTRACE_TRACEME, 0, 0, 0);
    if (rc < 0) { r->ptrace_self_blocked=1; r->debugger_present=1; }
    else        { ptrace(PTRACE_DETACH, 0, 0, 0); } /* release the slot */
#else
    (void)r;
#endif
}

/* ------------------------------------------------------------------ */
/* 6. Analysis-tool enumeration (process names)                        */
/* ------------------------------------------------------------------ */
static const char *ANALYSIS_NAMES[] = {
    /* disassemblers / decompilers */
    "ida","ida64","ida32","idaq","idaw","ghidra","ghidrarun",
    "binaryninja","binja","cutter","radare2","r2","rizin","hopper",
    /* debuggers */
    "x64dbg","x32dbg","ollydbg","immunity","windbg","cdb","gdb","lldb",
    "edb","dnspy","ilspy","megadumper","scylla","x96dbg",
    /* tracing / monitoring / network */
    "strace","ltrace","procmon","procexp","processhacker","tcpview",
    "wireshark","dumpcap","tshark","fiddler","httpdebugger","charles",
    /* memory / cheat / unpack */
    "cheatengine","cheat engine","pestudio","lordpe","importrec",
    "qemu-system","sandboxie","joeboxcontrol","vmtoolsd","vboxservice",
};
static int name_is_analysis(const char *n, env_report_t *r){
    for (size_t i=0;i<sizeof(ANALYSIS_NAMES)/sizeof(ANALYSIS_NAMES[0]);++i)
        if (ci_contains(n,ANALYSIS_NAMES[i])){
            if (!r->analysis_tool_name[0]){
                strncpy(r->analysis_tool_name,ANALYSIS_NAMES[i],sizeof(r->analysis_tool_name)-1);
                r->analysis_tool_name[sizeof(r->analysis_tool_name)-1]='\0';
            }
            return 1;
        }
    return 0;
}
static void check_analysis_tools(env_report_t *r){
#if defined(ENV_WINDOWS)
    HANDLE snap=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    if (snap!=INVALID_HANDLE_VALUE){
        PROCESSENTRY32 pe; pe.dwSize=sizeof(pe);
        if (Process32First(snap,&pe)){
            do { if (name_is_analysis(pe.szExeFile,r)){r->analysis_tool_found=1;break;} }
            while (Process32Next(snap,&pe));
        }
        CloseHandle(snap);
    }
    /* Also check for debugger/analysis top-level window class names. */
    if (!r->analysis_tool_found){
        const char *cls[]={"OLLYDBG","WinDbgFrameClass","ID","Zeta Debugger",
                           "Rock Debugger","ObsidianGUI","Qt5QWindowIcon"};
        for (size_t i=0;i<sizeof(cls)/sizeof(cls[0]);++i)
            if (FindWindowA(cls[i],NULL)){r->analysis_tool_found=1;
                if (!r->analysis_tool_name[0]){strncpy(r->analysis_tool_name,cls[i],63);}
                break;}
    }
#elif defined(ENV_LINUX)
    DIR *d=opendir("/proc");
    if (d){
        struct dirent *e;
        while ((e=readdir(d))){
            if (e->d_name[0]<'0'||e->d_name[0]>'9') continue;
            char path[320]; snprintf(path,sizeof(path),"/proc/%s/comm",e->d_name);
            int fd=open(path,O_RDONLY);
            if (fd>=0){char c[128];ssize_t n=read(fd,c,sizeof(c)-1);close(fd);
                if (n>0){c[n]='\0'; char *nl=strchr(c,'\n'); if (nl)*nl='\0';
                    if (name_is_analysis(c,r)){r->analysis_tool_found=1;break;}}}
        }
        closedir(d);
    }
#endif
}

/* ------------------------------------------------------------------ */
/* 7. Sandbox resource heuristics                                      */
/* ------------------------------------------------------------------ */
static void check_resources(env_report_t *r){
#if defined(ENV_WINDOWS)
    SYSTEM_INFO si; GetSystemInfo(&si);
    r->cpu_count=si.dwNumberOfProcessors;
    MEMORYSTATUSEX ms; ms.dwLength=sizeof(ms);
    if (GlobalMemoryStatusEx(&ms)) r->ram_mb=ms.ullTotalPhys/(1024ULL*1024ULL);
    ULARGE_INTEGER total; 
    if (GetDiskFreeSpaceExA("C:\\",NULL,&total,NULL))
        r->disk_gb=total.QuadPart/(1024ULL*1024ULL*1024ULL);
    r->uptime_sec=GetTickCount64()/1000ULL;
#elif defined(ENV_LINUX)
    r->cpu_count=(unsigned int)sysconf(_SC_NPROCESSORS_ONLN);
    struct sysinfo s;
    if (sysinfo(&s)==0){
        r->ram_mb=(unsigned long long)s.totalram*s.mem_unit/(1024ULL*1024ULL);
        r->uptime_sec=(unsigned long long)s.uptime;
    }
    struct statvfs vfs;
    if (statvfs("/",&vfs)==0)
        r->disk_gb=((unsigned long long)vfs.f_blocks*vfs.f_frsize)/(1024ULL*1024ULL*1024ULL);
#endif
    /* Thresholds are heuristic — sandboxes are usually small and freshly booted. */
    r->low_cpu_count = (r->cpu_count && r->cpu_count < 2);
    r->low_ram       = (r->ram_mb   && r->ram_mb   < 2048);
    r->small_disk    = (r->disk_gb  && r->disk_gb  < 60);
    r->short_uptime  = (r->uptime_sec && r->uptime_sec < 300);

    /* Host / user names that analysis images often use. */
    char host[256]={0}, user[256]={0};
#if defined(ENV_WINDOWS)
    DWORD hs=sizeof(host); GetComputerNameA(host,&hs);
    DWORD us=sizeof(user); GetUserNameA(user,&us);
#elif defined(ENV_LINUX)
    gethostname(host,sizeof(host)-1);
    const char *u=getenv("USER"); if (u) strncpy(user,u,sizeof(user)-1);
#endif
    static const char *bad[]={"sandbox","malware","virus","sample","cuckoo",
        "maltest","analysis","vmware","virtualbox","test","admin-pc","john-pc"};
    for (size_t i=0;i<sizeof(bad)/sizeof(bad[0]);++i)
        if (ci_contains(host,bad[i])||ci_contains(user,bad[i])){r->suspicious_identity=1;break;}
}

/* ------------------------------------------------------------------ */
/* 8. Keyboard layout — coarse market signal (not geolocation)         */
/* ------------------------------------------------------------------ */
static void check_keyboard_layout(env_report_t *r){
    r->layout_matches_target=-1;
#if defined(ENV_WINDOWS)
    HKL hkl=GetKeyboardLayout(0);
    r->primary_langid=(unsigned int)(LOWORD((DWORD_PTR)hkl));
    LCID lcid=MAKELCID(r->primary_langid,SORT_DEFAULT);
    GetLocaleInfoA(lcid,LOCALE_SISO639LANGNAME,r->layout_name,sizeof(r->layout_name));
#elif defined(ENV_LINUX)
    const char *e=getenv("LC_ALL");
    if (!e||!*e) e=getenv("LC_CTYPE");
    if (!e||!*e) e=getenv("LANG");
    if (e&&*e){strncpy(r->layout_name,e,sizeof(r->layout_name)-1);
               r->layout_name[sizeof(r->layout_name)-1]='\0';}
    /* For the real X11/Wayland layout you'd use libxkbcommon; env is the
       portable, dependency-free approximation. */
#endif
}
static int env_layout_matches(env_report_t *r,const char *expect,unsigned int langid){
    int m=0;
    if (langid && r->primary_langid==langid) m=1;
    if (!m && expect && r->layout_name[0] && ci_contains(r->layout_name,expect)) m=1;
    r->layout_matches_target=m;
    return m;
}

/* ------------------------------------------------------------------ */
/* Orchestrator                                                        */
/* ------------------------------------------------------------------ */
static env_report_t env_inspect(int run_ptrace_self){
    env_report_t r; memset(&r,0,sizeof(r));
    check_cpuid_hypervisor(&r);
    check_timing(&r);
    check_mac(&r);
    check_dmi_and_artifacts(&r);
    check_debugger(&r);
    if (run_ptrace_self) check_ptrace_self(&r);  /* opt-in, state-changing */
    check_analysis_tools(&r);
    check_resources(&r);
    check_keyboard_layout(&r);

    r.vm_score  = 0;
    r.vm_score += r.hypervisor_bit;
    r.vm_score += r.hypervisor_vendor[0]?2:0;
    r.vm_score += r.vm_mac_prefix?2:0;
    r.vm_score += r.vm_dmi_string?3:0;
    r.vm_score += r.vm_artifact_present?3:0;
    r.vm_score += r.timing_suspicious?1:0;
    r.vm_score += r.low_cpu_count?1:0;
    r.vm_score += r.low_ram?1:0;
    r.vm_score += r.small_disk?1:0;
    r.vm_score += r.short_uptime?1:0;
    r.vm_score += r.suspicious_identity?2:0;

    r.analysis_score  = 0;
    r.analysis_score += r.debugger_present?3:0;
    r.analysis_score += r.analysis_tool_found?3:0;
    r.analysis_score += r.hw_breakpoints?2:0;
    r.analysis_score += r.peb_ntglobalflag?1:0;
    r.analysis_score += r.ld_preload_set?1:0;
    r.analysis_score += r.ptrace_self_blocked?2:0;
    return r;
}

/* ------------------------------------------------------------------ */
/* Demo — prints findings, takes no other action                      */
/* ------------------------------------------------------------------ */
#ifdef ENVCHECK_DEMO
int main(void){
    /* pass 0 here to skip the state-changing ptrace probe */
    env_report_t r = env_inspect(1);
    env_layout_matches(&r,"pt",0x0416 /* pt-BR, ignored on Linux */);

    printf("== Environment report ==\n");
    printf("[VM]\n");
    printf("  hypervisor_bit      : %d\n", r.hypervisor_bit);
    printf("  hypervisor_vendor   : %s\n", r.hypervisor_vendor[0]?r.hypervisor_vendor:"(none)");
    printf("  vm_mac_prefix       : %d\n", r.vm_mac_prefix);
    printf("  vm_dmi_string       : %d\n", r.vm_dmi_string);
    printf("  vm_artifact_present : %d\n", r.vm_artifact_present);
    printf("[Debugger]\n");
    printf("  debugger_present    : %d\n", r.debugger_present);
    printf("  tracer_pid          : %d\n", r.tracer_pid);
    printf("  ptrace_self_blocked : %d\n", r.ptrace_self_blocked);
    printf("  peb_being_debugged  : %d\n", r.peb_being_debugged);
    printf("  peb_ntglobalflag    : %d\n", r.peb_ntglobalflag);
    printf("  hw_breakpoints      : %d\n", r.hw_breakpoints);
    printf("  debug_port_set      : %d\n", r.debug_port_set);
    printf("  ld_preload_set      : %d\n", r.ld_preload_set);
    printf("[Analysis tools]\n");
    printf("  analysis_tool_found : %d\n", r.analysis_tool_found);
    printf("  analysis_tool_name  : %s\n", r.analysis_tool_name[0]?r.analysis_tool_name:"(none)");
    printf("[Resources]\n");
    printf("  cpu_count           : %u (low=%d)\n", r.cpu_count, r.low_cpu_count);
    printf("  ram_mb              : %llu (low=%d)\n", r.ram_mb, r.low_ram);
    printf("  disk_gb             : %llu (small=%d)\n", r.disk_gb, r.small_disk);
    printf("  uptime_sec          : %llu (short=%d)\n", r.uptime_sec, r.short_uptime);
    printf("  suspicious_identity : %d\n", r.suspicious_identity);
    printf("[Timing]\n");
    printf("  cpuid_cycles (min)  : %llu (suspicious=%d)\n",
           (unsigned long long)r.cpuid_cycles, r.timing_suspicious);
    printf("[Keyboard/market]\n");
    printf("  primary_langid      : 0x%04x\n", r.primary_langid);
    printf("  layout_name         : %s\n", r.layout_name[0]?r.layout_name:"(unknown)");
    printf("  layout_matches      : %d\n", r.layout_matches_target);
    printf("-----------------------\n");
    printf("vm_score            : %d\n", r.vm_score);
    printf("analysis_score      : %d\n", r.analysis_score);
    return 0;
}
#endif
