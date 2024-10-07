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

try:
    from odf import text, teletype
    from odf.opendocument import load as load_odf
except ImportError:
    load_odf = None  # Optional, for LibreOffice support

# Function to load configuration
def load_config(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config.get('Keyword_Groups', {})

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
    text_content = ""
    try:
        if ext in ['.txt', '.csv', '.json', '.sql']:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text_content = f.read()
        elif ext in ['.docx', '.docm', '.dotx', '.dotm']:
            doc = docx.Document(file_path)
            text_content = '\n'.join([para.text for para in doc.paragraphs])
        elif ext in ['.xlsx', '.xls', '.xlsm', '.xltx', '.xltm']:
            workbook = xlrd.open_workbook(file_path, on_demand=True)
            sheets = workbook.sheet_names()
            for sheet in sheets:
                worksheet = workbook.sheet_by_name(sheet)
                for row in range(worksheet.nrows):
                    text_content += ' '.join([str(cell) for cell in worksheet.row(row)]) + '\n'
        elif ext in ['.pptx', '.pptm', '.potx', '.potm']:
            prs = pptx.Presentation(file_path)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text_content += shape.text + '\n'
        elif ext in ['.odt', '.ods', '.odp']:
            if load_odf:
                odf_doc = load_odf(file_path)
                if ext == '.odt':
                    allparas = odf_doc.getElementsByType(text.P)
                    text_content = '\n'.join([teletype.extractText(p) for p in allparas])
                elif ext == '.ods':
                    sheets = odf_doc.spreadsheet.getElementsByType(text.Table)
                    for sheet in sheets:
                        rows = sheet.getElementsByType(text.TableRow)
                        for row in rows:
                            cells = row.getElementsByType(text.TableCell)
                            row_text = ' '.join([teletype.extractText(cell) for cell in cells])
                            text_content += row_text + '\n'
                elif ext == '.odp':
                    slides = odf_doc.getElementsByType(text.Slide)
                    for slide in slides:
                        allparas = slide.getElementsByType(text.P)
                        text_content += '\n'.join([teletype.extractText(p) for p in allparas]) + '\n'
            else:
                logging.warning(f"LibreOffice support is not available. Install 'odfpy' to handle {ext} files.")
        elif ext == '.pdf' and PyPDF2:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_content += extracted + '\n'
        else:
            logging.warning(f"Unsupported file type: {file_path}")
    except Exception as e:
        logging.error(f"Error reading {file_path}: {e}")
    return text_content.lower()

# Function to search keywords in text
def search_keywords(text_content, keyword_groups):
    found_groups = {}
    for group, keywords in keyword_groups.items():
        for keyword in keywords:
            if keyword.lower() in text_content:
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
    if not keyword_groups:
        logging.error("No keyword groups found in the configuration file.")
        sys.exit(1)
    data_path = Path(data_dir)
    if not data_path.exists():
        logging.error(f"Data directory does not exist: {data_dir}")
        sys.exit(1)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    # Supported file extensions
    supported_exts = [
        '.txt', '.csv', '.json', '.sql',
        '.docx', '.docm', '.dotx', '.dotm',
        '.xlsx', '.xls', '.xlsm', '.xltx', '.xltm',
        '.pptx', '.pptm', '.potx', '.potm',
        '.odt', '.ods', '.odp',
        '.pdf'
    ]
    for root, dirs, files in os.walk(data_path):
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in supported_exts:
                logging.info(f"Processing file: {file_path}")
                text_content = extract_text(file_path)
                if text_content:
                    found = search_keywords(text_content, keyword_groups)
                    if found:
                        for group, keywords in found.items():
                            for keyword in keywords:
                                logging.info(f"Found keyword '{keyword}' in {file_path}")
                        copy_file_to_groups(file_path, found.keys(), output_path)
            else:
                logging.warning(f"Skipping unsupported file type: {file_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Keyword Search and File Organizer")
    parser.add_argument('--data', default='./data', help="Path to the data directory (default: ./data)")
    parser.add_argument('--config', default='./config.yaml', help="Path to the config.yaml file (default: ./config.yaml)")
    parser.add_argument('--output', default='./output', help="Directory to store copied files (default: ./output)")
    parser.add_argument('--log', default='./script.log', help="Log file path (default: ./script.log)")
    args = parser.parse_args()
    main(args.data, args.config, args.output, args.log)
