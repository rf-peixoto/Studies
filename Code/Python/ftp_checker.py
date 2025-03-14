import ftplib
import argparse
import sys
import socket
from colorama import Fore, Style, init

# Initialize colorama for colored output
init(autoreset=True)

def test_ftp_anonymous(domain):
    try:
        print(f"\n{Fore.CYAN}[INFO]{Style.RESET_ALL} Testing: {domain}")
        ftp = ftplib.FTP(domain, timeout=5)
        banner = ftp.getwelcome()
        ftp.login('anonymous', 'anonymous')
        print(f"{Fore.GREEN}[SUCCESS]{Style.RESET_ALL} Anonymous login allowed on {domain}")
        print(f"{Fore.BLUE}[BANNER]{Style.RESET_ALL} {banner}")
        
        # Test 'SITE' command variations
        site_commands = ["SITE HELP", "SITE CHMOD 777 test", "SITE EXEC ls", "SITE WHO"]
        site_results = []
        
        for cmd in site_commands:
            try:
                response = ftp.sendcmd(cmd)
                if "500" not in response and "502" not in response:
                    site_results.append(f"{cmd}: {response}")
            except ftplib.error_perm:
                continue
        
        if site_results:
            print(f"{Fore.RED}[ALERT]{Style.RESET_ALL} SITE commands available: {' | '.join(site_results)}")
        else:
            print(f"{Fore.YELLOW}[WARNING]{Style.RESET_ALL} No executable SITE commands found on {domain}")
        
        ftp.quit()
    except ftplib.error_perm as e:
        print(f"{Fore.RED}[FAIL]{Style.RESET_ALL} Anonymous login denied on {domain}: {e}")
    except socket.timeout:
        print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} Connection to {domain} timed out")
    except ConnectionRefusedError:
        print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} Connection to {domain} was refused")
    except ftplib.error_temp as e:
        print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} Temporary error on {domain}: {e}")
    except Exception as e:
        print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} Could not connect to {domain}: {e}")

def process_file(filename):
    try:
        with open(filename, "r") as file:
            domains = file.readlines()
            for domain in domains:
                domain = domain.strip()
                if domain:
                    test_ftp_anonymous(domain)
    except FileNotFoundError:
        print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} File not found: {filename}")

def main():
    parser = argparse.ArgumentParser(description="FTP Anonymous Login Tester")
    parser.add_argument("-u", "--url", help="Single domain/URL to test")
    parser.add_argument("-f", "--file", help="File containing list of domains/URLs")
    args = parser.parse_args()
    
    if args.url:
        test_ftp_anonymous(args.url)
    elif args.file:
        process_file(args.file)
    else:
        print(f"{Fore.YELLOW}[WARNING]{Style.RESET_ALL} Please specify either a URL (-u) or a file (-f). Use --help for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()
