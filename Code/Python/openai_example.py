# This code was made by GPT itself:
import requests
import json

# Endpoint and headers
endpoint = "https://api.openai.com/v1/engines/davinci/completions"
headers = {
    "Authorization": f"Bearer YOUR_API_KEY",
    "Content-Type": "application/json",
    "Openai-Organization": "YOUR_ORG_ID"  # Optional
}

# Prompt and parameters
data = {
    "prompt": "Write a short story about a robot named Toby:",
    "max_tokens": 150,  # Limits the response length
    "temperature": 0.5,  # Determines randomness; higher values make output more random
    "top_p": 0.9,  # Used for nucleus sampling; smaller values make output more focused
    "n": 3,  # Number of completions to generate for the given prompt
    "stream": False,  # If true, returns the results as a stream
    "stop": ["\n"],  # Stop sequence; in this case, stops generating after a newline
    "presence_penalty": 0.0,  # Penalizes new tokens based on how often they appear
    "frequency_penalty": 0.0,  # Penalizes new tokens based on their frequency
    "best_of": 5  # Generates n*best_of completions and returns the best n
}

response = requests.post(endpoint, headers=headers, data=json.dumps(data))

# Extract the completions
response_data = response.json()
completions = [choice["text"].strip() for choice in response_data["choices"]]

# Print each completion
for i, completion in enumerate(completions):
    print(f"Completion {i + 1}: {completion}\n")
