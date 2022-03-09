// Pointers area references to values in memory.

pub fn run() {
    // Primitive array:
    let array_one = [1, 2, 3];
    let array_two = array_one;
    println!("Values: {:?}", (array_one, array_two));

    // Vectors are non primitive:
    let vec_one = vec![1, 2, 3];
    let vec_two = &vec_one;

    println!("Values: {:?}", (&vec_one, vec_two));

}
