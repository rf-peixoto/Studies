require 'resolv'

def get_txt_records(domain)
  begin
    txt_records = Resolv::DNS.open do |dns|
      records = dns.getresources(domain, Resolv::DNS::Resource::IN::TXT)
      records.map { |r| r.strings.join(' ') }
    end
    return txt_records
  rescue Resolv::ResolvError => e
    puts "DNS query error: #{e.message}"
    return []
  end
end

def print_txt_records(domain, txt_records)
  if txt_records.empty?
    puts "No TXT records found for domain: #{domain}"
  else
    puts "TXT records for domain: #{domain}"
    txt_records.each { |record| puts "  #{record}" }
  end
end

if ARGV.empty?
  puts "Usage: ruby dns_query.rb <domain>"
else
  domain = ARGV[0]
  txt_records = get_txt_records(domain)
  print_txt_records(domain, txt_records)
end
