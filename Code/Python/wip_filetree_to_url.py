import os

def parse_tree(file_path):
    """
    Parses the tree-like structure file to extract file paths.
    
    :param file_path: Path to the file containing the tree structure.
    :return: A list of file paths.
    """
    file_paths = []
    current_path = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Determine the depth of the current line
            depth = line.count('│   ') + line.count('├── ') + line.count('└── ')
            
            # Trim the tree structure characters to get the name
            name = line.strip('│   ├── └\n')
            
            # Update the current path based on the depth
            current_path = current_path[:depth] + [name]
            
            # Check if the line represents a file (not containing further structure)
            if '├── ' in line or '└── ' in line:
                file_paths.append('/'.join(current_path))
    
    return file_paths

def create_urls(file_paths, base_url):
    """
    Creates URLs for each file path based on the provided base URL.
    
    :param file_paths: A list of file paths.
    :param base_url: The base URL to prepend to each file path.
    :return: A list of complete URLs.
    """
    urls = [os.path.join(base_url, file_path) for file_path in file_paths]
    return urls

def save_urls(urls, output_file):
    """
    Saves the list of URLs to a file.
    
    :param urls: A list of URLs to save.
    :param output_file: Path to the output file.
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        for url in urls:
            f.write(url + '\n')

# Example usage
if __name__ == "__main__":
    file_path = 'tree.txt'  # Change this to your file path
    base_url = 'BASEURL'  # User-defined base URL
    output_file = 'urls.txt'  # Output file path
    
    file_paths = parse_tree(file_path)
    urls = create_urls(file_paths, base_url)
    save_urls(urls, output_file)
    
    print(f'URLs have been saved to {output_file}')
