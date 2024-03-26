# Version one

private_key_path = ARGV[0]
unless private_key_path
  puts "Usage: crystal run prepare_decryptor.cr -- <path_to_private_key.pem>"
  exit
end

private_key_content = File.read(private_key_path).strip.gsub("\n", "\\n")

decryptor_source = <<-CRYSTAL
require "openssl"

private_key_content = <<-KEY
#{private_key_content}
KEY

def decrypt_file(file_path : String, private_key_content : String)
  begin
    private_key = OpenSSL::PKey::RSA.new(private_key_content)
  
    encrypted_data = File.read(file_path)
    decrypted_data = private_key.private_decrypt(encrypted_data)
  
    decrypted_path = file_path.sub(".enc", "")
    File.write(decrypted_path, decrypted_data)
    puts "File decrypted: \#{decrypted_path}"
  rescue e
    puts "Error decrypting \#{file_path}: \#{e.message}"
  end
end

def decrypt_directory(directory : String, private_key_content : String)
  Dir.each_child(directory) do |entry|
    full_path = File.join(directory, entry)
    if File.directory?(full_path)
      decrypt_directory(full_path, private_key_content)
    elsif full_path.ends_with?(".enc")
      decrypt_file(full_path, private_key_content)
    end
  end
end

# Adjust command-line usage for directory processing
if ARGV.size != 1
  puts "Usage: ./decryptor <encrypted_directory_path>"
  exit
end

directory_to_decrypt = ARGV[0]
decrypt_directory(directory_to_decrypt, private_key_content)
CRYSTAL

File.write("decryptor.cr", decryptor_source)
`crystal build decryptor.cr --release -o decryptor`
puts "Decryption executable 'decryptor' is ready."

# Usage: crystal run prepare_decryptor.cr -- /path/to/private_key.pem
# ./decryptor path/to/encrypted_folder
