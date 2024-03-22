def generate_urls_from_text_tree(text_tree, root_url):
    """
    Generates URLs from a textual representation of a file tree.

    :param text_tree: A string containing the textual representation of the file tree.
    :param root_url: The root URL to prepend to each file path.
    :return: A list of complete URLs for each file found.
    """
    urls = []
    lines = text_tree.strip().split('\n')
    path_stack = []

    for line in lines:
        # Determine the depth of the current item (indicated by the number of indents, assuming 4 spaces per indent level)
        depth = (len(line) - len(line.lstrip())) // 4

        # Truncate the stack to the current item's depth
        path_stack = path_stack[:depth]

        # Extract the current item's name (strip leading spaces and any trailing slashes for directories)
        current_item = line.strip().rstrip('/')

        if not current_item:  # Skip empty lines or lines that don't represent files/directories
            continue

        # Add the current item to the path stack
        path_stack.append(current_item)

        # Join the items in the stack to form the path, and generate the URL
        if '.' in current_item:  # Assuming that a dot in the name indicates a file
            file_path = '/'.join(path_stack)
            urls.append(f"{root_url}/{file_path}")

    return urls

# Example usage:
text_tree = """
FILETREE
"""
root_url = 'https://URL.com/download'
urls = generate_urls_from_text_tree(text_tree, root_url)

# Print the URLs
for url in urls:
    print(url)
