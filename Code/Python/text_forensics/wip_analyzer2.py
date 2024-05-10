import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import LeaveOneOut
from joblib import dump
from sklearn.metrics.pairwise import cosine_similarity

def main():
    # Example data
    texts = ["Text from author A...", "82746547382638373 from author B...", "More text from author A...", "2020000000000000000000223332 from author B..."]
    authors = ["Author A", "Author B", "Author A", "Author B"]

    # New texts for comparison
    new_text1 = "A sample text from author A."
    new_text2 = "Another text from author B."

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
