import sys
import os

# Helper function to display text with color
def print_colored(text, color_code):
    print(f"\033[{color_code}m{text}\033[0m")

# Helper function to clear the terminal screen
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def ask_question(question, options, explanation, current_step, total_steps):
    print("=" * 50)
    print_colored(f"QUESTION {current_step} of {total_steps}: {question}", "36")  # Cyan color for questions
    print(f"Explanation: {explanation}\n")
    for idx, option in enumerate(options, 1):
        print(f"{idx}. {option} (press {idx})")
    print("=" * 50)
    while True:
        try:
            choice = int(input("Choose an option (1/2/3/...): "))
            if 1 <= choice <= len(options):
                return choice
            else:
                print_colored("Invalid choice. Please select a valid option.", "31")  # Red color for errors
        except ValueError:
            print_colored("Invalid input. Please enter a number corresponding to your choice.", "31")

def evaluate_source_reliability(answers):
    score = 0
    score += answers[0]  # Trust level
    score += answers[1]  # Accuracy
    score += 3 - answers[2]  # Bias (reverse score for bias)
    score += answers[3]  # Consistency with past reports

    if score >= 10:
        return "A - Completely Reliable", "32"  # Green
    elif score >= 7:
        return "B - Usually Reliable", "34"  # Blue
    elif score >= 4:
        return "C - Fairly Reliable", "33"  # Yellow
    else:
        return "D - Not Usually Reliable", "31"  # Red

def evaluate_info_credibility(answers):
    score = 0
    score += answers[4]  # Confirmation
    score += answers[5]  # Consistency
    score += answers[6]  # Evidence
    score += answers[7]  # Plausibility

    if score >= 10:
        return "1 - Confirmed", "32"  # Green
    elif score >= 7:
        return "2 - Probably True", "34"  # Blue
    elif score >= 4:
        return "3 - Possibly True", "33"  # Yellow
    else:
        return "4 - Doubtful", "31"  # Red

def evaluate_tlp(answers):
    if answers[8] == 4 or answers[9] == 4 or answers[10] == 1:  # High restriction conditions
        return "TLP:RED - Do not share outside, highly restricted", "31"  # Red
    
    elif answers[8] == 3:  # Specific people
        if answers[9] >= 3 or answers[10] == 1:  # Sensitive or high impact
            return "TLP:AMBER+STRICT - Highly sensitive, share with extreme caution", "33"  # Yellow (Amber Strict)
        else:
            return "TLP:AMBER - Share with caution", "33"  # Yellow
    
    elif answers[8] == 2:  # Specific group or community
        return "TLP:GREEN - Share within the community", "32"  # Green

    elif answers[8] == 1:  # Anyone
        return "TLP:WHITE - Share freely", "37"  # White

    else:
        return "TLP:AMBER - Share with caution", "33"  # Yellow

def main():
    clear_screen()
    print_colored("WELCOME TO THE REPORT CLASSIFICATION HELPER", "35")  # Magenta for the title
    print("=" * 50)
    print("Answer the following questions to classify your report.")
    print("=" * 50)

    questions = [
        ("How much do you trust the source of this information?",
         ["High trust", "Medium trust", "Low trust", "Don't know"],
         "Consider how reliable this source has been in the past."),
        ("How often has this source provided accurate information?",
         ["Always", "Sometimes", "Rarely", "Don't know"],
         "Think about the history of this source's information."),
        ("Is the source known to have a bias?",
         ["No, never", "Yes, sometimes", "Yes, often", "Don't know"],
         "Bias can affect the accuracy and objectivity of information."),
        ("Does the source consistently report similar information?",
         ["Yes, consistently", "Sometimes", "No, often varies", "Don't know"],
         "Consistent reporting can indicate reliability."),
        ("Is this information confirmed by other reliable sources?",
         ["Yes, fully confirmed", "Partially confirmed", "Not confirmed", "Don't know"],
         "Confirmation by other sources adds credibility."),
        ("Does this information align with what you know or common sense?",
         ["Yes, fully aligns", "Somewhat aligns", "No, contradicts known facts", "Don't know"],
         "Alignment with existing knowledge suggests reliability."),
        ("Is there strong evidence or data to support this information?",
         ["Yes, strong evidence", "Some evidence", "No evidence", "Don't know"],
         "Evidence backing is critical for credibility."),
        ("Does this information seem logical and plausible?",
         ["Yes, completely logical", "Somewhat plausible", "No, seems implausible", "Don't know"],
         "Plausible information is more likely to be accurate."),
        ("Who can see this information?",
         ["Anyone", "Specific group or community", "Only specific people", "Only very trusted individuals"],
         "Decide who should access this based on its sensitivity."),
        ("What happens if this information is shared with the wrong people?",
         ["Nothing serious", "Might cause minor issues", "Could cause serious problems", "Will cause major issues"],
         "Consider potential consequences of sharing this information."),
        ("Does this information contain personal or sensitive data?",
         ["Yes", "No"],
         "Personal or sensitive data should be handled with care.")
    ]

    answers = []
    total_steps = len(questions)
    for idx, (question, options, explanation) in enumerate(questions, 1):
        answer = ask_question(question, options, explanation, idx, total_steps)
        if answer < 4:
            answers.append(answer)
        else:
            answers.append(1)  # Neutral score for "Don't know"
        clear_screen()  # Clear screen between questions for a clean UI

    source_reliability, sr_color = evaluate_source_reliability(answers)
    info_credibility, ic_color = evaluate_info_credibility(answers)
    tlp, tlp_color = evaluate_tlp(answers)

    print("\n" + "=" * 50)
    print_colored("CLASSIFICATION RESULTS", "35")  # Magenta for results header
    print("=" * 50)
    print_colored(f"Source Reliability: {source_reliability}", sr_color)
    print_colored(f"Information Credibility: {info_credibility}", ic_color)
    print_colored(f"TLP Classification: {tlp}", tlp_color)
    print("=" * 50)
    print_colored("Recommended Actions:", "35")
    print("- Ensure sensitive information is encrypted.")
    print("- Limit sharing to authorized personnel only.")
    print("- Refer to the organization's data handling policy for further guidelines.")
    print("=" * 50)

if __name__ == "__main__":
    main()
