// Ref: https://tokio.rs/

// On Cargo.toml:
tokio = { version = "1", features = ["full"] }

// Spawn:
tokio::spawn(async move {
    // Do your thing;
});

// Sleep:
tokio::time::sleep(Duration::from_millis(sleep_ms)).await;

// Timeout exmaple:
tokio::time::timeout(Duration::from_secs(3),
    TcpStream::connect(socket_address)).await
