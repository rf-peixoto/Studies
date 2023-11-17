import json, sys

# Valid format: 0000000000000000|DD|YYYY|000

def parse_file_to_json(file_path, output_file_path):

    json_data = []
    with open(file_path, 'r') as file:
        for line_number, line in enumerate(file, start=1):
            parts = line.strip().split('|')
            if len(parts) == 4:
                json_line = {
                    "id": line_number,
                    "bin": parts[0][:6],
                    "number": parts[0],
                    "expires": parts[1] + parts[2][-2:],
                    "cvv": parts[3]
                }
                json_data.append(json_line)

    with open(output_file_path, 'w') as outfile:
        json.dump(json_data, outfile, indent=4)

# Example usage
file_path = sys.argv[1]
output_file_path = "output.json"
parse_file_to_json(file_path, output_file_path)
print(f"Data parsed and saved to {output_file_path}")
