use sha1::Digest;
use std::{
    env,
    error::Error,
    fs::File,
    io::{BufRead, BufReader},
};

const SHA1_HEX_STRING_LENGTH: usize = 40;

fn main() -> Result<(), Box<dyn Error>> {
    // Check args list:
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        println!("[i] Usage:");
        println!("sha1_cracker <wordlist.txt> <hash.txt>");
        return Ok(());
    }

    // Get hash:
    let hash_to_crack = args[2].trim();
    if hash_to_crack.len() != SHA1_HEX_STRING_LENGTH {
        return Err("[!] Hash not valid!".into());
    }

    // Prepare wordlist:
    let wordlist_file = File::open(&args[1])?;
    let reader = BufReader::new(&wordlist_file);
    // Read:
    for line in reader.lines() {
        let line = line?;
        let com_passwd = line.trim();
        // Check word hash:
        if hash_to_crack == &hex::encode(sha1::Sha1::digest(com_passwd.as_bytes())) {
            println!("[+] Password found: {}", com_passwd);
            return Ok(());
        }
    }
    // Hash not found:
    println!("[-] Hash not found.");
    return Ok(());
}
