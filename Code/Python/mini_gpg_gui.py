import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import gnupg
import os

# Initialize GPG
gpg = gnupg.GPG(gnupghome=os.path.expanduser('~/.gnupg'))

# Import private key
def import_private_key(key_data):
    import_result = gpg.import_keys(key_data)
    return import_result

# Sign a file
def sign_file(file_path, key_fingerprint):
    with open(file_path, 'rb') as f:
        signed_data = gpg.sign_file(f, keyid=key_fingerprint)
        if signed_data:
            signed_file_path = f"{file_path}.sig"
            with open(signed_file_path, 'wb') as sf:
                sf.write(signed_data.data)
            return signed_file_path
    return None

# Verify a signed file
def verify_file(signed_file_path):
    with open(signed_file_path, 'rb') as sf:
        verified = gpg.verify_file(sf)
        return verified

class PGPApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PGP Sign & Verify")
        self.root.geometry("400x200")
        
        # Style Configuration
        style = ttk.Style()
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TLabel", background="#f0f0f0", font=('Arial', 12))
        style.configure("TButton", font=('Arial', 12), padding=5)
        
        # Main Frame
        self.main_frame = ttk.Frame(root, padding=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Import Key Frame
        self.import_frame = ttk.Frame(self.main_frame, padding=(10, 5))
        self.import_frame.pack(fill=tk.X)
        
        self.import_label = ttk.Label(self.import_frame, text="Import PGP Private Key:")
        self.import_label.pack(side=tk.LEFT)
        
        self.import_button = ttk.Button(self.import_frame, text="Import", command=self.import_key)
        self.import_button.pack(side=tk.LEFT, padx=5)
        
        # Sign File Frame
        self.sign_frame = ttk.Frame(self.main_frame, padding=(10, 5))
        self.sign_frame.pack(fill=tk.X)
        
        self.sign_label = ttk.Label(self.sign_frame, text="Sign File:")
        self.sign_label.pack(side=tk.LEFT)
        
        self.sign_button = ttk.Button(self.sign_frame, text="Sign", command=self.sign_file)
        self.sign_button.pack(side=tk.LEFT, padx=5)
        
        # Verify File Frame
        self.verify_frame = ttk.Frame(self.main_frame, padding=(10, 5))
        self.verify_frame.pack(fill=tk.X)
        
        self.verify_label = ttk.Label(self.verify_frame, text="Verify Signed File:")
        self.verify_label.pack(side=tk.LEFT)
        
        self.verify_button = ttk.Button(self.verify_frame, text="Verify", command=self.verify_file)
        self.verify_button.pack(side=tk.LEFT, padx=5)
        
        self.key_fingerprint = None

    def import_key(self):
        key_file = filedialog.askopenfilename(title="Select PGP Private Key File")
        if key_file:
            with open(key_file, 'r') as kf:
                key_data = kf.read()
                result = import_private_key(key_data)
                if result:
                    self.key_fingerprint = result.fingerprints[0]
                    messagebox.showinfo("Success", "Private key imported successfully.")
                else:
                    messagebox.showerror("Error", "Failed to import key.")

    def sign_file(self):
        if not self.key_fingerprint:
            messagebox.showwarning("Warning", "Please import a PGP private key first.")
            return
        file_path = filedialog.askopenfilename(title="Select File to Sign")
        if file_path:
            signed_file_path = sign_file(file_path, self.key_fingerprint)
            if signed_file_path:
                messagebox.showinfo("Success", f"File signed successfully.\nSigned file: {signed_file_path}")
            else:
                messagebox.showerror("Error", "Failed to sign file.")

    def verify_file(self):
        signed_file_path = filedialog.askopenfilename(title="Select Signed File to Verify")
        if signed_file_path:
            verified = verify_file(signed_file_path)
            if verified:
                messagebox.showinfo("Success", "Signature verified successfully.")
            else:
                messagebox.showerror("Error", "Failed to verify signature.")

# Create the main window
root = tk.Tk()
app = PGPApp(root)
root.mainloop()
