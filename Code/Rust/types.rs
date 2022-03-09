/*
Primitive types:
Interger:
u: unassign = can't take negative numbers.
u8, i8, u16, i16, u32, i32, u64, i64, u128, i128 (bits in memory)
Floats: f32, f64
Boolean: (bool)
Characters: (char)
Tuples,
Arrays
*/

pub fn run() {
    // Add explicit type:
    let n: i32 = 10;
    let nu: f32 = 1.00;
    println!("Interger: {}\nFloat: {}", n, nu);

    // Boolean:
    let switch: bool = true;
    println!("{}", switch);
    // Get fro mexpression
    let condition: bool = 2 > 5;
    println!("{}", condition);

    // Character:
    let letter: char = 'f';
    let face: char = '\u{1F600}';
    println!("{:?}", (letter, face));
}
