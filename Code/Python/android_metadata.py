import subprocess
import re
import requests
from bs4 import BeautifulSoup
from colorama import init, Fore, Style
import time

# Initialize colorama
init(autoreset=True)

# Define color shortcuts
INFO = Fore.CYAN + Style.BRIGHT
WARNING = Fore.YELLOW + Style.BRIGHT
DANGER = Fore.RED + Style.BRIGHT
SUCCESS = Fore.GREEN + Style.BRIGHT
RESET = Style.RESET_ALL

def run_shell_command(cmd):
    """Utility function to run shell commands with error handling."""
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print(DANGER + f"Error executing command {' '.join(cmd)}: {result.stderr.strip()}")
            return None
        return result.stdout.strip()
    except Exception as e:
        print(DANGER + f"Exception occurred while executing command {' '.join(cmd)}: {str(e)}")
        return None

def get_installed_packages():
    """Retrieve a list of installed packages."""
    result = run_shell_command(['pm', 'list', 'packages'])
    if result is None:
        print(DANGER + "Failed to retrieve installed packages.")
        return []
    packages = result.strip().split('\n')
    package_names = [pkg.replace('package:', '') for pkg in packages]
    return package_names

def fetch_app_metadata(package_name):
    """Fetch app metadata from Google Play Store."""
    try:
        # Construct the URL for the app's Play Store page
        url = f"https://play.google.com/store/apps/details?id={package_name}&hl=en"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(WARNING + f"Failed to fetch metadata for {package_name}. HTTP Status Code: {response.status_code}")
            return None
        return response.text
    except Exception as e:
        print(DANGER + f"Error fetching metadata for {package_name}: {str(e)}")
        return None

def parse_privacy_policy_url(html_content):
    """Parse the privacy policy URL from the app's Play Store page."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        link = soup.find('a', {'href': re.compile('^https?://')}, text='Privacy Policy')
        if link:
            return link['href']
        else:
            return None
    except Exception as e:
        print(DANGER + f"Error parsing privacy policy URL: {str(e)}")
        return None

def analyze_privacy_policy(url):
    """Analyze the privacy policy content for key privacy concerns."""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(WARNING + f"Failed to fetch privacy policy from {url}. HTTP Status Code: {response.status_code}")
            return None
        text = response.text.lower()
        # Keywords to look for
        keywords = ['data collection', 'third-party', 'personal information', 'location', 'cookies', 'tracking', 'advertising']
        findings = {}
        for keyword in keywords:
            findings[keyword] = keyword in text
        return findings
    except Exception as e:
        print(DANGER + f"Error analyzing privacy policy at {url}: {str(e)}")
        return None

def main():
    print(INFO + "Starting privacy policy analysis of installed apps...\n")

    packages = get_installed_packages()
    if not packages:
        print(DANGER + "No packages found.")
        return

    for package_name in packages:
        print(INFO + f"Analyzing {package_name}...")
        html_content = fetch_app_metadata(package_name)
        if html_content is None:
            continue

        privacy_policy_url = parse_privacy_policy_url(html_content)
        if not privacy_policy_url:
            print(WARNING + f"No privacy policy URL found for {package_name}.")
            continue

        findings = analyze_privacy_policy(privacy_policy_url)
        if findings is None:
            continue

        # Summarize findings
        concerns = [k for k, v in findings.items() if v]
        if concerns:
            print(DANGER + f"Potential privacy concerns in {package_name}:")
            for concern in concerns:
                print(f"    - {concern}")
        else:
            print(SUCCESS + f"No immediate privacy concerns found in {package_name}.")

        # Sleep to prevent rate limiting
        time.sleep(1)

    print(SUCCESS + "\nPrivacy policy analysis completed.")

if __name__ == '__main__':
    main()
