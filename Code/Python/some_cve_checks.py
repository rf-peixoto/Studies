import requests
from bs4 import BeautifulSoup
import re
import sys
import argparse

# Payload examples:
# data-target="<img src=1 onerror=alert(123) />"
# data-parent="<img src=1 onerror=alert(123) />"

# I totally forgot what is this thing for:
# https://demo.dotcms.com/html/portlet/ext/files/edit_text_inc.jsp?referer=">HTML Code Injection Here and XSS Vulnerability <br><br>
# Probably 2018-14041, 2018-14040 or 2019-8331


def find_buttons_with_data_target(url):
    # Send an HTTP GET request to the website
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the HTML content of the website using BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find buttons with the 'data-target' attribute
        buttons_with_data_target = soup.find_all('button', {'data-target': True})

        if buttons_with_data_target:
            print(f"Buttons with 'data-target' attribute found on {url}:")
            for button in buttons_with_data_target:
                print(f"Button text: {button.get_text(strip=True)}")
        else:
            print(f"No buttons with 'data-target' attribute found on {url}.")
    else:
        print(f"Failed to fetch {url}. Status code: {response.status_code}")

def check_bootstrap_version(url):
    # Send an HTTP GET request to the website
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the HTML content of the website using BeautifulSoup
        soup = BeautifulSoup(response.content, 'html.parser')

        # Check if the website uses Bootstrap
        bootstrap_found = False

        # Find all <link> tags with a 'href' attribute containing 'bootstrap' in the URL
        link_tags = soup.find_all('link', href=re.compile('bootstrap'))

        for link_tag in link_tags:
            if 'stylesheet' in link_tag.get('rel', []):
                bootstrap_found = True
                break

        if bootstrap_found:
            print(f"Bootstrap is used on {url}.")

            # Find the Bootstrap version (if available)
            version_match = re.search(r'Bootstrap (\d+\.\d+\.\d+)', str(soup))
            if version_match:
                bootstrap_version = version_match.group(1)
                print(f"Bootstrap version on {url}: {bootstrap_version}")

                # Check if the Bootstrap version is 4.3.x or lower
                bootstrap_major_version = int(bootstrap_version.split('.')[0])
                bootstrap_minor_version = int(bootstrap_version.split('.')[1])

                if bootstrap_major_version == 4 and bootstrap_minor_version <= 3:
                    print(f"Bootstrap version on {url} is 4.3.x or lower.")
                else:
                    print(f"Bootstrap version on {url} is greater than 4.3.x.")
            else:
                print(f"Bootstrap version not found on {url}.")
        else:
            print(f"Bootstrap is not used on {url}.")
    else:
        print(f"Failed to fetch {url}. Status code: {response.status_code}")

def main():
    parser = argparse.ArgumentParser(description="Check for Bootstrap usage and buttons with data-target attribute on websites.")
    parser.add_argument("url", metavar="URL", type=str, nargs='?', help="Website URL to check")
    parser.add_argument("-l", "--list", metavar="URL_FILE", type=str, help="File containing a list of URLs to check")

    args = parser.parse_args()

    if args.url:
        check_bootstrap_version(args.url)
        find_buttons_with_data_target(args.url)
    elif args.list:
        with open(args.list, 'r') as url_file:
            urls = url_file.read().splitlines()
            for url in urls:
                print(f"Checking {url}:")
                check_bootstrap_version(url)
                find_buttons_with_data_target(url)
                print()  # Add an empty line to separate results

if __name__ == "__main__":
    main()
