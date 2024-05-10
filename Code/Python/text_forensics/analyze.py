import nltk
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import spacy

# Load a larger model for more comprehensive syntactic parsing
nlp = spacy.load("en_core_web_md")

def extract_features(text):
    doc = nlp(text)
    # Extract lexical features
    tokens = [token.lemma_ for token in doc if not token.is_stop and not token.is_punct]
    # Extract stylistic features (e.g., punctuation)
    punctuation = [token.text for token in doc if token.is_punct]
    # Extract syntactic features
    pos_tags = [token.pos_ for token in doc]
    return tokens, punctuation, pos_tags

def vectorize_text(tokens):
    vectorizer = TfidfVectorizer()
    return vectorizer.fit_transform([' '.join(tokens)])

def main():
    text1 = "Read the first text file or string."
    text2 = "Read the second text file or string."
    
    tokens1, punct1, pos_tags1 = extract_features(text1)
    tokens2, punct2, pos_tags2 = extract_features(text2)
    
    # Vectorize only tokens for now
    vector1 = vectorize_text(tokens1)
    vector2 = vectorize_text(tokens2)
    
    # Calculate cosine similarity on vectorized tokens
    score = cosine_similarity(vector1, vector2)
    print(f"Similarity Score: {score}")

if __name__ == "__main__":
    main()
