# voice_evaluator_ml.py
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
import re

# Training Data (Expanded to recognize short vs long answers)
training_data = [
    ("I led a team of 4 developers to build a web app on time.", "High"),
    ("We achieved a 20% increase in sales by optimizing the code.", "High"),
    ("I solved the bug by debugging the system efficiently.", "High"),
    ("I designed a scalable database architecture for the project.", "High"),
    ("In my last role, I improved the API response time by 40%.", "High"),
    ("I want to get the job.", "Low"),
    ("I am a hard worker.", "Low"),
    ("I like coding.", "Low"),
    ("I don't know the answer to this.", "Low"),
    ("I am a hard worker and I like coding.", "Medium"),
    ("My team built a project using Python.", "Medium"),
    ("I have experience in React and Node.js.", "Medium")
]

texts = [x[0] for x in training_data]
labels = [x[1] for x in training_data]

# Train the model
vectorizer = CountVectorizer()
X = vectorizer.fit_transform(texts)
clf = MultinomialNB()
clf.fit(X, labels)

def evaluate_with_ml(text):
    if not text or len(text.split()) < 5: 
        return 10 # Too short
        
    word_count = len(text.split())
    
    # --- STRICT LENGTH PENALTY ---
    # If the answer is less than 15 words, it's too short for a real interview answer.
    # We cap the score at 40 regardless of what the ML model thinks.
    if word_count < 15:
        return 40
        
    X_test = vectorizer.transform([text])
    prediction = clf.predict(X_test)[0]
    
    # Map prediction to a score out of 10
    if prediction == "High": 
        return 90
    elif prediction == "Medium": 
        return 60
    else: 
        return 30