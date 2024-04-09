from tkinter import *
from tkinter import messagebox, scrolledtext
from scapy.all import *
import random
import threading
import re

# Your existing functions
def random_ipv4():
    return ".".join(str(random.randint(0, 255)) for _ in range(4))

def send_custom_ping(src_ip, dst_ip, payload):
    ip_layer = IP(src=src_ip, dst=dst_ip)
    icmp_layer = ICMP(type=8, code=0)
    packet = ip_layer / icmp_layer / payload
    send(packet, verbose=0)

def ping_thread(src_ip, payload, output_text):
    dst_ip = random_ipv4()
    send_custom_ping(src_ip, dst_ip, payload)
    output_text.insert(END, f"Pinged {dst_ip} from {src_ip} with payload size {len(payload)} bytes\n")
    output_text.see(END)

def main_loop(src_ip, payload, count, output_text):
    threads = []
    for _ in range(count):
        t = threading.Thread(target=ping_thread, args=(src_ip, payload, output_text))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

# Dark Theme Colors
bg_color = "#333333"
text_color = "#FFFFFF"
button_color = "#555555"
entry_bg_color = "#555555"
entry_fg_color = "#DDDDDD"

# GUI Class
class PingGUI:
    def __init__(self, master):
        self.master = master
        master.title("Custom Ping Interface")
        master.configure(bg=bg_color)

        # Configure the main frame for input fields
        self.frame_inputs = Frame(master, bg=bg_color)
        self.frame_inputs.pack(pady=10)

        # Source IP
        self.label_src_ip = Label(self.frame_inputs, text="Source IP:", bg=bg_color, fg=text_color)
        self.label_src_ip.grid(row=0, column=0, padx=5)
        self.entry_src_ip = Entry(self.frame_inputs, fg=entry_fg_color, bg=entry_bg_color)
        self.entry_src_ip.grid(row=0, column=1, padx=5)

        # Payload
        self.label_payload = Label(self.frame_inputs, text="Payload:", bg=bg_color, fg=text_color)
        self.label_payload.grid(row=0, column=2, padx=5)
        self.entry_payload = Entry(self.frame_inputs, fg=entry_fg_color, bg=entry_bg_color)
        self.entry_payload.grid(row=0, column=3, padx=5)

        # Count
        self.label_count = Label(self.frame_inputs, text="Count:", bg=bg_color, fg=text_color)
        self.label_count.grid(row=0, column=4, padx=5)
        self.entry_count = Entry(self.frame_inputs, fg=entry_fg_color, bg=entry_bg_color)
        self.entry_count.grid(row=0, column=5, padx=5)

        # Start Button
        self.start_button = Button(self.frame_inputs, text="Start Ping", command=self.start_ping, fg=text_color, bg=button_color)
        self.start_button.grid(row=0, column=6, padx=5)

        # Output Text Area with scrollbar
        self.output_text = scrolledtext.ScrolledText(master, fg=entry_fg_color, bg=entry_bg_color)
        self.output_text.pack(pady=10)

    def start_ping(self):
        src_ip = self.entry_src_ip.get()
        payload = self.entry_payload.get()
        count_str = self.entry_count.get()
        if not validate_ip(src_ip):
            messagebox.showerror("Error", "Invalid Source IP address.")
            return
        if not is_number(count_str):
            messagebox.showerror("Error", "Count must be a number.")
            return
        count = int(count_str)
        self.output_text.delete('1.0', END)  # Clear output text area
        threading.Thread(target=main_loop, args=(src_ip, payload, count, self.output_text), daemon=True).start()

# Function to validate IP address
def validate_ip(ip):
    pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    return pattern.match(ip) is not None

# Function to check if a string is a number
def is_number(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

# Run the GUI application
if __name__ == "__main__":
    root = Tk()
    my_gui = PingGUI(root)
    root.mainloop()
