from collections import Counter
import string
import re

def read_file(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        return file.read()

def clean_and_tokenize(text):
    text = text.lower()
    text = re.sub(f'[{string.punctuation}]', '', text)
    return text.split()

def count_punctuation(text):
    return Counter(c for c in text if c in string.punctuation)

def common_sentence_starters(text):
    sentences = re.split(r'(?<=[.!?]) +', text)
    starters = [sentence.split()[0].lower() if len(sentence.split()) > 0 else '' for sentence in sentences]
    return Counter(starters)

def text_statistics(text):
    words = clean_and_tokenize(text)
    punctuation_counts = count_punctuation(text)
    sentence_starters = common_sentence_starters(text)
    word_counts = Counter(words)
    
    return {
        "word_count": len(words),
        "punctuation_counts": punctuation_counts,
        "most_common_words": word_counts.most_common(10),
        "most_common_sentence_starters": sentence_starters.most_common(5)
    }

def print_statistics(stats, title):
    print(f"\n=== {title} ===")
    print(f"Word Count: {stats['word_count']}")
    print("Punctuation Counts:")
    for punct, count in stats['punctuation_counts'].items():
        print(f"  {punct}: {count}")
    print("Most Common Words:")
    for word, count in stats['most_common_words']:
        print(f"  {word}: {count}")
    print("Most Common Sentence Starters:")
    for starter, count in stats['most_common_sentence_starters']:
        print(f"  {starter}: {count}")

def compare_texts(file1, file2):
    text1 = read_file(file1)
    text2 = read_file(file2)

    stats1 = text_statistics(text1)
    stats2 = text_statistics(text2)

    print_statistics(stats1, f"Statistics for {file1}")
    print_statistics(stats2, f"Statistics for {file2}")

# Usage example:
compare_texts('text1.txt', 'text2.txt')
