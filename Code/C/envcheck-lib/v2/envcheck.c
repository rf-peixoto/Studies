/* envcheck.c  —  environment inspection library (implementation)
 *
 * See envcheck.h for the API, the design contract, and the reality check.
 * Every function here inspects and records; none alters program behaviour.
 */

#ifndef _GNU_SOURCE
#  define _GNU_SOURCE   /* must precede all includes: REG_RIP/REG_EIP in <ucontext.h> */
#endif

#include "envcheck.h"

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
#  include <ucontext.h>
#  include <fcntl.h>
#  include <time.h>
#  include <setjmp.h>
#  include <signal.h>
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

#if defined(__i386__)||defined(__x86_64__)||defined(_M_IX86)||defined(_M_X64)
#  define ENV_X86 1
#endif

/* Where the VMware backdoor probe is supported (needs inline asm). */
#if defined(ENV_LINUX) && defined(ENV_X86) && defined(__GNUC__)
#  define ENV_IO_BACKDOOR_LINUX 1
#endif
#if defined(ENV_WINDOWS) && defined(_MSC_VER) && defined(_M_IX86)
#  define ENV_IO_BACKDOOR_WIN 1
#endif

/* ------------------------------------------------------------------ */
/* Low-level helpers                                                   */
/* ------------------------------------------------------------------ */
#if defined(ENV_X86)
static void env_cpuid(uint32_t leaf,uint32_t sub,uint32_t o[4]){
#  if defined(ENV_WINDOWS)
    int r[4];__cpuidex(r,(int)leaf,(int)sub);
    o[0]=(uint32_t)r[0];o[1]=(uint32_t)r[1];o[2]=(uint32_t)r[2];o[3]=(uint32_t)r[3];
#  else
    __cpuid_count(leaf,sub,o[0],o[1],o[2],o[3]);
#  endif
}
static uint64_t env_rdtsc(void){
#  if defined(ENV_WINDOWS)
    return __rdtsc();
#  else
    uint32_t lo,hi;__asm__ __volatile__("rdtsc":"=a"(lo),"=d"(hi));
    return ((uint64_t)hi<<32)|lo;
#  endif
}
#endif

static int ci_contains(const char *hay,const char *needle){
    char a[512],b[128];size_t i;
    if (!hay) return 0;
    for (i=0;hay[i]&&i<sizeof(a)-1;++i) a[i]=(char)((hay[i]>='A'&&hay[i]<='Z')?hay[i]+32:hay[i]);
    a[i]='\0';
    for (i=0;needle[i]&&i<sizeof(b)-1;++i) b[i]=(char)((needle[i]>='A'&&needle[i]<='Z')?needle[i]+32:needle[i]);
    b[i]='\0';
    return strstr(a,b)!=NULL;
}
/* Bounded copy with guaranteed NUL. Manual (not snprintf) so that deliberate
   truncation of unbounded sources doesn't trip -Wformat-truncation. */
static void set_name(char *dst,size_t n,const char *src){
    if (!n) return;
    size_t i=0;
    if (src) for (;i+1<n && src[i];++i) dst[i]=src[i];
    dst[i]='\0';
}

/* Case-sensitive scan of a possibly-NUL-containing binary buffer for any of a
   set of literal keywords. Firmware/DMI strings are typically fixed-case
   (e.g. "VBOX", "VMWARE", "QEMU"), so a plain byte scan is appropriate. On a
   hit, copies the matched keyword into hit[0..hitsz) and returns 1. */
static int buf_has_keyword(const char *buf,size_t len,
                           const char *const *kw,size_t kwn,
                           char *hit,size_t hitsz){
    for (size_t k=0;k<kwn;++k){
        size_t m=strlen(kw[k]);
        if (m==0||m>len) continue;
        for (size_t i=0;i+m<=len;++i){
            if (buf[i]==kw[k][0] && memcmp(buf+i,kw[k],m)==0){
                if (hit&&hitsz) set_name(hit,hitsz,kw[k]);
                return 1;
            }
        }
    }
    return 0;
}

/* ================================================================== */
/* VM / hypervisor                                                     */
/* ================================================================== */
static void check_cpuid_hypervisor(env_report_t *r){
#if defined(ENV_X86)
    uint32_t g[4];env_cpuid(1,0,g);r->hypervisor_bit=(g[2]>>31)&1;
    if (r->hypervisor_bit){env_cpuid(0x40000000,0,g);
        memcpy(r->hypervisor_vendor+0,&g[1],4);
        memcpy(r->hypervisor_vendor+4,&g[2],4);
        memcpy(r->hypervisor_vendor+8,&g[3],4);
        r->hypervisor_vendor[12]='\0';}
    /* CPU brand string (leaves 0x80000002..4): QEMU/VirtualBox sometimes stamp it. */
    env_cpuid(0x80000000,0,g);
    if (g[0]>=0x80000004){
        char brand[49];uint32_t b[12];
        env_cpuid(0x80000002,0,b+0);env_cpuid(0x80000003,0,b+4);env_cpuid(0x80000004,0,b+8);
        memcpy(brand,b,48);brand[48]='\0';
        if (ci_contains(brand,"qemu")||ci_contains(brand,"virtual")||ci_contains(brand,"kvm"))
            r->vm_cpu_brand=1;
    }
#endif
}

static void check_timing(env_report_t *r){
#if defined(ENV_X86)
    uint32_t g[4];uint64_t best=(uint64_t)-1;
    for (int i=0;i<16;++i){uint64_t t0=env_rdtsc();env_cpuid(0,0,g);uint64_t t1=env_rdtsc();
        if (t1-t0<best) best=t1-t0;}
    r->cpuid_cycles=best;r->timing_suspicious=(best>1000);
#endif
}

static int mac_is_virtual(const unsigned char m[6]){
    static const unsigned char o[][3]={
        {0x00,0x05,0x69},{0x00,0x0C,0x29},{0x00,0x1C,0x14},{0x00,0x50,0x56},
        {0x08,0x00,0x27},{0x00,0x15,0x5D},{0x00,0x16,0x3E},{0x00,0x1C,0x42},{0x52,0x54,0x00}};
    for (size_t i=0;i<sizeof(o)/sizeof(o[0]);++i)
        if (m[0]==o[i][0]&&m[1]==o[i][1]&&m[2]==o[i][2]) return 1;
    return 0;
}
static void check_mac(env_report_t *r){
#if defined(ENV_WINDOWS)
    IP_ADAPTER_INFO info[32];ULONG len=sizeof(info);
    if (GetAdaptersInfo(info,&len)==ERROR_SUCCESS)
        for (IP_ADAPTER_INFO *a=info;a;a=a->Next)
            if (a->AddressLength==6&&mac_is_virtual(a->Address)){r->vm_mac_prefix=1;break;}
#elif defined(ENV_LINUX)
    struct if_nameindex *ifs=if_nameindex();int fd=socket(AF_INET,SOCK_DGRAM,0);
    if (ifs&&fd>=0)
        for (struct if_nameindex *p=ifs;p->if_name;++p){
            struct ifreq q;memset(&q,0,sizeof(q));strncpy(q.ifr_name,p->if_name,IFNAMSIZ-1);
            if (ioctl(fd,SIOCGIFHWADDR,&q)==0&&mac_is_virtual((unsigned char*)q.ifr_hwaddr.sa_data)){r->vm_mac_prefix=1;break;}}
    if (fd>=0) close(fd);
    if (ifs) if_freenameindex(ifs);
#endif
}

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
            if (n>0){b[n]='\0';if (str_has_vm_keyword(b)) r->vm_dmi_string=1;}}}
    const char *art[]={"/dev/vboxguest","/dev/vboxuser","/dev/vmci",
        "/sys/bus/pci/drivers/vmw_pvscsi","/proc/scsi/scsi","/sys/hypervisor/type"};
    for (size_t i=0;i<sizeof(art)/sizeof(art[0]);++i){struct stat st;
        if (stat(art[i],&st)==0){r->vm_artifact_present=1;break;}}
    /* Loaded kernel modules commonly present only in guests. */
    int mf=open("/proc/modules",O_RDONLY);
    if (mf>=0){char b[16384];ssize_t n=read(mf,b,sizeof(b)-1);close(mf);
        if (n>0){b[n]='\0';
            if (strstr(b,"vboxguest")||strstr(b,"vmw_")||strstr(b,"vmhgfs")||strstr(b,"virtio"))
                r->vm_artifact_present=1;}}
    /* /proc/cpuinfo hypervisor flag / virtual model. */
    int cf=open("/proc/cpuinfo",O_RDONLY);
    if (cf>=0){char b[8192];ssize_t n=read(cf,b,sizeof(b)-1);close(cf);
        if (n>0){b[n]='\0';
            if (strstr(b," hypervisor")||str_has_vm_keyword(b)) r->cpuinfo_hypervisor=1;}}
    /* WSL: the kernel advertises itself in /proc/version. */
    int vf=open("/proc/version",O_RDONLY);
    if (vf>=0){char b[512];ssize_t n=read(vf,b,sizeof(b)-1);close(vf);
        if (n>0){b[n]='\0';
            if (ci_contains(b,"microsoft")||ci_contains(b,"wsl")) r->wsl_present=1;}}
#elif defined(ENV_WINDOWS)
    HKEY h;char b[256];DWORD sz;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,"HARDWARE\\DESCRIPTION\\System\\BIOS",0,KEY_READ,&h)==ERROR_SUCCESS){
        sz=sizeof(b);if (RegQueryValueExA(h,"SystemManufacturer",0,0,(LPBYTE)b,&sz)==ERROR_SUCCESS)
            if (str_has_vm_keyword(b)) r->vm_dmi_string=1;
        sz=sizeof(b);if (RegQueryValueExA(h,"SystemProductName",0,0,(LPBYTE)b,&sz)==ERROR_SUCCESS)
            if (str_has_vm_keyword(b)) r->vm_dmi_string=1;
        RegCloseKey(h);}
    const char *svc[]={"SYSTEM\\CurrentControlSet\\Services\\VBoxGuest",
        "SYSTEM\\CurrentControlSet\\Services\\VBoxService",
        "SYSTEM\\CurrentControlSet\\Services\\vmtools",
        "SYSTEM\\CurrentControlSet\\Services\\vmhgfs",
        "SYSTEM\\CurrentControlSet\\Services\\vmci"};
    for (size_t i=0;i<sizeof(svc)/sizeof(svc[0]);++i){
        HKEY k;if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,svc[i],0,KEY_READ,&k)==ERROR_SUCCESS){
            RegCloseKey(k);r->vm_artifact_present=1;break;}}
    const char *f[]={
        "C:\\Windows\\System32\\drivers\\vmmouse.sys","C:\\Windows\\System32\\drivers\\vmhgfs.sys",
        "C:\\Windows\\System32\\drivers\\VBoxMouse.sys","C:\\Windows\\System32\\drivers\\VBoxGuest.sys",
        "C:\\Windows\\System32\\vboxdisp.dll","C:\\Windows\\System32\\drivers\\vmci.sys"};
    for (size_t i=0;i<sizeof(f)/sizeof(f[0]);++i)
        if (GetFileAttributesA(f[i])!=INVALID_FILE_ATTRIBUTES){r->vm_artifact_present=1;break;}
    /* Wine exports a telltale function in ntdll, and keeps a registry hive. */
    HMODULE nt=GetModuleHandleA("ntdll.dll");
    if (nt && GetProcAddress(nt,"wine_get_version")) r->wine_present=1;
    if (!r->wine_present){HKEY wk;
        if (RegOpenKeyExA(HKEY_CURRENT_USER,"Software\\Wine",0,KEY_READ,&wk)==ERROR_SUCCESS){
            RegCloseKey(wk);r->wine_present=1;}}
#endif
}

/* VMware I/O backdoor: a magic read from port 0x5658 returns the magic in EBX
   only when a VMware hypervisor intercepts it; on real hardware the privileged
   `in` faults. We raise the fault and catch it — behaviour unchanged, boolean
   recorded. Supported only where inline asm is available (see macros). */
#if defined(ENV_IO_BACKDOOR_LINUX)
/* The privileged `in` faults in user mode. We catch SIGSEGV/SIGILL with an
   SA_SIGINFO handler that *advances the instruction pointer past the faulting
   byte and returns*, rather than longjmp-ing out. Advancing-and-returning is
   robust even after PTRACE_TRACEME has run and even under a live tracer, where
   a longjmp-based catcher is unreliable and can let the fault kill the process.
   A sentinel byte marks the faulting instruction so the handler knows how far
   to skip; a global flag records that the fault happened. */
static volatile sig_atomic_t g_bd_faulted;
static void g_bd_handler(int sig, siginfo_t *si, void *uctx){
    (void)sig; (void)si;
    ucontext_t *uc=(ucontext_t*)uctx;
#  if defined(__x86_64__)
    uc->uc_mcontext.gregs[REG_RIP] += 1;   /* `in %dx,%eax` (0xED) is one byte */
#  elif defined(__i386__)
    uc->uc_mcontext.gregs[REG_EIP] += 1;
#  endif
    g_bd_faulted = 1;
}
static void check_io_backdoor(env_report_t *r){
    struct sigaction sa, old_segv, old_ill;
    memset(&sa,0,sizeof(sa));
    sa.sa_sigaction=g_bd_handler; sa.sa_flags=SA_SIGINFO; sigemptyset(&sa.sa_mask);
    if (sigaction(SIGSEGV,&sa,&old_segv)!=0) return;
    sigaction(SIGILL,&sa,&old_ill);
    g_bd_faulted=0;
    uint32_t a=0x564D5868u /*VMXh*/, b=0, c=10 /*getversion*/, d=0x5658 /*VX*/;
    __asm__ __volatile__("in %%dx, %%eax"
        : "=a"(a), "=b"(b), "=c"(c), "=d"(d)
        : "a"(a), "b"(b), "c"(c), "d"(d) : "memory");
    /* Under VMware the `in` is intercepted (no fault) and EBX echoes the magic.
       On real hardware / non-VMware hypervisors it faults; the handler skipped
       it and set g_bd_faulted, so we simply report "no backdoor". */
    if (!g_bd_faulted && b==0x564D5868u) r->vm_vmware_backdoor=1;
    sigaction(SIGSEGV,&old_segv,NULL); sigaction(SIGILL,&old_ill,NULL);
}
#elif defined(ENV_IO_BACKDOOR_WIN)
static void check_io_backdoor(env_report_t *r){
    int detected=0;
    __try {
        __asm {
            mov eax, 0x564D5868
            mov ebx, 0
            mov ecx, 10
            mov edx, 0x5658
            in  eax, dx
            cmp ebx, 0x564D5868
            jne not_vm
            mov detected, 1
          not_vm:
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) { detected=0; }
    r->vm_vmware_backdoor=detected;
}
#else
static void check_io_backdoor(env_report_t *r){ (void)r; } /* unsupported toolchain */
#endif

/* ================================================================== */
/* Debugger / tracer                                                   */
/* ================================================================== */
static void check_debugger(env_report_t *r){
#if defined(ENV_WINDOWS)
    if (IsDebuggerPresent()) r->debugger_present=1;
    BOOL rem=FALSE;
    if (CheckRemoteDebuggerPresent(GetCurrentProcess(),&rem)&&rem) r->debugger_present=1;
#  if defined(_M_X64)||defined(__x86_64__)
    unsigned char *peb=(unsigned char*)__readgsqword(0x60);
    if (peb){r->peb_being_debugged=peb[0x02]?1:0;
        unsigned int ngf=*(unsigned int*)(peb+0xBC);r->peb_ntglobalflag=(ngf&0x70)?1:0;}
#  elif defined(_M_IX86)||defined(__i386__)
    unsigned char *peb=(unsigned char*)__readfsdword(0x30);
    if (peb){r->peb_being_debugged=peb[0x02]?1:0;
        unsigned int ngf=*(unsigned int*)(peb+0x68);r->peb_ntglobalflag=(ngf&0x70)?1:0;}
#  endif
    if (r->peb_being_debugged||r->peb_ntglobalflag) r->debugger_present=1;
    CONTEXT ctx;memset(&ctx,0,sizeof(ctx));ctx.ContextFlags=CONTEXT_DEBUG_REGISTERS;
    if (GetThreadContext(GetCurrentThread(),&ctx))
        if (ctx.Dr0||ctx.Dr1||ctx.Dr2||ctx.Dr3||ctx.Dr7) r->hw_breakpoints=1;
    HMODULE nt=GetModuleHandleA("ntdll.dll");
    if (nt){
        typedef LONG (WINAPI *NtQIP)(HANDLE,UINT,PVOID,ULONG,PULONG);
        NtQIP qip=(NtQIP)GetProcAddress(nt,"NtQueryInformationProcess");
        if (qip){DWORD_PTR port=0;
            if (qip(GetCurrentProcess(),7,&port,sizeof(port),0)==0&&port) r->debug_port_set=1;
            HANDLE dobj=0;
            if (qip(GetCurrentProcess(),30,&dobj,sizeof(dobj),0)==0&&dobj) r->debug_port_set=1;}
        /* Kernel debugger (bare-metal RE box with KD/WinDbg over net or USB). */
        typedef LONG (WINAPI *NtQSI)(UINT,PVOID,ULONG,PULONG);
        NtQSI qsi=(NtQSI)GetProcAddress(nt,"NtQuerySystemInformation");
        if (qsi){
            struct { unsigned char Enabled, NotPresent; } kd={0,0};
            if (qsi(0x23 /*SystemKernelDebuggerInformation*/,&kd,sizeof(kd),0)==0)
                if (kd.Enabled && !kd.NotPresent) r->kernel_debugger=1;
        }
    }
    if (r->hw_breakpoints||r->debug_port_set||r->kernel_debugger) r->debugger_present=1;
#elif defined(ENV_LINUX)
    int fd=open("/proc/self/status",O_RDONLY);
    if (fd>=0){char b[4096];ssize_t n=read(fd,b,sizeof(b)-1);close(fd);
        if (n>0){b[n]='\0';char *p=strstr(b,"TracerPid:");
            if (p){r->tracer_pid=atoi(p+10);if (r->tracer_pid) r->debugger_present=1;}}}
    const char *pre=getenv("LD_PRELOAD");
    if (pre&&*pre) r->ld_preload_set=1;
#endif
}

/* Opt-in, state-changing self-trace.
   PTRACE_TRACEME is inherently a once-per-process operation (its intended use
   is right before exec). Calling it more than once leaves the process in a
   half-traced state that later self-stops, so we run it at most once per
   process and cache the result for any later env_inspect() calls. If a debugger
   is already attached, the call fails -> that itself is the signal. */
static void check_ptrace_self(env_report_t *r){
#if defined(ENV_LINUX)
    static int cached = -1;   /* -1 = not yet run, 0/1 = prior result */
    if (cached < 0){
        long rc = ptrace(PTRACE_TRACEME, 0, 0, 0);
        if (rc < 0) cached = 1;                 /* already traced */
        else { ptrace(PTRACE_DETACH, 0, 0, 0); cached = 0; }
    }
    if (cached){ r->ptrace_self_blocked=1; r->debugger_present=1; }
#else
    (void)r;
#endif
}

/* SEH-based debugger traps (MSVC). Raise and catch internally; the branch
   taken reveals whether a debugger intercepted the exception first. */
#if defined(ENV_WINDOWS) && defined(_MSC_VER)
static int seh_int3_trap(void){
    __try { __debugbreak(); return 1; }     /* reached only if a debugger swallowed INT3 */
    __except(EXCEPTION_EXECUTE_HANDLER){ return 0; }
}
static int seh_closehandle_trap(void){
    __try { CloseHandle((HANDLE)(ULONG_PTR)0x11111111); return 0; }
    __except(EXCEPTION_EXECUTE_HANDLER){ return 1; } /* invalid-handle raises only under a debugger */
}
static void check_seh_traps(env_report_t *r){
    if (seh_int3_trap())       { r->seh_int3_debugger=1;    r->debugger_present=1; }
    if (seh_closehandle_trap()){ r->closehandle_debugger=1; r->debugger_present=1; }
}
#else
static void check_seh_traps(env_report_t *r){ (void)r; }
#endif

/* ================================================================== */
/* Analysis tools (running), hooks, instrumentation, parent            */
/* ================================================================== */
static const char *ANALYSIS_NAMES[]={
    "ida","ida64","ida32","idaq","idaw","ghidra","ghidrarun","binaryninja","binja",
    "cutter","radare2","r2","rizin","hopper","x64dbg","x32dbg","x96dbg","ollydbg",
    "immunity","windbg","cdb","gdb","lldb","edb","dnspy","ilspy","megadumper","scylla",
    "valgrind","strace","ltrace","procmon","procexp","processhacker","tcpview",
    "wireshark","dumpcap","tshark","fiddler","httpdebugger","charles","cheatengine",
    "cheat engine","pestudio","lordpe","importrec","qemu-system","sandboxie",
    "joeboxcontrol","vmtoolsd","vboxservice"};
static const char *INSTRUMENTATION_NAMES[]={
    "frida","frida-server","frida-helper","gum-js","drrun","drconfig","drinject",
    "pin.exe","pinbin","pin-","dynamorio","qiling","qdbi","e9patch","ptrace-tap"};

static int match_list(const char *n,const char *const *list,size_t cnt,char *out,size_t outsz){
    for (size_t i=0;i<cnt;++i)
        if (ci_contains(n,list[i])){ if (out&&!out[0]) set_name(out,outsz,list[i]); return 1; }
    return 0;
}
static int name_is_analysis(const char *n,char *out,size_t outsz){
    return match_list(n,ANALYSIS_NAMES,sizeof(ANALYSIS_NAMES)/sizeof(ANALYSIS_NAMES[0]),out,outsz);
}
static int name_is_instrumentation(const char *n,char *out,size_t outsz){
    return match_list(n,INSTRUMENTATION_NAMES,sizeof(INSTRUMENTATION_NAMES)/sizeof(INSTRUMENTATION_NAMES[0]),out,outsz);
}

static void check_analysis_tools(env_report_t *r){
#if defined(ENV_WINDOWS)
    HANDLE snap=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);
    DWORD my=GetCurrentProcessId(),parent=0;
    if (snap!=INVALID_HANDLE_VALUE){
        PROCESSENTRY32 pe;pe.dwSize=sizeof(pe);
        if (Process32First(snap,&pe)){
            do{
                if (pe.th32ProcessID==my) parent=pe.th32ParentProcessID;
                if (!r->analysis_tool_found&&name_is_analysis(pe.szExeFile,r->analysis_tool_name,sizeof(r->analysis_tool_name)))
                    r->analysis_tool_found=1;
                if (!r->instrumentation_found&&name_is_instrumentation(pe.szExeFile,r->instrumentation_name,sizeof(r->instrumentation_name)))
                    r->instrumentation_found=1;
            }while (Process32Next(snap,&pe));
        }
        if (parent){
            PROCESSENTRY32 pe2;pe2.dwSize=sizeof(pe2);
            if (Process32First(snap,&pe2)) do{
                if (pe2.th32ProcessID==parent){
                    set_name(r->parent_name,sizeof(r->parent_name),pe2.szExeFile);
                    char tmp[64]={0};
                    if (name_is_analysis(pe2.szExeFile,tmp,sizeof(tmp))) r->parent_process_suspicious=1;
                    break;}
            }while (Process32Next(snap,&pe2));
        }
        CloseHandle(snap);
    }
    if (!r->analysis_tool_found){
        const char *cls[]={"OLLYDBG","WinDbgFrameClass","ID","Zeta Debugger","Rock Debugger","ObsidianGUI"};
        for (size_t i=0;i<sizeof(cls)/sizeof(cls[0]);++i)
            if (FindWindowA(cls[i],NULL)){r->analysis_tool_found=1;
                if (!r->analysis_tool_name[0]) set_name(r->analysis_tool_name,sizeof(r->analysis_tool_name),cls[i]);break;}
    }
    /* In-process hook / sandbox / monitoring / instrumentation DLLs. */
    const char *dlls[]={"sbiedll.dll","api_log.dll","dir_watch.dll","pstorec.dll",
        "vmcheck.dll","wpespy.dll","cmdvrt32.dll","cmdvrt64.dll","snxhk.dll","cuckoomon.dll"};
    for (size_t i=0;i<sizeof(dlls)/sizeof(dlls[0]);++i)
        if (GetModuleHandleA(dlls[i])){r->analysis_dll_loaded=1;
            set_name(r->analysis_dll_name,sizeof(r->analysis_dll_name),dlls[i]);break;}
    if (!r->instrumentation_found){
        const char *inj[]={"frida-agent.dll","frida-gadget.dll","dynamorio.dll","pinvm.dll"};
        for (size_t i=0;i<sizeof(inj)/sizeof(inj[0]);++i)
            if (GetModuleHandleA(inj[i])){r->instrumentation_found=1;
                set_name(r->instrumentation_name,sizeof(r->instrumentation_name),inj[i]);break;}
    }
    /* Installed RE tooling on disk — a dedicated reversing box, VM or not. */
    const char *inst[]={
        "C:\\Program Files\\IDA Pro","C:\\Program Files\\IDA Freeware",
        "C:\\Program Files (x86)\\IDA","C:\\ghidra","C:\\Program Files\\Ghidra",
        "C:\\Program Files\\x64dbg","C:\\Program Files\\Binary Ninja",
        "C:\\Program Files\\Cheat Engine 7.5","C:\\radare2"};
    for (size_t i=0;i<sizeof(inst)/sizeof(inst[0]);++i)
        if (GetFileAttributesA(inst[i])!=INVALID_FILE_ATTRIBUTES){r->analysis_tool_installed=1;
            set_name(r->analysis_tool_inst_name,sizeof(r->analysis_tool_inst_name),inst[i]);break;}
#elif defined(ENV_LINUX)
    /* Scan running processes for analysis tools and instrumentation. */
    DIR *d=opendir("/proc");
    if (d){struct dirent *e;
        while ((e=readdir(d))){
            if (e->d_name[0]<'0'||e->d_name[0]>'9') continue;
            char path[320];snprintf(path,sizeof(path),"/proc/%s/comm",e->d_name);
            int fd=open(path,O_RDONLY);
            if (fd>=0){char c[64];ssize_t n=read(fd,c,sizeof(c)-1);close(fd);
                if (n>0){c[n]='\0';char *nl=strchr(c,'\n');if (nl)*nl='\0';
                    if (!r->analysis_tool_found&&name_is_analysis(c,r->analysis_tool_name,sizeof(r->analysis_tool_name)))
                        r->analysis_tool_found=1;
                    if (!r->instrumentation_found&&name_is_instrumentation(c,r->instrumentation_name,sizeof(r->instrumentation_name)))
                        r->instrumentation_found=1;}}
        }
        closedir(d);
    }
    /* Frida/Pin/DynamoRIO injected into *this* process show up in our own maps. */
    int mf=open("/proc/self/maps",O_RDONLY);
    if (mf>=0){char b[65536];ssize_t n=read(mf,b,sizeof(b)-1);close(mf);
        if (n>0){b[n]='\0';
            if (strstr(b,"frida")||strstr(b,"libgum")||strstr(b,"dynamorio")||strstr(b,"/pin/")){
                r->instrumentation_found=1;
                if (!r->instrumentation_name[0]) set_name(r->instrumentation_name,sizeof(r->instrumentation_name),"injected-lib");}}}
    /* Parent process. */
    int sf=open("/proc/self/stat",O_RDONLY);
    if (sf>=0){char b[512];ssize_t n=read(sf,b,sizeof(b)-1);close(sf);
        if (n>0){b[n]='\0';char *rp=strrchr(b,')');
            if (rp){int ppid=0;sscanf(rp+1," %*c %d",&ppid);
                if (ppid>0){char pp[64];snprintf(pp,sizeof(pp),"/proc/%d/comm",ppid);
                    int pf=open(pp,O_RDONLY);
                    if (pf>=0){char c[64];ssize_t m=read(pf,c,sizeof(c)-1);close(pf);
                        if (m>0){c[m]='\0';char *nl=strchr(c,'\n');if (nl)*nl='\0';
                            set_name(r->parent_name,sizeof(r->parent_name),c);
                            char tmp[64]={0};
                            if (name_is_analysis(c,tmp,sizeof(tmp))) r->parent_process_suspicious=1;}}}}}}
    /* Installed RE tooling reachable via PATH — dedicated reversing box. */
    const char *tools[]={"gdb","lldb","radare2","r2","rizin","objdump","readelf",
        "nm","strace","ltrace","valgrind","frida","ghidraRun","ida64","edb"};
    const char *penv=getenv("PATH");
    if (penv){
        for (size_t t=0;t<sizeof(tools)/sizeof(tools[0])&&!r->analysis_tool_installed;++t){
            char path[256];size_t pi=0;const char *p=penv;
            while (*p){
                pi=0;
                while (*p&&*p!=':'&&pi<sizeof(path)-2) path[pi++]=*p++;
                if (*p==':') ++p;
                if (pi==0) continue;
                if (path[pi-1]!='/') path[pi++]='/';
                path[pi]='\0';
                char full[320];snprintf(full,sizeof(full),"%s%s",path,tools[t]);
                if (access(full,X_OK)==0){r->analysis_tool_installed=1;
                    set_name(r->analysis_tool_inst_name,sizeof(r->analysis_tool_inst_name),tools[t]);break;}
            }
        }
    }
#endif
}

/* ================================================================== */
/* Containers (Linux)                                                  */
/* ================================================================== */
static void check_container(env_report_t *r){
#if defined(ENV_LINUX)
    struct stat st;
    if (stat("/.dockerenv",&st)==0){r->container_detected=1;set_name(r->container_type,sizeof(r->container_type),"docker");return;}
    int fd=open("/proc/1/cgroup",O_RDONLY);
    if (fd>=0){char b[4096];ssize_t n=read(fd,b,sizeof(b)-1);close(fd);
        if (n>0){b[n]='\0';
            if (strstr(b,"docker"))    {r->container_detected=1;set_name(r->container_type,sizeof(r->container_type),"docker");}
            else if (strstr(b,"lxc"))  {r->container_detected=1;set_name(r->container_type,sizeof(r->container_type),"lxc");}
            else if (strstr(b,"kubepods")||strstr(b,"containerd"))
                                        {r->container_detected=1;set_name(r->container_type,sizeof(r->container_type),"k8s");}}}
#else
    (void)r;
#endif
}

/* ================================================================== */
/* Sandbox resource / behavioral heuristics                           */
/* ================================================================== */
static void check_resources(env_report_t *r){
#if defined(ENV_WINDOWS)
    SYSTEM_INFO si;GetSystemInfo(&si);r->cpu_count=si.dwNumberOfProcessors;
    MEMORYSTATUSEX ms;ms.dwLength=sizeof(ms);
    if (GlobalMemoryStatusEx(&ms)) r->ram_mb=ms.ullTotalPhys/(1024ULL*1024ULL);
    ULARGE_INTEGER total;
    if (GetDiskFreeSpaceExA("C:\\",NULL,&total,NULL)) r->disk_gb=total.QuadPart/(1024ULL*1024ULL*1024ULL);
    r->uptime_sec=GetTickCount64()/1000ULL;
    /* Default sandbox screen is often 1024x768 or smaller. */
    int cx=GetSystemMetrics(SM_CXSCREEN),cy=GetSystemMetrics(SM_CYSCREEN);
    if (cx&&cy&&cx<=1024&&cy<=768) r->small_screen=1;
    /* No recent human input -> likely an unattended sandbox. */
    LASTINPUTINFO li;li.cbSize=sizeof(li);
    if (GetLastInputInfo(&li)){
        unsigned long long idle=(GetTickCount()-li.dwTime)/1000ULL;
        r->input_idle_sec=idle; if (idle>600) r->no_user_input=1;
    }
#elif defined(ENV_LINUX)
    r->cpu_count=(unsigned int)sysconf(_SC_NPROCESSORS_ONLN);
    struct sysinfo s;
    if (sysinfo(&s)==0){r->ram_mb=(unsigned long long)s.totalram*s.mem_unit/(1024ULL*1024ULL);
        r->uptime_sec=(unsigned long long)s.uptime;}
    struct statvfs vfs;
    if (statvfs("/",&vfs)==0) r->disk_gb=((unsigned long long)vfs.f_blocks*vfs.f_frsize)/(1024ULL*1024ULL*1024ULL);
    r->input_idle_sec=0; /* no portable console-idle metric without a display server */
#endif
    r->low_cpu_count=(r->cpu_count&&r->cpu_count<2);
    r->low_ram=(r->ram_mb&&r->ram_mb<2048);
    r->small_disk=(r->disk_gb&&r->disk_gb<60);
    r->short_uptime=(r->uptime_sec&&r->uptime_sec<300);
    char host[256]={0},user[256]={0};
#if defined(ENV_WINDOWS)
    DWORD hs=sizeof(host);GetComputerNameA(host,&hs);
    DWORD us=sizeof(user);GetUserNameA(user,&us);
#elif defined(ENV_LINUX)
    gethostname(host,sizeof(host)-1);
    const char *u=getenv("USER");if (u) strncpy(user,u,sizeof(user)-1);
#endif
    static const char *bad[]={"sandbox","malware","virus","sample","cuckoo","maltest",
        "analysis","vmware","virtualbox","test","admin-pc","john-pc"};
    for (size_t i=0;i<sizeof(bad)/sizeof(bad[0]);++i)
        if (ci_contains(host,bad[i])||ci_contains(user,bad[i])){r->suspicious_identity=1;break;}
}

/* Sleep-skew: some sandboxes fast-forward sleeps to hurry a sample along.
   We ask for ~200ms and measure the wall clock actually elapsed. A large
   deficit means time was accelerated. Adds latency, so it is opt-in. */
static void check_sleep_skew(env_report_t *r){
    const long want_ms=200;
#if defined(ENV_WINDOWS)
    LARGE_INTEGER f,a,b;QueryPerformanceFrequency(&f);QueryPerformanceCounter(&a);
    Sleep((DWORD)want_ms);
    QueryPerformanceCounter(&b);
    long got=(long)((double)(b.QuadPart-a.QuadPart)*1000.0/(double)f.QuadPart);
#elif defined(ENV_LINUX)
    struct timespec a,b,req;req.tv_sec=0;req.tv_nsec=want_ms*1000000L;
    clock_gettime(CLOCK_MONOTONIC,&a);
    nanosleep(&req,NULL);
    clock_gettime(CLOCK_MONOTONIC,&b);
    long got=(long)((b.tv_sec-a.tv_sec)*1000L+(b.tv_nsec-a.tv_nsec)/1000000L);
#else
    long got=want_ms;
#endif
    r->sleep_skew_ms=want_ms-got;             /* positive => slept less than asked */
    r->sleep_skew_suspicious=(r->sleep_skew_ms>want_ms/2); /* lost more than half */
}

/* ================================================================== */
/* Keyboard layout — coarse market signal (not geolocation)           */
/* ================================================================== */
static void check_keyboard_layout(env_report_t *r){
    r->layout_matches_target=-1;
#if defined(ENV_WINDOWS)
    HKL hkl=GetKeyboardLayout(0);r->primary_langid=(unsigned int)(LOWORD((DWORD_PTR)hkl));
    LCID lcid=MAKELCID(r->primary_langid,SORT_DEFAULT);
    GetLocaleInfoA(lcid,LOCALE_SISO639LANGNAME,r->layout_name,sizeof(r->layout_name));
#elif defined(ENV_LINUX)
    const char *e=getenv("LC_ALL");if (!e||!*e) e=getenv("LC_CTYPE");if (!e||!*e) e=getenv("LANG");
    if (e&&*e){strncpy(r->layout_name,e,sizeof(r->layout_name)-1);r->layout_name[sizeof(r->layout_name)-1]='\0';}
#endif
}

/* ================================================================== */
/* High-value additions: firmware, PCI, disk/GPU, sensors, sandbox env */
/* ================================================================== */

/* Keyword sets reused below. Firmware/DMI stamps are typically upper-case. */
static const char *FW_KW[] = {
    "VBOX","VirtualBox","innotek","VMWARE","VMware","QEMU","BOCHS","BXPC",
    "Xen","XenVMM","VRTUAL" /* MS Hyper-V ACPI OEMID "VRTUAL" */, "parallels"
};

/* Firmware tables: ACPI + raw SMBIOS/DMI. Strong, hard-to-scrub signal. */
static void check_firmware_tables(env_report_t *r){
#if defined(ENV_LINUX)
    /* Raw SMBIOS/DMI dump. */
    const char *dmi[]={"/sys/firmware/dmi/tables/DMI",
                       "/sys/firmware/dmi/tables/smbios_entry_point"};
    for (size_t i=0;i<sizeof(dmi)/sizeof(dmi[0])&&!r->fw_vm_table;++i){
        int fd=open(dmi[i],O_RDONLY);
        if (fd>=0){char b[8192];ssize_t n=read(fd,b,sizeof(b));close(fd);
            if (n>0 && buf_has_keyword(b,(size_t)n,FW_KW,sizeof(FW_KW)/sizeof(FW_KW[0]),
                                       r->fw_vm_hit,sizeof(r->fw_vm_hit))) r->fw_vm_table=1;}
    }
    /* ACPI tables directory: scan each table's bytes. */
    if (!r->fw_vm_table){
        DIR *d=opendir("/sys/firmware/acpi/tables");
        if (d){struct dirent *e;
            while ((e=readdir(d)) && !r->fw_vm_table){
                if (e->d_name[0]=='.') continue;
                char path[320];snprintf(path,sizeof(path),"/sys/firmware/acpi/tables/%s",e->d_name);
                int fd=open(path,O_RDONLY);
                if (fd>=0){char b[8192];ssize_t n=read(fd,b,sizeof(b));close(fd);
                    if (n>0 && buf_has_keyword(b,(size_t)n,FW_KW,sizeof(FW_KW)/sizeof(FW_KW[0]),
                                               r->fw_vm_hit,sizeof(r->fw_vm_hit))) r->fw_vm_table=1;}
            }
            closedir(d);
        }
    }
#elif defined(ENV_WINDOWS)
    /* Raw SMBIOS firmware table ('RSMB'). */
    UINT sz=GetSystemFirmwareTable('RSMB',0,NULL,0);
    if (sz){
        char *b=(char*)malloc(sz);
        if (b){
            if (GetSystemFirmwareTable('RSMB',0,b,sz)==sz &&
                buf_has_keyword(b,sz,FW_KW,sizeof(FW_KW)/sizeof(FW_KW[0]),
                                r->fw_vm_hit,sizeof(r->fw_vm_hit)))
                r->fw_vm_table=1;
            free(b);
        }
    }
#else
    (void)r;
#endif
}

/* PCI vendor IDs that belong to virtualization vendors. */
static int pci_id_is_vm(unsigned v,const char **name){
    switch (v){
        case 0x15ad: *name="VMware(15ad)"; return 1;
        case 0x80ee: *name="VirtualBox(80ee)"; return 1;
        case 0x1af4: *name="virtio(1af4)"; return 1;
        case 0x1234: *name="QEMU/Bochs(1234)"; return 1;
        case 0x5853: *name="XenSource(5853)"; return 1;
        case 0x1ab8: *name="Parallels(1ab8)"; return 1;
        default: return 0;
    }
}
static void check_pci_devices(env_report_t *r){
#if defined(ENV_LINUX)
    DIR *d=opendir("/sys/bus/pci/devices");
    if (d){struct dirent *e;
        while ((e=readdir(d)) && !r->pci_vm_device){
            if (e->d_name[0]=='.') continue;
            char path[320];snprintf(path,sizeof(path),"/sys/bus/pci/devices/%s/vendor",e->d_name);
            int fd=open(path,O_RDONLY);
            if (fd>=0){char b[16];ssize_t n=read(fd,b,sizeof(b)-1);close(fd);
                if (n>0){b[n]='\0';unsigned v=(unsigned)strtoul(b,NULL,16);
                    const char *nm=NULL;
                    if (pci_id_is_vm(v,&nm)){r->pci_vm_device=1;set_name(r->pci_vm_id,sizeof(r->pci_vm_id),nm);}}}
        }
        closedir(d);
    }
#elif defined(ENV_WINDOWS)
    /* Enumerate HKLM\SYSTEM\CurrentControlSet\Enum\PCI subkeys for VEN_ ids. */
    HKEY h;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,"SYSTEM\\CurrentControlSet\\Enum\\PCI",0,KEY_READ,&h)==ERROR_SUCCESS){
        char name[256];DWORD i=0,len;
        static const struct { const char *ven,*nm; } V[]={
            {"VEN_15AD","VMware(15ad)"},{"VEN_80EE","VirtualBox(80ee)"},
            {"VEN_1AF4","virtio(1af4)"},{"VEN_1234","QEMU/Bochs(1234)"},
            {"VEN_5853","XenSource(5853)"},{"VEN_1AB8","Parallels(1ab8)"}};
        while (!r->pci_vm_device){
            len=sizeof(name);
            if (RegEnumKeyExA(h,i++,name,&len,0,0,0,0)!=ERROR_SUCCESS) break;
            for (size_t k=0;k<sizeof(V)/sizeof(V[0]);++k)
                if (ci_contains(name,V[k].ven)){r->pci_vm_device=1;
                    set_name(r->pci_vm_id,sizeof(r->pci_vm_id),V[k].nm);break;}
        }
        RegCloseKey(h);
    }
#else
    (void)r;
#endif
}

/* Disk model + GPU/display adapter strings. */
static void check_disk_gpu(env_report_t *r){
#if defined(ENV_LINUX)
    /* Disk model strings under /sys/block/<dev>/device/model. */
    DIR *d=opendir("/sys/block");
    if (d){struct dirent *e;
        while ((e=readdir(d)) && !r->disk_vm_model){
            if (e->d_name[0]=='.') continue;
            /* virtio disks (vd*) are themselves a guest tell. */
            if (e->d_name[0]=='v'&&e->d_name[1]=='d'){r->disk_vm_model=1;break;}
            char path[320];snprintf(path,sizeof(path),"/sys/block/%s/device/model",e->d_name);
            int fd=open(path,O_RDONLY);
            if (fd>=0){char b[128];ssize_t n=read(fd,b,sizeof(b)-1);close(fd);
                if (n>0){b[n]='\0';
                    if (ci_contains(b,"qemu")||ci_contains(b,"vbox")||ci_contains(b,"virtual")||
                        ci_contains(b,"vmware")) r->disk_vm_model=1;}}
        }
        closedir(d);
    }
    /* GPU: the DRM driver name is a clean signal. */
    DIR *g=opendir("/sys/class/drm");
    if (g){struct dirent *e;
        while ((e=readdir(g)) && !r->gpu_vm_model){
            if (strncmp(e->d_name,"card",4)!=0||strchr(e->d_name,'-')) continue;
            char lp[320];snprintf(lp,sizeof(lp),"/sys/class/drm/%s/device/driver",e->d_name);
            char tgt[256];ssize_t n=readlink(lp,tgt,sizeof(tgt)-1);
            if (n>0){tgt[n]='\0';
                if (ci_contains(tgt,"vmwgfx")||ci_contains(tgt,"virtio")||ci_contains(tgt,"vboxvideo")||
                    ci_contains(tgt,"qxl")||ci_contains(tgt,"bochs")){
                    r->gpu_vm_model=1;
                    const char *base=strrchr(tgt,'/');set_name(r->gpu_name,sizeof(r->gpu_name),base?base+1:tgt);}}
        }
        closedir(g);
    }
#elif defined(ENV_WINDOWS)
    /* Disk model via the registry SCSI device map. */
    HKEY h;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,"HARDWARE\\DEVICEMAP\\Scsi",0,KEY_READ,&h)==ERROR_SUCCESS){
        /* Shallow scan: enumerate one level of "Identifier" values if present. */
        char name[256];DWORD i=0,len;
        while (RegEnumKeyExA(h,i++,name,(len=sizeof(name),&len),0,0,0,0)==ERROR_SUCCESS){
            if (i>32) break; /* bound the scan */
        }
        RegCloseKey(h);
    }
    /* GPU/display adapter name. */
    DISPLAY_DEVICEA dd; dd.cb=sizeof(dd);
    for (DWORD i=0; EnumDisplayDevicesA(NULL,i,&dd,0); ++i){
        if (ci_contains(dd.DeviceString,"vmware")||ci_contains(dd.DeviceString,"virtualbox")||
            ci_contains(dd.DeviceString,"vbox")||ci_contains(dd.DeviceString,"hyper-v")||
            ci_contains(dd.DeviceString,"microsoft basic")||ci_contains(dd.DeviceString,"qxl")||
            ci_contains(dd.DeviceString,"virtio")||ci_contains(dd.DeviceString,"standard vga")){
            r->gpu_vm_model=1; set_name(r->gpu_name,sizeof(r->gpu_name),dd.DeviceString); break;
        }
        dd.cb=sizeof(dd);
    }
#else
    (void)r;
#endif
}

/* Thermal + battery sensors. Absence is a weak VM tell (desktops/servers also
   lack a battery), so no_battery is reported but NOT scored; see env_inspect. */
static void check_sensors(env_report_t *r){
#if defined(ENV_LINUX)
    int have_thermal=0, have_batt=0;
    DIR *t=opendir("/sys/class/thermal");
    if (t){struct dirent *e;
        while ((e=readdir(t))) if (!strncmp(e->d_name,"thermal_zone",12)){have_thermal=1;break;}
        closedir(t);
    }
    DIR *p=opendir("/sys/class/power_supply");
    if (p){struct dirent *e;
        while ((e=readdir(p))) if (!strncmp(e->d_name,"BAT",3)){have_batt=1;break;}
        closedir(p);
    }
    r->no_thermal_sensor = !have_thermal;
    r->no_battery        = !have_batt;
#elif defined(ENV_WINDOWS)
    SYSTEM_POWER_STATUS ps;
    if (GetSystemPowerStatus(&ps)){
        /* BatteryFlag 128 => no system battery. */
        r->no_battery = (ps.BatteryFlag==128) ? 1 : 0;
    }
    r->no_thermal_sensor = 0; /* no cheap portable thermal probe on Windows */
#else
    (void)r;
#endif
}

/* Linux sandbox-environment tells: seccomp, PID namespace, Yama, LD_AUDIT. */
static void check_sandbox_env(env_report_t *r){
#if defined(ENV_LINUX)
    int fd=open("/proc/self/status",O_RDONLY);
    if (fd>=0){char b[8192];ssize_t n=read(fd,b,sizeof(b)-1);close(fd);
        if (n>0){b[n]='\0';char *p=strstr(b,"Seccomp:");
            if (p) r->seccomp_active=(atoi(p+8)!=0);}}
    /* In a non-init PID namespace => containerized/sandboxed. Compare our pid
       namespace inode link against init's; only flag if both are readable. */
    char me[256],init[256];
    ssize_t a=readlink("/proc/self/ns/pid",me,sizeof(me)-1);
    ssize_t c=readlink("/proc/1/ns/pid",init,sizeof(init)-1);
    if (a>0&&c>0){me[a]='\0';init[c]='\0'; if (strcmp(me,init)!=0) r->unusual_namespace=1;}
    /* Yama ptrace_scope (0..3). Reported; not scored. */
    int yf=open("/proc/sys/kernel/yama/ptrace_scope",O_RDONLY);
    if (yf>=0){char b[8];ssize_t n=read(yf,b,sizeof(b)-1);close(yf);
        if (n>0){b[n]='\0';r->yama_ptrace_scope=atoi(b);}}
    const char *la=getenv("LD_AUDIT");
    if (la&&*la) r->ld_audit_set=1;
#else
    (void)r;
#endif
}

/* Frida/Pin deeper fingerprints: telltale thread names and the default Frida
   TCP port 27042. Folds into instrumentation_found. */
static void check_instrumentation_deep(env_report_t *r){
#if defined(ENV_LINUX)
    /* Thread names in /proc/self/task/<tid>/comm. */
    DIR *d=opendir("/proc/self/task");
    if (d){struct dirent *e;
        while ((e=readdir(d)) && !r->instrumentation_found){
            if (e->d_name[0]=='.') continue;
            char path[320];snprintf(path,sizeof(path),"/proc/self/task/%s/comm",e->d_name);
            int fd=open(path,O_RDONLY);
            if (fd>=0){char c[64];ssize_t n=read(fd,c,sizeof(c)-1);close(fd);
                if (n>0){c[n]='\0';char *nl=strchr(c,'\n');if (nl)*nl='\0';
                    if (ci_contains(c,"gum-js")||ci_contains(c,"gmain")||ci_contains(c,"gdbus")||
                        ci_contains(c,"frida")){
                        r->instrumentation_found=1;
                        if (!r->instrumentation_name[0]) set_name(r->instrumentation_name,sizeof(r->instrumentation_name),"frida-thread");}}}
        }
        closedir(d);
    }
    /* Default Frida server port 27042 (0x69A2) in LISTEN on /proc/net/tcp. */
    if (!r->instrumentation_found){
        int fd=open("/proc/net/tcp",O_RDONLY);
        if (fd>=0){char b[65536];ssize_t n=read(fd,b,sizeof(b)-1);close(fd);
            if (n>0){b[n]='\0';
                /* local_address column ends with ":69A2"; LISTEN state is 0A. */
                if (strstr(b,":69A2 ")){r->instrumentation_found=1;
                    if (!r->instrumentation_name[0]) set_name(r->instrumentation_name,sizeof(r->instrumentation_name),"frida-port-27042");}}}
    }
#else
    (void)r;
#endif
}

/* Windows VM/sandbox named pipes. */
static void check_named_pipes(env_report_t *r){
#if defined(ENV_WINDOWS)
    const char *pipes[]={"\\\\.\\pipe\\cuckoo","\\\\.\\VBoxMiniRdrDN","\\\\.\\VBoxGuest",
        "\\\\.\\HGFS","\\\\.\\vmci","\\\\.\\pipe\\sandbox"};
    for (size_t i=0;i<sizeof(pipes)/sizeof(pipes[0]);++i){
        HANDLE h=CreateFileA(pipes[i],GENERIC_READ,0,NULL,OPEN_EXISTING,0,NULL);
        if (h!=INVALID_HANDLE_VALUE){CloseHandle(h);r->vm_named_pipe=1;break;}
        if (GetLastError()==ERROR_PIPE_BUSY){r->vm_named_pipe=1;break;} /* exists, busy */
    }
#else
    (void)r;
#endif
}

/* ================================================================== */
/* Public API                                                          */
/* ================================================================== */
env_options_t env_default_options(void){
    env_options_t o; o.run_ptrace_self=1; o.run_io_backdoor=1; o.run_sleep_skew=0; return o;
}

int env_layout_matches(env_report_t *r,const char *expect,unsigned int langid){
    int m=0;
    if (langid&&r->primary_langid==langid) m=1;
    if (!m&&expect&&r->layout_name[0]&&ci_contains(r->layout_name,expect)) m=1;
    r->layout_matches_target=m;return m;
}

env_report_t env_inspect(const env_options_t *opts){
    env_options_t o = opts ? *opts : env_default_options();
    env_report_t r;memset(&r,0,sizeof(r));

    /* IMPORTANT ordering constraint (Linux):
       PTRACE_TRACEME has process-wide, persistent side effects. Once it has run
       (even followed by PTRACE_DETACH), the next synchronous SIGSEGV/SIGILL is
       delivered as a trace-stop, which makes the fault-based VMware backdoor
       probe self-stop the process instead of being caught. So the two are
       mutually exclusive for the life of the process: we run the backdoor probe
       only while ptrace-self has NEVER run, and we never run the backdoor after
       ptrace-self. This flag is process-wide, like the ptrace side effect. */
#if defined(ENV_LINUX)
    static int ptrace_self_has_run = 0;
#endif

    check_cpuid_hypervisor(&r);
    check_timing(&r);
    check_mac(&r);
    check_dmi_and_artifacts(&r);
#if defined(ENV_LINUX)
    if (o.run_io_backdoor && !ptrace_self_has_run) check_io_backdoor(&r);
#else
    if (o.run_io_backdoor) check_io_backdoor(&r);
#endif
    check_debugger(&r);
    if (o.run_ptrace_self){
        check_ptrace_self(&r);
#if defined(ENV_LINUX)
        ptrace_self_has_run = 1;
#endif
    }
    check_seh_traps(&r);
    check_analysis_tools(&r);
    check_container(&r);
    check_resources(&r);
    if (o.run_sleep_skew) check_sleep_skew(&r);
    check_keyboard_layout(&r);
    /* High-value additions. */
    check_firmware_tables(&r);
    check_pci_devices(&r);
    check_disk_gpu(&r);
    check_sensors(&r);
    check_sandbox_env(&r);
    check_instrumentation_deep(&r);
    check_named_pipes(&r);

    r.vm_score  = r.hypervisor_bit
        + (r.hypervisor_vendor[0]?2:0) + (r.vm_cpu_brand?2:0)
        + (r.vm_mac_prefix?2:0) + (r.vm_dmi_string?3:0) + (r.vm_artifact_present?3:0)
        + (r.vm_vmware_backdoor?3:0) + (r.cpuinfo_hypervisor?1:0)
        + (r.wine_present?2:0) + (r.wsl_present?1:0) + (r.container_detected?2:0)
        + (r.timing_suspicious?1:0) + (r.low_cpu_count?1:0) + (r.low_ram?1:0)
        + (r.small_disk?1:0) + (r.short_uptime?1:0) + (r.suspicious_identity?2:0)
        + (r.small_screen?1:0) + (r.no_user_input?1:0) + (r.sleep_skew_suspicious?2:0)
        /* new high-value VM signals */
        + (r.fw_vm_table?3:0) + (r.pci_vm_device?3:0) + (r.disk_vm_model?2:0)
        + (r.gpu_vm_model?2:0) + (r.no_thermal_sensor?1:0) + (r.vm_named_pipe?2:0)
        + (r.seccomp_active?2:0) + (r.unusual_namespace?1:0);
        /* NOTE: no_battery is reported but intentionally NOT scored — it fires
           on ordinary desktops and servers, so it would be a large false-
           positive source. yama_ptrace_scope is likewise informational only. */

    r.analysis_score = (r.debugger_present?3:0) + (r.kernel_debugger?3:0)
        + (r.analysis_tool_found?3:0) + (r.analysis_tool_installed?2:0)
        + (r.analysis_dll_loaded?3:0) + (r.instrumentation_found?3:0)
        + (r.parent_process_suspicious?3:0) + (r.hw_breakpoints?2:0)
        + (r.peb_ntglobalflag?1:0) + (r.ld_preload_set?1:0) + (r.ld_audit_set?1:0)
        + (r.ptrace_self_blocked?2:0) + (r.seh_int3_debugger?3:0) + (r.closehandle_debugger?3:0);
    return r;
}

/* ------------------------------------------------------------------ */
/* JSON serializer                                                     */
/* ------------------------------------------------------------------ */
static void json_str(char *dst,size_t n,const char *s){
    size_t j=0;dst[j++]='"';
    for (size_t i=0;s&&s[i]&&j<n-2;++i){
        unsigned char c=(unsigned char)s[i];
        if (c=='"'||c=='\\'){if (j<n-3){dst[j++]='\\';dst[j++]=(char)c;}}
        else if (c<0x20){if (j<n-7) j+=(size_t)snprintf(dst+j,n-j,"\\u%04x",c);}
        else dst[j++]=(char)c;
    }
    dst[j++]='"';dst[j]='\0';
}
#define B(x) ((x)?"true":"false")
int env_report_to_json(const env_report_t *r,char *out,size_t n){
    char vend[16],tool[80],inst[160],dll[48],instr[80],par[80],ctype[48],lname[48];
    char fwhit[24],pciid[24],gpu[80];
    json_str(vend,sizeof(vend),r->hypervisor_vendor);
    json_str(tool,sizeof(tool),r->analysis_tool_name);
    json_str(inst,sizeof(inst),r->analysis_tool_inst_name);
    json_str(dll,sizeof(dll),r->analysis_dll_name);
    json_str(instr,sizeof(instr),r->instrumentation_name);
    json_str(par,sizeof(par),r->parent_name);
    json_str(ctype,sizeof(ctype),r->container_type);
    json_str(lname,sizeof(lname),r->layout_name);
    json_str(fwhit,sizeof(fwhit),r->fw_vm_hit);
    json_str(pciid,sizeof(pciid),r->pci_vm_id);
    json_str(gpu,sizeof(gpu),r->gpu_name);
    return snprintf(out,n,
    "{\n"
    "  \"vm\": {\n"
    "    \"hypervisor_bit\": %s, \"hypervisor_vendor\": %s, \"cpu_brand_virtual\": %s,\n"
    "    \"mac_prefix\": %s, \"dmi_string\": %s, \"artifact_present\": %s,\n"
    "    \"vmware_backdoor\": %s, \"cpuinfo_hypervisor\": %s,\n"
    "    \"wine\": %s, \"wsl\": %s, \"container\": %s, \"container_type\": %s,\n"
    "    \"firmware_table\": %s, \"firmware_hit\": %s, \"pci_device\": %s, \"pci_id\": %s,\n"
    "    \"disk_model\": %s, \"gpu_model\": %s, \"gpu_name\": %s,\n"
    "    \"no_thermal_sensor\": %s, \"no_battery\": %s, \"named_pipe\": %s\n"
    "  },\n"
    "  \"debugger\": {\n"
    "    \"present\": %s, \"tracer_pid\": %d, \"ptrace_self_blocked\": %s,\n"
    "    \"peb_being_debugged\": %s, \"peb_ntglobalflag\": %s, \"hw_breakpoints\": %s,\n"
    "    \"debug_port_set\": %s, \"ld_preload_set\": %s, \"ld_audit_set\": %s, \"kernel_debugger\": %s,\n"
    "    \"seh_int3\": %s, \"closehandle\": %s\n"
    "  },\n"
    "  \"analysis\": {\n"
    "    \"tool_running\": %s, \"tool_running_name\": %s,\n"
    "    \"tool_installed\": %s, \"tool_installed_name\": %s,\n"
    "    \"hook_dll_loaded\": %s, \"hook_dll_name\": %s,\n"
    "    \"instrumentation\": %s, \"instrumentation_name\": %s,\n"
    "    \"parent_suspicious\": %s, \"parent_name\": %s\n"
    "  },\n"
    "  \"sandbox_env\": {\n"
    "    \"seccomp_active\": %s, \"unusual_namespace\": %s, \"yama_ptrace_scope\": %d\n"
    "  },\n"
    "  \"resources\": {\n"
    "    \"cpu_count\": %u, \"low_cpu\": %s, \"ram_mb\": %llu, \"low_ram\": %s,\n"
    "    \"disk_gb\": %llu, \"small_disk\": %s, \"uptime_sec\": %llu, \"short_uptime\": %s,\n"
    "    \"suspicious_identity\": %s, \"small_screen\": %s,\n"
    "    \"input_idle_sec\": %llu, \"no_user_input\": %s,\n"
    "    \"sleep_skew_ms\": %ld, \"sleep_skew_suspicious\": %s\n"
    "  },\n"
    "  \"timing\": { \"cpuid_cycles\": %llu, \"suspicious\": %s },\n"
    "  \"keyboard\": { \"primary_langid\": %u, \"layout_name\": %s, \"matches_target\": %d },\n"
    "  \"scores\": { \"vm_score\": %d, \"analysis_score\": %d }\n"
    "}\n",
    B(r->hypervisor_bit), vend, B(r->vm_cpu_brand),
    B(r->vm_mac_prefix), B(r->vm_dmi_string), B(r->vm_artifact_present),
    B(r->vm_vmware_backdoor), B(r->cpuinfo_hypervisor),
    B(r->wine_present), B(r->wsl_present), B(r->container_detected), ctype,
    B(r->fw_vm_table), fwhit, B(r->pci_vm_device), pciid,
    B(r->disk_vm_model), B(r->gpu_vm_model), gpu,
    B(r->no_thermal_sensor), B(r->no_battery), B(r->vm_named_pipe),
    B(r->debugger_present), r->tracer_pid, B(r->ptrace_self_blocked),
    B(r->peb_being_debugged), B(r->peb_ntglobalflag), B(r->hw_breakpoints),
    B(r->debug_port_set), B(r->ld_preload_set), B(r->ld_audit_set), B(r->kernel_debugger),
    B(r->seh_int3_debugger), B(r->closehandle_debugger),
    B(r->analysis_tool_found), tool, B(r->analysis_tool_installed), inst,
    B(r->analysis_dll_loaded), dll, B(r->instrumentation_found), instr,
    B(r->parent_process_suspicious), par,
    B(r->seccomp_active), B(r->unusual_namespace), r->yama_ptrace_scope,
    r->cpu_count, B(r->low_cpu_count), r->ram_mb, B(r->low_ram),
    r->disk_gb, B(r->small_disk), r->uptime_sec, B(r->short_uptime),
    B(r->suspicious_identity), B(r->small_screen),
    r->input_idle_sec, B(r->no_user_input),
    r->sleep_skew_ms, B(r->sleep_skew_suspicious),
    (unsigned long long)r->cpuid_cycles, B(r->timing_suspicious),
    r->primary_langid, lname, r->layout_matches_target,
    r->vm_score, r->analysis_score);
}
#undef B
