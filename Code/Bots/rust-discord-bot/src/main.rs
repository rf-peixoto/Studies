// Ref: https://betterprogramming.pub/writing-a-discord-bot-in-rust-2d0e50869f64

pub mod config;
use config::Config;
use serenity::{
    prelude::*,
    model::prelude::*,
    Client,
};

struct Handler;
impl EventHandler for Handler {
    fn message(&self, context: Context, msg: Message) {
        if msg.content == "%ping" {
            if let Err(why) = msg.channel_id.say(&context.http, "Pong") {
                println!("Error while sending message: {}", why);
            }
        }
    }
}


fn main() {
    let _ = Config::new().save();
    let config = Config::load().unwrap();
    let mut client = Client::new(config.token(), Handler)
        .expect("Could'nt create the new client!");
    if let Err(why) = client.start() {
        println!("Client error: {}", why)
    }
}
