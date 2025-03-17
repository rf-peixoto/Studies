# pip install PyPDF2 colorama sentence-transformers numpy

import os
import sys
import subprocess
import concurrent.futures
import numpy as np
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer
from colorama import init, Fore, Style

# Initialize colorama for colored terminal output
init(autoreset=True)

# Global settings for chunking and context length
CHUNK_MAX_WORDS = 500
CONTEXT_MAX_WORDS = 2000
TOP_K_CHUNKS = 3

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

def get_file_paths(folder):
    """
    Recursively collects file paths for PDF and text files within the folder.
    """
    file_paths = []
    for root, _, files in os.walk(folder):
        for filename in files:
            if filename.lower().endswith(('.pdf', '.txt')):
                file_paths.append(os.path.join(root, filename))
    return file_paths

def load_documents(folder):
    """
    Scans the specified folder (recursively) for PDF and text files.
    Provides feedback during the ingestion process and reads files concurrently.
    Returns a dictionary mapping filenames to their content.
    """
    print(Fore.CYAN + "Starting file ingestion process...")
    file_paths = get_file_paths(folder)
    docs = {}
    if not file_paths:
        sys.stderr.write(Fore.RED + "No PDF or text files found in the folder.\n")
        return docs

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_path = {executor.submit(read_file, path): path for path in file_paths}
        for future in concurrent.futures.as_completed(future_to_path):
            path = future_to_path[future]
            filename = os.path.basename(path)
            print(Fore.YELLOW + f"Ingesting file: {filename}...")
            try:
                content = future.result()
                if content:
                    docs[filename] = content
            except Exception as exc:
                sys.stderr.write(Fore.RED + f"Error processing {filename}: {exc}\n")
    print(Fore.CYAN + f"Ingestion complete. {len(docs)} files loaded.")
    return docs

def chunk_text(text, max_words=CHUNK_MAX_WORDS):
    """
    Splits text into chunks of up to max_words words.
    """
    words = text.split()
    chunks = []
    for i in range(0, len(words), max_words):
        chunk = " ".join(words[i:i+max_words])
        chunks.append(chunk)
    return chunks

def process_documents_with_embeddings(docs, embed_model):
    """
    Processes each document: splits its content into chunks and computes embeddings.
    Returns a list of dictionaries containing document name, chunk text, and embedding.
    """
    chunks_data = []
    print(Fore.CYAN + "Processing documents into chunks and computing embeddings...")
    for doc_name, content in docs.items():
        chunks = chunk_text(content)
        try:
            # Compute embeddings for all chunks at once for efficiency.
            embeddings = embed_model.encode(chunks, show_progress_bar=False)
        except Exception as e:
            sys.stderr.write(Fore.RED + f"Error computing embeddings for {doc_name}: {e}\n")
            continue
        for chunk, emb in zip(chunks, embeddings):
            chunks_data.append({
                "doc": doc_name,
                "text": chunk,
                "embedding": emb
            })
    print(Fore.CYAN + f"Processed {len(chunks_data)} text chunks from the documents.")
    return chunks_data

def cosine_similarity(vec1, vec2):
    """
    Computes the cosine similarity between two vectors.
    """
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return np.dot(vec1, vec2) / (norm1 * norm2)

def advanced_search_context(chunks_data, query, embed_model, top_k=TOP_K_CHUNKS):
    """
    Uses embeddings to find the most relevant text chunks for the query.
    Returns a concatenated string of the top matching chunks.
    """
    print(Fore.MAGENTA + "Performing advanced context search using embeddings...")
    try:
        query_embedding = embed_model.encode([query], show_progress_bar=False)[0]
    except Exception as e:
        sys.stderr.write(Fore.RED + f"Error computing query embedding: {e}\n")
        return ""
    
    similarities = []
    for chunk in chunks_data:
        sim = cosine_similarity(query_embedding, chunk["embedding"])
        similarities.append(sim)
    
    # Get indices of top_k chunks based on similarity
    if similarities:
        top_indices = np.argsort(similarities)[-top_k:][::-1]
    else:
        top_indices = []

    selected_chunks = []
    for idx in top_indices:
        sim = similarities[idx]
        chunk = chunks_data[idx]
        # Optionally, set a threshold for similarity if desired.
        selected_chunks.append(f"From {chunk['doc']} (similarity: {sim:.2f}):\n{chunk['text']}")
    
    if not selected_chunks:
        print(Fore.MAGENTA + "No relevant context found using embeddings.")
        return ""
    
    context = "\n\n".join(selected_chunks)
    return trim_context(context, CONTEXT_MAX_WORDS)

def trim_context(text, max_words=CONTEXT_MAX_WORDS):
    """
    Trims the context text to a maximum number of words.
    """
    words = text.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + " ..."
    return text

def ask_model(context, question, model="my-model"):
    """
    Constructs a prompt using the provided context and the user's question.
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

    # Initialize the SentenceTransformer model (this may take a moment).
    print(Fore.CYAN + "Loading embedding model...")
    try:
        embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    except Exception as e:
        sys.stderr.write(Fore.RED + f"Error loading embedding model: {e}\n")
        return

    # Process documents into chunks and compute embeddings.
    chunks_data = process_documents_with_embeddings(documents, embed_model)
    if not chunks_data:
        sys.stderr.write(Fore.RED + "No chunks processed. Exiting.\n")
        return

    # Read the user's question.
    question = input(Fore.CYAN + "Enter your question: ").strip()
    if not question:
        sys.stderr.write(Fore.RED + "No question provided.\n")
        return

    # Retrieve advanced context using embeddings.
    context = advanced_search_context(chunks_data, question, embed_model)
    if not context:
        print(Fore.MAGENTA + "No specific context found using embeddings; falling back to all documents.")
        # Fallback: use all document texts concatenated and trimmed.
        all_text = "\n\n".join(documents.values())
        context = trim_context(all_text, CONTEXT_MAX_WORDS)

    print(Fore.GREEN + "Processing your query...")
    answer = ask_model(context, question)
    print(Style.BRIGHT + "\nOutput:")
    print(answer)

if __name__ == "__main__":
    main()
