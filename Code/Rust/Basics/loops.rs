// Iterate until a condition is met.

pub fn run() {
    let mut count: i32 = 0;

    // Infinite loop:
    loop {
        count += 1;
        println!("Number is {}", count);
        if count == 5 {
            break;
        }
    }

    // While loop: {FizzBuzz}
    while count <= 100 {
        if count % 15 == 0 {
            println!("{} FizzBuzz!", count);
        } else if count % 3 == 0 {
            println!("{} Fizz!", count);
        } else if count % 5 == 0 {
            println!("{} Buzz!", count);
        }
        count += 1;
    }

    // For range loop:
    for x in 0..100 {
        if x % 15 == 0 {
            println!("For {} FizzBuzz!", x);
        } else if x % 3 == 0 {
            println!("For {} Fizz!", x);
        } else if x % 5 == 0 {
            println!("For {} Buzz!", x);
        }
    }
}
