#pip install python-oqs cryptography tkinter (or tk)

import os
import struct
import tkinter as tk
from tkinter import filedialog, messagebox
import oqs
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend


class KyberFileEncryptor:
    """
    Provides file encryption and decryption with a CRYSTALS-Kyber KEM
    and AES for symmetric encryption.
    """

    def __init__(self, kyber_variant: str = "Kyber512"):
        self.kyber_variant = kyber_variant
        self.public_key = None
        self.private_key = None

    def generate_keys(self):
        """
        Generates a new Kyber public-private key pair.
        """
        kem = oqs.KeyEncapsulation(self.kyber_variant)
        public_key = kem.generate_keypair()
        private_key = kem.export_secret_key()
        self.public_key = public_key
        self.private_key = private_key

    def encrypt_file(self, input_file_path: str, output_file_path: str):
        """
        Encrypts the file located at 'input_file_path' and saves the result
        to 'output_file_path'.
        """
        if self.public_key is None:
            raise ValueError("No public key found. Generate keys first.")

        kem_obj = oqs.KeyEncapsulation(self.kyber_variant)
        kem_ciphertext, shared_secret = kem_obj.encap_secret(self.public_key)
        aes_key = shared_secret[:32]

        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        with open(input_file_path, "rb") as f_in:
            plaintext_data = f_in.read()

        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext_data) + padder.finalize()

        aes_ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        with open(output_file_path, "wb") as f_out:
            f_out.write(struct.pack(">I", len(kem_ciphertext)))
            f_out.write(kem_ciphertext)
            f_out.write(iv)
            f_out.write(aes_ciphertext)

    def decrypt_file(self, input_file_path: str, output_file_path: str):
        """
        Decrypts the file at 'input_file_path' and saves the plaintext
        to 'output_file_path'.
        """
        if self.private_key is None:
            raise ValueError("No private key found. Generate keys first.")

        with open(input_file_path, "rb") as f_in:
            kem_ciphertext_length_data = f_in.read(4)
            kem_ciphertext_length = struct.unpack(">I", kem_ciphertext_length_data)[0]

            kem_ciphertext = f_in.read(kem_ciphertext_length)
            iv = f_in.read(16)
            aes_ciphertext = f_in.read()

        kem_obj = oqs.KeyEncapsulation(self.kyber_variant)
        kem_obj.import_secret_key(self.private_key)
        shared_secret = kem_obj.decap_secret(kem_ciphertext)
        aes_key = shared_secret[:32]

        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_padded_data = decryptor.update(aes_ciphertext) + decryptor.finalize()

        unpadder = padding.PKCS7(128).unpadder()
        decrypted_data = unpadder.update(decrypted_padded_data) + unpadder.finalize()

        with open(output_file_path, "wb") as f_out:
            f_out.write(decrypted_data)


class KyberEncryptorGUI:
    """
    Provides a Tkinter-based GUI to demonstrate CRYSTALS-Kyber file
    encryption and decryption.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("CRYSTALS-Kyber File Encryptor")

        self.encryptor = KyberFileEncryptor()

        # Widgets
        self.key_frame = tk.LabelFrame(root, text="Key Management")
        self.key_frame.pack(padx=10, pady=5, fill="x")

        self.btn_generate_keys = tk.Button(
            self.key_frame, text="Generate New Keys", command=self.generate_keys
        )
        self.btn_generate_keys.pack(side="left", padx=5, pady=5)

        self.encrypt_frame = tk.LabelFrame(root, text="Encrypt a File")
        self.encrypt_frame.pack(padx=10, pady=5, fill="both")

        self.btn_select_file_to_encrypt = tk.Button(
            self.encrypt_frame,
            text="Select File",
            command=self.select_file_to_encrypt
        )
        self.btn_select_file_to_encrypt.pack(side="left", padx=5, pady=5)

        self.lbl_encrypt_file_path = tk.Label(self.encrypt_frame, text="No file selected")
        self.lbl_encrypt_file_path.pack(side="left", padx=5, pady=5)

        self.btn_encrypt_file = tk.Button(
            self.encrypt_frame, text="Encrypt", command=self.encrypt_file
        )
        self.btn_encrypt_file.pack(side="left", padx=5, pady=5)

        self.decrypt_frame = tk.LabelFrame(root, text="Decrypt a File")
        self.decrypt_frame.pack(padx=10, pady=5, fill="both")

        self.btn_select_file_to_decrypt = tk.Button(
            self.decrypt_frame,
            text="Select File",
            command=self.select_file_to_decrypt
        )
        self.btn_select_file_to_decrypt.pack(side="left", padx=5, pady=5)

        self.lbl_decrypt_file_path = tk.Label(self.decrypt_frame, text="No file selected")
        self.lbl_decrypt_file_path.pack(side="left", padx=5, pady=5)

        self.btn_decrypt_file = tk.Button(
            self.decrypt_frame, text="Decrypt", command=self.decrypt_file
        )
        self.btn_decrypt_file.pack(side="left", padx=5, pady=5)

        self.file_to_encrypt = None
        self.file_to_decrypt = None

    def generate_keys(self):
        """
        Generates new Kyber keys.
        """
        try:
            self.encryptor.generate_keys()
            messagebox.showinfo("Key Generation", "Keys generated successfully.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def select_file_to_encrypt(self):
        """
        Allows the user to select the file that will be encrypted.
        """
        file_path = filedialog.askopenfilename()
        if file_path:
            self.file_to_encrypt = file_path
            self.lbl_encrypt_file_path.config(text=file_path)

    def encrypt_file(self):
        """
        Encrypts the selected file and saves the result.
        """
        if not self.file_to_encrypt:
            messagebox.showerror("Error", "No file selected to encrypt.")
            return

        output_path = filedialog.asksaveasfilename(
            defaultextension=".enc",
            filetypes=[("Encrypted Files", "*.enc"), ("All Files", "*.*")]
        )
        if output_path:
            try:
                self.encryptor.encrypt_file(self.file_to_encrypt, output_path)
                messagebox.showinfo("Encryption", "File encrypted successfully.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    def select_file_to_decrypt(self):
        """
        Allows the user to select the file that will be decrypted.
        """
        file_path = filedialog.askopenfilename()
        if file_path:
            self.file_to_decrypt = file_path
            self.lbl_decrypt_file_path.config(text=file_path)

    def decrypt_file(self):
        """
        Decrypts the selected file and saves the plaintext.
        """
        if not self.file_to_decrypt:
            messagebox.showerror("Error", "No file selected to decrypt.")
            return

        output_path = filedialog.asksaveasfilename(
            defaultextension=".dec",
            filetypes=[("Decrypted Files", "*.dec"), ("All Files", "*.*")]
        )
        if output_path:
            try:
                self.encryptor.decrypt_file(self.file_to_decrypt, output_path)
                messagebox.showinfo("Decryption", "File decrypted successfully.")
            except Exception as e:
                messagebox.showerror("Error", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = KyberEncryptorGUI(root)
    root.mainloop()
