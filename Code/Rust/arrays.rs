// Arrays length is fixed;
// Elements must have the same type.
use std::mem;


pub fn run() {
    // [type, number of elements]
    let mut numbers: [i8; 4] = [0, 1, 2, 3];
    println!("{:?}", numbers);
    // Get value:
    println!("{}", numbers[0]);
    // Change:
    numbers[3] = 0;
    println!("{:?}", numbers);
    // Get length:
    println!("{}", numbers.len());
    // Memory (stack allocated):
    println!("Size in memory: {} bytes", mem::size_of_val(&numbers)); 
    // Get slice:
    let slice: &[i8] = &numbers[0..1];
    println!("{:?}", slice);
}
