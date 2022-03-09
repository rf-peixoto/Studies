// Variables hold primitive data or reference to data;
// They are immutable by default and
// Rust is a block-scoped language!

pub fn run() {
    let name = "Brah";

    // This one must be mutable:
    let mut age = 27;
    println!("I'm {} and I am {} old.", name, age);
    age = 28;
    println!("Now I am {} old!", age);
    
    // Define CONSTANT:
    const MY_CONSTANT: i32 = 001;
    println!("ID: {}", MY_CONSTANT);

    // Assign to multiple variables:
    let (my_name, my_age) = ("Bob", 44);
    println!("{} is {} old.", my_name, my_age);
}
