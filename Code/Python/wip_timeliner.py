import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import datetime

class Timeline:
    def __init__(self, name):
        self.name = name
        self.events = []  # each event is a dict with keys: id, date, title, category, description

class TimelineApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Timeline Editor")
        self.geometry("1200x700")
        
        # Data structures
        self.timelines = {}   # key: timeline name, value: Timeline object
        self.event_counter = 1
        self.correlations = []  # list of tuples: (timeline1, event_id1, timeline2, event_id2)
        
        # Current event being edited (None when adding a new event)
        self.current_edit_event = None  # (timeline_name, event_index)
        
        self.create_widgets()
    
    def create_widgets(self):
        # Main layout: left panel for data management; right panel for graphical timeline
        self.left_frame = ttk.Frame(self)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)
        
        self.right_frame = ttk.Frame(self)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # --- Left panel: Timeline and Event Management ---
        # Timeline List
        timeline_frame = ttk.LabelFrame(self.left_frame, text="Timelines")
        timeline_frame.pack(fill=tk.X, padx=5, pady=5)
        self.timeline_listbox = tk.Listbox(timeline_frame, height=5)
        self.timeline_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.timeline_listbox.bind("<<ListboxSelect>>", self.on_timeline_select)
        timeline_btn_frame = ttk.Frame(timeline_frame)
        timeline_btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        ttk.Button(timeline_btn_frame, text="Add", command=self.add_timeline).pack(fill=tk.X, pady=2)
        ttk.Button(timeline_btn_frame, text="Delete", command=self.delete_timeline).pack(fill=tk.X, pady=2)
        
        # Event List
        event_frame = ttk.LabelFrame(self.left_frame, text="Events")
        event_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.event_listbox = tk.Listbox(event_frame, selectmode=tk.MULTIPLE)
        self.event_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        event_btn_frame = ttk.Frame(event_frame)
        event_btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(event_btn_frame, text="Add Event", command=self.show_event_editor_for_add).pack(side=tk.LEFT, padx=2)
        ttk.Button(event_btn_frame, text="Edit Event", command=self.show_event_editor_for_edit).pack(side=tk.LEFT, padx=2)
        ttk.Button(event_btn_frame, text="Delete Event", command=self.delete_event).pack(side=tk.LEFT, padx=2)
        ttk.Button(event_btn_frame, text="Link Selected", command=self.link_selected_events).pack(side=tk.LEFT, padx=2)
        
        # Correlations List
        corr_frame = ttk.LabelFrame(self.left_frame, text="Correlations")
        corr_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.corr_listbox = tk.Listbox(corr_frame)
        self.corr_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Button(corr_frame, text="Delete Correlation", command=self.delete_correlation).pack(padx=5, pady=5)
        
        # Event Editor Panel (integrated, initially hidden)
        self.event_editor_frame = ttk.LabelFrame(self.left_frame, text="Event Editor")
        # Layout using grid
        ttk.Label(self.event_editor_frame, text="Date:").grid(row=0, column=0, sticky=tk.W, padx=2, pady=2)
        self.year_var = tk.StringVar()
        self.month_var = tk.StringVar()
        self.day_var = tk.StringVar()
        self.year_cb = ttk.Combobox(self.event_editor_frame, textvariable=self.year_var, width=5,
                                    values=[str(y) for y in range(1900, 2101)])
        self.year_cb.grid(row=0, column=1, padx=2, pady=2)
        self.month_cb = ttk.Combobox(self.event_editor_frame, textvariable=self.month_var, width=3,
                                     values=[f"{m:02d}" for m in range(1, 13)])
        self.month_cb.grid(row=0, column=2, padx=2, pady=2)
        self.day_cb = ttk.Combobox(self.event_editor_frame, textvariable=self.day_var, width=3,
                                   values=[f"{d:02d}" for d in range(1, 32)])
        self.day_cb.grid(row=0, column=3, padx=2, pady=2)
        
        ttk.Label(self.event_editor_frame, text="Title:").grid(row=1, column=0, sticky=tk.W, padx=2, pady=2)
        self.title_entry = ttk.Entry(self.event_editor_frame, width=30)
        self.title_entry.grid(row=1, column=1, columnspan=3, padx=2, pady=2)
        
        ttk.Label(self.event_editor_frame, text="Category:").grid(row=2, column=0, sticky=tk.W, padx=2, pady=2)
        self.category_entry = ttk.Entry(self.event_editor_frame, width=30)
        self.category_entry.grid(row=2, column=1, columnspan=3, padx=2, pady=2)
        
        ttk.Label(self.event_editor_frame, text="Description:").grid(row=3, column=0, sticky=tk.NW, padx=2, pady=2)
        self.description_text = tk.Text(self.event_editor_frame, width=30, height=4)
        self.description_text.grid(row=3, column=1, columnspan=3, padx=2, pady=2)
        
        editor_btn_frame = ttk.Frame(self.event_editor_frame)
        editor_btn_frame.grid(row=4, column=0, columnspan=4, pady=5)
        ttk.Button(editor_btn_frame, text="Save", command=self.save_event).pack(side=tk.LEFT, padx=5)
        ttk.Button(editor_btn_frame, text="Cancel", command=self.cancel_event_edit).pack(side=tk.LEFT, padx=5)
        # Hide the editor panel initially
        self.event_editor_frame.pack_forget()
        
        # --- Right panel: Graphical Timeline View ---
        self.canvas = tk.Canvas(self.right_frame, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Button(self.right_frame, text="Refresh Timeline", command=self.draw_timeline).pack(pady=5)
    
    # --- Timeline management ---
    def add_timeline(self):
        name = simpledialog.askstring("Add Timeline", "Enter timeline name:")
        if name:
            if name in self.timelines:
                messagebox.showerror("Error", "Timeline already exists.")
            else:
                self.timelines[name] = Timeline(name)
                self.timeline_listbox.insert(tk.END, name)
    
    def delete_timeline(self):
        selection = self.timeline_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No timeline selected.")
            return
        index = selection[0]
        timeline_name = self.timeline_listbox.get(index)
        del self.timelines[timeline_name]
        self.timeline_listbox.delete(index)
        self.event_listbox.delete(0, tk.END)
    
    def on_timeline_select(self, event):
        self.event_listbox.delete(0, tk.END)
        selection = self.timeline_listbox.curselection()
        if not selection:
            return
        timeline_name = self.timeline_listbox.get(selection[0])
        timeline = self.timelines[timeline_name]
        for ev in timeline.events:
            display = f"[{ev['id']}] {ev['date']} - {ev['title']} ({ev.get('category','')})"
            self.event_listbox.insert(tk.END, display)
    
    # --- Event Editor (integrated panel) ---
    def show_event_editor_for_add(self):
        self.current_edit_event = None
        self.set_editor_fields("", datetime.date.today().strftime("%Y-%m-%d"), "", "")
        self.event_editor_frame.pack(fill=tk.X, padx=5, pady=5)
    
    def show_event_editor_for_edit(self):
        selection = self.event_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No event selected for editing.")
            return
        index = selection[0]
        timeline_name = self.timeline_listbox.get(self.timeline_listbox.curselection()[0])
        timeline = self.timelines[timeline_name]
        if index >= len(timeline.events):
            messagebox.showerror("Error", "Invalid event selected.")
            return
        event_data = timeline.events[index]
        self.current_edit_event = (timeline_name, index)
        self.set_editor_fields(event_data["title"], event_data["date"],
                               event_data.get("category", ""), event_data.get("description", ""))
        self.event_editor_frame.pack(fill=tk.X, padx=5, pady=5)
    
    def set_editor_fields(self, title, date_str, category, description):
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            dt = datetime.date.today()
        self.year_var.set(str(dt.year))
        self.month_var.set(f"{dt.month:02d}")
        self.day_var.set(f"{dt.day:02d}")
        self.title_entry.delete(0, tk.END)
        self.title_entry.insert(0, title)
        self.category_entry.delete(0, tk.END)
        self.category_entry.insert(0, category)
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert(tk.END, description)
    
    def save_event(self):
        year = self.year_var.get()
        month = self.month_var.get()
        day = self.day_var.get()
        try:
            dt = datetime.date(int(year), int(month), int(day))
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            messagebox.showerror("Error", "Invalid date.")
            return
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showerror("Error", "Title cannot be empty.")
            return
        category = self.category_entry.get().strip()
        description = self.description_text.get("1.0", tk.END).strip()
        event_data = {
            "id": self.event_counter,
            "date": date_str,
            "title": title,
            "category": category,
            "description": description
        }
        timeline_name = self.timeline_listbox.get(self.timeline_listbox.curselection()[0])
        timeline = self.timelines[timeline_name]
        if self.current_edit_event is None:
            timeline.events.append(event_data)
            self.event_counter += 1
        else:
            idx = self.current_edit_event[1]
            event_data["id"] = timeline.events[idx]["id"]
            timeline.events[idx] = event_data
        self.event_editor_frame.pack_forget()
        self.on_timeline_select(None)
        self.draw_timeline()
    
    def cancel_event_edit(self):
        self.event_editor_frame.pack_forget()
    
    def delete_event(self):
        selection = self.event_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No event selected to delete.")
            return
        timeline_name = self.timeline_listbox.get(self.timeline_listbox.curselection()[0])
        timeline = self.timelines[timeline_name]
        for index in reversed(selection):
            if index < len(timeline.events):
                del timeline.events[index]
        self.on_timeline_select(None)
        self.draw_timeline()
    
    # --- Correlation functions ---
    def link_selected_events(self):
        selection = self.event_listbox.curselection()
        if len(selection) != 2:
            messagebox.showerror("Error", "Select exactly 2 events to link.")
            return
        timeline_name = self.timeline_listbox.get(self.timeline_listbox.curselection()[0])
        timeline = self.timelines[timeline_name]
        try:
            ev1 = timeline.events[selection[0]]
            ev2 = timeline.events[selection[1]]
        except IndexError:
            messagebox.showerror("Error", "Invalid event selection.")
            return
        self.correlations.append((timeline_name, ev1["id"], timeline_name, ev2["id"]))
        self.refresh_correlations()
        self.draw_timeline()
    
    def refresh_correlations(self):
        self.corr_listbox.delete(0, tk.END)
        for corr in self.correlations:
            text = f"{corr[0]} (Event {corr[1]}) <--> {corr[2]} (Event {corr[3]})"
            self.corr_listbox.insert(tk.END, text)
    
    def delete_correlation(self):
        selection = self.corr_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "No correlation selected.")
            return
        index = selection[0]
        del self.correlations[index]
        self.refresh_correlations()
        self.draw_timeline()
    
    # --- Graphical Timeline Drawing ---
    def draw_timeline(self):
        self.canvas.delete("all")
        event_positions = {}
        all_dates = []
        for timeline in self.timelines.values():
            for ev in timeline.events:
                try:
                    dt = datetime.datetime.strptime(ev["date"], "%Y-%m-%d").date()
                    all_dates.append(dt)
                except:
                    pass
        if all_dates:
            min_date = min(all_dates)
            max_date = max(all_dates)
        else:
            min_date = datetime.date.today()
            max_date = datetime.date.today()
        total_days = (max_date - min_date).days or 1
        width = self.canvas.winfo_width() or 800
        height = self.canvas.winfo_height() or 600
        margin_x = 100
        margin_y = 50
        timeline_names = list(self.timelines.keys())
        num_timelines = len(timeline_names)
        if num_timelines == 0:
            self.canvas.create_text(width/2, height/2, text="No timelines available.")
            return
        row_height = (height - 2 * margin_y) / num_timelines
        
        for i, t_name in enumerate(timeline_names):
            y = margin_y + i * row_height + row_height/2
            self.canvas.create_line(margin_x, y, width - margin_x, y, fill="black")
            self.canvas.create_text(margin_x - 50, y, text=t_name, anchor="e")
            timeline = self.timelines[t_name]
            for ev in timeline.events:
                try:
                    ev_date = datetime.datetime.strptime(ev["date"], "%Y-%m-%d").date()
                except:
                    continue
                x = margin_x + ((ev_date - min_date).days / total_days) * (width - 2 * margin_x)
                r = 5
                self.canvas.create_oval(x - r, y - r, x + r, y + r, fill="blue")
                self.canvas.create_text(x, y - 10, text=ev["title"], angle=45,
                                        anchor="s", font=("Arial", 8))
                event_positions[(t_name, ev["id"])] = (x, y)
        
        for corr in self.correlations:
            pos1 = event_positions.get((corr[0], corr[1]))
            pos2 = event_positions.get((corr[2], corr[3]))
            if pos1 and pos2:
                self.canvas.create_line(pos1[0], pos1[1], pos2[0], pos2[1],
                                        fill="red", dash=(4, 2))

if __name__ == "__main__":
    app = TimelineApp()
    app.mainloop()
