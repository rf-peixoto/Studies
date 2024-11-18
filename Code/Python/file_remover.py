import os
import sys

def delete_files_without_keyword(folder_path: str, keyword: str) -> None:
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return
    
    keyword_lower = keyword.lower()
    deleted_files = []
    
    for file_name in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file_name)
        if os.path.isfile(file_path) and keyword_lower not in file_name.lower():
            try:
                os.remove(file_path)
                deleted_files.append(file_name)
            except Exception as e:
                print(f"Error deleting file '{file_name}': {e}")
    
    if deleted_files:
        print(f"Deleted files: {', '.join(deleted_files)}")
    else:
        print("No files were deleted.")

if __name__ == "__main__":
    # Ensure the script is used properly
    if len(sys.argv) != 3:
        print("Usage: python script.py <folder_path> <keyword>")
        sys.exit(1)

    folder_path = sys.argv[1]
    keyword = sys.argv[2]

    delete_files_without_keyword(folder_path, keyword)
