// Structs are similar to clasess:

// Traditional struct:
struct Color {
    red: u8,
    green: u8,
    blue: u8,
}

// Tuple struct:
struct Another (u8, u8, u8);


// Struct with function:
struct Person {
    first_name: String,
    last_name: String,
}

// Implement
impl Person {
    fn new(first: &str, last: &str) -> Person {
        Person {
            first_name: first.to_string(),
            last_name: last.to_string()
        }
    }

    fn full_name(&self) -> String {
        format!("{} {}", self.first_name, self.last_name)
    }

    fn set_last_name(&mut self, last: &str) {
        self.last_name = last.to_string();
    }

    fn name_to_tuple(self) -> (String, String) {
        (self.first_name, self.last_name)
    }
}

pub fn run() {

    let mut c = Color {red: 255, green: 0, blue: 0};
    println!("RGB {}:{}:{}", c.red, c.green, c.blue);
    c.green = 200;
    println!("RGB {}:{}:{}", c.red, c.green, c.blue);

    let mut a = Another(0, 120, 250);
    println!("RGB {}:{}:{}", a.0, a.1, a.2);
    a.1 = 100;
    println!("RGB {}:{}:{}", a.0, a.1, a.2);

    let mut p = Person::new("John", "Doe");
    println!("Person: {} {}", p.first_name, p.last_name);
    p.set_last_name("Jane");
    println!("Person {}", p.full_name());
    println!("Person Tup {:?}", p.name_to_tuple());
}
