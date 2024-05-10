import nltk
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from joblib import dump

# Example data preparation
texts = ["Text from author A...", "Text from author B...", "More text from author A...", "More text from author B..."]
authors = ["Author A", "Author B", "Author A", "Author B"]

# Vectorize text data
vectorizer = TfidfVectorizer(max_features=1000)
X = vectorizer.fit_transform(texts)
y = authors

# Split the data into training and testing sets
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train the model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Evaluate the model
predictions = model.predict(X_test)
print(classification_report(y_test, predictions))

# Save the trained model and the vectorizer
dump(model, 'authorship_model.joblib')
dump(vectorizer, 'tfidf_vectorizer.joblib')

print("Model and vectorizer saved successfully.")
