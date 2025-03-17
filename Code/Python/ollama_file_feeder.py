import os
import subprocess
import sys
from PyPDF2 import PdfReader
from colorama import init, Fore, Style

# Initialize colorama for colored terminal output
init(autoreset=True)

def read_file(filepath):
    """
    Reads a PDF or text file and returns its content as a string.
    """
    if filepath.lower().endswith('.pdf'):
        try:
            reader = PdfReader(filepath)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text
        except Exception as e:
            sys.stderr.write(Fore.RED + f"Error reading PDF {filepath}: {e}\n")
            return ""
    elif filepath.lower().endswith('.txt'):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            sys.stderr.write(Fore.RED + f"Error reading text file {filepath}: {e}\n")
            return ""
    else:
        return ""

def load_documents(folder):
    """
    Scans the specified folder for PDF and text files.
    Provides feedback during the ingestion process.
    Returns a dictionary mapping filenames to their content.
    """
    print(Fore.CYAN + "Starting file ingestion process...")
    docs = {}
    files_found = 0
    for filename in os.listdir(folder):
        if filename.lower().endswith(('.pdf', '.txt')):
            files_found += 1
            full_path = os.path.join(folder, filename)
            print(Fore.YELLOW + f"Ingesting file: {filename}...")
            content = read_file(full_path)
            if content:
                docs[filename] = content
    print(Fore.CYAN + f"Ingestion complete. {files_found} files processed.")
    return docs

def search_context(docs, query):
    """
    Searches for relevant context by checking if the query is present in each document.
    Provides feedback during the search.
    Returns a concatenated string of all matching document contents.
    """
    print(Fore.MAGENTA + "Searching for relevant context in the documents...")
    relevant_contents = []
    query_lower = query.lower()
    for name, text in docs.items():
        if query_lower in text.lower():
            relevant_contents.append(f"From {name}:\n{text}")
    return "\n\n".join(relevant_contents)

def ask_model(context, question, model="my-model"):
    """
    Constructs a prompt using the context from the documents and the user's question.
    Calls the Ollama CLI and returns only the final answer.
    """
    prompt = f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
    try:
        result = subprocess.run(
            ["ollama", "run", model, "--prompt", prompt],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        sys.stderr.write(Fore.RED + "Error querying the model.\n")
        return "An error occurred while querying the model."

def main():
    # Set the folder containing PDF and text files.
    folder = "path/to/your/folder"  # Change to your folder path
    documents = load_documents(folder)
    if not documents:
        sys.stderr.write(Fore.RED + "No documents loaded. Check folder path and file types.\n")
        return

    # Read the user's question.
    question = input(Fore.CYAN + "Enter your question: ").strip()
    if not question:
        sys.stderr.write(Fore.RED + "No question provided.\n")
        return

    # Retrieve relevant context from the documents.
    context = search_context(documents, question)
    if not context:
        print(Fore.MAGENTA + "No specific context found; using all available documents.")
        context = "\n\n".join(documents.values())

    print(Fore.GREEN + "Processing your query...")
    answer = ask_model(context, question)
    print(Style.BRIGHT + "\nOutput:")
    print(answer)

if __name__ == "__main__":
    main()
