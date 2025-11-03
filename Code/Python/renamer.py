import os

def rename_eml_files(path, prefix, start_id):
    """
    Rename all .eml files in a directory with an incremental ID and prefix.

    Example:
        prefix = "sample-"
        start_id = 6070
        Files will be renamed as:
            sample-6071.eml, sample-6072.eml, ...
    """
    if not os.path.isdir(path):
        print(f"Error: '{path}' is not a valid directory.")
        return

    # List all .eml files and sort them for consistent ordering
    eml_files = sorted([f for f in os.listdir(path) if f.lower().endswith('.eml')])
    if not eml_files:
        print("No .eml files found in the directory.")
        return

    current_id = start_id

    for filename in eml_files:
        current_id += 1
        old_path = os.path.join(path, filename)
        new_filename = f"{prefix}{current_id}.eml"
        new_path = os.path.join(path, new_filename)

        # Avoid overwriting existing files
        if os.path.exists(new_path):
            print(f"Skipping '{filename}' -> '{new_filename}' (target exists)")
            continue

        os.rename(old_path, new_path)
        print(f"Renamed: {filename} -> {new_filename}")

    print(f"\nDone. {len(eml_files)} file(s) processed. Last ID used: {current_id}")

# Example usage:
# rename_eml_files("/path/to/folder", "sample-", 6070)
