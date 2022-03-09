use rand::Rng;

pub fn run() {
    let mut rng = rand::thread_rng();
    println!("Random u8: {}", rng.gen::<u8>());
}
