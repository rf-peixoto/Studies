import os
import subprocess
import sys

# If processing PDFs, install PyPDF2 via pip:
# pip install PyPDF2
from PyPDF2 import PdfReader

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
            sys.stderr.write(f"Error reading PDF {filepath}: {e}\n")
            return ""
    elif filepath.lower().endswith('.txt'):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            sys.stderr.write(f"Error reading text file {filepath}: {e}\n")
            return ""
    else:
        return ""

def load_documents(folder):
    """
    Scans the specified folder and loads the content of all PDF and text files.
    Returns a dictionary mapping filenames to their content.
    """
    docs = {}
    for filename in os.listdir(folder):
        if filename.lower().endswith(('.pdf', '.txt')):
            full_path = os.path.join(folder, filename)
            content = read_file(full_path)
            if content:
                docs[filename] = content
    return docs

def search_context(docs, query):
    """
    Performs a simple search: returns a list of document contents
    where the query text is found.
    
    Note: This is a basic implementation. For better performance with many files,
    consider using a vector store or a more advanced search mechanism.
    """
    relevant_contents = []
    query_lower = query.lower()
    for name, text in docs.items():
        if query_lower in text.lower():
            # Optionally, include a header for each document's content
            relevant_contents.append(f"From {name}:\n{text}")
    return "\n\n".join(relevant_contents)

def ask_model(context, question, model="my-model"):
    """
    Constructs the prompt using the context from the documents and the user's question,
    then calls the Ollama command-line interface to get a response.
    
    Adjust the model parameter and CLI options as necessary.
    """
    # Construct prompt: include the context and the question.
    prompt = f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
    
    # Call the Ollama CLI (assumes 'ollama' is installed and in the PATH)
    try:
        result = subprocess.run(
            ["ollama", "run", model, "--prompt", prompt],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"Ollama error: {e.stderr}\n")
        return "An error occurred while querying the model."

def main():
    # Set the folder containing PDF and text files.
    folder = "path/to/your/folder"  # Change to your folder path
    
    # Load documents from the folder.
    documents = load_documents(folder)
    if not documents:
        sys.stderr.write("No documents were loaded. Verify the folder path and file types.\n")
        return

    # Read the user's question.
    question = input("Enter your question: ").strip()
    if not question:
        sys.stderr.write("No question provided.\n")
        return

    # Retrieve relevant context from the documents.
    context = search_context(documents, question)
    if not context:
        sys.stderr.write("No relevant context found in the documents. Using all documents as context.\n")
        context = "\n\n".join(documents.values())

    # Query the model using Ollama.
    answer = ask_model(context, question)
    print("\nResponse from model:")
    print(answer)

if __name__ == "__main__":
    main()
