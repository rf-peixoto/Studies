require "http"
require "socket"

LISTEN_PORT = 8080 # Port to listen for incoming connections

# Log a message with a timestamp
def log(message : String)
  puts "[#{Time.local}] #{message}"
end

# Extract host and port from HTTP request
def extract_destination_host_and_port(http_header : String) : Tuple(String, Int32)
  if http_header =~ /Host: (\S+)/
    host_header = $1
    host_parts = host_header.split(':')
    host = host_parts[0]
    port = host_parts.size > 1 ? host_parts[1].to_i : 80 # Default to port 80 if not specified
    {host, port}
  else
    raise "Host header not found"
  end
end

# Forward data between sockets and log the data
def forward_and_log_data(source : IO, destination : IO, direction : String)
  buffer = Bytes.new(4096)
  while (bytes_read = source.read(buffer)) > 0
    data = String.new(buffer[0, bytes_read])
    log("#{direction} data: #{data.inspect}")
    destination.write(data)
  end
rescue
  # Ignoring errors here, typically would log or handle them
ensure
  destination.close
end

# Handle client connection
def handle_client(client : TCPSocket)
  begin
    # Read the initial request line and headers from the client
    initial_data = client.gets_to_end
    log("Received data from client: #{initial_data.inspect}")

    # Extract the destination host and port from the request
    host, port = extract_destination_host_and_port(initial_data)
    log("Forwarding to #{host}:#{port}")

    # Connect to the destination server
    destination = TCPSocket.new(host, port)

    # Forward the initial request and log it
    destination.write(initial_data)
    log("Forwarded initial data to #{host}:#{port}")

    # Use fibers to handle bidirectional forwarding and logging
    Fiber.new do
      forward_and_log_data(client, destination, "Client to Server")
    end.resume

    Fiber.new do
      forward_and_log_data(destination, client, "Server to Client")
    end.resume
  rescue ex
    log("Error: #{ex.message}")
  ensure
    client.close unless client.closed?
    log("Client connection closed")
  end
end

# Start listening for incoming connections
server = TCPServer.new(LISTEN_PORT)
log("Proxy server started on port #{LISTEN_PORT}")

# Main server loop
while client = server.accept?
  log("New connection from #{client.remote_address.to_s}")
  Fiber.new { handle_client(client) }.resume
end
