// String functions:

fn main() {

    let example = "Hello, world.";
    // Get as bytes:
    let bytes = example.as_bytes(); // b'Hello, world.'
    let individual_bytes = example.bytes(); // b'H', b'e', b'l', ...
    // Split all kind of whitepaces:
    let no_spaces = example.split_whitespace(); // "Hello,", "world."
    // Get size:
    let example_size = example.size();
    // Split only ASCII whitespaces:
    let no_ascii_spaces = example.split_ascii_whitespace();
    // Split lines:
    let lines = example.lines();
    // Check for content:
    assert!(example.contains("wor"));
    // Check start of string:
    assert!(!example.starts_with("J")); // The "!" means NOT.
    // Check end of string:
    assert!(example.ends_with("."));
    // Find patterns:
    assert!(example.find("l"), Some(3)); // Checks if the character "l" appear 3 times.
    // Split by specific character:
    let splitted = example.split(",").collect();
    let splitted = example.split(char::is_numeric).collect(); // Every number.
    let splitted = example.split(char::is_uppercase).collect(); // By character case;
    let splitted = example.split(|c| c == 'e' || c == 'w').collect(); // By one or other charactere;
    let splitted = example.split_once(",").collect(); // Split only the first occurrence.

}
