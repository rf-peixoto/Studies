# To allow in-app passphrase prompts (recommended), enable loopback in your GPG agent:
# Create or edit ~/.gnupg/gpg-agent.conf and add the line (remove the #):
# allow-loopback-pinentry
# default-cache-ttl 0
# max-cache-ttl 0
# Then run:
# gpgconf --kill gpg-agent


#!/usr/bin/env python3
import os
import sys
import shlex
import tempfile
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

GPG = "gpg"  # Path to gpg binary

# -------------------------- Utilities --------------------------

def run(cmd, input_bytes=None):
    """
    Run a command. Return (rc, stdout, stderr).
    """
    try:
        p = subprocess.run(
            cmd,
            input=input_bytes,
            capture_output=True,
            check=False
        )
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"
    except Exception as e:
        return 1, "", f"{type(e).__name__}: {e}"

def gpg_ok():
    rc, out, err = run([GPG, "--version"])
    return rc == 0, (out + "\n" + err).strip()

def agent_allows_loopback():
    """
    Detect if 'allow-loopback-pinentry' is present in gpg-agent.conf.
    If not, ask the user if they want to add recommended lines.
    """
    agent_conf = Path.home() / ".gnupg" / "gpg-agent.conf"

    try:
        if agent_conf.exists():
            txt = agent_conf.read_text(encoding="utf-8", errors="ignore")
            if "allow-loopback-pinentry" in txt:
                return True
        else:
            txt = ""
    except Exception:
        txt = ""

    # Not found -> ask user
    if messagebox.askyesno(
        "Enable Loopback Pinentry?",
        ("Your gpg-agent is not configured to allow loopback pinentry.\n\n"
         "This is needed for the GUI to prompt passphrases inside the app.\n\n"
         "Do you want to add the following lines to ~/.gnupg/gpg-agent.conf?\n\n"
         "  allow-loopback-pinentry\n"
         "  default-cache-ttl 0\n"
         "  max-cache-ttl 0\n\n"
         "(Afterwards, you must run: gpgconf --kill gpg-agent)")
    ):
        try:
            agent_conf.parent.mkdir(mode=0o700, exist_ok=True)
            with agent_conf.open("a", encoding="utf-8") as f:
                if not txt.endswith("\n"):
                    f.write("\n")
                f.write("allow-loopback-pinentry\n")
                f.write("default-cache-ttl 0\n")
                f.write("max-cache-ttl 0\n")
            messagebox.showinfo(
                "Config Updated",
                f"Lines added to {agent_conf}.\n\n"
                "Now run:\n\n  gpgconf --kill gpg-agent\n\n"
                "to reload the configuration."
            )
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update {agent_conf}:\n{e}")
            return False

    return False


def info(msg):
    messagebox.showinfo("Info", msg)

def warn(msg):
    messagebox.showwarning("Warning", msg)

def errbox(msg):
    messagebox.showerror("Error", msg)

def save_text_to_file(text, title="Save As", defaultextension=".txt"):
    path = filedialog.asksaveasfilename(title=title, defaultextension=defaultextension)
    if not path:
        return None
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path
    except Exception as e:
        errbox(f"Failed to save file:\n{e}")
        return None

def choose_file(title="Select File"):
    return filedialog.askopenfilename(title=title)

def choose_output_file(title="Save As", default_ext=""):
    return filedialog.asksaveasfilename(title=title, defaultextension=default_ext)

def yesno(question, title="Confirm"):
    return messagebox.askyesno(title, question)

# -------------------------- GPG wrappers --------------------------

def list_keys(secret=False):
    """
    Returns a list of dicts with keys:
    {'fpr': 'FINGERPRINT', 'uid': 'Name (Comment) <email>', 'keyid': 'SHORTID'}
    """
    args = [GPG, "--with-colons", "--fingerprint"]
    args.append("--list-secret-keys" if secret else "--list-keys")
    rc, out, err = run(args)
    if rc != 0:
        raise RuntimeError(err or out)

    keys = []
    current = None
    for line in out.splitlines():
        parts = line.split(":")
        if not parts:
            continue
        t = parts[0]
        if t in ("pub", "sec"):
            if current:
                keys.append(current)
            current = {"uids": [], "fpr": None, "keyid": parts[4] or ""}
        elif t == "uid" and current is not None:
            current["uids"].append(parts[9] or "")
        elif t == "fpr" and current is not None:
            current["fpr"] = parts[9] or ""
    if current:
        keys.append(current)

    # Flatten to best UID + fpr/keyid
    flat = []
    for k in keys:
        uid = k["uids"][0] if k["uids"] else "(no UID)"
        flat.append({"fpr": k["fpr"] or "", "uid": uid, "keyid": k["keyid"]})
    return flat

def import_key_from_file(path):
    rc, out, err = run([GPG, "--batch", "--yes", "--import", path])
    return rc == 0, (out + err)

def export_public_key_ascii(fpr, dest_path):
    rc, out, err = run([GPG, "--armor", "--export", fpr])
    if rc != 0:
        return False, err or out
    try:
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(out)
        return True, f"Public key saved to: {dest_path}"
    except Exception as e:
        return False, str(e)

def export_private_key_ascii(fpr, dest_path, passphrase=None, loopback=True):
    cmd = [GPG, "--armor", "--batch", "--yes", "--export-secret-keys", fpr]
    if loopback:
        cmd += ["--pinentry-mode", "loopback"]
    if passphrase:
        cmd += ["--passphrase", passphrase]
    rc, out, err = run(cmd)
    if rc != 0:
        return False, err or out
    try:
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(out)
        return True, f"Private key saved to: {dest_path}"
    except Exception as e:
        return False, str(e)

def generate_revocation_cert(fpr, dest_path, passphrase=None, loopback=True):
    cmd = [GPG, "--batch", "--yes", "--output", dest_path, "--gen-revoke", fpr]
    if loopback:
        cmd += ["--pinentry-mode", "loopback"]
    if passphrase:
        cmd += ["--passphrase", passphrase]
    rc, out, err = run(cmd, input_bytes=b"y\ny\n")  # auto-confirm reasons interactively
    if rc != 0:
        return False, err or out
    return True, f"Revocation certificate saved to: {dest_path}"

def quick_generate_key(uid, algo="rsa", bits=4096, expire="0", passphrase=None, loopback=True):
    """
    Create a primary key with default capabilities.
    """
    # gpg --batch --pinentry-mode loopback --passphrase ... --quick-generate-key "Name <mail>" rsa4096 default 0
    algo_bits = f"{algo}{bits}"
    cmd = [GPG, "--batch", "--yes", "--quick-generate-key", uid, algo_bits, "default", expire]
    if loopback:
        cmd += ["--pinentry-mode", "loopback"]
    if passphrase:
        cmd += ["--passphrase", passphrase]
    rc, out, err = run(cmd)
    if rc != 0:
        return False, err or out
    return True, out.strip() or "Key created."

def encrypt_file(src_path, recipient_fpr, dest_path, ascii_armor=False):
    cmd = [GPG, "--batch", "--yes", "-o", dest_path, "-r", recipient_fpr, "--encrypt"]
    if ascii_armor:
        cmd.insert(1, "--armor")
    cmd.append(src_path)
    rc, out, err = run(cmd)
    if rc != 0:
        return False, err or out
    return True, f"Encrypted file saved to: {dest_path}"

def decrypt_file(src_path, dest_path, passphrase=None, loopback=True):
    cmd = [GPG, "--batch", "--yes", "-o", dest_path, "--decrypt", src_path]
    if loopback:
        cmd.insert(1, "--pinentry-mode")
        cmd.insert(2, "loopback")
    if passphrase:
        cmd.insert(1, "--passphrase")
        cmd.insert(2, passphrase)
    rc, out, err = run(cmd)
    if rc != 0:
        return False, err or out
    return True, f"Decrypted file saved to: {dest_path}"

def detach_sign_file(src_path, signer_fpr, dest_sig_path, passphrase=None, loopback=True):
    cmd = [GPG, "--batch", "--yes", "-u", signer_fpr, "-o", dest_sig_path, "--detach-sign", src_path]
    if loopback:
        cmd.insert(1, "--pinentry-mode")
        cmd.insert(2, "loopback")
    if passphrase:
        cmd.insert(1, "--passphrase")
        cmd.insert(2, passphrase)
    rc, out, err = run(cmd)
    if rc != 0:
        return False, err or out
    return True, f"Signature saved to: {dest_sig_path}"

def verify_signature(file_path, sig_path):
    cmd = [GPG, "--batch", "--status-fd", "1", "--verify", sig_path, file_path]
    rc, out, err = run(cmd)
    # Interpret a bit; rc=0 means verification succeeded.
    if rc == 0:
        return True, "Signature verification SUCCESS.\n" + (out or err)
    else:
        return False, "Signature verification FAILED.\n" + (out + err)

def clearsign_text(text, signer_fpr, passphrase=None, loopback=True):
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmpin:
        tmpin.write(text)
        tmpin_path = tmpin.name
    tmpout_path = tmpin_path + ".asc"
    try:
        cmd = [GPG, "--batch", "--yes", "-u", signer_fpr, "--clearsign", "-o", tmpout_path, tmpin_path]
        if loopback:
            cmd.insert(1, "--pinentry-mode")
            cmd.insert(2, "loopback")
        if passphrase:
            cmd.insert(1, "--passphrase")
            cmd.insert(2, passphrase)
        rc, out, err = run(cmd)
        if rc != 0:
            return False, err or out
        signed = Path(tmpout_path).read_text(encoding="utf-8", errors="replace")
        return True, signed
    finally:
        try:
            os.remove(tmpin_path)
        except Exception:
            pass
        try:
            os.remove(tmpout_path)
        except Exception:
            pass

# -------------------------- GUI --------------------------

class GPGGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GPG Helper")
        self.geometry("900x650")
        self.minsize(820, 560)

        ok, ver = gpg_ok()
        if not ok:
            errbox(f"gpg not found or not working.\n\n{ver}")
            self.destroy()
            return

        self.loopback_ok = agent_allows_loopback()

        self._build_header(ver)
        self._build_tabs()
        self.refresh_all_key_lists()

    def _build_header(self, ver):
        frame = ttk.Frame(self, padding=8)
        frame.pack(fill="x")

        ttk.Label(frame, text="GPG binary:", font=("TkDefaultFont", 9, "bold")).pack(side="left")
        ttk.Label(frame, text=GPG).pack(side="left", padx=(6, 20))

        ttk.Label(frame, text="Version:", font=("TkDefaultFont", 9, "bold")).pack(side="left")
        ttk.Label(frame, text=ver.splitlines()[0].strip()).pack(side="left", padx=(6, 20))

        if not self.loopback_ok:
            msg = ("Passphrase loopback is not enabled. Some operations may pop up an external pinentry "
                   "or fail.\nEnable by adding 'allow-loopback-pinentry' to ~/.gnupg/gpg-agent.conf "
                   "and then run: gpgconf --kill gpg-agent")
            banner = tk.Label(frame, text=msg, fg="black", bg="#ffdd88", justify="left")
            banner.pack(fill="x", padx=10, pady=6)

    def _build_tabs(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        # Keys tab
        self.keys_tab = ttk.Frame(nb, padding=8)
        nb.add(self.keys_tab, text="Keys")

        # Encrypt/Decrypt tab
        self.enc_tab = ttk.Frame(nb, padding=8)
        nb.add(self.enc_tab, text="Encrypt / Decrypt")

        # Sign/Verify tab
        self.sign_tab = ttk.Frame(nb, padding=8)
        nb.add(self.sign_tab, text="Sign / Verify")

        # Clear-Sign tab
        self.clear_tab = ttk.Frame(nb, padding=8)
        nb.add(self.clear_tab, text="Clear-Sign Text")

        self._build_keys_tab()
        self._build_encrypt_tab()
        self._build_sign_tab()
        self._build_clear_tab()

    # ---------------- Keys tab ----------------
    def _build_keys_tab(self):
        root = self.keys_tab

        # Lists
        lists = ttk.Frame(root)
        lists.pack(fill="both", expand=True)

        pub_frame = ttk.LabelFrame(lists, text="Public Keys (Recipients)")
        pub_frame.pack(side="left", fill="both", expand=True, padx=(0,6), pady=4)

        sec_frame = ttk.LabelFrame(lists, text="Private Keys (You / Signers)")
        sec_frame.pack(side="right", fill="both", expand=True, padx=(6,0), pady=4)

        self.pub_list = tk.Listbox(pub_frame, activestyle="dotbox")
        self.pub_list.pack(fill="both", expand=True, padx=6, pady=6)
        self.sec_list = tk.Listbox(sec_frame, activestyle="dotbox")
        self.sec_list.pack(fill="both", expand=True, padx=6, pady=6)

        # Buttons
        btns = ttk.Frame(root)
        btns.pack(fill="x", pady=(6,0))

        ttk.Button(btns, text="Refresh", command=self.refresh_all_key_lists).pack(side="left")

        ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=6)

        ttk.Button(btns, text="Create Key", command=self.dialog_create_key).pack(side="left")

        ttk.Button(btns, text="Import Key...", command=self.action_import_key).pack(side="left", padx=(6,0))

        ttk.Separator(btns, orient="vertical").pack(side="left", fill="y", padx=6)

        ttk.Button(btns, text="Export Public...", command=self.action_export_pub).pack(side="left")
        ttk.Button(btns, text="Export Private...", command=self.action_export_priv).pack(side="left", padx=(6,0))

        ttk.Button(btns, text="Generate Revocation Cert...", command=self.action_revocation_cert).pack(side="left", padx=(6,0))

        help_txt = ("Tips: A revocation certificate lets you revoke a key later. Store it offline. "
                    "Export public key to share with others; export private key only for secure backup.")
        tk.Label(root, text=help_txt, anchor="w", justify="left", fg="#333").pack(fill="x", pady=6)

    def refresh_all_key_lists(self):
        try:
            pubs = list_keys(secret=False)
            secs = list_keys(secret=True)
        except Exception as e:
            errbox(f"Failed to list keys:\n{e}")
            return

        self.pub_list.delete(0, "end")
        for k in pubs:
            self.pub_list.insert("end", f"{k['uid']}   [{k['fpr']}]")

        self.sec_list.delete(0, "end")
        for k in secs:
            self.sec_list.insert("end", f"{k['uid']}   [{k['fpr']}]")

    def _selected_fpr_from_list(self, lstbox):
        sel = lstbox.curselection()
        if not sel:
            return None
        line = lstbox.get(sel[0])
        # extract [FPR]
        if "[" in line and "]" in line:
            return line.split("[",1)[1].split("]",1)[0].strip()
        return None

    def dialog_create_key(self):
        win = tk.Toplevel(self)
        win.title("Create New Key")
        win.transient(self)
        win.grab_set()

        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Name (Real Name):").grid(row=0, column=0, sticky="w")
        name_var = tk.StringVar()
        ttk.Entry(frm, textvariable=name_var, width=40).grid(row=0, column=1, sticky="we", pady=2)

        ttk.Label(frm, text="Email:").grid(row=1, column=0, sticky="w")
        email_var = tk.StringVar()
        ttk.Entry(frm, textvariable=email_var, width=40).grid(row=1, column=1, sticky="we", pady=2)

        ttk.Label(frm, text="Comment (optional):").grid(row=2, column=0, sticky="w")
        comment_var = tk.StringVar()
        ttk.Entry(frm, textvariable=comment_var, width=40).grid(row=2, column=1, sticky="we", pady=2)

        ttk.Label(frm, text="Key Size (bits):").grid(row=3, column=0, sticky="w")
        bits_var = tk.StringVar(value="4096")
        ttk.Combobox(frm, textvariable=bits_var, values=["3072", "4096"], state="readonly", width=10).grid(row=3, column=1, sticky="w", pady=2)

        ttk.Label(frm, text="Expiration (days, 0 = never):").grid(row=4, column=0, sticky="w")
        exp_var = tk.StringVar(value="0")
        ttk.Entry(frm, textvariable=exp_var, width=10).grid(row=4, column=1, sticky="w", pady=2)

        ttk.Label(frm, text="Passphrase (recommended):").grid(row=5, column=0, sticky="w")
        pw_var = tk.StringVar()
        ttk.Entry(frm, textvariable=pw_var, show="•", width=40).grid(row=5, column=1, sticky="we", pady=2)

        ttk.Label(frm, text="Confirm Passphrase:").grid(row=6, column=0, sticky="w")
        pw2_var = tk.StringVar()
        ttk.Entry(frm, textvariable=pw2_var, show="•", width=40).grid(row=6, column=1, sticky="we", pady=2)

        def do_create():
            name = name_var.get().strip()
            email = email_var.get().strip()
            comment = comment_var.get().strip()
            bits = bits_var.get().strip()
            expire_days = exp_var.get().strip() or "0"
            pw = pw_var.get()
            pw2 = pw2_var.get()
            if not name or not email or "@" not in email:
                errbox("Please provide a valid Name and Email.")
                return
            if pw != pw2:
                errbox("Passphrases do not match.")
                return
            uid = f"{name} <{email}>"
            if comment:
                uid = f"{name} ({comment}) <{email}>"
            # Map days to gpg 'expire' format (e.g., '0' or '365d')
            expire = "0" if expire_days == "0" else f"{expire_days}d"
            ok, msg = quick_generate_key(uid, algo="rsa", bits=int(bits), expire=expire,
                                         passphrase=(pw or None),
                                         loopback=True)
            if ok:
                info(f"Success:\n{msg}")
                self.refresh_all_key_lists()
                win.destroy()
            else:
                errbox(f"Failed to create key:\n{msg}")

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=2, pady=(10,0), sticky="e")
        ttk.Button(btns, text="Create", command=do_create).pack(side="right")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=(0,6))

        frm.columnconfigure(1, weight=1)

    def action_import_key(self):
        path = choose_file("Select key file to import")
        if not path:
            return
        ok, msg = import_key_from_file(path)
        if ok:
            info(f"Imported successfully.\n\n{msg}")
            self.refresh_all_key_lists()
        else:
            errbox(f"Import failed:\n{msg}")

    def action_export_pub(self):
        fpr = self._selected_fpr_from_list(self.pub_list) or self._selected_fpr_from_list(self.sec_list)
        if not fpr:
            errbox("Select a key (public or private) first.")
            return
        dest = choose_output_file("Export Public Key", default_ext=".asc")
        if not dest:
            return
        ok, msg = export_public_key_ascii(fpr, dest)
        info(msg if ok else f"Failed:\n{msg}")

    def action_export_priv(self):
        fpr = self._selected_fpr_from_list(self.sec_list)
        if not fpr:
            errbox("Select a private key (from the right list).")
            return
        if not yesno("Exporting a PRIVATE key is risky. Continue?"):
            return
        dest = choose_output_file("Export Private Key (ASCII armored)", default_ext=".asc")
        if not dest:
            return
        pw = self.prompt_passphrase("Passphrase to unlock your private key (for export)")
        ok, msg = export_private_key_ascii(fpr, dest, passphrase=pw, loopback=True)
        info(msg if ok else f"Failed:\n{msg}")

    def action_revocation_cert(self):
        fpr = self._selected_fpr_from_list(self.sec_list)
        if not fpr:
            errbox("Select a private key (from the right list).")
            return
        dest = choose_output_file("Save Revocation Certificate", default_ext=".rev")
        if not dest:
            return
        pw = self.prompt_passphrase("Passphrase to unlock your private key (to generate revocation cert)")
        ok, msg = generate_revocation_cert(fpr, dest, passphrase=pw, loopback=True)
        info(msg if ok else f"Failed:\n{msg}")

    # ---------------- Encrypt/Decrypt tab ----------------
    def _build_encrypt_tab(self):
        root = self.enc_tab

        top = ttk.Frame(root)
        top.pack(fill="x")

        ttk.Label(top, text="Recipient (public key):").pack(side="left")
        self.recipient_var = tk.StringVar()
        self.recipient_combo = ttk.Combobox(top, textvariable=self.recipient_var, state="readonly", width=60)
        self.recipient_combo.pack(side="left", padx=6, fill="x", expand=True)

        self.ascii_armor_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="ASCII armor (.asc)", variable=self.ascii_armor_var).pack(side="left", padx=6)

        mid = ttk.LabelFrame(root, text="Encrypt a File")
        mid.pack(fill="x", pady=(8,6))
        self.enc_src_var = tk.StringVar()
        self.enc_dst_var = tk.StringVar()

        row1 = ttk.Frame(mid); row1.pack(fill="x", padx=6, pady=4)
        ttk.Label(row1, text="Source file:").pack(side="left")
        ttk.Entry(row1, textvariable=self.enc_src_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row1, text="Browse...", command=lambda: self._browse(self.enc_src_var)).pack(side="left")

        row2 = ttk.Frame(mid); row2.pack(fill="x", padx=6, pady=4)
        ttk.Label(row2, text="Output file:").pack(side="left")
        ttk.Entry(row2, textvariable=self.enc_dst_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row2, text="Browse...", command=lambda: self._saveas(self.enc_dst_var)).pack(side="left")

        ttk.Button(mid, text="Encrypt", command=self.action_encrypt).pack(side="right", padx=6, pady=6)

        dec = ttk.LabelFrame(root, text="Decrypt a File")
        dec.pack(fill="x", pady=(8,6))
        self.dec_src_var = tk.StringVar()
        self.dec_dst_var = tk.StringVar()

        d1 = ttk.Frame(dec); d1.pack(fill="x", padx=6, pady=4)
        ttk.Label(d1, text="Encrypted file:").pack(side="left")
        ttk.Entry(d1, textvariable=self.dec_src_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(d1, text="Browse...", command=lambda: self._browse(self.dec_src_var)).pack(side="left")

        d2 = ttk.Frame(dec); d2.pack(fill="x", padx=6, pady=4)
        ttk.Label(d2, text="Output file:").pack(side="left")
        ttk.Entry(d2, textvariable=self.dec_dst_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(d2, text="Browse...", command=lambda: self._saveas(self.dec_dst_var)).pack(side="left")

        ttk.Button(dec, text="Decrypt", command=self.action_decrypt).pack(side="right", padx=6, pady=6)

    def _browse(self, var):
        p = choose_file()
        if p:
            var.set(p)

    def _saveas(self, var):
        p = choose_output_file()
        if p:
            var.set(p)

    def action_encrypt(self):
        rec = self._combo_fpr(self.recipient_combo)
        if not rec:
            errbox("Select a recipient public key.")
            return
        src = self.enc_src_var.get().strip()
        dst = self.enc_dst_var.get().strip()
        if not (src and os.path.isfile(src)):
            errbox("Choose a valid source file.")
            return
        if not dst:
            errbox("Choose an output file path.")
            return
        ok, msg = encrypt_file(src, rec, dst, ascii_armor=self.ascii_armor_var.get())
        info(msg if ok else f"Failed:\n{msg}")

    def action_decrypt(self):
        src = self.dec_src_var.get().strip()
        dst = self.dec_dst_var.get().strip()
        if not (src and os.path.isfile(src)):
            errbox("Choose a valid encrypted file.")
            return
        if not dst:
            errbox("Choose an output file path.")
            return
        pw = self.prompt_passphrase("If your private key is protected, enter passphrase")
        ok, msg = decrypt_file(src, dst, passphrase=pw, loopback=True)
        info(msg if ok else f"Failed:\n{msg}")

    # ---------------- Sign/Verify tab ----------------
    def _build_sign_tab(self):
        root = self.sign_tab

        top = ttk.Frame(root)
        top.pack(fill="x")

        ttk.Label(top, text="Signer (your private key):").pack(side="left")
        self.signer_var = tk.StringVar()
        self.signer_combo = ttk.Combobox(top, textvariable=self.signer_var, state="readonly", width=60)
        self.signer_combo.pack(side="left", padx=6, fill="x", expand=True)

        sigf = ttk.LabelFrame(root, text="Sign (detached signature)")
        sigf.pack(fill="x", pady=(8,6))

        self.sig_src_var = tk.StringVar()
        self.sig_out_var = tk.StringVar()

        s1 = ttk.Frame(sigf); s1.pack(fill="x", padx=6, pady=4)
        ttk.Label(s1, text="File to sign:").pack(side="left")
        ttk.Entry(s1, textvariable=self.sig_src_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(s1, text="Browse...", command=lambda: self._browse(self.sig_src_var)).pack(side="left")

        s2 = ttk.Frame(sigf); s2.pack(fill="x", padx=6, pady=4)
        ttk.Label(s2, text="Signature output (.sig):").pack(side="left")
        ttk.Entry(s2, textvariable=self.sig_out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(s2, text="Browse...", command=lambda: self._saveas(self.sig_out_var)).pack(side="left")

        ttk.Button(sigf, text="Sign", command=self.action_sign).pack(side="right", padx=6, pady=6)

        verf = ttk.LabelFrame(root, text="Verify a detached signature")
        verf.pack(fill="both", pady=(8,6), expand=True)

        self.ver_file_var = tk.StringVar()
        self.ver_sig_var = tk.StringVar()
        self.ver_output = scrolledtext.ScrolledText(verf, height=10, wrap="word")
        self.ver_output.pack(fill="both", expand=True, padx=6, pady=(0,6))

        v1 = ttk.Frame(verf); v1.pack(fill="x", padx=6, pady=4)
        ttk.Label(v1, text="Original file:").pack(side="left")
        ttk.Entry(v1, textvariable=self.ver_file_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(v1, text="Browse...", command=lambda: self._browse(self.ver_file_var)).pack(side="left")

        v2 = ttk.Frame(verf); v2.pack(fill="x", padx=6, pady=4)
        ttk.Label(v2, text="Signature (.sig):").pack(side="left")
        ttk.Entry(v2, textvariable=self.ver_sig_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(v2, text="Browse...", command=lambda: self._browse(self.ver_sig_var)).pack(side="left")

        ttk.Button(verf, text="Verify", command=self.action_verify).pack(side="right", padx=6, pady=6)

    def action_sign(self):
        signer = self._combo_fpr(self.signer_combo)
        if not signer:
            errbox("Select a signer (your private key).")
            return
        src = self.sig_src_var.get().strip()
        dst = self.sig_out_var.get().strip()
        if not (src and os.path.isfile(src)):
            errbox("Choose a valid file to sign.")
            return
        if not dst:
            errbox("Choose a signature output path.")
            return
        pw = self.prompt_passphrase("Passphrase for your private key (to sign)")
        ok, msg = detach_sign_file(src, signer, dst, passphrase=pw, loopback=True)
        info(msg if ok else f"Failed:\n{msg}")

    def action_verify(self):
        f = self.ver_file_var.get().strip()
        s = self.ver_sig_var.get().strip()
        if not (f and os.path.isfile(f)):
            errbox("Choose a valid original file.")
            return
        if not (s and os.path.isfile(s)):
            errbox("Choose a valid signature (.sig).")
            return
        ok, msg = verify_signature(f, s)
        self.ver_output.delete("1.0", "end")
        self.ver_output.insert("1.0", msg)

    # ---------------- Clear-Sign tab ----------------
    def _build_clear_tab(self):
        root = self.clear_tab

        top = ttk.Frame(root)
        top.pack(fill="x")

        ttk.Label(top, text="Signer (your private key):").pack(side="left")
        self.clr_signer_var = tk.StringVar()
        self.clr_signer_combo = ttk.Combobox(top, textvariable=self.clr_signer_var, state="readonly", width=60)
        self.clr_signer_combo.pack(side="left", padx=6, fill="x", expand=True)

        self.clear_in = scrolledtext.ScrolledText(root, height=12, wrap="word")
        self.clear_in.pack(fill="both", expand=True, padx=6, pady=(8,6))
        self.clear_in.insert("1.0", "Type or paste the message you want to clear-sign here...")

        btn_row = ttk.Frame(root)
        btn_row.pack(fill="x")

        ttk.Button(btn_row, text="Clear-Sign", command=self.action_clearsign).pack(side="left", padx=(0,6))
        ttk.Button(btn_row, text="Save Result...", command=self.action_save_clearsigned).pack(side="left")

        ttk.Label(root, text="Result (ASCII clear-signed):").pack(anchor="w", padx=6, pady=(8,0))
        self.clear_out = scrolledtext.ScrolledText(root, height=12, wrap="word")
        self.clear_out.pack(fill="both", expand=True, padx=6, pady=(0,6))

    def action_clearsign(self):
        signer = self._combo_fpr(self.clr_signer_combo)
        if not signer:
            errbox("Select a signer (your private key).")
            return
        text = self.clear_in.get("1.0", "end")
        pw = self.prompt_passphrase("Passphrase for your private key (to clear-sign)")
        ok, result = clearsign_text(text, signer, passphrase=pw, loopback=True)
        if ok:
            self.clear_out.delete("1.0", "end")
            self.clear_out.insert("1.0", result)
        else:
            errbox(f"Failed to clear-sign:\n{result}")

    def action_save_clearsigned(self):
        data = self.clear_out.get("1.0", "end").strip()
        if not data:
            warn("There is no clear-signed text to save.")
            return
        path = save_text_to_file(data, title="Save Clear-Signed Text", defaultextension=".asc")
        if path:
            info(f"Saved to: {path}")

    # ---------------- Helpers ----------------
    def prompt_passphrase(self, prompt_title):
        # Simple passphrase dialog; returns str or None
        dlg = tk.Toplevel(self)
        dlg.title("Passphrase")
        dlg.transient(self)
        dlg.grab_set()
        ttk.Label(dlg, text=prompt_title, wraplength=380, justify="left").pack(padx=12, pady=(12,6))
        var = tk.StringVar()
        e = ttk.Entry(dlg, textvariable=var, show="•", width=50)
        e.pack(padx=12, pady=6)
        e.focus_set()
        out = {"pw": None}
        def ok():
            out["pw"] = var.get()
            dlg.destroy()
        def cancel():
            out["pw"] = None
            dlg.destroy()
        btns = ttk.Frame(dlg)
        btns.pack(padx=12, pady=(6,12), anchor="e")
        ttk.Button(btns, text="OK", command=ok).pack(side="right")
        ttk.Button(btns, text="Cancel", command=cancel).pack(side="right", padx=(0,6))
        dlg.wait_window()
        return out["pw"]

    def _combo_fpr(self, combo):
        """
        Entries are "UID   [FPR]". Extract FPR.
        """
        val = combo.get().strip()
        if "[" in val and "]" in val:
            return val.split("[",1)[1].split("]",1)[0].strip()
        return None

    def refresh_recipient_combo(self):
        try:
            pubs = list_keys(secret=False)
        except Exception:
            pubs = []
        vals = [f"{k['uid']}   [{k['fpr']}]" for k in pubs]
        self.recipient_combo["values"] = vals

    def refresh_signer_combos(self):
        try:
            secs = list_keys(secret=True)
        except Exception:
            secs = []
        vals = [f"{k['uid']}   [{k['fpr']}]" for k in secs]
        self.signer_combo["values"] = vals
        self.clr_signer_combo["values"] = vals

    def refresh_all_key_lists(self):
        # override parent method to also refresh combos
        try:
            pubs = list_keys(secret=False)
            secs = list_keys(secret=True)
        except Exception as e:
            errbox(f"Failed to list keys:\n{e}")
            return

        self.pub_list.delete(0, "end")
        for k in pubs:
            self.pub_list.insert("end", f"{k['uid']}   [{k['fpr']}]")

        self.sec_list.delete(0, "end")
        for k in secs:
            self.sec_list.insert("end", f"{k['uid']}   [{k['fpr']}]")

        self.refresh_recipient_combo()
        self.refresh_signer_combos()

# -------------------------- Main --------------------------

if __name__ == "__main__":
    app = GPGGUI()
    # If gpg not available, app will destroy itself
    try:
        app.mainloop()
    except tk.TclError:
        pass

