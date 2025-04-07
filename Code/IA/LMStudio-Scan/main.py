#!/usr/bin/env python3
import argparse
import subprocess
import json
import requests
import logging
import re
import os
import time
from colorama import init, Fore

# Initialize colorama for colored terminal output.
init(autoreset=True)

# Configure logging: log to file "scan_log.txt" at DEBUG level.
logging.basicConfig(
    filename='scan_log.txt',
    filemode='w',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def load_config():
    """Load configuration from config.json if available; otherwise, use defaults."""
    default_config = {
        "assetfinder_cmd": "assetfinder",
        "nuclei_cmd": "nuclei",
        "nmap_cmd": "nmap",
        "shodan_endpoint": "https://internetdb.shodan.io",
        "batch_word_limit": 50,
        "llm_model": "deepseek-r1-distill-qwen-7b",
        "llm_temperature": 0.7,
        "llm_max_tokens": -1,
        "retry_attempts": 3,
        "retry_delay": 2
    }
    if os.path.exists("config.json"):
        try:
            with open("config.json", "r") as f:
                user_config = json.load(f)
                default_config.update(user_config)
                logging.info("Loaded configuration from config.json")
        except Exception as e:
            logging.error("Error loading config.json: %s", e)
    else:
        logging.info("config.json not found; using default configuration")
    return default_config

# Load global configuration.
config = load_config()
BATCH_WORD_LIMIT = config["batch_word_limit"]

def retry_api_call(method, url, headers=None, data=None):
    """Attempt an API call with retries based on configuration."""
    attempts = config["retry_attempts"]
    delay = config["retry_delay"]
    for i in range(attempts):
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
                logging.error("Attempt %d: Request to %s returned status %d", i+1, url, response.status_code)
        except Exception as e:
            logging.error("Attempt %d: Exception during request to %s: %s", i+1, url, e)
        time.sleep(delay)
    return None

def extract_ip_addresses(text):
    """
    Extract unique IPv4 addresses from the given text.
    This regex finds any sequence of four dot-separated numbers.
    """
    ips = re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text)
    return list(set(ips))

def remove_thinking(content):
    """
    Remove the LLM's thinking content (text between <think> and </think>).
    """
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    return cleaned.strip()

def run_command(command):
    logging.info("Executing command: %s", ' '.join(command))
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        logging.info("Command succeeded: %s", ' '.join(command))
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error("Error running command: %s", ' '.join(command))
        logging.error("Error details: %s", e)
        print(Fore.RED + f"Error running command: {' '.join(command)}")
        return ""

def run_assetfinder(domain):
    print(Fore.CYAN + f"[+] Running assetfinder on: {domain}")
    logging.info("Running assetfinder on: %s", domain)
    output = run_command([config["assetfinder_cmd"], "--subs-only", domain])
    subdomains = list(set(filter(None, output.splitlines())))
    logging.info("Assetfinder found %d subdomains for %s", len(subdomains), domain)
    print(Fore.GREEN + f"[+] Found {len(subdomains)} subdomain(s).")
    return subdomains

def run_nuclei(subdomain):
    print(Fore.CYAN + f"[+] Running nuclei on: {subdomain}")
    logging.info("Running nuclei on: %s", subdomain)
    output = run_command([config["nuclei_cmd"], "-u", subdomain, "-silent"])
    logging.debug("Nuclei output for %s: %s", subdomain, output)
    return output

def run_nmap(subdomain):
    print(Fore.CYAN + f"[+] Running nmap on: {subdomain}")
    logging.info("Running nmap on: %s", subdomain)
    output = run_command([config["nmap_cmd"], "-Pn", subdomain])
    logging.debug("Nmap output for %s: %s", subdomain, output)
    return output

def filter_relevant(text):
    logging.info("Filtering relevant information from output.")
    keywords = ["vulnerability", "critical", "open", "port", "http"]
    filtered_lines = [line for line in text.splitlines() if any(keyword.lower() in line.lower() for keyword in keywords)]
    filtered_text = "\n".join(filtered_lines)
    logging.debug("Filtered output: %s", filtered_text)
    return filtered_text

def split_into_batches(text, word_limit):
    logging.info("Splitting text into batches with word limit: %d", word_limit)
    words = text.split()
    batches = []
    for i in range(0, len(words), word_limit):
        batch = " ".join(words[i:i+word_limit])
        batches.append(batch)
    logging.info("Created %d batches.", len(batches))
    return batches

def get_shodan_info(ip_address):
    """Query the Shodan InternetDB endpoint for the given IP address."""
    url = f"{config['shodan_endpoint']}/{ip_address}"
    logging.info("Querying Shodan for IP: %s", ip_address)
    response = retry_api_call("GET", url)
    if response:
        try:
            data = response.json()
            return json.dumps(data, indent=2)
        except Exception as e:
            logging.error("Error parsing Shodan response for IP %s: %s", ip_address, e)
            return "Error parsing Shodan data."
    else:
        return "No Shodan data available."

def call_llm_api_batches(content):
    print(Fore.CYAN + "[+] Sending findings to LLM for analysis in batches...")
    logging.info("Sending findings to LLM in batches.")
    batches = split_into_batches(content, BATCH_WORD_LIMIT)
    all_responses = []
    url = "http://localhost:1234/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    prompt_prefix = (
        "You are a security analysis expert. Analyze the following aggregated findings from "
        "asset discovery, vulnerability scanning, and port scanning. Identify and summarize the most "
        "critical vulnerabilities and open ports, and provide recommendations. Use formal language without any emojis or slang.\n\n"
    )
    
    for index, batch in enumerate(batches):
        print(Fore.CYAN + f"[+] Processing batch {index+1} of {len(batches)}...")
        logging.info("Processing batch %d of %d.", index+1, len(batches))
        payload = {
            "model": config["llm_model"],
            "messages": [
                { "role": "system", "content": prompt_prefix },
                { "role": "user", "content": batch }
            ],
            "temperature": config["llm_temperature"],
            "max_tokens": config["llm_max_tokens"],
            "stream": False
        }
        data = json.dumps(payload)
        response = retry_api_call("POST", url, headers=headers, data=data)
        if response:
            try:
                data = response.json()
                llm_output = data["choices"][0]["message"]["content"]
                cleaned_output = remove_thinking(llm_output)
                logging.info("Received LLM output for batch %d", index+1)
                print(Fore.GREEN + f"[+] Batch {index+1} analysis received.")
                all_responses.append(cleaned_output)
            except Exception as e:
                logging.error("Error parsing LLM response for batch %d: %s", index+1, e)
                print(Fore.RED + f"Error parsing LLM response for batch {index+1}.")
        else:
            print(Fore.RED + f"LLM API error for batch {index+1}.")
    return "\n\n".join(all_responses)

def main():
    parser = argparse.ArgumentParser(
        description="Security assessment tool with enhanced configurability and Shodan integration."
    )
    parser.add_argument("domain", help="Target domain for security assessment")
    args = parser.parse_args()
    domain = args.domain

    logging.info("Starting security assessment for domain: %s", domain)
    final_report = f"Security Assessment Report for {domain}\n" + "=" * 50 + "\n\n"
    aggregated_findings = ""

    subdomains = run_assetfinder(domain)
    if not subdomains:
        logging.error("No subdomains found for domain: %s. Exiting.", domain)
        print(Fore.RED + "No subdomains found. Exiting.")
        return

    if domain not in subdomains:
        subdomains.insert(0, domain)
        logging.info("Main domain added to subdomains list.")

    for sub in subdomains:
        final_report += f"Subdomain: {sub}\n" + "-" * 30 + "\n"
        nuclei_output = run_nuclei(sub)
        nmap_output = run_nmap(sub)
        filtered_nuclei = filter_relevant(nuclei_output)
        filtered_nmap = filter_relevant(nmap_output)
        final_report += "Nuclei Findings:\n" + (filtered_nuclei if filtered_nuclei else "No relevant vulnerabilities found.") + "\n\n"
        final_report += "Nmap Findings:\n" + (filtered_nmap if filtered_nmap else "No relevant ports found.") + "\n\n"
        
        # Extract IP addresses from Nmap output and get Shodan info.
        ips = extract_ip_addresses(nmap_output)
        shodan_results = ""
        for ip in ips:
            info = get_shodan_info(ip)
            shodan_results += f"IP: {ip}\n{info}\n\n"
        if shodan_results:
            final_report += "Shodan Info:\n" + shodan_results + "\n"
        
        aggregated_findings += f"Subdomain: {sub}\n"
        aggregated_findings += "Nuclei:\n" + (filtered_nuclei if filtered_nuclei else "None") + "\n"
        aggregated_findings += "Nmap:\n" + (filtered_nmap if filtered_nmap else "None") + "\n\n"

    llm_response = call_llm_api_batches(aggregated_findings)
    final_report += "=" * 50 + "\nLLM Analysis:\n" + llm_response + "\n"

    print(Fore.YELLOW + "\nFinal Report:\n")
    print(final_report)
    logging.info("Final report generated and printed.")

if __name__ == "__main__":
    main()
