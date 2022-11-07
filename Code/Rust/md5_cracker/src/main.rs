use md5::Digest;
use std::{
    env,
    error::Error,
    fs::File,
    io::{BufRead, BufReader},
};

// Hash size:
const MD5_LENGTH: usize = 32;

// Main:
fn main() -> Result<(), Box<dyn Error>> {
    // Read command line args:
    let args: Vec<String> = env::args().collect();

    // Check for all args:
    if args.len() != 3 {
        println!("Usage:");
        println!("{} <wordlist> <md5>", args[0].trim());
        return Ok(());
    }

    // Verify hash:
    let md5_hash = args[2].trim();
    if md5_hash.len() != MD5_LENGTH {
        return Err("Invalid hash size!".into());
    }    

    // Read wordlist:
    let wordlist_file = File::open(&args[1])?;
    let reader = BufReader::new(&wordlist_file);

    // Iteration:
    for line in reader.lines() {
        // Hash object:
        //let md5_obj = md5::Md5::new();
        let line = line?;
        let passwd = line.trim();
        if md5_hash ==
            &hex::encode(md5::Md5::digest(passwd.as_bytes())) {
//            &hex::encode(md5::compute(passwd.as_bytes())) {
            println!("Password found: {}", &passwd);
            return Ok(());
        }
    }

    println!("Done.");
    Ok(())
}
