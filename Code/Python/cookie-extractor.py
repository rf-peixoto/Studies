import requests
import json
from urllib.parse import urlparse

class WebRequestHandler:
    def __init__(self):
        # Initial headers with placeholders for dynamic values
        self.base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
        }

    def make_request_with_new_cookies(self, url):
        return self._make_request(url)

    def make_request_with_preconfigured_headers(self, url):
        # Configure headers for this specific request
        headers = self._configure_headers_for_url(url)
        return self._make_request(url, headers)

    def _configure_headers_for_url(self, url):
        # Parse the URL to dynamically set the Referer header
        parsed_url = urlparse(url)
        referer = f"{parsed_url.scheme}://{parsed_url.netloc}"
        headers = self.base_headers.copy()
        headers['Referer'] = referer
        return headers

    def _make_request(self, url, headers=None):
        try:
            response = requests.get(url, headers=headers)
            result = {
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'cookies': response.cookies.get_dict()
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({'status_code': 'Error', 'error': str(e)}, indent=2)

# Example of using the class
if __name__ == "__main__":
    handler = WebRequestHandler()
    url = 'http://twitter.com/'  # Replace with the actual URL

    # Making a request with new cookies (or without specific headers)
    print("Request with new cookies:")
    print(handler.make_request_with_new_cookies(url))

    # Making a request with pre-configured headers
    print("\nRequest with pre-configured headers:")
    print(handler.make_request_with_preconfigured_headers(url))
