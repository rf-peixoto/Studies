import os
import shutil
import logging
import yaml
import sys
import argparse
from pathlib import Path

# Import libraries for different file types
import docx
import xlrd
import pptx
import csv
import json

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None  # Optional, for PDF support

# Function to load configuration
def load_config(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config['Keyword_Groups']

# Function to setup logging
def setup_logging(log_file):
    logging.basicConfig(
        filename=log_file,
        filemode='w',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    # Also log to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logging.getLogger().addHandler(console)

# Function to extract text from different file types
def extract_text(file_path):
    ext = file_path.suffix.lower()
    text = ""
    try:
        if ext == '.txt' or ext == '.csv' or ext == '.json' or ext == '.sql':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        elif ext in ['.docx']:
            doc = docx.Document(file_path)
            text = '\n'.join([para.text for para in doc.paragraphs])
        elif ext in ['.xlsx', '.xls']:
            workbook = xlrd.open_workbook(file_path, on_demand=True)
            sheets = workbook.sheet_names()
            for sheet in sheets:
                worksheet = workbook.sheet_by_name(sheet)
                for row in range(worksheet.nrows):
                    text += ' '.join([str(cell) for cell in worksheet.row(row)]) + '\n'
        elif ext in ['.pptx']:
            prs = pptx.Presentation(file_path)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text += shape.text + '\n'
        elif ext == '.pdf' and PyPDF2:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() + '\n'
        else:
            logging.warning(f"Unsupported file type: {file_path}")
    except Exception as e:
        logging.error(f"Error reading {file_path}: {e}")
    return text.lower()

# Function to search keywords in text
def search_keywords(text, keyword_groups):
    found_groups = {}
    for group, keywords in keyword_groups.items():
        for keyword in keywords:
            if keyword.lower() in text:
                if group not in found_groups:
                    found_groups[group] = set()
                found_groups[group].add(keyword)
    return found_groups

# Function to copy file to group folders
def copy_file_to_groups(file_path, groups, output_dir):
    for group in groups:
        group_folder = output_dir / group
        group_folder.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(file_path, group_folder)
            logging.info(f"Copied {file_path} to {group_folder}")
        except Exception as e:
            logging.error(f"Error copying {file_path} to {group_folder}: {e}")

# Main function
def main(data_dir, config_path, output_dir, log_file):
    setup_logging(log_file)
    keyword_groups = load_config(config_path)
    data_path = Path(data_dir)
    if not data_path.exists():
        logging.error(f"Data directory does not exist: {data_dir}")
        sys.exit(1)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    # Supported file extensions
    supported_exts = [
        '.txt', '.csv', '.json', '.sql',
        '.docx', '.xlsx', '.xls', '.pptx',
        '.pdf'
    ]
    for root, dirs, files in os.walk(data_path):
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in supported_exts:
                logging.info(f"Processing file: {file_path}")
                text = extract_text(file_path)
                if text:
                    found = search_keywords(text, keyword_groups)
                    if found:
                        for group, keywords in found.items():
                            for keyword in keywords:
                                logging.info(f"Found keyword '{keyword}' in {file_path}")
                        copy_file_to_groups(file_path, found.keys(), output_path)
            else:
                logging.warning(f"Skipping unsupported file type: {file_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Keyword Search and File Organizer")
    parser.add_argument('--data', required=True, help="Path to the data directory")
    parser.add_argument('--config', required=True, help="Path to the config.yaml file")
    parser.add_argument('--output', default='output', help="Directory to store copied files")
    parser.add_argument('--log', default='script.log', help="Log file path")
    args = parser.parse_args()
    main(args.data, args.config, args.output, args.log)
