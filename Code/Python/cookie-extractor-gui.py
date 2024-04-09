import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk, filedialog
import requests
from urllib.parse import urlparse
import json

class WebRequestHandlerGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Web Request Handler")
        self.master.resizable(False, False)

        # Configuring the main window layout
        self.main_frame = ttk.Frame(self.master)
        self.main_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # URL Input
        ttk.Label(self.main_frame, text="URL:").grid(row=0, column=0, pady=(0, 10), sticky=tk.W)
        self.url_entry = ttk.Entry(self.main_frame, width=60)
        self.url_entry.grid(row=0, column=1, pady=(0, 10), columnspan=3, sticky=tk.EW)
        self.url_entry.focus()

        # Request Type Selection
        self.request_type = tk.StringVar(value="new_cookies")
        ttk.Radiobutton(self.main_frame, text="New Cookies", variable=self.request_type, value="new_cookies").grid(row=1, column=0, sticky=tk.W)
        ttk.Radiobutton(self.main_frame, text="Preconfigured Headers", variable=self.request_type, value="preconfigured").grid(row=1, column=1, sticky=tk.W)

        # Buttons
        self.send_request_btn = ttk.Button(self.main_frame, text="Send Request", command=self.send_request)
        self.send_request_btn.grid(row=1, column=3, sticky=tk.E, padx=(10,0))

        # Response Area
        ttk.Label(self.main_frame, text="Response:").grid(row=2, column=0, pady=(10, 0), sticky=tk.W, columnspan=4)
        self.response_area = scrolledtext.ScrolledText(self.main_frame, height=15)
        self.response_area.grid(row=3, column=0, columnspan=4, pady=(5, 0), sticky=tk.EW + tk.NS)

        # Export Button
        self.export_btn = ttk.Button(self.main_frame, text="Export Result", command=self.export_result)
        self.export_btn.grid(row=4, column=3, sticky=tk.E, pady=(10,0))

        # Import Cookies Button
        self.import_btn = ttk.Button(self.main_frame, text="Import Cookies", command=self.import_cookies)
        self.import_btn.grid(row=4, column=0, sticky=tk.W, pady=(10,0))

    def send_request(self):
        url = self.validate_url(self.url_entry.get().strip())
        if not url:
            messagebox.showerror("Error", "Invalid URL")
            return
        if self.request_type.get() == "new_cookies":
            response = self.make_request(url)
        else:  # preconfigured headers
            response = self.make_request(url, self.configure_headers_for_url(url))
        self.display_response(response)
        self.url_entry.delete(0, tk.END)

    def validate_url(self, url):
        if not urlparse(url).scheme:
            url = 'http://' + url
        return url if urlparse(url).netloc else None

    def make_request(self, url, headers=None):
        try:
            response = requests.get(url, headers=headers)
            result = {
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'cookies': response.cookies.get_dict()
            }
            return json.dumps(result, indent=2)
        except Exception as e:
            return json.dumps({'status_code': 'Error', 'error': str(e)}, indent=2)

    def configure_headers_for_url(self, url):
        parsed_url = urlparse(url)
        referer = f"{parsed_url.scheme}://{parsed_url.netloc}"
        return {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': referer
        }

    def display_response(self, response):
        self.response_area.delete('1.0', tk.END)
        self.response_area.insert(tk.INSERT, response)

    def export_result(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".json")
        if file_path:
            with open(file_path, 'w') as file:
                file.write(self.response_area.get('1.0', tk.END))

    def import_cookies(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if file_path:
            with open(file_path, 'r') as file:
                cookies = json.load(file)
            messagebox.showinfo("Import Successful", f"Cookies imported from {file_path}. Ready to make a request with these cookies.")

if __name__ == "__main__":
    root = tk.Tk()
    app = WebRequestHandlerGUI(root)
    root.mainloop()
