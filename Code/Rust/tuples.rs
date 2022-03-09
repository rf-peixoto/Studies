// Tuples are group of values.
// Max 12 elements.

pub fn run() {
    let personal_data: (&str, &str, i8) = ("Name", "Location", 30);
    println!("{} if from {} and is {} old.",
    personal_data.0, personal_data.1, personal_data.2);
}
