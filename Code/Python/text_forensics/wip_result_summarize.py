import re
import numpy as np

# Example classification report (You would replace this string with the output from your model)
classification_report_output = """
              precision    recall  f1-score   support

    Author A       0.00      0.00      0.00       1.0
    Author B       0.00      0.00      0.00       0.0

    accuracy                           0.00       1.0
   macro avg       0.00      0.00      0.00       1.0
weighted avg       0.00      0.00      0.00       1.0
"""

def parse_classification_report(report):
    """Parse the sklearn classification report to a dictionary."""
    lines = report.split('\n')
    report_data = []
    for line in lines[2:-5]:  # Avoid summary lines
        row = {}
        parts = line.split()
        if len(parts) == 5:  # Valid lines of data
            row['class'] = parts[0]
            row['precision'] = float(parts[1])
            row['recall'] = float(parts[2])
            row['f1_score'] = float(parts[3])
            row['support'] = float(parts[4])
            report_data.append(row)
    return report_data

def summarize_results(parsed_report):
    """Generate a human-readable summary of the classification report."""
    summary = []
    for row in parsed_report:
        summary.append(f"Class {row['class']} has a precision of {row['precision']*100:.2f}%, "
                       f"recall of {row['recall']*100:.2f}%, and f1-score of {row['f1_score']*100:.2f}%. "
                       f"Support (number of samples): {int(row['support'])}.")
    if not summary:
        return "No valid data to summarize."
    return "\n".join(summary)

def analyze_report(report):
    """Analyze the classification report and provide insights."""
    parsed_report = parse_classification_report(report)
    summary = summarize_results(parsed_report)
    print("Summary of Classification Report:")
    print(summary)
    # Additional analysis or recommendations based on the parsed data
    low_recall = [row for row in parsed_report if row['recall'] < 0.5]
    if low_recall:
        print("\nRecommendations:")
        for row in low_recall:
            print(f"Class {row['class']} has low recall ({row['recall']*100:.2f}%). Consider gathering more samples or reviewing feature selection.")

# Example usage
analyze_report(classification_report_output)
