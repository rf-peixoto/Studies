import os
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import LeaveOneOut
from joblib import dump, load
from sklearn.metrics.pairwise import cosine_similarity

def read_texts_from_files(directory):
    texts = []
    authors = []
    for filename in os.listdir(directory):
        author = filename.replace('.txt', '')  # Remove the file extension to get the author's name
        filepath = os.path.join(directory, filename)
        with open(filepath, 'r', encoding='utf-8') as file:
            for line in file:
                texts.append(line.strip())  # Add the text
                authors.append(author)  # Add the corresponding author
    return texts, authors

def main():
    directory = 'texts'  # Directory where text files are stored
    texts, authors = read_texts_from_files(directory)
    
    # New texts for comparison (could also be read from a file)
    new_text1 = "Example new text 1."
    new_text2 = "Example new text 2."

    # All texts (old + new) for fitting vectorizer
    all_texts = texts + [new_text1, new_text2]

    # Fit the vectorizer on all texts
    vectorizer = TfidfVectorizer(max_features=1000)
    vectorizer.fit(all_texts)

    # Transform texts
    X = vectorizer.transform(texts)
    y = np.array(authors)  # Ensure y is a numpy array for indexing

    # Prepare leave-one-out cross-validation
    loo = LeaveOneOut()

    # Cross-validation loop
    for train_index, test_index in loo.split(X):
        X_train, X_test = X[train_index], X[test_index]
        y_train, y_test = y[train_index], y[test_index]

        # Train the model
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)

        # Evaluate the model
        predictions = model.predict(X_test)
        print(classification_report(y_test, predictions, zero_division=0))

    # Save the trained model and the vectorizer
    dump(model, 'authorship_model.joblib')
    dump(vectorizer, 'tfidf_vectorizer.joblib')
    print("Model and vectorizer saved successfully.")

    # Transform new texts for similarity
    vector1 = vectorizer.transform([new_text1])
    vector2 = vectorizer.transform([new_text2])

    # Calculate cosine similarity
    score = cosine_similarity(vector1, vector2)[0][0]
    print(f"Similarity Score between Text 1 and Text 2: {score:.2f}")

if __name__ == "__main__":
    main()
