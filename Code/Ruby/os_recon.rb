require 'socket'
require 'etc'

class OSRecon
  def initialize
    @os = RbConfig::CONFIG['host_os']
    @arch = "#{RbConfig::CONFIG['host_cpu']} #{RbConfig::CONFIG['host_vendor']}"
    @username = Etc.getlogin
    @home = Dir.home
    @node = Socket.gethostname
    @node_ip = Socket.getaddrinfo(@node, nil)[0][3]
    @dump = `cat /etc/os-release` # You may need to adjust this for your specific Linux distribution
  end

  def display_info
    puts "OS: #{@os}"
    puts "Architecture: #{@arch}"
    puts "Username: #{@username}"
    puts "Home Path: #{@home}"
    puts "Network Node: #{@node}"
    puts "Local Address: #{@node_ip}"
  end
end

# Debug:
r = OSRecon.new
r.display_info
