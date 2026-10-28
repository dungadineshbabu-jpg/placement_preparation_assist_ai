import random
import json

# Add this import at the top of ai_engine.py
from answer_evaluator import evaluate_interview_answer

class AIEngine:
    """Core AI Engine for the Placement Preparation Assistant"""

    # ========== INTERVIEW ROUNDS ==========
    @staticmethod
    def generate_round_questions(company, job_role, user_skills, missing_skills, weak_areas):
        """Generate a structured interview with rounds (Introduction, HR, Technical, Non-Technical)"""
        rounds = {
            "introduction": {
                "name": "Introduction",
                "questions": [
                    f"Hello! I'm your interviewer from {company}. Could you please introduce yourself briefly?",
                    f"What brings you to apply for the {job_role} position at {company}?",
                    f"Tell me something about yourself that is not on your resume."
                ]
            },
            "hr": {
                "name": "HR Round",
                "questions": [
                    "What are your greatest strengths and weaknesses?",
                    "Where do you see yourself in 5 years?",
                    "Why should we hire you over other candidates?",
                    "Describe a time you faced a conflict at work and how you resolved it.",
                    "How do you handle pressure and tight deadlines?",
                    "What is your salary expectation?"
                ]
            },
            "technical": {
                "name": "Technical Round",
                "questions": []
            },
            "non_technical": {
                "name": "Non-Technical / Problem Solving",
                "questions": [
                    "If you had unlimited resources, what problem would you solve?",
                    "How would you explain a complex technical concept to a non-technical person?",
                    "Describe a situation where you had to learn something new quickly.",
                    "How do you prioritize tasks when everything is urgent?",
                    "Tell me about a time you failed and what you learned."
                ]
            }
        }

        # Generate technical questions based on job role
        tech_questions = {
            'software engineer': [
                "Explain the difference between arrays and linked lists. When would you use each?",
                "What are the four pillars of Object-Oriented Programming? Explain with examples.",
                "How does garbage collection work in languages like Java/Python?",
                "Explain the concept of time complexity. What is Big O notation?",
                "What is the difference between TCP and UDP? Give use cases.",
                "How would you design a URL shortening service like TinyURL?",
                "Explain the difference between SQL and NoSQL databases.",
                "What is a deadlock? How can you prevent it?",
                "Explain the difference between process and thread.",
                "What is REST API? List the main HTTP methods."
            ],
            'data analyst': [
                "Explain the difference between INNER JOIN and LEFT JOIN with examples.",
                "What is the difference between correlation and causation?",
                "How would you handle missing values in a dataset?",
                "Explain the process of data cleaning and preprocessing.",
                "What is the difference between pandas and numpy?",
                "How would you identify outliers in a dataset?",
                "Explain the difference between supervised and unsupervised learning.",
                "What is data normalization and why is it important?",
                "How would you create a dashboard to track KPIs?",
                "Explain the difference between variance and standard deviation."
            ],
            'web developer': [
                "Explain the difference between localStorage and sessionStorage.",
                "What is the virtual DOM and how does React use it?",
                "Explain the difference between HTTP GET and POST methods.",
                "What is CORS and how do you handle it?",
                "How does responsive web design work?",
                "Explain event delegation in JavaScript.",
                "What is the difference between flexbox and grid?",
                "How do you optimize website loading speed?",
                "Explain the concept of promises in JavaScript.",
                "What are web sockets and when would you use them?"
            ]
        }

        role_lower = job_role.lower()
        tech_q_list = tech_questions.get('software engineer', [])  # default
        for role, qlist in tech_questions.items():
            if role in role_lower:
                tech_q_list = qlist
                break

        # Add missing skills questions as technical
        for skill in missing_skills[:3]:
            tech_q_list.append(f"Explain your experience with {skill} and how you would apply it in this role.")

        # Add weak areas questions
        for weak in weak_areas[:2]:
            tech_q_list.append(f"I see you may need improvement in {weak}. Can you tell me how you plan to strengthen this area?")

        # Shuffle and take up to 10 technical questions
        random.shuffle(tech_q_list)
        rounds["technical"]["questions"] = tech_q_list[:10]

        # Ensure each round has at least 3 questions (but max 5)
        for r in rounds.values():
            if len(r["questions"]) < 3:
                r["questions"] = r["questions"] * 3
            r["questions"] = r["questions"][:5]  # max 5 per round

        return rounds

    # ========== FOLLOW-UP QUESTIONS ==========
    @staticmethod
    def generate_follow_up(question_text, user_answer, round_type):
        """Generate a contextual follow-up question based on user's answer and round type"""
        answer_lower = user_answer.lower()

        if round_type == "introduction":
            if "project" in answer_lower or "experience" in answer_lower:
                return "That sounds interesting. Could you tell me more about that project and your specific role in it?"
            elif "student" in answer_lower or "graduate" in answer_lower:
                return "Great. What motivated you to pursue this field, and what are you most passionate about?"
            else:
                return "Thank you. What makes you excited about working with us?"

        elif round_type == "hr":
            if "weakness" in question_text.lower():
                return "How are you working to overcome that weakness?"
            elif "conflict" in question_text.lower():
                return "What did you learn from that experience?"
            elif "pressure" in question_text.lower():
                return "Can you give a specific example of a high-pressure situation you handled well?"
            else:
                return "Interesting. Could you elaborate with a specific example?"

        elif round_type == "technical":
            if "explain" in question_text.lower():
                return "Can you give a practical example of how you've used that concept?"
            else:
                return "How would you approach solving that problem in a real-world scenario?"

        else:  # non_technical
            return "That's a good point. Anything else you'd like to add?"

    # ========== CONVERSATIONAL EVALUATION ==========
    @staticmethod
    def evaluate_conversational(answer):
        """Evaluate answer based on length and keyword richness (simple but effective)"""
        word_count = len(answer.split())
        if word_count < 10:
            score = max(0, word_count / 10 * 5)
        else:
            score = min(10, 5 + (word_count - 10) / 30 * 5)
        score = round(score, 1)

        if score >= 8:
            feedback = "Excellent! Very clear and detailed."
        elif score >= 5:
            feedback = "Good answer. Could add a bit more detail or examples."
        else:
            feedback = "Your answer was brief. Try to elaborate more with specific examples."

        return score, feedback

    # ========== LEGACY METHODS (Backward Compatibility) ==========
    @staticmethod
    def generate_questions(company, job_role, missing_skills, weak_areas):
        """Generate a flat list of interview questions (used by text mock interview)"""
        rounds = AIEngine.generate_round_questions(company, job_role, [], missing_skills, weak_areas)
        all_q = []
        for r in rounds.values():
            for q in r["questions"]:
                all_q.append({"text": q, "type": r["name"].lower().replace(" round", "")})
        return all_q[:15]

    @staticmethod
    def evaluate_answer(question_text, user_answer, question_type):
        """Evaluate an answer using the smarter content-aware evaluator."""
        return evaluate_interview_answer(question_text, user_answer, question_type)

    # ========== ROLE-BASED ROADMAP GENERATION ==========
    @staticmethod
    def generate_roadmap(weak_areas, missing_skills, company, job_role, avg_score):
        """Generate a 4-week personalized study roadmap based on actual weak areas"""
        
        # Clean up weak areas (remove the "Missing " prefix to get actual skills)
        clean_weak = []
        for w in weak_areas:
            # If it says "Missing Java", extract "Java"
            if w.lower().startswith("missing "):
                clean_weak.append(w[8:].strip())
            else:
                clean_weak.append(w.strip())
                
        # Combine clean weak areas and missing skills
        topics = clean_weak + [f"{s}" for s in missing_skills[:3]]
        
        # If no topics found, provide specific defaults based on role
        if not topics or all(t in ["technical skills", "problem solving", "communication"] for t in topics):
            if 'software' in job_role.lower() or 'developer' in job_role.lower():
                topics = ["Data Structures", "Algorithms", "System Design", "SQL & Databases", "Git & Version Control"]
            elif 'data' in job_role.lower():
                topics = ["SQL", "Python for Data Science", "Statistics", "Data Visualization", "Pandas & NumPy"]
            else:
                topics = ["Core Technical Concepts", "Problem Solving", "System Design", "Communication Skills"]

        # Deduplicate topics
        seen = set()
        topics = [x for x in topics if not (x.lower() in seen or seen.add(x.lower()))]

        roadmap = {
            "week1": {
                "focus": f"Foundation & Core Concepts for {job_role}",
                "daily_plan": [
                    f"Day 1-2: Deep dive into {topics[0]}",
                    f"Day 3-4: Study {topics[1] if len(topics)>1 else 'Algorithms'}",
                    f"Day 5: Review weak areas: {topics[2] if len(topics)>2 else 'Problem Solving'}",
                    f"Day 6-7: Practice mock interviews & review {company} interview patterns"
                ]
            },
            "week2": {
                "focus": "Practical Application & Mock Interviews",
                "daily_plan": [
                    "Day 8-9: Solve medium problems on LeetCode related to your weak topics",
                    "Day 10-11: Practice system design / architecture (if applicable)",
                    "Day 12-13: Take 2 mock interviews (use our Face-to-Face module)",
                    "Day 14: Revise HR answers and company-specific questions"
                ]
            },
            "week3": {
                "focus": "Advanced Topics & Weak Area Elimination",
                "daily_plan": [
                    f"Day 15-16: Deep dive into {topics[0]} advanced concepts",
                    "Day 17-18: Practice coding under time constraints (30 min each)",
                    "Day 19-20: Review previous mistakes and improve based on feedback",
                    "Day 21: Full-length mock interview with self-evaluation"
                ]
            },
            "week4": {
                "focus": "Final Polish & Confidence Building",
                "daily_plan": [
                    "Day 22-23: Solve previously incorrect problems",
                    "Day 24-25: Practice HR/behavioral questions with STAR method",
                    "Day 26-27: Research company culture and prepare questions for interviewer",
                    "Day 28: Final revision, relaxation, and confidence boosting"
                ]
            }
        }
        platforms = [
            "LeetCode (focus on easy-medium problems related to your weak areas)",
            f"HackerRank ({company}-specific preparation kits)",
            "GeeksforGeeks (topic-wise practice)"
        ]
        return roadmap, platforms