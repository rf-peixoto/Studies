use sysinfo::{NetworkExt, NetworksExt, ProcessExt, System, SystemExt};
use external_ip;

fn main() {
    // Get stuff:
    let mut sys = System::new_all();
    sys.refresh_all(); // Update your shit

    // Disks:
    println!("\n[*] DISKS");
    for disk in sys.disks() {
        println!("{:?}", disk);
    }

    // Network interfaces and data:
    println!("\n[*] NETWORK");
    for (interface, data) in sys.networks() {
        println!("{}: {}/{} B", interface, data.received(), data.transmitted());
    }

    // Temperature:
    println!("\n[*] TEMPERATURE");
    for component in sys.components() {
        println!("{:?}", component);
    }

    // Memory:
    println!("\n[*] MEMORY");
    println!("total memory:	{} bytes", sys.total_memory());
    println!("used memory:	{} bytes", sys.used_memory());
    println!("total swap:	{} bytes", sys.total_swap());
    println!("used swap:	{} bytes", sys.used_swap());

    // System Info:
    println!("\n[*] SYSTEM");
    println!("System name:	{}", sys.name().unwrap_or_default());
    println!("Kernel version:	{}", sys.kernel_version().unwrap_or_default());
    println!("OS version:	{}", sys.os_version().unwrap_or_default());
    println!("Host name:	{}", sys.host_name().unwrap_or_default());

    // External IP:
//    println!("\n[*] EXTERNAL IP");
//    let dns_sources: external_ip::Sources = external_ip::get_dns_sources();
//    println!("DNS Sources: {:#?}", dns_sources.to_string());
//    for source in dns_sources {
//        match external_ip::get_ip() {
//            Ok(ip) => println!("External IP ({}):	{}", source, ip),
//            Err(error) => println!("Cannot retrieve IP from {}: {}", source, error),
//        }
//    }

    // Processes:
    println!("\n[*] PROCESSES:");
    for (pid, process) in sys.processes() {
        println!("[{}]	{}", pid, process.name());
        //println!("[{}]	{}	{:?}", pid, process.name(), process.disk_usage());
    }

}
