import tkinter as tk
from tkinter import filedialog, scrolledtext, messagebox
import gnupg
import re

def verify_content(content):
    # Initialize the GPG interface
    gpg = gnupg.GPG()
    
    # Verify the content
    verified = gpg.verify(content)
    
    # Prepare to extract signatures
    results = []
    if verified:
        for sig in verified.signatures:
            result = f"Signature Fingerprint: {sig.fingerprint}, Date/Time: {sig.timestamp}"
            results.append(result)
    return results

def load_file():
    # Open file dialog to select a file
    file_path = filedialog.askopenfilename()
    if file_path:
        with open(file_path, 'r') as file:
            content_text.delete('1.0', tk.END)
            content_text.insert('1.0', file.read())

def analyze_signatures():
    content = content_text.get('1.0', tk.END)
    if '-----BEGIN PGP SIGNED MESSAGE-----' in content:
        results = verify_content(content)
        signature_text.delete('1.0', tk.END)
        if results:
            signature_text.insert('1.0', '\n'.join(results))
        else:
            signature_text.insert('1.0', "No signatures found or failed to verify.")
    else:
        messagebox.showinfo("Error", "No GPG signed message found in the content.")

# Create the main window
root = tk.Tk()
root.title("GPG Signature Verifier")

# Create a text field to paste or display file content
content_text = scrolledtext.ScrolledText(root, height=15, width=70)
content_text.pack(pady=10)

# Create a text field to display signatures
signature_text = scrolledtext.ScrolledText(root, height=10, width=70)
signature_text.pack(pady=10)

# Create buttons
load_button = tk.Button(root, text="Load File", command=load_file)
load_button.pack(side=tk.LEFT, padx=10)

verify_button = tk.Button(root, text="Verify Signatures", command=analyze_signatures)
verify_button.pack(side=tk.RIGHT, padx=10)

# Start the GUI event loop
root.mainloop()
