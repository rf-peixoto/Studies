pub fn run() {
    // Print to console:
    println!("This is the print.rs file!");
    // To print anything that is not a string:
    println!("Number: {}", 1);
    // Multiple parameters:
    println!("A little {} came to the {}.", "crab", "door");
    // Positional arguments:
    println!("{0} is from {1} and {0} likes to {2}.",
    "Crab", "Anywhere", "code");
    // Named arguments:
    println!("{name} likes to play {stuff}.",
    name = "Joe",
    stuff = "chess"
    );
    // PLaceholder traits:
    println!("Binary {:b}, Hex {:x}, Octal {:o}", 10, 10, 10);
    // Placeholder for debug traits:
    println!("What if {:?}", (12, true, "test"));
    // Math:
    println!("10 + 10 = {}", 10 + 10);
}
