require "http/client"
require "base64"
require "digest/md5"
require "random/secure"

# Function to decode the URL using URL-safe Base64
def decode_url(encoded_url : String)
  Base64.urlsafe_decode_string(encoded_url)
rescue
  puts "Invalid encoded URL."
  exit
end

# Function to generate a filename from the URL with a random salt
def generate_filename(url : String)
  salt = Random::Secure.hex(8) # Generates a random 8-byte hex string
  hash = Digest::MD5.hexdigest("#{url}#{salt}")
  "file_#{hash}.bin" # Filename includes URL hash and salt
end

# Main logic with chunked download
if ARGV.size != 1
  puts "Usage: program <encoded_url>"
  exit
end

encoded_url = ARGV[0]
url = decode_url(encoded_url)
filename = generate_filename(url)

# Open a file for writing
File.open(filename, "w") do |file|
  HTTP::Client.get(url) do |response|
    if response.status_code == 200
      # Read the response body in chunks
      IO.copy(response.body_io, file, 256) # Adjust chunk size as needed
      puts "File saved as #{filename}"
    else
      puts "Failed to download file: HTTP Status Code #{response.status_code}"
    end
  end
end



# ------------------------#
# How to encode URLs:
#require "base64"
# Check if an argument was provided
#if ARGV.size != 1
#  puts "Usage: crystal encode.cr <url>"
#  exit
#end
# Take the first argument as the URL
#url = ARGV[0]
# Encode the URL
#encoded_url = Base64.urlsafe_encode(url)
# Print the encoded URL
#puts encoded_url
