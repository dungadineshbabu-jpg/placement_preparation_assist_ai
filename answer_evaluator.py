# answer_evaluator.py
# Smart answer evaluation for interview responses

import re
from collections import Counter

# -------------------------------------------------------------------
# Optional: load a spell-checker if available
try:
    from spellchecker import SpellChecker
    _spell = SpellChecker()
except Exception:
    _spell = None


def _word_count(text):
    return len(text.split())


def _has_numbers(text):
    return bool(re.search(r'\d', text))


def _has_examples(text):
    markers = ['for example', 'for instance', 'such as', 'e.g.', 'like when',
               'in my project', 'in my internship', 'during my', 'in college',
               'in my team', 'last year', 'recently', 'previously']
    return any(m in text.lower() for m in markers)


def _has_star(text):
    markers = ['situation', 'task', 'action', 'result',
               'first', 'then', 'next', 'finally', 'because', 'therefore']
    return sum(1 for m in markers if m in text.lower()) >= 2


def _has_metrics(text):
    return bool(re.search(r'(\d+%|\d+ percent|\$\d+|₹\d+|\d+ (users|customers|projects|hours|days|weeks|months))', text.lower()))


def _is_technical(text):
    tech_words = ['algorithm', 'code', 'function', 'api', 'database', 'sql',
                  'python', 'java', 'react', 'class', 'object', 'variable',
                  'complexity', 'big-o', 'index', 'query', 'framework', 'library']
    lower = text.lower()
    return sum(1 for w in tech_words if w in lower) >= 2


def _grammar_score(text):
    """Very basic grammar / readability heuristic."""
    if not text.strip():
        return 0
    # Count of sentences that end with punctuation
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 3
    # Penalise sentences that don't start with a capital letter
    capitalised = sum(1 for s in sentences if s[0].isupper())
    ratio = capitalised / len(sentences)
    return round(ratio * 10, 1)


def _keyword_overlap(question, answer):
    """How much does the answer overlap with the question keywords?"""
    stop = {'what','is','the','a','an','of','to','in','on','for','and','or','why','how',
            'tell','me','about','you','your','yourself','please','briefly','could',
            'would','do','did','are','were','this','that','these','those','it','them'}
    q_words = [w.lower() for w in re.findall(r'\w+', question) if w.lower() not in stop]
    a_words = [w.lower() for w in re.findall(r'\w+', answer)]
    if not q_words:
        return 0
    overlap = sum(1 for w in set(q_words) if w in a_words)
    return overlap / len(set(q_words))


def _spelling_errors(text):
    if _spell is None:
        return []
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
    return list(_spell.unknown(words))


def evaluate_interview_answer(question_text, user_answer, question_type='general'):
    """
    Evaluate an interview answer and return:
      - score (0-10)
      - feedback (specific to the answer)
      - improved_answer (tailored suggestion)
      - clarity_score
      - confidence_score
      - metrics breakdown
    """
    answer = (user_answer or '').strip()
    wc = _word_count(answer)

    # ============ Edge cases ============
    if wc == 0:
        return {
            'score': 0,
            'feedback': "You didn't provide an answer.",
            'improved_answer': "Write a clear response of at least 40–60 words with examples.",
            'clarity_score': 0,
            'confidence_score': 0,
            'metrics': {'words': 0, 'has_example': False, 'has_star': False, 'has_metrics': False},
        }

    if wc < 10:
        return {
            'score': 2,
            'feedback': "Answer is too short. Aim for 40–80 words with a specific example.",
            'improved_answer': "Start with a 1-line intro, then add a concrete example and end with the result.",
            'clarity_score': 3,
            'confidence_score': 2,
            'metrics': {'words': wc, 'has_example': False, 'has_star': False, 'has_metrics': False},
        }

    # ============ Scoring components ============
    # Length (0-3)
    if wc < 20:
        length_score = 1
    elif wc < 40:
        length_score = 2
    elif wc < 80:
        length_score = 3
    else:
        length_score = 3  # longer isn't necessarily better

    # Content (0-4)
    content_score = 0
    has_example = _has_examples(answer)
    has_metrics = _has_metrics(answer)
    has_star = _has_star(answer)
    overlap = _keyword_overlap(question_text, answer)

    if has_example:
        content_score += 1.5
    if has_metrics:
        content_score += 1
    if has_star:
        content_score += 1
    if overlap >= 0.3:
        content_score += 0.5
    content_score = min(content_score, 4)

    # Clarity (0-2)
    grammar = _grammar_score(answer)
    clarity_score = round(grammar / 5, 1)  # scale to 0-2
    clarity_score = min(clarity_score, 2)

    # Confidence (0-1)
    confident_words = ['i led', 'i built', 'i designed', 'i achieved', 'i managed',
                       'i delivered', 'i created', 'i implemented', 'i solved',
                       'i improved', 'i handled', 'i coordinated']
    lower = answer.lower()
    conf_hits = sum(1 for w in confident_words if w in lower)
    confidence_component = min(conf_hits * 0.4, 1)

    raw_score = length_score + content_score + clarity_score + confidence_component
    score = round(min(10, raw_score * 10 / 10), 1)  # already on 0-10 scale

    # ============ Question-type awareness ============
    q_lower = question_text.lower()
    is_intro = 'introduce yourself' in q_lower or 'tell me about yourself' in q_lower
    is_hr = any(k in q_lower for k in ['strength', 'weakness', '5 years', 'salary',
                                       'why should we hire', 'conflict', 'pressure',
                                       'deadline', 'team', 'motivation'])
    is_behavioral = any(k in q_lower for k in ['tell me about a time', 'describe a time',
                                               'give me an example', 'situation where'])
    is_technical = (question_type or '').lower() == 'technical' or _is_technical(answer)

    # ============ Specific Feedback ============
    feedback_parts = []

    if is_intro:
        if not re.search(r'\b(i am|i\'m|my name)\b', lower):
            feedback_parts.append("Start with your name and current role/education.")
        if 'skill' not in lower and 'experience' not in lower and 'project' not in lower:
            feedback_parts.append("Mention 2–3 key skills or experiences.")
        if not has_example:
            feedback_parts.append("Add one specific project or achievement.")
        if wc < 40:
            feedback_parts.append("Aim for 60–90 words (about 30–45 seconds spoken).")
        default_tip = "Structure: Name → Education → Skills/Experience → Why this role."
        improved = (
            "Example: \"I'm Dinesh, a final-year IT student at GMRIT. I've built 3 projects "
            "including a Flask-based placement assistant. I'm strong in Python, SQL, and "
            "React, and I'm excited about the Web Developer role at TCS because it matches "
            "my full-stack experience.\""
        )

    elif is_behavioral or is_hr:
        if not has_star:
            feedback_parts.append("Use the STAR method (Situation → Task → Action → Result).")
        if not has_example:
            feedback_parts.append("Include a concrete example from your past experience.")
        if not has_metrics:
            feedback_parts.append("Quantify the result (e.g., 'reduced time by 30%').")
        default_tip = "STAR method with measurable results works best."
        improved = (
            "Template: \"In my [role/project] (Situation), I had to [task]. "
            "I [action taken]. As a result, [specific measurable outcome].\""
        )

    elif is_technical:
        if overlap < 0.2:
            feedback_parts.append("Your answer drifted from the question. Focus on the exact concept asked.")
        if not re.search(r'\b(example|for instance|such as|complexity|time|space)\b', lower):
            feedback_parts.append("Add a concrete technical example or complexity analysis.")
        if not _has_numbers(answer):
            feedback_parts.append("Mention time/space complexity or a numeric detail.")
        default_tip = "Define the concept → give an example → mention complexity/edge cases."
        improved = (
            "Template: \"[Concept] is [1-line definition]. For example, [real use case]. "
            "Its time complexity is O(...) and space is O(...).\""
        )

    else:
        default_tip = "Be specific: intro → example → result."
        improved = "Provide a 40–80 word answer with at least one concrete example."

    # Length-based feedback
    if wc < 30:
        feedback_parts.append(f"Your answer is only {wc} words. Aim for 40–80.")
    elif wc > 200:
        feedback_parts.append("Answer is quite long. Try to stay under 120 words.")

    # Spelling feedback
    spelling_errs = _spelling_errors(answer)
    if spelling_errs:
        feedback_parts.append(f"Check spelling: {', '.join(spelling_errs[:4])}.")

    # Compose final feedback
    if not feedback_parts:
        if score >= 8:
            feedback_parts.append("Excellent answer! Clear, structured, and specific.")
        elif score >= 6:
            feedback_parts.append("Good answer. You can strengthen it with one more specific detail.")
        else:
            feedback_parts.append(default_tip)

    feedback = " ".join(feedback_parts)

    return {
        'score': score,
        'feedback': feedback,
        'improved_answer': improved,
        'clarity_score': round(clarity_score * 5, 1),   # 0-10 scale
        'confidence_score': round(confidence_component * 10, 1),  # 0-10 scale
        'metrics': {
            'words': wc,
            'has_example': has_example,
            'has_star': has_star,
            'has_metrics': has_metrics,
            'keyword_overlap': round(overlap, 2),
            'grammar': grammar,
        },
    }