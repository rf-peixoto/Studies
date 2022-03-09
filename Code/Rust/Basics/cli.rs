// Command line interfaces:
use std::env;

pub fn run() {

    let args: Vec<String> = env::args().collect();
    println!("Arguments: {:?}", args);
    let command = args[1].clone();
    println!("Command {}", command);
    let name = "Donnie";



    if command == "Hello" {
        println!("How are you, {}?", name);
    }
}
