import json
import sys
import logging

# Valid format: 0000000000000000|DD|YYYY|000

def read_last_id(file_path):
    try:
        with open(file_path, 'r') as file:
            return int(file.read().strip())
    except FileNotFoundError:
        return 0  # Start from 0 since we add 1 when parsing starts
    except ValueError:
        logging.warning("Last ID file is corrupted. Starting from ID 1.")
        return 0

def save_last_id(file_path, last_id):
    try:
        with open(file_path, 'w') as file:
            file.write(str(last_id))
    except IOError as e:
        logging.error(f"Failed to save last ID: {e}")

def parse_file_to_json(file_path, output_file_path, last_id_file):
    last_id = read_last_id(last_id_file)

    json_data = []
    try:
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if len(line) != 28:
                    logging.warning(f"Skipping invalid line {last_id+1}: Incorrect length")
                    continue

                parts = line.split('|')
                if len(parts) == 4:
                    last_id += 1
                    json_line = {
                        "id": last_id,
                        "bin": parts[0][:6],
                        "number": parts[0],
                        "expires": parts[1] + parts[2][-2:],
                        "cvv": parts[3]
                    }
                    json_data.append(json_line)
                else:
                    logging.warning(f"Skipping invalid line {last_id+1}: Incorrect format")

        with open(output_file_path, 'w') as outfile:
            json.dump(json_data, outfile, indent=4)

        save_last_id(last_id_file, last_id)

    except IOError as e:
        logging.error(f"File operation failed: {e}")
        raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        logging.error("Usage: python script.py <input_file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    output_file_path = "output.json"
    last_id_file = "last_id.txt"
    
    try:
        parse_file_to_json(file_path, output_file_path, last_id_file)
        logging.info(f"Data parsed and saved to {output_file_path}")
    except Exception as e:
        logging.error(f"An error occurred: {e}")

