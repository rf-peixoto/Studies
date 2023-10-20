// Example made by GPT.

// Cargo.toml:
//[dependencies]
//otr = "0.3.4"
//tokio = { version = "1", features = ["full"] }

// Handler:
use otr::Otr;
use tokio::net::TcpStream;
use std::io::{Read, Write};

async fn handle_client(mut stream: TcpStream) {
    let mut otr = Otr::new("alice".into(), "bob".into());
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

// Node:
use tokio::net::{TcpListener, TcpStream};
use std::thread;
use std::io::{Read, Write};
use otr::Otr;

#[tokio::main]
async fn main() {
    let listener = TcpListener::bind("127.0.0.1:12345").await.unwrap();

    thread::spawn(move || {
        tokio::runtime::Runtime::new().unwrap().block_on(async {
            loop {
                let (stream, _) = listener.accept().await.unwrap();
                tokio::spawn(handle_client(stream));
            }
        });
    });

    loop {
        let receiver_address = "127.0.0.1:12346"; // Replace with the desired receiver address
        let mut stream = TcpStream::connect(receiver_address).unwrap();
        let mut otr = Otr::new("alice".into(), "bob".into()); // Replace names accordingly

        let to_send = "Hello, Bob!".as_bytes(); // Replace with the message you want to send
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
