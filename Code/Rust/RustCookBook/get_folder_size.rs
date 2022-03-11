use walkdir::Walkdir;

fn main() {
    let total_size = WalkDir::new(".")
        .min_depth(1)
        .max_depth(9)
        .into_iter()
        .filter_map(|entry| entry.ok())
        .filter_map(|entry| entry.metadata().ok())
        .filter(|metadata| metadata.is_file())
        .fold(0, |acc, m| acc + m.len());

    println!("Total size: {} bytes.", total_size);
}
