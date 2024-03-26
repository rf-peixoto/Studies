require "http/server"
require "log"

# Setup:
PORT = 8000
LOG_FILE = "server.log"
log_backend = Log::IOBackend.new(File.new(LOG_FILE, "w"))
Log.builder.bind("*", :info, log_backend)

# Custom handler
class CustomHandler < HTTP::Handler
  def call(context)
    # Custom server version and error message
    context.response.headers["Server"] = "nginx/1.6.2"
    context.response.version = "HTTP/1.1"

    # Example response, customize as needed
    context.response.content_type = "text/plain"
    context.response.print "Hello, World!"

    # Log the request
    Log.info { "Request: #{context.request.method} #{context.request.path}" }
  rescue exception
    context.response.status_code = 500
    context.response.print "Undefined error."
    Log.error { "Error processing request: #{exception.message}" }
  end
end

# Start the server
server = HTTP::Server.new do |context|
  CustomHandler.new.call(context)
end

Log.info { "[*] Starting server." }
begin
  server.bind_tcp(PORT)
  Log.info { "[*] Serving on port #{PORT}." }
  server.listen
rescue ex
  Log.error { "\n[-] Closing due to an error: #{ex.message}" }
ensure
  log_backend.close
end
