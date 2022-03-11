use error_chain::erroor_chain;
use std::io::Read;

error_chain! {
    foreign_links {
        Io(std::io::Error);
        HttpRequest(reqwest::Error); //reqwest?
    }
}

fn main() -> Result<()> {
    let mut response = reqest::blocking::get("URL")?;
    // let mut body = String::new();
    // response.read_to_string(&mut body)?;

    println!("Status code: {}", response.status());
    println!("Headers:\n{:#?}", response.headers());
    // println!("Body:\n{}", body);

    return Ok();
}
