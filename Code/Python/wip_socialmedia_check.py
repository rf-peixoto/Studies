import sys
import requests
from bs4 import BeautifulSoup
import whois
import re
import urllib.parse

def extract_facebook_details(profile_url):
    response = requests.get(profile_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    profile_details = {
        "username": soup.find("meta", {"property": "og:title"})["content"],
        "profile_picture": soup.find("meta", {"property": "og:image"})["content"],
        "bio": soup.find("meta", {"property": "og:description"})["content"]
    }
    return profile_details

def extract_instagram_details(profile_url):
    response = requests.get(profile_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    profile_details = {
        "username": soup.find("meta", {"property": "og:title"})["content"],
        "profile_picture": soup.find("meta", {"property": "og:image"})["content"],
        "bio": soup.find("meta", {"property": "og:description"})["content"]
    }
    return profile_details

def extract_twitter_details(profile_url):
    response = requests.get(profile_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    profile_details = {
        "username": soup.find("meta", {"property": "profile:username"})["content"],
        "profile_picture": soup.find("meta", {"property": "og:image"})["content"],
        "bio": soup.find("meta", {"name": "description"})["content"]
    }
    return profile_details

def extract_tiktok_details(profile_url):
    response = requests.get(profile_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    profile_details = {
        "username": soup.find("meta", {"property": "og:title"})["content"],
        "profile_picture": soup.find("meta", {"property": "og:image"})["content"],
        "bio": soup.find("meta", {"name": "description"})["content"]
    }
    return profile_details

def extract_youtube_details(profile_url):
    response = requests.get(profile_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    profile_details = {
        "username": soup.find("meta", {"name": "title"})["content"],
        "profile_picture": soup.find("meta", {"property": "og:image"})["content"],
        "bio": soup.find("meta", {"name": "description"})["content"]
    }
    return profile_details

def extract_profile_details(profile_url):
    if "facebook.com" in profile_url:
        return extract_facebook_details(profile_url)
    elif "instagram.com" in profile_url:
        return extract_instagram_details(profile_url)
    elif "twitter.com" in profile_url:
        return extract_twitter_details(profile_url)
    elif "tiktok.com" in profile_url:
        return extract_tiktok_details(profile_url)
    elif "youtube.com" in profile_url:
        return extract_youtube_details(profile_url)
    else:
        return None

def google_reverse_image_search(image_url):
    search_url = 'https://www.google.com/searchbyimage?&image_url=' + urllib.parse.quote(image_url)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
    response = requests.get(search_url, headers=headers)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        similar_images = [img['src'] for img in soup.find_all('img') if 'src' in img.attrs]
        return similar_images
    else:
        return None

def yandex_reverse_image_search(image_url):
    search_url = 'https://yandex.com/images/search?rpt=imageview&url=' + urllib.parse.quote(image_url)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
    response = requests.get(search_url, headers=headers)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        similar_images = [img['src'] for img in soup.find_all('img') if 'src' in img.attrs]
        return similar_images
    else:
        return None

def reverse_image_search(image_url):
    result = google_reverse_image_search(image_url)
    if not result:
        result = yandex_reverse_image_search(image_url)
    return result

def whois_lookup(domain):
    domain_info = whois.whois(domain)
    return domain_info

def check_activity_pattern(profile_url):
    response = requests.get(profile_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Example to count number of posts (assuming posts are identifiable by a class)
    posts = soup.find_all("div", class_="post-class")
    post_count = len(posts)
    
    # Example to analyze posting frequency (timestamps required)
    timestamps = [post.find("time")["datetime"] for post in posts]
    timestamp_diffs = [int(timestamps[i]) - int(timestamps[i-1]) for i in range(1, len(timestamps))]
    
    average_post_frequency = sum(timestamp_diffs) / len(timestamp_diffs) if timestamp_diffs else 0
    
    return {
        "post_count": post_count,
        "average_post_frequency": average_post_frequency
    }

def main(profile_url):
    profile_details = extract_profile_details(profile_url)
    if profile_details:
        print(f"Profile Details: {profile_details}")
        
        image_search_result = reverse_image_search(profile_details["profile_picture"])
        print(f"Reverse Image Search Result: {image_search_result}")
        
        #domain = re.search(r"https?://([^/]+)", profile_url).group(1)
        #domain_info = whois_lookup(domain)
        #print(f"Domain WHOIS Info: {domain_info}")
        
        #activity_pattern = check_activity_pattern(profile_url)
        #print(f"Activity Pattern: {activity_pattern}")
    else:
        print("Unsupported social media platform.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <profile_url>")
        sys.exit(1)
    
    profile_url = sys.argv[1]
    main(profile_url)
