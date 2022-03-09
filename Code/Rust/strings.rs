// Primitive types: immutable fixed-lenght in memory.
// String: Growable, heap-allocated data structure.
// Use when you need to modify your own string data.

pub fn run() {
    // Primitive:
//    let mut hello = "Hello";
    // String:
    let mut new_hello = String::from("Hello");

    // Get length:
    println!("hello size: {}", new_hello.len());

    // Push character:
    new_hello.push('a');
    // Push string:
    new_hello.push_str(" some stuff");

    // Get length:
    println!("new_hello size: {}", new_hello.len());
    // Capacity:
    println!("Capacity: {}", new_hello.capacity());
    println!("{}", new_hello.is_empty());
    println!("Contains ll: {}", new_hello.contains("ll"));
    println!("{}", new_hello.replace("ll", "11"));

    // Loop through sring by whitespace:
    for word in new_hello.split_whitespace() {
        println!("{}", word);
    }

    // create string with capacity:
    let mut s = String::with_capacity(10);
    s.push('x');
    s.push('x');
    s.push('x');
    println!("{}", s);

    // Assertion testing. Only show something if it fails:
    assert_eq!(10, s.capacity());
    assert_eq!(2, s.len());


}
