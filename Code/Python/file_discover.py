# Reminder: Look for the original creator of the self.extensions code:


import os

class Discover:

    def __init__(self):
        # Define types:
        self.extensions = [
                          # System Files
                          #'exe', 'dll', 'so', 'deb', 'img', 'msi',
                          # Images
                          'jpg', 'jpeg', 'bmp', 'gif', 'png', 'svg', 'psd', 'raw',
                          # Audio
                          'mp3', 'mp4', 'm4a', 'aac', 'ogg', 'flac', 'wav', 'wma',
                          'aiff', 'ape', 'mid',
                          # Video
                          'avi', 'flv', 'm4v', 'mov', 'mpg', 'mpeg', 'wmv', '3gp', 'mkv',
                          # Office
                          'doc', 'odt', 'docx', 'xls', 'ppt', 'pptx', 'odp', 'ods',
                          'txt', 'rtf', 'pdf', 'epub',
                          # Database, Virtual Images
                          'md', 'yml', 'json', 'csv', 'db', 'sql',
                          'dbf', 'mdb', 'iso', 'ova', 'dat',
                          # Websites
                          'html', 'css', 'xml', 'php', 'php5',
                          'aspx', 'xml', 'js', 'json',
                          # Programming Languages
                          'c', 'cpp', 'rb', 'py', 'r', 'java', 'bat',
                          'vb', 'lua', 'sh', 'temp', 'go', 'pyc', 'ps',
                          # Compacted Files
                          'rar', 'zip', 'tar', '7z', 'bak'
                          ]
        # Save paths:
        self.files_found = []
        
    def run(self, start_path):
        # Discover files:
        for dirpath, dirs, files in os.walk(start_path):
            for f in files:
                absolute_path = os.path.abspath(os.path.join(dirpath, f))
                f_extension = absolute_path.split('.')[-1]
                if f_extension in self.extensions:
                    self.files_found.append(absolute_path)
                    yield absolute_path
            
# If executed, run this verification:
if __name__ == '__main__':
    test_class = Discover()
    test = test_class.run(os.getcwd())
    for i in test:
        print(i)

input()
