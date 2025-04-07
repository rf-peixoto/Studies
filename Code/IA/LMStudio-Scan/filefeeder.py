#!/usr/bin/env python3
import argparse
import json
import requests
import time
import logging
import re
import sys

# Configure logging.
logging.basicConfig(
    filename=sys.argv[1],
    filemode='w',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Prompt prefix used for LLM analysis.
PROMPT_PREFIX = (
    "You are a security analysis expert. Analyze the following aggregated findings from "
    "asset discovery, vulnerability scanning, and port scanning. Identify and summarize with details the most "
    "critical vulnerabilities and open ports. Provide possible TTPs and CVEs, if any. "
	"Use formal language without any emojis or slang.\n\n"
)

# Configuration parameters.
BATCH_WORD_LIMIT = 50
LLM_MODEL = "deepseek-r1-distill-qwen-7b"
LLM_TEMPERATURE = 0.4
LLM_MAX_TOKENS = -1
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2
LLM_API_URL = "http://localhost:1234/v1/chat/completions"

def retry_api_call(method, url, headers=None, data=None):
    """Attempt an API call with retries."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, data=data)
            else:
                logging.error("Unsupported HTTP method: %s", method)
                return None

            if response.status_code == 200:
                return response
            else:
                logging.error("Attempt %d: Request to %s returned status %d", attempt + 1, url, response.status_code)
        except Exception as e:
            logging.error("Attempt %d: Exception during request to %s: %s", attempt + 1, url, e)
        time.sleep(RETRY_DELAY)
    return None

def remove_thinking(content):
    """Remove LLM 'thinking' markers from the output."""
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    return cleaned.strip()

def split_into_batches(text, word_limit):
    """Split text into batches with a maximum number of words per batch."""
    words = text.split()
    batches = []
    for i in range(0, len(words), word_limit):
        batch = " ".join(words[i:i + word_limit])
        batches.append(batch)
    return batches

def call_llm_api_batches(content):
    """Send the content to the LLM API in batches and return aggregated responses."""
    batches = split_into_batches(content, BATCH_WORD_LIMIT)
    all_responses = []
    headers = {"Content-Type": "application/json"}

    for index, batch in enumerate(batches):
        logging.info("Processing batch %d of %d", index + 1, len(batches))
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": PROMPT_PREFIX},
                {"role": "user", "content": batch}
            ],
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS,
            "stream": False
        }
        data = json.dumps(payload)
        response = retry_api_call("POST", LLM_API_URL, headers=headers, data=data)
        if response:
            try:
                response_data = response.json()
                llm_output = response_data["choices"][0]["message"]["content"]
                cleaned_output = remove_thinking(llm_output)
                logging.info("Received LLM output for batch %d", index + 1)
                all_responses.append(cleaned_output)
            except Exception as e:
                logging.error("Error parsing LLM response for batch %d: %s", index + 1, e)
        else:
            logging.error("LLM API error for batch %d", index + 1)

    return "\n\n".join(all_responses)

def main():
    parser = argparse.ArgumentParser(
        description="Feed scan results from a text file to an LLM in batches."
    )
    parser.add_argument("results_file", help="Path to the text file containing scan results")
    args = parser.parse_args()

    with open(args.results_file, "r") as f:
        content = f.read()

    llm_response = call_llm_api_batches(content)
    print("LLM Analysis:\n")
    print(llm_response)

if __name__ == "__main__":
    main()
