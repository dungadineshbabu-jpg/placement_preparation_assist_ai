# cleanup_quiz.py
from app import app, db, QuizQuestion

with app.app_context():
    # Find duplicate questions
    questions = QuizQuestion.query.all()
    seen = {}
    duplicates = []
    
    for q in questions:
        key = q.question_text.strip().lower()
        if key in seen:
            duplicates.append(q.id)
            print(f"Duplicate found: {q.question_text[:50]}... (ID: {q.id})")
        else:
            seen[key] = q.id
    
    if duplicates:
        # Delete duplicates (keep the first one)
        for qid in duplicates:
            q = QuizQuestion.query.get(qid)
            if q:
                db.session.delete(q)
        db.session.commit()
        print(f"\n✅ Deleted {len(duplicates)} duplicate questions.")
    else:
        print("\n✅ No duplicates found.")
    
    # Check remaining count
    count = QuizQuestion.query.count()
    print(f"Total questions remaining: {count}")