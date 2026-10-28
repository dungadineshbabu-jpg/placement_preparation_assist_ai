from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import make_pipeline
import os
import pickle

# 1. Training Data (Questions users might ask mapped to Intents)
training_data = [
    # Skills
    ("What skills do I need?", "skills"),
    ("What are the required skills for this role?", "skills"),
    ("Tell me the tech stack I should learn", "skills"),
    ("What technologies should I know?", "skills"),
    
    # Resume
    ("How can I improve my resume?", "resume"),
    ("Fix my CV", "resume"),
    ("Is my resume good?", "resume"),
    ("Resume tips for placement", "resume"),
    
    # Preparation
    ("How should I prepare?", "preparation"),
    ("Give me a study plan", "preparation"),
    ("What should I study today?", "preparation"),
    ("How to crack the interview?", "preparation"),
    ("I have an interview tomorrow what to do", "preparation"),
    
    # Company Culture
    ("Tell me about the company culture", "culture"),
    ("What are the company values?", "culture"),
    ("What is TCS known for?", "culture"),
    ("How is the work environment?", "culture"),
    
    # Weak Areas
    ("What are my weak areas?", "weak_areas"),
    ("Where do I need improvement?", "weak_areas"),
    ("What am I lacking?", "weak_areas"),
    
    # Technical
    ("Explain DBMS", "technical"),
    ("What is normalization?", "technical"),
    ("Tell me about OOPs concepts", "technical"),
    ("What is a binary search tree?", "technical"),
    
    # HR
    ("Tell me about yourself", "hr"),
    ("How to answer strengths and weaknesses?", "hr"),
    ("What is the STAR method?", "hr"),
    
    # Greeting
    ("Hi", "greeting"),
    ("Hello mentor", "greeting"),
    ("Hey", "greeting")
]

def train_model():
    """Trains the ML model and saves it to disk."""
    print("🤖 Training the Mentor ML Model...")
    # Extract texts and labels
    texts = [item[0].lower() for item in training_data]
    labels = [item[1] for item in training_data]
    
    # Create a Pipeline: TF-IDF (converts text to numbers) + Naive Bayes (classifier)
    model = make_pipeline(TfidfVectorizer(ngram_range=(1, 2)), MultinomialNB())
    
    # Train the model
    model.fit(texts, labels)
    
    # Save the model to a file
    with open('mentor_model.pkl', 'wb') as f:
        pickle.dump(model, f)
    print("✅ Model trained and saved as mentor_model.pkl")
    return model

def predict_intent(user_question):
    """Loads the model and predicts the intent of the user's question."""
    if not os.path.exists('mentor_model.pkl'):
        # Train if it doesn't exist
        model = train_model()
    else:
        # Load existing model
        with open('mentor_model.pkl', 'rb') as f:
            model = pickle.load(f)
            
    # Predict the intent
    intent = model.predict([user_question.lower()])[0]
    return intent