// Manage the flow of execution;//

pub fn run() {
    let age: u8 = 18;
    let check_id: bool = false;
    let group_member: bool = true;

    if check_id && age >= 21 || group_member {
        println!("What would you like to drink?");
    } else if check_id && age < 21 {
        println!("Leave now!");
    } else {
        println!("I will need to see your ID.");
    }

    // Short hand If:
    let is_of_age: bool = if age >= 21 { true } else { false };
    println!("Is of age: {}", is_of_age);

}
