# pip install cabby

from cabby import Client10 as Client
from cabby.entities import ContentBlock
from lxml import etree

class TAXIIClient:
    def __init__(self, server_url, username, password):
        self.server_url = server_url
        self.username = username
        self.password = password
        self.client = Client(self.server_url)
        self.client.set_auth(username=self.username, password=self.password)
    
    def send_file(self, file_path, collection_name, content_binding='urn:stix.mitre.org:xml:1.2'):
        with open(file_path, 'rb') as f:
            file_content = f.read()
        content_block = ContentBlock(
            content_binding=content_binding,
            content=file_content,
            timestamp_label=etree.Element("timestamp_label")
        )
        response = self.client.push(
            content_blocks=[content_block],
            collection_name=collection_name
        )
        print(f'Response status: {response.status_message}')
    
    def search_content(self, collection_name, start_time=None, end_time=None):
        response = self.client.poll(
            collection_name=collection_name,
            begin_date=start_time,
            end_date=end_time
        )
        for content_block in response.content_blocks:
            print(f'Content Block ID: {content_block.id}')
            print(f'Content: {content_block.content}')
    
    def receive_continuous_feed(self, collection_name, interval=60):
        import time
        while True:
            self.search_content(collection_name)
            time.sleep(interval)

# Example usage:
taxii_client = TAXIIClient(
    server_url='http://example.com/taxii-discovery-service',
    username='your_username',
    password='your_password'
)

# Send a file
taxii_client.send_file(
    file_path='your_file.txt',
    collection_name='example_collection'
)

# Search for content in a collection
taxii_client.search_content(
    collection_name='example_collection',
    start_time='2023-01-01T00:00:00Z',
    end_time='2023-12-31T23:59:59Z'
)

# Receive continuous data feed
taxii_client.receive_continuous_feed(
    collection_name='example_collection',
    interval=3600  # Poll every hour
)
