import re
from rich.console import Console
from rich.prompt import Prompt
from rich import print
import language_tool_python
from pathlib import Path

# Create a tool for checking English grammar
tool = language_tool_python.LanguageTool('en-US')

# Define simple lists of common slangs and abbreviations
common_slangs = {'lol', 'brb', 'btw', 'idk'}
common_abbreviations = {'etc', 'e.g.', 'i.e.', 'vs.'}

def analyze_text(text):
    matches = tool.check(text)
    grammar_errors = len(matches)

    words = re.findall(r'\b\w+\b', text)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    commas = text.count(',')

    slangs_found = sum(1 for word in words if word.lower() in common_slangs)
    abbreviations_found = sum(1 for word in words if word.lower() in common_abbreviations)

    return {
        'total_sentences': len(sentences),
        'total_words': len(words),
        'total_commas': commas,
        'grammar_errors': grammar_errors,
        'slangs_used': slangs_found,
        'abbreviations_used': abbreviations_found
    }

def main():
    console = Console()
    console.print("[bold magenta]Text Authorship Analysis Tool[/bold magenta]\n", style="bold green")

    option = Prompt.ask("Type 'file' to load from a file or 'text' to enter text directly", console=console)
    if option.lower() == 'file':
        file_path = Prompt.ask("Enter the file path", console=console)
        if Path(file_path).is_file():
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read()
        else:
            console.print("File not found. Exiting program.", style="bold red")
            return
    else:
        text = Prompt.ask("Enter or paste the text you want to analyze", console=console)

    results = analyze_text(text)

    console.print("\n[bold underline]Analysis Results:[/bold underline]", style="bold yellow")
    console.print(f"Total Sentences: [bold cyan]{results['total_sentences']}[/bold cyan]")
    console.print(f"Total Words: [bold cyan]{results['total_words']}[/bold cyan]")
    console.print(f"Total Commas: [bold cyan]{results['total_commas']}[/bold cyan]")
    console.print(f"Grammar Errors: [bold cyan]{results['grammar_errors']}[/bold cyan]")
    console.print(f"Slangs Used: [bold cyan]{results['slangs_used']}[/bold cyan]")
    console.print(f"Abbreviations Used: [bold cyan]{results['abbreviations_used']}[/bold cyan]")

if __name__ == "__main__":
    main()
