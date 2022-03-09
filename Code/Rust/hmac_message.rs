use ring::{hmac, rand};
use ring ::rand::SecureRandom;
use ring::error::Unespecified;

pub fn run(msg) -> Result<(), Unespecified> {
    let mut key_value = [0u8; 48];
    let rng = rand::SystemRandom::new();
    rng.fill(&mut key_value)?;
    let key = hmac::Key::new(hmac::HMAC_SHA256, &key_value);

    let signature = hmac::sign(&key, msg.as_bytes());
    hmac::verify(&key, msg.as_bytes(), signature.as_ref())?;

    Ok(())
}
