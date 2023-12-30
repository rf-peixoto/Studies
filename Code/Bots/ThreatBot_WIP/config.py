import json

class Config:
    def __init__(self, filename):
        with open(filename, 'r') as file:
            self.config = json.load(file)
        
    def __getattr__(self, name):
        return self.config.get(name, None)
