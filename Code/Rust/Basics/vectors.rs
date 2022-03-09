// Vectors are resizable arrays:
use std::mem;


pub fn run() {
    // [type, number of elements]
    let mut numbers: Vec<i8> = vec![0, 1, 2, 3];
    println!("{:?}", numbers);
    // Get value:
    println!("{}", numbers[0]);
    // Change:
    numbers[3] = 0;
    println!("{:?}", numbers);
    // Add value:
    numbers.push(5);
    // Get length:
    println!("{}", numbers.len());
    // Pop out last value:
    numbers.pop();
    // Memory (stack allocated):
    println!("Size in memory: {} bytes", mem::size_of_val(&numbers)); 
    // Get slice:
    let slice: &[i8] = &numbers[0..2];
    println!("{:?}", slice);

    // Loop through values:
    for n in numbers.iter() {
        println!("Number: {}", n);
    }

    // Loop and mutatte:
    for n in numbers.iter_mut() {
        *n *= 2;
    }

    println!("End vector: {:?}", numbers);
}
