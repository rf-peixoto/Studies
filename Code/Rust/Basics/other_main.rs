// Error Handling:
use error_chain::error_chain;
use std::net::IpAddr;
use std::str;

error_chain! {
    foreign_links {
        Utf8(std::str::Utf8Error);
        AddrParse(std::net::AddrParseError);
    }
}

// Actual module on test:
mod hmac_message;

// Run code:
fn main() -> Result<()> {
    hmac_message::run("Test");


    // Return Ok code:
    Ok(())
}
