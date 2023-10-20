// Example made by GPT.

// Cargo.toml:
//[dependencies]
//otr = "0.3.4"
//tokio = { version = "1", features = ["full"] }

use std::io::{Read, Write, stdin, stdout, Write};
use std::thread;
use otr::Otr;
use tokio::net::{TcpListener, TcpStream};

async fn handle_client(mut stream: TcpStream) {
    let mut otr = Otr::new("alice".into(), "bob".into()); // Replace with actual usernames
    let mut buffer = [0; 512];

    loop {
        let bytes_read = stream.read(&mut buffer).unwrap();
        if bytes_read == 0 {
            break;
        }
        
        let decrypted = otr.decrypt(&buffer[0..bytes_read]).unwrap();
        println!("Received: {:?}", std::str::from_utf8(&decrypted).unwrap());
    }
}

fn main() {
    // Server
    thread::spawn(|| {
        let rt = tokio::runtime::Runtime::new().unwrap();
        rt.block_on(async {
            let listener = TcpListener::bind("127.0.0.1:12345").await.unwrap();
            loop {
                let (stream, _) = listener.accept().await.unwrap();
                tokio::spawn(handle_client(stream));
            }
        });
    });

    // Client
    loop {
        let mut input = String::new();
        print!("Enter the receiver's address (e.g., 127.0.0.1:12346): ");
        stdout().flush().unwrap();
        stdin().read_line(&mut input).unwrap();
        let receiver_address = input.trim();

        let mut stream = TcpStream::connect(receiver_address).unwrap();
        let mut otr = Otr::new("alice".into(), "bob".into()); // Replace with actual usernames

        print!("Enter your message: ");
        stdout().flush().unwrap();
        input.clear();
        stdin().read_line(&mut input).unwrap();

        let to_send = input.trim().as_bytes();
        let encrypted = otr.encrypt(to_send).unwrap();
        
        stream.write_all(&encrypted).unwrap();

        let mut buffer = [0; 512];
        let bytes_read = stream.read(&mut buffer).unwrap();
        if bytes_read == 0 {
            continue;
        }

        let decrypted = otr.decrypt(&buffer[0..bytes_read]).unwrap();
        println!("Received: {:?}", std::str::from_utf8(&decrypted).unwrap());
    }
}
