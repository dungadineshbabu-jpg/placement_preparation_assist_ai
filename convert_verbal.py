import json
import os

# Get the absolute path to the project directory
base_dir = os.path.dirname(os.path.abspath(__file__))
verbal_path = os.path.join(base_dir, 'data', 'verbal.json')

try:
    # 1. Load the existing verbal.json (utf-8-sig removes the BOM character)
    with open(verbal_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    # 2. Extract the questions array
    questions = data.get('questions', [])

    converted = []
    for q in questions:
        opts = q.get('options', {})
        
        # Convert options dict {A, B, C, D} to a list [Opt A, Opt B, Opt C, Opt D]
        option_list = [
            opts.get('A', ''), 
            opts.get('B', ''), 
            opts.get('C', ''), 
            opts.get('D', '')
        ]
        
        # Find the actual text of the correct answer (e.g., if correct_answer is "C", get options["C"])
        correct_letter = q.get('correct_answer', 'A')
        correct_text = opts.get(correct_letter, '')
        
        # Create the new formatted question
        converted.append({
            "q": q.get('question', ''),
            "options": option_list,
            "ans": correct_text
        })

    # 3. Overwrite the file with the corrected simple format
    with open(verbal_path, 'w', encoding='utf-8') as f:
        json.dump(converted, f, indent=2, ensure_ascii=False)

    print(f"✅ Successfully converted {len(converted)} verbal questions to the correct format!")

except Exception as e:
    print(f"❌ Error: {e}")