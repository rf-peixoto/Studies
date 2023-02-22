use chrono::{DateTime, Utc};
use std::net::{TcpListener, TcpStream};

// Handle connections:
fn client_manager(stream: TcpStream) {
    // Process stuff:
    let now: DateTime<Utc> = Utc::now();
    println!(
        "[\x1b[94mPING\x1b[0m]	{:?}	[\x1b[94m{}\x1b[0m]",
        now,
        stream.peer_addr().unwrap().ip()
    );
}

// Main loop:
fn main() -> std::io::Result<()> {
    // Listen:
    let listener = TcpListener::bind("127.0.0.1:8040")?;
    // Accept and process:
    for stream in listener.incoming() {
        client_manager(stream?);
    }
    return Ok(());
}
