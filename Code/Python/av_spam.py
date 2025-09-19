import os
import random
import string
import platform
import sys
import argparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

def get_system_specific_directories():
    """Get appropriate directories based on the operating system"""
    system = platform.system().lower()
    base_dirs = []
    
    if system == "windows":
        # For Windows, use user directory and maybe some common locations
        base_dirs.append(os.path.expanduser("~"))
        # Add other common Windows directories (avoiding system-protected areas)
        if os.path.exists("C:\\Temp"):
            base_dirs.append("C:\\Temp")
        if os.path.exists("C:\\Users\\Public"):
            base_dirs.append("C:\\Users\\Public")
    else:  # Linux, macOS, etc.
        # For Unix-like systems, use home directory and /tmp
        base_dirs.append(os.path.expanduser("~"))
        base_dirs.append("/tmp")
        # Add desktop if it exists
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        if os.path.exists(desktop_path):
            base_dirs.append(desktop_path)
    
    return base_dirs

def create_eicar_file(args, root, file_counter):
    """Create a single EICAR file with random name and extension"""
    # EICAR test string
    eicar_string = r"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    
    # Provided extensions list
    extensions = ["txt", "pdf", "odt", "xls", "png", "jpg", "jpeg", "exe", "epub", "mp3", 
                 "gif", "doc", "odp", "ods", "json", "rs", "mp4", "avi", "md", "ogg", "m4a", 
                 "ini", "c", "cpp", "jar", "rb", "java", "pl", "py", "apk", "raw", "eml", 
                 "msg", "tmp", "conf", "config", "yaml", "asm", "h", "r", "m", "luac", "dat", 
                 "sasf", "lua", "src", "perl", "c#", "go", "smali", "csproj", "bash", "sh", 
                 "asic", "run", "vb", "vbe", "kt", "lsp", "vba", "nt", "geojson", "c++", "ps1", 
                 "dev", "mk", "owl", "scala", "mkv", "odl", "rar", "bak", "bkp", "iso", "zip", 
                 "7z", "sbf", "old", "meta", "psw", "bkf", "fbk", "xar", "moz-backup", "orig", 
                 "new", "001", "bps", "img", "deleted", "eg", "ren", "undo", "ofb", "da1", "sql", 
                 "bak1", "gcb", "in1", "och", "exclude", "data", "$$$", "000", "bac", "arc", 
                 "assets", "resource", "resS", "info", "dll", "vdx", "cache", "csv"]
    
    try:
        # Generate random filename
        filename = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        
        # Choose extension: 50% chance from list, 50% chance random 3-character extension
        if random.random() < 0.5:
            extension = random.choice(extensions)
        else:
            # Generate random 3-character extension using letters and digits
            extension = ''.join(random.choices(string.ascii_letters + string.digits, k=3))
        
        # Create full path
        file_path = os.path.join(root, f"{filename}.{extension}")
        
        # Write EICAR string to file
        with open(file_path, 'w') as f:
            f.write(eicar_string)
            
        if args.verbose:
            print(f"Created: {file_path}")
            
        return True
        
    except Exception as e:
        if args.verbose:
            print(f"Error creating file in {root}: {str(e)}")
        return False

def process_directory(args, base_dir, file_counter_lock):
    """Process a single directory and its subdirectories up to the specified depth"""
    files_created = 0
    
    for root, dirs, files in os.walk(base_dir):
        # Calculate current depth
        current_depth = root.count(os.sep) - base_dir.count(os.sep)
        
        # Skip if we've exceeded the depth limit
        if args.depth is not None and current_depth > args.depth:
            del dirs[:]  # Don't recurse into subdirectories
            continue
            
        # Skip system directories on Windows
        if platform.system().lower() == "windows":
            skip_dirs = ["Windows", "Program Files", "Program Files (x86)", "System Volume Information"]
            dirs[:] = [d for d in dirs if d not in skip_dirs]
        
        # Skip hidden directories on Unix-like systems
        else:
            dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        # Create files in this directory
        for _ in range(args.files_per_dir):
            with file_counter_lock:
                if args.max_files is not None and file_counter[0] >= args.max_files:
                    return files_created
                
                success = create_eicar_file(args, root, file_counter)
                if success:
                    file_counter[0] += 1
                    files_created += 1
                    
                    if args.max_files is not None and file_counter[0] >= args.max_files:
                        return files_created
    
    return files_created

def generate_eicar_files(args):
    """Main function to generate EICAR files with multi-threading"""
    # Get system-specific directories or use the provided path
    if args.path:
        base_dirs = [args.path]
    else:
        base_dirs = get_system_specific_directories()
    
    # Create a thread-safe counter and lock
    file_counter = [0]
    file_counter_lock = threading.Lock()
    
    print(f"Starting EICAR test file generation with {args.threads} threads...")
    if args.max_files:
        print(f"Maximum files to create: {args.max_files}")
    if args.depth:
        print(f"Maximum directory depth: {args.depth}")
    
    # Use ThreadPoolExecutor for multi-threading
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        # Submit all directory processing tasks
        future_to_dir = {
            executor.submit(process_directory, args, base_dir, file_counter_lock): base_dir 
            for base_dir in base_dirs
        }
        
        # Process results as they complete
        for future in as_completed(future_to_dir):
            base_dir = future_to_dir[future]
            try:
                files_created = future.result()
                if args.verbose:
                    print(f"Created {files_created} files in {base_dir}")
            except Exception as e:
                print(f"Error processing {base_dir}: {str(e)}")
    
    print(f"Finished generating {file_counter[0]} test files.")

def main():
    parser = argparse.ArgumentParser(description="Generate EICAR test files to test antivirus response")
    parser.add_argument("-t", "--threads", type=int, default=4,
                        help="Number of threads to use (default: 4)")
    parser.add_argument("-m", "--max-files", type=int, default=None,
                        help="Maximum number of files to generate (default: no limit)")
    parser.add_argument("-d", "--depth", type=int, default=None,
                        help="Maximum directory recursion depth (default: no limit)")
    parser.add_argument("-f", "--files-per-dir", type=int, default=1,
                        help="Number of files to create per directory (default: 1)")
    parser.add_argument("-p", "--path", type=str, default=None,
                        help="Base path to use (default: system-specific directories)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose output")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Skip confirmation prompt")
    
    args = parser.parse_args()
    
    system = platform.system()
    print(f"Detected operating system: {system}")
    print("EICAR test file generator")
    print("WARNING: This will trigger antivirus software!")
    
    if not args.yes:
        response = input("Continue? (y/N): ")
        if response.lower() != 'y':
            print("Operation cancelled.")
            sys.exit(0)
    
    generate_eicar_files(args)

if __name__ == "__main__":
    main()
