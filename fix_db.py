import sqlite3

def fix():
    conn = sqlite3.connect('instance/placement_assistant.db')
    cursor = conn.cursor()
    try:
        # Add the new column
        cursor.execute("ALTER TABLE quiz_attempt ADD COLUMN question_ids TEXT")
        print("✅ Successfully added question_ids column!")
    except sqlite3.OperationalError:
        print("⚠️ Column already exists, skipping.")
    conn.commit()
    conn.close()

if __name__ == '__main__':
    fix()