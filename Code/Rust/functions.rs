// Stores blocks of code to reuse:


// Simple example:
fn greeting(greet: &str, name: &str) {
    println!("{}, {}!", greet, name);
}

fn add(a: i8, b: i8) -> i8 {
    // Do not use the ; on the end of the line
    // to return its result:
    a + b
}


// Call it:
pub fn run() {
    greeting("Hello", "Jane");
    let get_sum: i8 = add(2, 8);
    println!("Result: {}", get_sum);

    // Closure:
    let add_nums = |a: i8, b: i8| a + b;
    println!("See closure: {}", add_nums(7, 7));
}
