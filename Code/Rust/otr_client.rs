// Example made by GPT.
// Cargo.toml:
//[dependencies]
//otr = "0.3.4"

// CLIENT:
use std::net::TcpStream;
use std::io::{Read, Write};
use otr::Otr;

fn main() {
    let mut stream = TcpStream::connect("127.0.0.1:12345").unwrap();
    let mut otr = Otr::new("bob".into(), "alice".into());
    let mut buffer = [0; 512];

    loop {
        let to_send = "Hello, Alice!".as_bytes();
        let encrypted = otr.encrypt(to_send).unwrap();

        stream.write_all(&encrypted).unwrap();

        let bytes_read = stream.read(&mut buffer).unwrap();
        if bytes_read == 0 {
            break;
        }

        let decrypted = otr.decrypt(&buffer[0..bytes_read]).unwrap();
        println!("Received: {:?}", std::str::from_utf8(&decrypted).unwrap());
    }
}

// SERVER:
use std::net::{TcpListener, TcpStream};
use std::io::{Read, Write};
use otr::Otr;

fn handle_client(mut stream: TcpStream) {
    let mut otr = Otr::new("alice".into(), "bob".into());
    let mut buffer = [0; 512];

    loop {
        let bytes_read = stream.read(&mut buffer).unwrap();
        if bytes_read == 0 {
            break;
        }

        let decrypted = otr.decrypt(&buffer[0..bytes_read]).unwrap();
        println!("Received: {:?}", std::str::from_utf8(&decrypted).unwrap());

        let to_send = "Hello, Bob!".as_bytes();
        let encrypted = otr.encrypt(to_send).unwrap();

        stream.write_all(&encrypted).unwrap();
    }
}

fn main() {
    let listener = TcpListener::bind("127.0.0.1:12345").unwrap();

    for stream in listener.incoming() {
        handle_client(stream.unwrap());
    }
}
