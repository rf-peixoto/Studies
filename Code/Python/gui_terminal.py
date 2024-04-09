# For some reason, if you need a GUI Terminal... Well, here it is...

import tkinter as tk
from tkinter import scrolledtext
from tkinter import END
import subprocess
import threading

class TerminalApp:
    def __init__(self, master):
        self.master = master
        master.title("Python Terminal")
        # Remove the default TK icon
        master.iconphoto(False, tk.PhotoImage(file='/path/to/your/icon.png'))  # Specify your own icon path

        self.command_history = []
        self.history_index = 0

        master.configure(bg='black')
        self.output = scrolledtext.ScrolledText(master, state='disabled', height=20, width=80,
                                                bg='black', fg='green', insertbackground='white')
        self.output.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        self.input = tk.Entry(master, width=80, bg='black', fg='green', insertbackground='white')
        self.input.grid(row=1, column=0, sticky='ew', padx=5)
        self.input.bind("<Return>", self.execute_command_async)
        self.input.focus_set()

        master.grid_columnconfigure(0, weight=1)
        master.grid_rowconfigure(0, weight=1)

    def execute_command_async(self, event):
        command = self.input.get().strip()
        self.input.delete(0, END)
        if command:
            self.command_history.append(command)
            self.history_index = len(self.command_history)
            threading.Thread(target=self.execute_command, args=(command,), daemon=True).start()

    def execute_command(self, command):
        if command in ["reset", "clear"]:
            self.clear_screen()
            return

        self.output.configure(state='normal')
        self.output.insert(END, f">>> {command}\n")
        self.output.configure(state='disabled')

        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in iter(process.stdout.readline, ''):
            self.output.configure(state='normal')
            self.output.insert(END, line)
            self.output.configure(state='disabled')
            self.output.see(END)
        process.stdout.close()
        process.wait()
        self.input.focus_set()

    def clear_screen(self):
        self.output.configure(state='normal')
        self.output.delete('1.0', END)
        self.output.configure(state='disabled')

def main():
    root = tk.Tk()
    app = TerminalApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
