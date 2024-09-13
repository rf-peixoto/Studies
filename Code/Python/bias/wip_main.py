import tkinter as tk
from tkinter import messagebox, ttk
import json
import random
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Use TkAgg backend for compatibility with Tkinter
matplotlib.use('TkAgg')

# Scoring system and corresponding answer map
score_map = {
    "Y": 2,
    "M": 1,
    "N": 0,
    "m": -1,
    "NO": -2
}

numeric_score_map = {
    1: "Y",   # Yes
    2: "M",   # Maybe Yes
    3: "N",   # Neutral
    4: "m",   # Maybe No
    5: "NO"   # No
}

class BiasTestGUI:
    def __init__(self, master, biases):
        self.master = master
        self.biases = biases
        self.total_score = 0
        self.bias_scores = {}
        self.bias_question_counts = {}
        self.test_mode = None  # Quick or Comprehensive
        self.all_questions = []
        self.current_index = 0
        self.max_score = 0
        self.min_score = 0
        self.user_responses = {}
        self.adaptive_threshold = 3  # Threshold to trigger adaptive questioning
        self.setup_test()

    def setup_test(self):
        self.master.title("Cognitive Assessment")
        self.frame = tk.Frame(self.master, padx=20, pady=20)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Responsive layout
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)

        # Welcome label
        tk.Label(self.frame, text="Welcome to the Cognitive Assessment", font=("Arial", 16)).pack(pady=10)

        # Test mode selection
        tk.Label(self.frame, text="Select Assessment Type:", font=("Arial", 14)).pack(pady=10)
        self.mode_var = tk.StringVar(value="Quick")
        modes = [("Quick Assessment (Approx. 10 mins)", "Quick"), ("Comprehensive Assessment (Approx. 20 mins)", "Comprehensive")]
        for text, value in modes:
            tk.Radiobutton(self.frame, text=text, variable=self.mode_var, value=value, font=("Arial", 12)).pack(anchor=tk.W)

        tk.Button(self.frame, text="Start Test", command=self.start_test, font=("Arial", 12)).pack(pady=20)

    def start_test(self):
        self.test_mode = self.mode_var.get()
        self.frame.destroy()
        self.prepare_questions()
        self.create_widgets()
        self.show_question()

    def prepare_questions(self):
        self.all_questions = []
        self.bias_question_counts = {bias: 0 for bias in self.biases.keys()}

        # Number of initial questions per bias
        initial_questions_per_bias = 1 if self.test_mode == "Quick" else 2

        for bias_name, bias_data in self.biases.items():
            questions = bias_data["questions"]
            # Include reverse-worded questions
            random.shuffle(questions)
            selected_questions = questions[:initial_questions_per_bias]
            for question in selected_questions:
                self.all_questions.append({
                    "bias_name": bias_name,
                    "question": question["text"],
                    "reverse": question.get("reverse", False),
                    "weight": bias_data["weight"]
                })
                self.bias_question_counts[bias_name] += 1

        random.shuffle(self.all_questions)
        self.max_score = self.calculate_max_score()
        self.min_score = self.calculate_min_score()

    def calculate_max_score(self):
        return len(self.all_questions) * 2  # Maximum score per question is 2

    def calculate_min_score(self):
        return len(self.all_questions) * -2  # Minimum score per question is -2

    def create_widgets(self):
        self.master.title("Cognitive Assessment")
        self.frame = tk.Frame(self.master, padx=20, pady=20)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Progress bar
        self.progress = ttk.Progressbar(self.frame, orient=tk.HORIZONTAL, length=400, mode='determinate')
        self.progress.pack(pady=(0, 20))

        # Question label
        self.question_label = tk.Label(self.frame, text="", wraplength=600, font=("Arial", 14), justify=tk.LEFT)
        self.question_label.pack(pady=10, anchor=tk.W)

        # Answer options
        self.var = tk.IntVar()
        self.options_frame = tk.Frame(self.frame)
        self.options_frame.pack(anchor=tk.W)

        options = [("Yes", 1), ("Maybe Yes", 2), ("Neutral", 3), ("Maybe No", 4), ("No", 5)]
        for text, value in options:
            rb = tk.Radiobutton(
                self.options_frame, text=text, variable=self.var, value=value,
                font=("Arial", 12)
            )
            rb.pack(anchor=tk.W)
            rb.bind("<Key>", self.key_pressed)

        # Navigation buttons
        self.button_frame = tk.Frame(self.frame)
        self.button_frame.pack(pady=20)

        self.prev_button = tk.Button(
            self.button_frame, text="Previous", command=self.go_previous,
            state=tk.DISABLED, font=("Arial", 12)
        )
        self.prev_button.pack(side=tk.LEFT, padx=10)

        self.next_button = tk.Button(
            self.button_frame, text="Next", command=self.submit_answer,
            font=("Arial", 12)
        )
        self.next_button.pack(side=tk.LEFT, padx=10)

        self.update_progress()

    def key_pressed(self, event):
        if event.char == '\r':
            self.submit_answer()

    def update_progress(self):
        total_questions = len(self.all_questions)
        progress_value = (self.current_index / total_questions) * 100
        self.progress['value'] = progress_value
        self.master.update_idletasks()

    def show_question(self):
        if self.current_index < len(self.all_questions):
            question_data = self.all_questions[self.current_index]
            self.current_question = question_data
            question_text = f"Question {self.current_index + 1} of {len(self.all_questions)}:\n\n{question_data['question']}"
            self.question_label.config(text=question_text)
            self.var.set(0)
            self.update_progress()

            # Update button states
            if self.current_index == 0:
                self.prev_button.config(state=tk.DISABLED)
            else:
                self.prev_button.config(state=tk.NORMAL)
        else:
            self.display_results()

    def go_previous(self):
        if self.current_index > 0:
            self.current_index -= 1
            # Remove the last answer
            last_question = self.all_questions[self.current_index]
            last_bias_name = last_question["bias_name"]
            last_response = self.user_responses.pop(self.current_index, None)
            if last_response is not None:
                last_score = self.calculate_score(last_response, last_question["reverse"])
                self.total_score -= last_score
                self.bias_scores[last_bias_name] -= last_score
                self.bias_question_counts[last_bias_name] -= 1
            self.show_question()

    def submit_answer(self):
        if self.var.get() == 0:
            messagebox.showwarning("Input Required", "Please select an answer before proceeding.")
            return

        answer_value = self.var.get()
        answer_str = numeric_score_map[answer_value]
        reverse = self.current_question["reverse"]
        score = self.calculate_score(answer_str, reverse)
        bias_name = self.current_question["bias_name"]

        self.total_score += score
        self.bias_scores.setdefault(bias_name, 0)
        self.bias_scores[bias_name] += score
        self.bias_question_counts[bias_name] += 1
        self.user_responses[self.current_index] = answer_str

        # Adaptive Testing: Add additional questions if strong tendency detected
        if abs(self.bias_scores[bias_name]) >= self.adaptive_threshold and self.bias_question_counts[bias_name] == 1:
            additional_questions = self.biases[bias_name]["questions"][2:]  # Skip initial questions
            for question in additional_questions:
                self.all_questions.insert(self.current_index + 1, {
                    "bias_name": bias_name,
                    "question": question["text"],
                    "reverse": question.get("reverse", False),
                    "weight": self.biases[bias_name]["weight"]
                })

        self.current_index += 1
        self.show_question()

    def calculate_score(self, answer_str, reverse):
        score = score_map[answer_str]
        if reverse:
            score = -score  # Reverse the score for reverse-worded questions
        return score

    def interpret_score(self):
        normalized_score = ((self.total_score - self.min_score) / (self.max_score - self.min_score)) * 100
        return normalized_score

    def display_results(self):
        try:
            normalized_score = self.interpret_score()
            overall_interpretation = self.get_overall_interpretation(normalized_score)

            # Create results window
            result_window = tk.Toplevel(self.master)
            result_window.title("Assessment Results")
            result_window.geometry("800x600")

            # Create a notebook (tabbed interface)
            notebook = ttk.Notebook(result_window)
            notebook.pack(expand=True, fill=tk.BOTH)

            # Overall Results Tab
            overall_frame = ttk.Frame(notebook)
            notebook.add(overall_frame, text="Overall Results")

            overall_label = tk.Label(overall_frame, text=overall_interpretation, font=("Arial", 12), wraplength=750, justify=tk.LEFT)
            overall_label.pack(pady=10, padx=10)

            # Bias Scores Tab
            bias_frame = ttk.Frame(notebook)
            notebook.add(bias_frame, text="Bias Scores")

            # Generate bar chart of bias scores
            self.create_bias_score_chart(bias_frame)

            # Detailed Feedback Tab
            feedback_frame = ttk.Frame(notebook)
            notebook.add(feedback_frame, text="Detailed Feedback")

            feedback_text = tk.Text(feedback_frame, wrap=tk.WORD)
            feedback_text.pack(expand=True, fill=tk.BOTH)

            for bias_name, bias_data in self.biases.items():
                if bias_name in self.bias_scores:
                    bias_score = self.bias_scores[bias_name]
                    num_questions = self.bias_question_counts[bias_name]
                    avg_score = bias_score / num_questions if num_questions else 0
                    interpretation = self.get_bias_interpretation(avg_score)
                    feedback_text.insert(tk.END, f"{bias_name}:\n")
                    feedback_text.insert(tk.END, f"  Average Score: {avg_score:.2f}\n")
                    feedback_text.insert(tk.END, f"  {bias_data['description']}\n")
                    feedback_text.insert(tk.END, f"  Interpretation: {interpretation}\n\n")

            feedback_text.config(state=tk.DISABLED)

            # Ensure the results window stays open even if the main window is closed
            self.master.withdraw()

        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while displaying the results:\n{str(e)}")
        finally:
            # Destroy the main window
            self.master.destroy()

    def create_bias_score_chart(self, parent_frame):
        try:
            biases = []
            scores = []
            for bias_name, bias_data in self.biases.items():
                if bias_name in self.bias_scores:
                    bias_score = self.bias_scores[bias_name]
                    num_questions = self.bias_question_counts[bias_name]
                    avg_score = bias_score / num_questions if num_questions else 0
                    biases.append(bias_name)
                    scores.append(avg_score)

            # Create the figure
            fig, ax = plt.subplots(figsize=(8, 6))

            # Create the bar chart
            bars = ax.barh(biases, scores, color='skyblue')

            # Add labels and title
            ax.set_xlabel('Average Score')
            ax.set_title('Your Bias Scores')

            # Adjust layout
            fig.tight_layout()

            # Embed the chart in the Tkinter window
            canvas = FigureCanvasTkAgg(fig, master=parent_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while generating the chart:\n{str(e)}")

    def get_overall_interpretation(self, score):
        if score >= 80:
            return f"Your Overall Score: {score:.2f}\n\nYou exhibit strong tendencies towards certain cognitive biases. Being aware of these can help you make more objective decisions."
        elif 60 <= score < 80:
            return f"Your Overall Score: {score:.2f}\n\nYou have moderate tendencies in some cognitive biases. Reflecting on these can enhance your critical thinking."
        elif 40 <= score < 60:
            return f"Your Overall Score: {score:.2f}\n\nYou have a balanced perspective with some awareness of cognitive biases."
        elif 20 <= score < 40:
            return f"Your Overall Score: {score:.2f}\n\nYou exhibit low tendencies towards cognitive biases. This indicates strong critical thinking skills."
        else:
            return f"Your Overall Score: {score:.2f}\n\nYou have very low tendencies towards cognitive biases, demonstrating exceptional objectivity."

    def get_bias_interpretation(self, avg_score):
        if avg_score >= 1.5:
            return "High tendency towards this bias."
        elif 0.5 <= avg_score < 1.5:
            return "Moderate tendency towards this bias."
        elif -0.5 < avg_score < 0.5:
            return "Balanced perspective on this bias."
        elif -1.5 < avg_score <= -0.5:
            return "Low tendency towards this bias."
        else:
            return "Very low tendency towards this bias."

# Function to load biases from JSON file
def load_biases_from_json(file_path):
    with open(file_path, 'r') as file:
        biases = json.load(file)
    return biases

# Run the GUI test
if __name__ == "__main__":
    try:
        biases = load_biases_from_json('biases.json')
        root = tk.Tk()
        app = BiasTestGUI(root, biases)
        root.mainloop()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to start the application:\n{str(e)}")
