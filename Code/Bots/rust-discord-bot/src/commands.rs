use serenity::{
  prelude::*,
  model::prelude::*,
  framework::standard::{
    CommandResult, macros::command,
  },
};

#[command]
fn ping(ctx: &mut Context, msg: Message) -> CommandResult {
  if let Err(why) = msg.channel_id.say(&ctx.http, "Pong!") {
    println!("Error sending message: {}", why);
  }
  return Ok(());
}
