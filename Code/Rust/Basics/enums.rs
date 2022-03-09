// Enumas have a few definite values.

enum Movement {
    // Variants:
    Up,
    Down,
    Left,
    Right
}

fn move_avatar(m: Movement) {
    // Perform action:
    match m {
        Movement::Up => println!("Move up."),
        Movement::Down => println!("Move down."),
        Movement::Left => println!("Move left."),
        Movement::Right => println!("Move right.")
    }
}



pub fn run() {

    let avatar_one = Movement::Left;
    let avatar_two = Movement::Down;
    let avatar_tree = Movement::Right;
    let avatar_four = Movement::Up;

    move_avatar(avatar_one);
    move_avatar(avatar_two);
    move_avatar(avatar_tree);
    move_avatar(avatar_four);

}
