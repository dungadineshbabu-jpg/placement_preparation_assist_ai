from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import json
import PyPDF2
from datetime import datetime, date
import random
import logging
import hashlib
import datetime as dt
import re
import tempfile

# Groq import removed
from database import db, User, ResumeAnalysis, InterviewQuestion, AnswerEvaluation, WeakArea, Roadmap, UserProgress, ResumeData
from database import CompanyPlacement, JobApplication, Certificate, GroupDiscussion, CodingContest, Achievement, CompanyResume, ResumeVersion
from database import QuizQuestion, QuizAttempt
from database import DailyCodingChallenge
from database import AptitudeResult
from resume_parser import ResumeParser
from ai_engine import AIEngine
from company_resume_optimizer import CompanyResumeOptimizer
from email_utils import generate_verification_token, confirm_verification_token

# ========== ML IMPORTS ==========
from mentor_ml_model import predict_intent
from voice_evaluator_ml import evaluate_with_ml

# ========== LOGGING ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== FLASK APP INIT WITH ABSOLUTE PATHS (FIXES RENDER TEMPLATE NOT FOUND) ==========
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, 
            template_folder=os.path.join(basedir, 'templates'),
            static_folder=os.path.join(basedir, 'static'))

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))

# ========== VERCEL/RENDER COMPATIBLE DATABASE PATH ==========
# Uses /tmp so the database can be written to on read-only cloud servers
db_path = os.path.join(tempfile.gettempdir(), 'placement_assistant.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(tempfile.gettempdir(), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {'pdf', 'txt'}

# ========== LOCAL EVALUATOR (No API Key Needed) ==========
def local_evaluate_answer(user_answer, question_text=""):
    """
    Evaluates an interview answer locally using NLP heuristics.
    Returns a score out of 10, detailed feedback, and a suggested improved answer.
    """
    if not user_answer or len(user_answer.strip()) < 5:
        return {
            'score': 0, 
            'feedback': 'Your answer is too short. Please write at least a sentence.',
            'improved_answer': 'Try using the STAR method (Situation, Task, Action, Result) to give a complete answer.',
            'clarity_score': 0,
            'confidence_score': 0
        }

    answer_lower = user_answer.lower()
    words = re.findall(r'\b\w+\b', answer_lower)
    word_count = len(words)

    # --- NEW: Gibberish Checker ---
    has_vowel = any(char in 'aeiou' for char in answer_lower)
    is_gibberish = bool(re.search(r'[bcdfghjklmnpqrstvwxz]{5,}', answer_lower))

    if not has_vowel or is_gibberish:
        return {
            'score': 0,
            'feedback': '❌ This answer appears to be random keyboard characters or gibberish. Please write a valid English response.',
            'improved_answer': 'Try using the STAR method: Explain the **Situation**, the **Task**, the **Action**, and the **Result**.',
            'clarity_score': 0,
            'confidence_score': 0
        }

    # 1. Base Score for giving an answer (Max 4 points)
    if word_count < 10: base_score = 2
    elif word_count < 20: base_score = 3
    else: base_score = 4

    # 2. Structure / STAR Method Score (Max 3 points)
    star_words = ['situation', 'task', 'action', 'result', 'first', 'second', 'then', 'finally', 'because', 'therefore', 'example', 'achieved', 'led', 'managed']
    found_star = sum(1 for w in star_words if w in words)
    structure_score = min(3, found_star)

    # 3. Technical Depth Score (Max 3 points)
    tech_words = ['api', 'database', 'system', 'design', 'code', 'project', 'experience', 'team', 'algorithm', 'framework', 'development', 'solution', 'testing', 'web', 'frontend', 'react']
    found_tech = sum(1 for w in tech_words if w in words)
    tech_score = min(3, found_tech)

    # Calculate Final Score (out of 10)
    final_score = base_score + structure_score + tech_score
    final_score = min(10, final_score)

    # Generate Feedback
    if final_score >= 8:
        feedback = "Excellent! Your answer is detailed, well-structured, and technically sound."
    elif final_score >= 5:
        feedback = "Good answer. You covered the basics, but could add more specific technical details or real-world examples."
    else:
        feedback = "This answer is a bit brief. To score higher, try explaining the 'how' and 'why' of your actions."

    improved = "To improve, use the STAR method: Explain the **Situation**, the **Task** you had to do, the **Action** you took, and the **Result** you achieved."

    clarity_score = min(10, (base_score * 2) + (structure_score * 1))
    confidence_score = min(10, (word_count / 10) + (structure_score * 1.5))

    return {
        'score': final_score,
        'feedback': feedback,
        'improved_answer': improved,
        'clarity_score': round(clarity_score, 1),
        'confidence_score': round(confidence_score, 1)
    }

# ========== HELPER FUNCTIONS ==========
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

CERT_ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
def allowed_cert_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in CERT_ALLOWED_EXTENSIONS

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ========== DATABASE INIT ==========
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

resume_optimizer = CompanyResumeOptimizer()

def extract_text_from_pdf(file_path):
    text = ""
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text()
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
    return text

def award_badge(user_id, badge_name, badge_type):
    existing = Achievement.query.filter_by(user_id=user_id, badge_name=badge_name).first()
    if not existing:
        badge = Achievement(user_id=user_id, badge_name=badge_name, badge_type=badge_type)
        db.session.add(badge)
        db.session.commit()

def evaluate_code_quality(code):
    score = 50
    if len(code.strip()) > 100: score += 10
    if 'def' in code or 'function' in code: score += 15
    if 'return' in code: score += 10
    if '#' in code or '//' in code: score += 5
    if 'try' in code or 'except' in code: score += 10
    return min(100, score)

def verify_answer_with_ai(question, answer):
    # Purely local check, no Groq needed
    if re.search(r'(.)\1{3,}', answer) or len(set(answer.replace(" ", ""))) < 5:
        return False
    return True

def is_meaningful_answer(answer, question_text=""):
    if not answer or len(answer.strip()) < 5:
        return False, "Your answer is too short. Please provide a proper response."
    lower = answer.lower().strip()
    nonsense_phrases = ["i love you","i dont know","idk","nothing","no","yes","hi","hello","hey","abc","xyz","test","asdf","lorem ipsum","blah","whatever","ok","okay","i dont care","i don't care","nothing to say"]
    if lower in nonsense_phrases:
        return False, "This is not a valid interview answer. Please try again with a real response."
    if not any(c.isalpha() for c in answer):
        return False, "Please write a meaningful answer."
    words = lower.split()
    if len(words) >= 3 and len(set(words)) == 1:
        return False, "Please provide a proper answer, not repeated words."
    if question_text:
        if not verify_answer_with_ai(question_text, answer):
            return False, "This answer appears to be random gibberish. Please write a valid English response."
    return True, ""

def get_quiz_categories_from_resume(user_id):
    analysis = ResumeAnalysis.query.filter_by(user_id=user_id).first()
    if not analysis: return [], []
    skills = json.loads(analysis.skills) if analysis.skills else []
    skills_lower = [s.lower() for s in skills]
    keyword_map = {
        'html':'Web','css':'Web','javascript':'Web','react':'Web','angular':'Web','vue':'Web','node.js':'Web','node':'Web','bootstrap':'Web','jquery':'Web','typescript':'Web',
        'sql':'Data','mysql':'Data','postgresql':'Data','mongodb':'Data','oracle':'Data','database':'Data','excel':'Data','tableau':'Data','power bi':'Data','pandas':'Data','numpy':'Data',
        'machine learning':'ML','deep learning':'ML','tensorflow':'ML','pytorch':'ML','keras':'ML','scikit-learn':'ML','sklearn':'ML','nlp':'ML','computer vision':'ML','data science':'ML','artificial intelligence':'ML','ai':'ML',
        'python':'General','java':'General','c++':'General','c':'General','c#':'General','go':'General','rust':'General','ruby':'General','php':'General','kotlin':'General','swift':'General',
    }
    detected_categories, detected_keywords = set(), set()
    for skill in skills_lower:
        for keyword, category in keyword_map.items():
            if keyword in skill:
                detected_categories.add(category)
                detected_keywords.add(keyword)
    detected_categories.add('General')
    return list(detected_categories), list(detected_keywords)

def get_personalized_quiz_questions(user_id, count=10):
    categories, keywords = get_quiz_categories_from_resume(user_id)
    resume_specific = []
    if keywords:
        for q in QuizQuestion.query.all():
            q_text = q.question_text.lower()
            for kw in keywords:
                if kw in q_text:
                    resume_specific.append(q); break
    seen = set()
    resume_specific_unique = []
    for q in resume_specific:
        if q.id not in seen: seen.add(q.id); resume_specific_unique.append(q)
    category_questions = []
    for cat in categories:
        category_questions.extend(QuizQuestion.query.filter_by(category=cat).all())
    combined = resume_specific_unique + category_questions
    unique_combined = []
    for q in combined:
        if q.id not in seen: seen.add(q.id); unique_combined.append(q)
    if len(unique_combined) < count:
        for q in QuizQuestion.query.all():
            if q.id not in seen: seen.add(q.id); unique_combined.append(q)
    random.shuffle(unique_combined)
    return unique_combined[:count]

def generate_ai_quiz_questions(user_id, count=10, day_number=1):
    # Just use the local database questions instead of Groq
    return get_personalized_quiz_questions(user_id, count)

def evaluate_face_to_face_response(answer, question_text=""):
    is_valid, error_msg = is_meaningful_answer(answer, question_text)
    if not is_valid:
        return {'communication':0,'confidence':0,'structure':0,'overall':0,'comm_feedback':error_msg,'is_valid':False}
    word_count = len(answer.split()); lower = answer.lower()
    confidence_keywords = ['sure','confident','definitely','absolutely','clearly','i believe','i can','i will','committed','experience','achieved','led','managed']
    found_conf = sum(1 for kw in confidence_keywords if kw in lower)
    confidence_score = min(100, (found_conf / 4) * 100) if found_conf else 30
    structure_words = ['first','second','then','finally','because','therefore','as a result','for example','in conclusion','situation','task','action','result']
    found_struct = sum(1 for w in structure_words if w in lower)
    structure_score = min(100, 40 + found_struct * 15)
    if word_count < 20: comm_score = 40; comm_feedback = "Answer too brief. Elaborate more with examples."
    elif word_count < 50: comm_score = 65; comm_feedback = "Good start. Add more details and structure."
    elif word_count < 100: comm_score = 80; comm_feedback = "Good answer. Well structured."
    else: comm_score = 90; comm_feedback = "Excellent! Very comprehensive answer."
    overall = (comm_score * 0.4) + (confidence_score * 0.3) + (structure_score * 0.3)
    return {'communication':round(comm_score,1),'confidence':round(confidence_score,1),'structure':round(structure_score,1),'overall':round(overall,1),'comm_feedback':comm_feedback,'is_valid':True}

def initialize_quiz_questions():
    if QuizQuestion.query.count() == 0:
        questions = [
            {'question':'What does HTML stand for?','options':['Hyper Text Markup Language','High Tech Modern Language','Hyper Transfer Markup Language','None of the above'],'correct':'A','category':'Web','difficulty':'Easy'},
            {'question':'Which CSS property changes background color?','options':['color','background-color','bgcolor','background'],'correct':'B','category':'Web','difficulty':'Easy'},
            {'question':'What is Python?','options':['Programming language','Database','Web framework','Operating system'],'correct':'A','category':'General','difficulty':'Easy'},
            {'question':'What is SQL?','options':['Database query language','Programming language','Web framework','CSS preprocessor'],'correct':'A','category':'General','difficulty':'Easy'},
            {'question':'What is the Virtual DOM in React?','options':['A copy of the real DOM','A database','A CSS framework','A programming language'],'correct':'A','category':'Web','difficulty':'Medium'},
            {'question':'What is a JOIN in SQL?','options':['Combining tables','Deleting tables','Creating tables','Renaming tables'],'correct':'A','category':'Data','difficulty':'Medium'},
            {'question':'What is supervised learning?','options':['Learning with labeled data','Learning without labels','Reinforcement learning','Unsupervised learning'],'correct':'A','category':'ML','difficulty':'Medium'},
            {'question':'What is overfitting in ML?','options':['Model learns training data too well','Model underperforms','Data is missing','Model is too simple'],'correct':'A','category':'ML','difficulty':'Hard'},
            {'question':'What is the difference between TCP and UDP?','options':['TCP is connection-oriented, UDP is connectionless','No difference','UDP is faster than TCP','TCP uses less bandwidth'],'correct':'A','category':'General','difficulty':'Hard'},
            {'question':'What is the time complexity of binary search?','options':['O(log n)','O(n)','O(n log n)','O(n^2)'],'correct':'A','category':'General','difficulty':'Hard'},
            {'question':'Tell me about a time you worked in a team.','options':['Teamwork experience','Individual work','No experience','Other'],'correct':'A','category':'General','difficulty':'Medium'},
            {'question':'How do you handle pressure and deadlines?','options':['Time management','Ignore pressure','Ask for help','Procrastinate'],'correct':'A','category':'General','difficulty':'Medium'},
        ]
        for q in questions:
            if not QuizQuestion.query.filter_by(question_text=q['question']).first():
                db.session.add(QuizQuestion(question_text=q['question'], option_a=q['options'][0], option_b=q['options'][1], option_c=q['options'][2], option_d=q['options'][3], correct_answer=q['correct'], category=q['category'], difficulty=q['difficulty']))
        db.session.commit()
        print("✅ Quiz questions initialized!")

CODE_PROBLEMS = [
    {'id':1,'title':'Two Sum','difficulty':'Easy','statement':'Given an array of integers nums and an integer target, return indices of the two numbers that add up to target.','sample_input':'nums = [2,7,11,15], target = 9','sample_output':'[0,1]','constraints':'2 <= nums.length <= 10^4','test_cases':[{'input':'[2,7,11,15],9','output':'[0,1]'},{'input':'[3,2,4],6','output':'[1,2]'},{'input':'[3,3],6','output':'[0,1]'}]},
    {'id':2,'title':'Reverse a String','difficulty':'Easy','statement':'Write a function that reverses a string.','sample_input':'["h","e","l","l","o"]','sample_output':'["o","l","l","e","h"]','constraints':'1 <= s.length <= 10^5','test_cases':[{'input':'["h","e","l","l","o"]','output':'["o","l","l","e","h"]'},{'input':'["H","a","n","n","a","h"]','output':'["h","a","n","n","a","H"]'}]},
    {'id':3,'title':'FizzBuzz','difficulty':'Easy','statement':'Print numbers from 1 to n, multiples of 3 print "Fizz", multiples of 5 print "Buzz", both print "FizzBuzz".','sample_input':'n = 15','sample_output':'1,2,Fizz,4,Buzz,Fizz,7,8,Fizz,Buzz,11,Fizz,13,14,FizzBuzz','constraints':'1 <= n <= 1000','test_cases':[{'input':'n = 3','output':'1,2,Fizz'},{'input':'n = 5','output':'1,2,Fizz,4,Buzz'},{'input':'n = 15','output':'1,2,Fizz,4,Buzz,Fizz,7,8,Fizz,Buzz,11,Fizz,13,14,FizzBuzz'}]},
    {'id':4,'title':'Palindrome Check','difficulty':'Medium','statement':'Check if a given string is a palindrome.','sample_input':'"A man, a plan, a canal: Panama"','sample_output':'True','constraints':'1 <= s.length <= 2*10^5','test_cases':[{'input':'"A man, a plan, a canal: Panama"','output':'True'},{'input':'"race a car"','output':'False'},{'input':'" "','output':'True'}]},
    {'id':5,'title':'Factorial','difficulty':'Easy','statement':'Compute the factorial of n.','sample_input':'n = 5','sample_output':'120','constraints':'0 <= n <= 20','test_cases':[{'input':'n = 0','output':'1'},{'input':'n = 5','output':'120'},{'input':'n = 10','output':'3628800'}]},
    {'id':6,'title':'Maximum Subarray','difficulty':'Medium','statement':'Find contiguous subarray with largest sum.','sample_input':'nums = [-2,1,-3,4,-1,2,1,-5,4]','sample_output':'6','constraints':'1 <= nums.length <= 10^5','test_cases':[{'input':'[-2,1,-3,4,-1,2,1,-5,4]','output':'6'},{'input':'[1]','output':'1'},{'input':'[5,4,-1,7,8]','output':'23'}]},
    {'id':7,'title':'Valid Parentheses','difficulty':'Easy','statement':'Determine if input string with brackets is valid.','sample_input':'s = "()[]{}"','sample_output':'True','constraints':'1 <= s.length <= 10^4','test_cases':[{'input':'"()"','output':'True'},{'input':'"()[]{}"','output':'True'},{'input':'"(]"','output':'False'}]},
    {'id':8,'title':'Merge Two Sorted Arrays','difficulty':'Easy','statement':'Merge two sorted arrays into one sorted array.','sample_input':'arr1 = [1,3,5], arr2 = [2,4,6]','sample_output':'[1,2,3,4,5,6]','constraints':'0 <= arr.length <= 1000','test_cases':[{'input':'[1,3,5],[2,4,6]','output':'[1,2,3,4,5,6]'},{'input':'[1,2,3],[4,5,6]','output':'[1,2,3,4,5,6]'},{'input':'[],[1]','output':'[1]'}]},
    {'id':9,'title':'Contains Duplicate','difficulty':'Easy','statement':'Return true if any value appears at least twice.','sample_input':'nums = [1,2,3,1]','sample_output':'True','constraints':'1 <= nums.length <= 10^5','test_cases':[{'input':'[1,2,3,1]','output':'True'},{'input':'[1,2,3,4]','output':'False'},{'input':'[1,1,1,3,3,4,3,2,4,2]','output':'True'}]},
    {'id':10,'title':'Best Time to Buy and Sell Stock','difficulty':'Easy','statement':'Find maximum profit from stock prices.','sample_input':'prices = [7,1,5,3,6,4]','sample_output':'5','constraints':'1 <= prices.length <= 10^5','test_cases':[{'input':'[7,1,5,3,6,4]','output':'5'},{'input':'[7,6,4,3,1]','output':'0'},{'input':'[2,4,1]','output':'2'}]},
    {'id':11,'title':'Anagram Check','difficulty':'Easy','statement':'Return true if t is an anagram of s.','sample_input':'s = "anagram", t = "nagaram"','sample_output':'True','constraints':'1 <= s.length, t.length <= 5*10^4','test_cases':[{'input':'"anagram","nagaram"','output':'True'},{'input':'"rat","car"','output':'False'},{'input':'"listen","silent"','output':'True'}]},
    {'id':12,'title':'Missing Number','difficulty':'Easy','statement':'Find the only missing number in range [0, n].','sample_input':'nums = [3,0,1]','sample_output':'2','constraints':'n == nums.length','test_cases':[{'input':'[3,0,1]','output':'2'},{'input':'[0,1]','output':'2'},{'input':'[9,6,4,2,3,5,7,0,1]','output':'8'}]},
    {'id':13,'title':'Single Number','difficulty':'Easy','statement':'Find the single element that appears once.','sample_input':'nums = [2,2,1]','sample_output':'1','constraints':'1 <= nums.length <= 3*10^4','test_cases':[{'input':'[2,2,1]','output':'1'},{'input':'[4,1,2,1,2]','output':'4'},{'input':'[1]','output':'1'}]},
    {'id':14,'title':'Move Zeroes','difficulty':'Easy','statement':'Move all 0s to the end while maintaining order.','sample_input':'nums = [0,1,0,3,12]','sample_output':'[1,3,12,0,0]','constraints':'1 <= nums.length <= 10^4','test_cases':[{'input':'[0,1,0,3,12]','output':'[1,3,12,0,0]'},{'input':'[0]','output':'[0]'},{'input':'[1,2,3]','output':'[1,2,3]'}]},
    {'id':15,'title':'Longest Common Prefix','difficulty':'Easy','statement':'Find the longest common prefix string.','sample_input':'strs = ["flower","flow","flight"]','sample_output':'"fl"','constraints':'1 <= strs.length <= 200','test_cases':[{'input':'["flower","flow","flight"]','output':'"fl"'},{'input':'["dog","racecar","car"]','output':'""'},{'input':'["interview","internet","internal"]','output':'"inter"'}]},
]

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ========== AUTHENTICATION ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        pwd = request.form.get('password')
        confirm = request.form.get('confirm_password')
        if pwd != confirm:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))
        user = User(name=name, email=email, password=generate_password_hash(pwd))
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        pwd = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, pwd):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password!', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.', 'info')
    return redirect(url_for('index'))

# ========== EMAIL VERIFICATION ==========
@app.route('/send_verification')
@login_required
def send_verification():
    token = generate_verification_token(current_user.email)
    verification_url = url_for('verify_email', token=token, _external=True)
    flash(f'Verification link (demo): {verification_url}', 'info')
    return redirect(url_for('dashboard'))

@app.route('/verify_email/<token>')
def verify_email(token):
    email = confirm_verification_token(token)
    if email:
        user = User.query.filter_by(email=email).first()
        if user:
            user.email_verified = True
            db.session.commit()
            flash('Email verified successfully!', 'success')
        else:
            flash('User not found.', 'danger')
    else:
        flash('Invalid or expired token.', 'danger')
    return redirect(url_for('login'))

# ========== DASHBOARD ==========
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

# ========== RESUME PROCESSING ==========
@app.route('/process_resume', methods=['POST'])
@login_required
def process_resume():
    company = request.form.get('company')
    role = request.form.get('role')
    if not company or not role:
        flash('Please provide both company and job role!', 'danger')
        return redirect(url_for('dashboard'))
    if 'resume' not in request.files:
        flash('Please upload a resume file!', 'danger')
        return redirect(url_for('dashboard'))
    file = request.files['resume']
    if file.filename == '':
        flash('Select a file!', 'danger')
        return redirect(url_for('dashboard'))
    if not allowed_file(file.filename):
        flash('Only PDF or TXT files allowed!', 'danger')
        return redirect(url_for('dashboard'))
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{current_user.id}_{filename}")
    file.save(filepath)
    if os.path.getsize(filepath) > app.config['MAX_CONTENT_LENGTH']:
        os.remove(filepath)
        flash('File too large! Maximum 5MB allowed.', 'danger')
        return redirect(url_for('dashboard'))
    if filename.endswith('.pdf'):
        resume_text = extract_text_from_pdf(filepath)
    else:
        with open(filepath, 'r', encoding='utf-8') as f:
            resume_text = f.read()
    os.remove(filepath)
    if not resume_text.strip():
        flash('Could not extract text from resume.', 'danger')
        return redirect(url_for('dashboard'))
    skills = ResumeParser.extract_skills(resume_text)
    projects = ResumeParser.extract_projects(resume_text)
    education = ResumeParser.extract_education(resume_text)
    strengths = ResumeParser.analyze_strengths(skills, role)
    weak_resume = ResumeParser.identify_weak_areas(skills, role)
    missing = ResumeParser.get_missing_skills(skills, company)
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if analysis:
        analysis.resume_text = resume_text
        analysis.target_company = company
        analysis.job_role = role
        analysis.skills = json.dumps(skills)
        analysis.projects = json.dumps(projects)
        analysis.education = education
        analysis.strengths = json.dumps(strengths)
        analysis.weak_areas_resume = json.dumps(weak_resume)
        analysis.missing_skills = json.dumps(missing)
    else:
        analysis = ResumeAnalysis(user_id=current_user.id, resume_text=resume_text, target_company=company, job_role=role, skills=json.dumps(skills), projects=json.dumps(projects), education=education, strengths=json.dumps(strengths), weak_areas_resume=json.dumps(weak_resume), missing_skills=json.dumps(missing))
        db.session.add(analysis)
    WeakArea.query.filter_by(user_id=current_user.id).delete()
    for w in weak_resume:
        db.session.add(WeakArea(user_id=current_user.id, topic=w, source='resume', severity=7))
    InterviewQuestion.query.filter_by(user_id=current_user.id).delete()
    questions = AIEngine.generate_questions(company, role, missing, weak_resume)
    for q in questions:
        db.session.add(InterviewQuestion(user_id=current_user.id, question_text=q['text'], question_type=q['type']))
    db.session.commit()
    session['company'] = company
    session['role'] = role
    flash('Resume analyzed successfully!', 'success')
    return redirect(url_for('preparation'))

# ========== PREPARATION ==========
@app.route('/preparation')
@login_required
def preparation():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('Please upload resume first!', 'warning')
        return redirect(url_for('dashboard'))
    initialize_quiz_questions()
    attempts = QuizAttempt.query.filter_by(user_id=current_user.id).order_by(QuizAttempt.day_number).all()
    completed = sum(1 for a in attempts if a.completed)
    next_day = completed + 1 if completed < 28 else 28
    stats = {'current_day': next_day}
    questions = InterviewQuestion.query.filter_by(user_id=current_user.id).all()
    answers = AnswerEvaluation.query.filter_by(user_id=current_user.id).all()
    weak = WeakArea.query.filter_by(user_id=current_user.id).all()
    strengths = json.loads(analysis.strengths) if analysis.strengths else []
    missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
    return render_template('preparation.html', analysis=analysis, questions=questions, answers=answers, weak_areas=weak, strengths=strengths, missing_skills=missing, stats=stats)

# ========== EVALUATE ANSWER ==========
@app.route('/evaluate_answer', methods=['POST'])
@login_required
def evaluate_answer():
    data = request.get_json()
    qid = data.get('question_id')
    answer = data.get('answer', '')
    question = InterviewQuestion.query.get(qid)
    if not question or question.user_id != current_user.id:
        return jsonify({'error': 'Invalid question'}), 400
    is_valid, error_msg = is_meaningful_answer(answer, question.question_text)
    if not is_valid:
        return jsonify({'score': 0,'feedback': f'❌ {error_msg}','improved_answer': 'Please write a real answer with 40–80 words, including a specific example.','clarity_score': 0,'confidence_score': 0})
    eval_res = AIEngine.evaluate_answer(question.question_text, answer, question.question_type)
    existing = AnswerEvaluation.query.filter_by(user_id=current_user.id, question_id=qid).first()
    if existing:
        existing.user_answer = answer; existing.score = eval_res['score']; existing.feedback = eval_res['feedback']; existing.improved_answer = eval_res['improved_answer']; existing.clarity_score = eval_res['clarity_score']; existing.confidence_score = eval_res['confidence_score']
    else:
        db.session.add(AnswerEvaluation(user_id=current_user.id, question_id=qid, user_answer=answer, score=eval_res['score'], feedback=eval_res['feedback'], improved_answer=eval_res['improved_answer'], clarity_score=eval_res['clarity_score'], confidence_score=eval_res['confidence_score']))
    if eval_res['score'] < 5:
        topic = f"Answering {question.question_type} question: {question.question_text[:50]}"
        if not WeakArea.query.filter_by(user_id=current_user.id, topic=topic).first():
            db.session.add(WeakArea(user_id=current_user.id, topic=topic, source='answer', severity=8))
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id); db.session.add(progress)
    total = AnswerEvaluation.query.filter_by(user_id=current_user.id).count()
    avg = db.session.query(db.func.avg(AnswerEvaluation.score)).filter_by(user_id=current_user.id).scalar() or 0
    progress.total_questions_answered = total; progress.average_score = avg; progress.last_active = datetime.utcnow()
    db.session.commit()
    return jsonify(eval_res)

# ========== LEGACY MOCK INTERVIEW ==========
@app.route('/mock_interview')
@login_required
def mock_interview():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('Please upload resume first', 'warning')
        return redirect(url_for('dashboard'))
    questions = InterviewQuestion.query.filter_by(user_id=current_user.id).all()
    if not questions:
        missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
        weak = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
        qs = AIEngine.generate_questions(analysis.target_company, analysis.job_role, missing, weak)
        for q in qs:
            db.session.add(InterviewQuestion(user_id=current_user.id, question_text=q['text'], question_type=q['type']))
        db.session.commit()
        questions = InterviewQuestion.query.filter_by(user_id=current_user.id).all()
    q_list = [{'id': q.id, 'text': q.question_text, 'type': q.question_type} for q in questions]
    return render_template('mock_interview.html', questions=q_list)

@app.route('/evaluate_mock', methods=['POST'])
@login_required
def evaluate_mock():
    data = request.get_json()
    qid = data.get('question_id')
    answer = data.get('answer', '')
    question = InterviewQuestion.query.get(qid)
    if not question or question.user_id != current_user.id:
        return jsonify({'error': 'Invalid question'}), 400
    is_valid, error_msg = is_meaningful_answer(answer, question.question_text)
    if not is_valid:
        return jsonify({'score': 0,'feedback': f'❌ {error_msg}','improved_answer': 'Please write a real answer with 40–80 words, including a specific example.'})
    eval_res = AIEngine.evaluate_answer(question.question_text, answer, question.question_type)
    existing = AnswerEvaluation.query.filter_by(user_id=current_user.id, question_id=qid).first()
    if existing:
        existing.user_answer = answer; existing.score = eval_res['score']; existing.feedback = eval_res['feedback']; existing.improved_answer = eval_res['improved_answer']
    else:
        db.session.add(AnswerEvaluation(user_id=current_user.id, question_id=qid, user_answer=answer, score=eval_res['score'], feedback=eval_res['feedback'], improved_answer=eval_res['improved_answer'], clarity_score=eval_res['clarity_score'], confidence_score=eval_res['confidence_score']))
    if eval_res['score'] < 5:
        topic = f"Mock Q: {question.question_text[:50]}"
        if not WeakArea.query.filter_by(user_id=current_user.id, topic=topic).first():
            db.session.add(WeakArea(user_id=current_user.id, topic=topic, source='mock', severity=8))
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id); db.session.add(progress)
    total = AnswerEvaluation.query.filter_by(user_id=current_user.id).count()
    avg = db.session.query(db.func.avg(AnswerEvaluation.score)).filter_by(user_id=current_user.id).scalar() or 0
    progress.total_questions_answered = total; progress.average_score = avg; progress.last_active = datetime.utcnow()
    db.session.commit()
    return jsonify({'score': eval_res['score'], 'feedback': eval_res['feedback'], 'improved_answer': eval_res['improved_answer']})

# ========== FACE-TO-FACE MOCK INTERVIEW ==========
@app.route('/mock_interview_start')
@login_required
def mock_interview_start():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('Please upload your resume first!', 'warning')
        return redirect(url_for('dashboard'))
    force = request.args.get('force', '0')
    if force == '1' or 'mock_questions' not in session:
        session.pop('mock_questions', None); session.pop('mock_index', None); session.pop('mock_answers', None)
        missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
        weak = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
        questions = AIEngine.generate_questions(analysis.target_company, analysis.job_role, missing, weak)
        face_to_face_questions = ["Tell me about a time you faced a challenge and how you overcame it.","How do you handle constructive criticism from your manager?","Describe a situation where you worked in a team and had a conflict.","What motivates you to perform at your best?","How do you stay updated with the latest technologies?","Tell me about your most significant achievement.","How do you prioritize your tasks when everything is urgent?","Describe a time you failed and what you learned from it.","How do you handle stress and pressure at work?","What makes you the best candidate for this role?"]
        all_questions = list(questions)
        for q in face_to_face_questions:
            all_questions.append({"text": q, "type": "behavioral"})
        random.shuffle(all_questions)
        session['mock_questions'] = all_questions[:15]
        session['mock_index'] = 0
        session['mock_answers'] = []
    return render_template('mock_interview_session.html', total_questions=len(session['mock_questions']), company=analysis.target_company, role=analysis.job_role)

@app.route('/get_mock_question')
@login_required
def get_mock_question():
    questions = session.get('mock_questions', [])
    index = session.get('mock_index', 0)
    if index >= len(questions):
        return jsonify({'finished': True})
    question = questions[index]
    return jsonify({'finished': False, 'question': question['text'], 'type': question['type'], 'question_number': index + 1, 'total_questions': len(questions), 'progress': int((index / len(questions)) * 100)})

@app.route('/submit_mock_answer', methods=['POST'])
@login_required
def submit_mock_answer():
    data = request.get_json()
    answer = data.get('answer', '')
    time_taken = data.get('time_taken', 0)
    questions = session.get('mock_questions', [])
    index = session.get('mock_index', 0)
    if index >= len(questions):
        return jsonify({'finished': True})
    current_q = questions[index]
    face_to_face_score = evaluate_face_to_face_response(answer, current_q['text'])
    if not face_to_face_score.get('is_valid', True):
        combined_score = 0
        feedback = face_to_face_score['comm_feedback']
        eval_result = {'score': 0, 'improved_answer': 'Please provide a valid English response.'}
    else:
        eval_result = AIEngine.evaluate_answer(current_q['text'], answer, current_q['type'])
        combined_score = (eval_result['score'] * 0.6) + ((face_to_face_score['overall'] / 10) * 0.4)
        combined_score = round(min(10, max(0, combined_score)), 1)
        if combined_score >= 8: feedback = "Excellent answer! Well-structured and confident."
        elif combined_score >= 6: feedback = "Good answer. Add more specific examples for higher impact."
        elif combined_score >= 4: feedback = "Decent attempt. Use the STAR method to structure your answer."
        else: feedback = face_to_face_score['comm_feedback']
    answers = session.get('mock_answers', [])
    answers.append({'question': current_q['text'],'answer': answer,'type': current_q['type'],'score': combined_score,'feedback': feedback,'improved_answer': eval_result['improved_answer'],'time_taken': time_taken,'face_to_face_score': face_to_face_score})
    session['mock_answers'] = answers
    session['mock_index'] = index + 1
    question_obj = InterviewQuestion(user_id=current_user.id, question_text=current_q['text'], question_type=current_q['type'])
    db.session.add(question_obj)
    db.session.commit()
    evaluation = AnswerEvaluation(user_id=current_user.id, question_id=question_obj.id, user_answer=answer, score=combined_score, feedback=feedback, improved_answer=eval_result['improved_answer'], clarity_score=eval_result.get('clarity_score', 0), confidence_score=face_to_face_score.get('confidence', 0))
    db.session.add(evaluation)
    if combined_score < 5:
        topic = f"Face-to-Face: {current_q['text'][:50]}"
        if not WeakArea.query.filter_by(user_id=current_user.id, topic=topic).first():
            db.session.add(WeakArea(user_id=current_user.id, topic=topic, source='mock', severity=8))
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id); db.session.add(progress)
    total = AnswerEvaluation.query.filter_by(user_id=current_user.id).count()
    avg = db.session.query(db.func.avg(AnswerEvaluation.score)).filter_by(user_id=current_user.id).scalar() or 0
    progress.total_questions_answered = total; progress.average_score = avg; progress.last_active = datetime.utcnow()
    db.session.commit()
    if combined_score >= 8: award_badge(current_user.id, 'Interview Master', 'Interview')
    return jsonify({'score': combined_score,'feedback': feedback,'improved_answer': eval_result['improved_answer'],'face_to_face_score': face_to_face_score,'finished': index + 1 >= len(questions),'next_question_number': index + 2,'total_questions': len(questions),'progress': int(((index + 1) / len(questions)) * 100)})

@app.route('/mock_interview_results')
@login_required
def mock_interview_results():
    answers = session.get('mock_answers', [])
    if not answers:
        flash('Complete a mock interview first!', 'warning')
        return redirect(url_for('mock_interview_start'))
    avg_score = sum(a['score'] for a in answers) / len(answers) if answers else 0
    total_time = sum(a.get('time_taken', 0) for a in answers)
    return render_template('mock_interview_results.html', answers=answers, avg_score=round(avg_score, 1), total_questions=len(answers), total_time=round(total_time, 1))

# ========== CHATBOT ==========
@app.route('/interview_chatbot')
@login_required
def interview_chatbot():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('Please upload your resume first!', 'warning')
        return redirect(url_for('dashboard'))
    session.pop('chatbot_questions', None); session.pop('chatbot_index', None)
    missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
    weak = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
    questions_data = AIEngine.generate_questions(analysis.target_company, analysis.job_role, missing, weak)
    if not questions_data:
        questions_data = [{"text": "Tell me about yourself.", "type": "introduction"},{"text": "What are your greatest strengths and weaknesses?", "type": "hr"},{"text": "Why do you want to work at this company?", "type": "hr"},{"text": "Explain a challenging technical project you worked on.", "type": "technical"},{"text": "How do you handle pressure and tight deadlines?", "type": "behavioral"},{"text": "Where do you see yourself in 5 years?", "type": "hr"},{"text": "Describe a time you had a conflict with a team member and how you resolved it.", "type": "behavioral"}]
    session['chatbot_questions'] = questions_data
    session['chatbot_index'] = 0
    session['chatbot_history'] = []
    return render_template('interview_chatbot.html', company=analysis.target_company, role=analysis.job_role, total_questions=len(questions_data))

@app.route('/chatbot_get_question', methods=['GET'])
@login_required
def chatbot_get_question():
    questions = session.get('chatbot_questions', [])
    
    # Fallback if session got wiped out somehow
    if not questions:
        analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
        if analysis:
            missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
            weak = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
            questions = AIEngine.generate_questions(analysis.target_company, analysis.job_role, missing, weak)
            session['chatbot_questions'] = questions
            session['chatbot_index'] = 0
            session['chatbot_history'] = []

    index = session.get('chatbot_index', 0)
    if index >= len(questions):
        return jsonify({'finished': True})
        
    q = questions[index]
    return jsonify({'finished': False, 'question': q['text'], 'type': q['type'], 'index': index+1, 'total': len(questions)})

@app.route('/chatbot_submit_answer', methods=['POST'])
@login_required
def chatbot_submit_answer():
    data = request.get_json()
    user_answer = data.get('answer', '')
    index = session.get('chatbot_index', 0)
    questions = session.get('chatbot_questions', [])
    
    if index >= len(questions):
        return jsonify({'finished': True})
        
    current_q = questions[index]
    
    # Use local ML to evaluate instead of Groq API
    eval_res = local_evaluate_answer(user_answer, current_q['text'])
    
    # Save history to session
    history = session.get('chatbot_history', [])
    history.append({
        'question': current_q['text'], 
        'type': current_q['type'], 
        'answer': user_answer, 
        'score': eval_res['score'], 
        'feedback': eval_res['feedback']
    })
    session['chatbot_history'] = history
    
    # Update User Progress & Weak Areas
    if eval_res['score'] < 5:
        topic = f"Chatbot Q: {current_q['text'][:50]}"
        if not WeakArea.query.filter_by(user_id=current_user.id, topic=topic).first():
            db.session.add(WeakArea(user_id=current_user.id, topic=topic, source='chatbot', severity=7))
            db.session.commit()
            
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id)
        db.session.add(progress)
        
    total_answers = AnswerEvaluation.query.filter_by(user_id=current_user.id).count() + 1
    new_avg = (progress.average_score * progress.total_questions_answered + eval_res['score']) / total_answers if total_answers > 0 else eval_res['score']
    progress.total_questions_answered = total_answers
    progress.average_score = new_avg
    progress.last_active = datetime.utcnow()
    db.session.commit()
    
    session['chatbot_index'] = index + 1
    
    return jsonify({
        'score': eval_res['score'], 
        'feedback': eval_res['feedback'], 
        'improved_answer': eval_res['improved_answer'], 
        'next_index': index+1, 
        'finished': index+1 >= len(questions)
    })

@app.route('/chatbot_reset', methods=['POST'])
@login_required
def chatbot_reset():
    # 1. Clear existing session data
    session.pop('chatbot_questions', None)
    session.pop('chatbot_index', None)
    session.pop('chatbot_history', None)
    
    # 2. Re-fetch the questions from the database / AI Engine
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if analysis:
        missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
        weak = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
        questions_data = AIEngine.generate_questions(analysis.target_company, analysis.job_role, missing, weak)
        
        # Fallback if AI Engine fails or returns nothing
        if not questions_data:
            questions_data = [
                {"text": "Tell me about yourself.", "type": "introduction"},
                {"text": "What are your greatest strengths?", "type": "hr"},
                {"text": "Why do you want to work here?", "type": "hr"}
            ]
            
        # 3. Save the new questions and reset the index
        session['chatbot_questions'] = questions_data
        session['chatbot_index'] = 0
        session['chatbot_history'] = []
        
    return jsonify({'status': 'reset'})

# ========== VOICE INTERVIEW ==========
@app.route('/voice_interview')
@login_required
def voice_interview():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('Please upload your resume first!', 'warning')
        return redirect(url_for('dashboard'))
    
    has_resume = bool(analysis.skills)
    return render_template('voice_interview.html', 
                           company=analysis.target_company, 
                           role=analysis.job_role,
                           has_resume=has_resume)

@app.route('/voice_interview/start', methods=['POST'])
@login_required
def voice_interview_start():
    data = request.get_json()
    
    # Reset session
    session['voice_q_index'] = 0
    session['voice_history'] = []
    
    custom_qs = data.get('custom_questions', '').strip()
    
    if custom_qs:
        questions = [q.strip() for q in custom_qs.split('\n') if q.strip()]
        session['voice_rounds'] = {
            'custom': {
                'name': 'Custom Questions',
                'questions': questions
            }
        }
        session['voice_current_round'] = 'custom'
    else:
        analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
        if not analysis:
            return jsonify({'error': 'Please upload a resume first.'}), 400
            
        skills = json.loads(analysis.skills) if analysis.skills else []
        missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
        weak = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
        
        company = data.get('company') or analysis.target_company
        role = data.get('job_role') or analysis.job_role
        
        # Generate questions using your AI Engine
        interview_rounds = AIEngine.generate_round_questions(company, role, skills, missing, weak)
        
        # Flatten and limit to requested count
        all_questions = []
        for r_name, r_data in interview_rounds.items():
            all_questions.extend(r_data.get('questions', []))
            
        try:
            q_count = int(data.get('question_count', 5))
        except ValueError:
            q_count = 5
            
        session['voice_rounds'] = {
            'generated': {
                'name': 'Interview',
                'questions': all_questions[:q_count]
            }
        }
        session['voice_current_round'] = 'generated'

    total = len(session['voice_rounds'][session['voice_current_round']]['questions'])
    return jsonify({'status': 'success', 'interview_id': 'mock_123', 'total': total})

@app.route('/voice_interview_next', methods=['GET'])
@login_required
def voice_interview_next():
    rounds = session.get('voice_rounds', {})
    current_round = session.get('voice_current_round', 'generated')
    q_index = session.get('voice_q_index', 0)
    
    round_data = rounds.get(current_round, {})
    questions = round_data.get('questions', [])
    
    if q_index >= len(questions):
        # Calculate mock overall score for completion screen
        history = session.get('voice_history', [])
        avg_score = sum(h.get('score', 0) for h in history) / len(history) if history else 0
        return jsonify({'finished': True, 'overall_score': avg_score * 10, 'interview_id': 'mock_123'})
        
    return jsonify({
        'finished': False,
        'type': 'question',
        'round_name': round_data.get('name', 'Interview'),
        'question': questions[q_index],
        'question_index': q_index + 1,
        'total_in_round': len(questions)
    })

@app.route('/voice_interview_submit', methods=['POST'])
@login_required
def voice_interview_submit():
    data = request.get_json()
    user_answer = data.get('answer', '')
    
    current_round = session.get('voice_current_round')
    q_index = session.get('voice_q_index', 0)
    rounds = session.get('voice_rounds', {})
    round_data = rounds.get(current_round, {})
    questions = round_data.get('questions', [])
    current_question = questions[q_index] if q_index < len(questions) else ""
    
    if not user_answer or len(user_answer.strip()) < 5:
        return jsonify({'score': 0, 'feedback': '❌ Answer too short. Please elaborate.', 'next_index': q_index})

    # =========================================================
    # --- STRICT LENGTH CHECK (Fixes the "I want a job" bug) ---
    # =========================================================
    word_count = len(user_answer.split())
    
    if word_count < 15:
        # Force a 0 score for short answers
        ml_score_out_of_10 = 0
        score_out_of_100 = 0
        feedback = "❌ Answer is too brief. In a real interview, you must speak for at least 30-60 seconds (approx 40+ words). Please use the STAR method to elaborate."
    else:
        # If the answer is long enough, use the ML model
        from voice_evaluator_ml import evaluate_with_ml
        ml_score_out_of_10 = evaluate_with_ml(user_answer)
        score_out_of_100 = ml_score_out_of_10 * 10
        
        if score_out_of_100 >= 80: 
            feedback = "Excellent use of action-oriented language! Very structured."
        elif score_out_of_100 >= 50: 
            feedback = "Good answer. Try using more specific technical examples."
        else: 
            feedback = "Needs improvement. Please provide a longer, more structured answer using the STAR method."
    # =========================================================

    # Save history
    history = session.get('voice_history', [])
    history.append({'round': current_round, 'question': current_question, 'answer': user_answer, 'score': ml_score_out_of_10})
    session['voice_history'] = history
    
    # Update Progress DB
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    if not progress:
        progress = UserProgress(user_id=current_user.id)
        db.session.add(progress)
        
    total_answers = AnswerEvaluation.query.filter_by(user_id=current_user.id).count() + 1
    new_avg = (progress.average_score * progress.total_questions_answered + ml_score_out_of_10) / total_answers if total_answers > 0 else ml_score_out_of_10
    progress.total_questions_answered = total_answers
    progress.average_score = new_avg
    progress.last_active = datetime.utcnow()
    db.session.commit()
    
    session['voice_q_index'] = q_index + 1
    
    return jsonify({
        'score': score_out_of_100, 
        'correctness_score': score_out_of_100,
        'clarity_score': score_out_of_100,
        'communication_score': score_out_of_100,
        'feedback': feedback, 
        'ideal_answer': 'Use the STAR method: Situation, Task, Action, Result.',
        'strengths': ['None detected'] if score_out_of_100 == 0 else ['Clear communication'],
        'weaknesses': ['Answer too short'] if score_out_of_100 == 0 else ['Could use more technical depth'],
        'next_index': q_index+1,
        'finished_after_this': (q_index + 1) >= len(questions)
    })

@app.route('/voice_interview_reset', methods=['POST'])
@login_required
def voice_interview_reset():
    session.pop('voice_rounds', None)
    session.pop('voice_current_round', None)
    session.pop('voice_q_index', None)
    session.pop('voice_history', None)
    return jsonify({'status': 'reset'})

# ========== ANALYSIS ==========
@app.route('/analysis')
@login_required
def analysis():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('No resume found.', 'warning')
        return redirect(url_for('dashboard'))
    skills = json.loads(analysis.skills) if analysis.skills else []
    projects = json.loads(analysis.projects) if analysis.projects else []
    strengths = json.loads(analysis.strengths) if analysis.strengths else []
    weak_resume = json.loads(analysis.weak_areas_resume) if analysis.weak_areas_resume else []
    missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
    return render_template('analysis.html', skills=skills, projects=projects, strengths=strengths, weak_resume=weak_resume, missing=missing, education=analysis.education, company=analysis.target_company, role=analysis.job_role)

# ========== MENTOR ==========
@app.route('/mentor')
@login_required
def mentor():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    company = analysis.target_company if analysis else "your target company"
    role = analysis.job_role if analysis else "the role"
    return render_template('mentor.html', company=company, role=role)

@app.route('/ask_mentor', methods=['POST'])
@login_required
def ask_mentor():
    data = request.get_json()
    user_question = data.get('question', '')
    
    if not user_question.strip():
        return jsonify({'reply': 'Please ask a question.'})

    # 1. Use ML to predict intent
    predicted_intent = predict_intent(user_question)
    print(f"🧠 ML Predicted Intent: {predicted_intent}")

    # 2. Gather Context from Database
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    company = analysis.target_company.title() if analysis and analysis.target_company else "your target company"
    role = analysis.job_role.title() if analysis and analysis.job_role else "your target role"
    
    # --- NEW: If the user mentions a specific company in the question, override the DB company ---
    known_companies = ['Google', 'Amazon', 'Microsoft', 'TCS', 'Infosys', 'Wipro', 'Accenture', 'Cognizant', 'Meta', 'Adobe']
    for c in known_companies:
        if c.lower() in user_question.lower():
            company = c
            break
    # ----------------------------------------------------------------------------------------------

    user_skills, missing_skills = [], []
    if analysis:
        if analysis.skills:
            try: user_skills = json.loads(analysis.skills)
            except: pass
        if analysis.missing_skills:
            try: missing_skills = json.loads(analysis.missing_skills)
            except: pass
            
    user_skills_str = ', '.join(user_skills[:5]) if user_skills else "None detected yet"
    missing_str = ', '.join(missing_skills[:4]) if missing_skills else "None detected"
    
    weak_areas = WeakArea.query.filter_by(user_id=current_user.id).all()
    weak_str = ', '.join([w.topic for w in weak_areas[:3]]) if weak_areas else "None detected yet"

    # 3. Generate Response based on ML Intent
    if predicted_intent == "greeting":
        reply = f"Hello! 👋 I am your AI Mentor. I see you are targeting **{role}** at **{company}**. How can I help you today? You can ask about skills, resume, preparation, or your weak areas."
        
    elif predicted_intent == "skills":
        reply = f"Based on your target role as a **{role}** at **{company}**, here are the key skills you should focus on:\n\n"
        
        # Customize skills based on the specific company asked
        if company.lower() == 'google':
            reply += "• Data Structures & Algorithms (Graphs, Trees, DP)\n• System Design (Scalability, Load Balancing)\n• Strong coding in Python, Java, or C++\n• Problem Solving & Googleyness (Cultural Fit)"
        elif company.lower() == 'amazon':
            reply += "• Data Structures & Algorithms (Trees, Heaps)\n• System Design (Distributed Systems)\n• OOP Concepts\n• Leadership Principles (STAR method)"
        elif company.lower() == 'tcs':
            reply += "• Aptitude & Logical Reasoning\n• Basic Coding (C, C++, Java)\n• Database Management (SQL)\n• Good Communication & HR skills"
        elif 'web' in role.lower() or 'frontend' in role.lower():
            reply += "• HTML, CSS, JavaScript\n• React or Angular\n• Responsive Design & Git"
        elif 'data' in role.lower() or 'analyst' in role.lower():
            reply += "• Advanced SQL (Joins, Window functions)\n• Python (Pandas, NumPy)\n• Data Visualization (Tableau/Power BI)\n• Statistics"
        elif 'backend' in role.lower() or 'developer' in role.lower():
            reply += "• REST APIs & System Design\n• Database Management (SQL/NoSQL)\n• Language mastery (Java/Python/Node.js)\n• Docker & Git"
        else:
            reply += "• Data Structures & Algorithms\n• Object-Oriented Programming\n• Database Management (SQL)\n• Communication Skills"
        reply += f"\n\n**Your detected missing skills:** {missing_str}\n**Your current skills:** {user_skills_str}"

    elif predicted_intent == "resume":
        reply = f"To improve your resume for **{company} {role}**:\n"
        reply += f"• Add projects demonstrating: {missing_str}\n"
        reply += "• Use action verbs: 'Developed', 'Optimized', 'Implemented'.\n"
        reply += "• Quantify results: 'Improved efficiency by 20%'.\n"
        reply += "• Keep it to 1 page if you are a fresher.\n"

    elif predicted_intent == "preparation":
        reply = f"Here is a quick prep plan for **{company} {role}**:\n"
        reply += f"1. **Fix Weaknesses:** Focus on {weak_str}.\n"
        reply += f"2. **Learn Missing Skills:** Dedicate 2 hours daily to {missing_str}.\n"
        reply += "3. **DSA Practice:** Solve 3 LeetCode Medium problems daily.\n"
        reply += "4. **Mock Interviews:** Use our Face-to-Face module 2 times a week.\n"

    elif predicted_intent == "culture":
        reply = f"Insights for **{company}**:\n"
        if 'tcs' in company.lower():
            reply += "• Focuses heavily on aptitude, basic coding (C/C++/Java), and HR communication.\n• Values teamwork and adaptability."
        elif 'google' in company.lower():
            reply += "• Values 'Googleyness' (collaboration, intellectual humility).\n• Heavy focus on DSA (Graphs, Trees, DP) and System Design."
        elif 'amazon' in company.lower():
            reply += "• Obsessed with 'Leadership Principles' (Customer Obsession, Ownership).\n• Expect behavioral questions based on these principles."
        elif 'microsoft' in company.lower():
            reply += "• Values a growth mindset and diverse perspectives.\n• Expect questions on system design, OOP, and problem-solving."
        else:
            reply += f"• Typically looks for strong problem-solving skills, solid fundamentals, and cultural fit.\n• Prepare to discuss your projects in depth."

    elif predicted_intent == "weak_areas":
        reply = f"Your current weak areas based on your resume and mock tests are:\n**{weak_str}**\n\n"
        reply += "**Action Plan:**\n"
        reply += "1. Don't just memorize; build a small project using these concepts.\n"
        reply += "2. Watch YouTube crash courses on these specific topics.\n"

    elif predicted_intent == "technical":
        reply = "**Core Technical Topics to Master:**\n"
        reply += "• **DSA:** Arrays, Strings, Linked Lists, Trees, Dynamic Programming.\n"
        reply += "• **DBMS:** Normalization, ACID properties, Indexing.\n"
        reply += "• **OS:** Deadlocks, Threads vs Processes, Memory Management.\n"
        
    elif predicted_intent == "hr":
        reply = "For HR questions, always use the **STAR Method**:\n"
        reply += "• **S**ituation: Set the context.\n"
        reply += "• **T**ask: Describe your responsibility.\n"
        reply += "• **A**ction: Explain exactly what *you* did.\n"
        reply += "• **R**esult: Share the positive outcome.\n\n"
        reply += "For 'Tell me about yourself': Present -> Past -> Future."

    else:
        reply = f"I'm not exactly sure what you mean, but as your mentor for **{company}**, I recommend focusing on your missing skills: {missing_str}. Ask me about 'skills', 'resume', or 'preparation'!"

    return jsonify({'reply': reply})

# ========== 100-DAY APTITUDE SYSTEM ==========
DATA_FOLDER = os.path.join(os.path.dirname(__file__), 'data')

def load_aptitude_questions(section):
    file_path = os.path.join(DATA_FOLDER, f"{section}.json")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        formatted_questions = []
        for item in raw_data:
            formatted_questions.append({
                'question': item.get('q'),
                'options': item.get('options'),
                'answer': str(item.get('ans'))
            })
        return formatted_questions
    except Exception as e:
        logger.error(f"Error loading {section}.json: {e}")
        return []

@app.route('/aptitude')
@login_required
def aptitude():
    return render_template('aptitude.html')

@app.route('/api/aptitude/load', methods=['GET'])
@login_required
def api_aptitude_load():
    section = request.args.get('section', 'quantitative')
    day = int(request.args.get('day', 1))
    all_questions = load_aptitude_questions(section)
    if not all_questions:
        return jsonify({'error': f'No questions found for {section}'}), 404
    start_index = (day - 1) * 10
    end_index = start_index + 10
    if end_index <= len(all_questions):
        selected_questions = all_questions[start_index:end_index]
    else:
        random.shuffle(all_questions)
        selected_questions = all_questions[:10]
    session[f'aptitude_{section}_answers'] = [q['answer'] for q in selected_questions]
    session[f'aptitude_{section}_questions'] = [{'question': q['question']} for q in selected_questions]
    frontend_questions = [{'id': i, 'question': q['question'], 'options': q['options']}
                          for i, q in enumerate(selected_questions)]
    return jsonify({'questions': frontend_questions})

@app.route('/api/aptitude/submit_section', methods=['POST'])
@login_required
def api_aptitude_submit_section():
    data = request.get_json()
    section = data.get('section')
    user_answers = data.get('answers', {})
    day = int(data.get('day', 1))
    correct_answers = session.get(f'aptitude_{section}_answers', [])
    session_questions = session.get(f'aptitude_{section}_questions', [])
    if not correct_answers:
        return jsonify({'error': 'Session expired'}), 400
    score = 0
    for i, correct_ans in enumerate(correct_answers):
        user_ans = user_answers.get(str(i), "Not Answered")
        if user_ans != "Not Answered":
            is_correct = (str(user_ans) == str(correct_ans))
            if is_correct:
                score += 1
            q_text = session_questions[i]['question'] if i < len(session_questions) else "Unknown Question"
            result = AptitudeResult(
                user_id=current_user.id,
                day_number=day,
                section=section,
                question_text=q_text,
                correct_option=correct_ans,
                user_option=user_ans,
                is_correct=is_correct
            )
            db.session.add(result)
    db.session.commit()
    return jsonify({'score': score, 'total': len(correct_answers)})

@app.route('/aptitude_dashboard')
@login_required
def aptitude_dashboard():
    results = AptitudeResult.query.filter_by(user_id=current_user.id).order_by(AptitudeResult.day_number.desc(), AptitudeResult.created_at.desc()).all()
    dashboard_data = {}
    for r in results:
        if r.day_number not in dashboard_data:
            dashboard_data[r.day_number] = {'quantitative': [], 'reasoning': [], 'verbal': []}
        dashboard_data[r.day_number][r.section].append(r)
    return render_template('aptitude_dashboard.html', dashboard_data=dashboard_data)

# ========== LEADERBOARD ==========
@app.route('/leaderboard')
@login_required
def leaderboard():
    users_data = []
    for u in User.query.all():
        prog = UserProgress.query.filter_by(user_id=u.id).first()
        if prog:
            avg = min(10, round(prog.average_score, 1)) if prog.average_score else 0
            total = prog.total_questions_answered if prog.total_questions_answered else 0
        else:
            avg = 0; total = 0
        users_data.append({'name': u.name, 'email': u.email, 'avg_score': avg, 'total_answers': total})
    users_data.sort(key=lambda x: x['avg_score'], reverse=True)
    for i, user in enumerate(users_data, 1):
        user['rank'] = i
    return render_template('leaderboard.html', users=users_data)

# ========== RESUME BUILDER ==========
@app.route('/resume_templates')
@login_required
def resume_templates():
    return render_template('resume_templates.html')

@app.route('/resume_builder')
@login_required
def resume_builder():
    rd = ResumeData.query.filter_by(user_id=current_user.id).first()
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    parsed_skills = json.loads(analysis.skills) if analysis and analysis.skills else []
    parsed_projects = json.loads(analysis.projects) if analysis and analysis.projects else []
    parsed_education = analysis.education if analysis else ""
    certs = Certificate.query.filter_by(user_id=current_user.id).all()
    certificates_list = [{'name': c.certificate_name, 'issuer': c.issuing_authority, 'date': c.issue_date.strftime('%Y-%m-%d')} for c in certs]
    if rd:
        full_name = rd.full_name or current_user.name
        email = rd.email or current_user.email
        phone = rd.phone or ""
        address = rd.address or ""
        summary = rd.summary or ""
        target_company = rd.target_company or "TCS"
        job_role = rd.job_role or "Software Engineer"
        skills_list = json.loads(rd.skills) if rd.skills else parsed_skills
        projects_list = json.loads(rd.projects) if rd.projects else [{"title": p, "description": "", "technologies": ""} for p in parsed_projects]
        education_list = json.loads(rd.education) if rd.education else [{"degree": parsed_education, "institution": "", "year": "", "cgpa": ""}]
        experience_list = json.loads(rd.experience) if rd.experience else [{"title": "", "company": "", "duration": "", "description": ""}]
        template_choice = rd.template_choice
    else:
        full_name = current_user.name; email = current_user.email; phone = ""; address = ""; summary = ""; target_company = "TCS"; job_role = "Software Engineer"
        skills_list = parsed_skills; projects_list = [{"title": p, "description": "", "technologies": ""} for p in parsed_projects]; education_list = [{"degree": parsed_education, "institution": "", "year": "", "cgpa": ""}]; experience_list = [{"title": "", "company": "", "duration": "", "description": ""}]; template_choice = "professional"
    return render_template('resume_builder.html', full_name=full_name, email=email, phone=phone, address=address, summary=summary, target_company=target_company, job_role=job_role, skills_list=skills_list, projects_list=projects_list, education_list=education_list, experience_list=experience_list, certificates_list=certificates_list, template_choice=template_choice)

@app.route('/save_resume_data', methods=['POST'])
@login_required
def save_resume_data():
    data = request.get_json()
    rd = ResumeData.query.filter_by(user_id=current_user.id).first()
    if not rd:
        rd = ResumeData(user_id=current_user.id); db.session.add(rd)
    rd.full_name = data.get('full_name'); rd.email = data.get('email'); rd.phone = data.get('phone'); rd.address = data.get('address'); rd.summary = data.get('summary'); rd.target_company = data.get('target_company', 'TCS'); rd.job_role = data.get('job_role', 'Software Engineer'); rd.skills = json.dumps(data.get('skills', [])); rd.projects = json.dumps(data.get('projects', [])); rd.education = json.dumps(data.get('education', [])); rd.experience = json.dumps(data.get('experience', [])); rd.template_choice = data.get('template_choice', 'professional')
    certificates = data.get('certificates', [])
    for cert_data in certificates:
        if cert_data.get('name'):
            if not Certificate.query.filter_by(user_id=current_user.id, certificate_name=cert_data.get('name'), issuing_authority=cert_data.get('issuer')).first():
                db.session.add(Certificate(user_id=current_user.id, certificate_name=cert_data.get('name'), issuing_authority=cert_data.get('issuer'), category='Other', verified=True))
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/preview_resume')
@login_required
def preview_resume():
    rd = ResumeData.query.filter_by(user_id=current_user.id).first()
    if not rd:
        flash('Please build your resume first.', 'warning')
        return redirect(url_for('resume_builder'))
    skills = json.loads(rd.skills) if rd.skills else []
    projects = json.loads(rd.projects) if rd.projects else []
    education = json.loads(rd.education) if rd.education else []
    experience = json.loads(rd.experience) if rd.experience else []
    certificates = Certificate.query.filter_by(user_id=current_user.id).all()
    return render_template('resume_preview.html', full_name=rd.full_name, email=rd.email, phone=rd.phone, address=rd.address, summary=rd.summary, skills=skills, projects=projects, education=education, experience=experience, certificates=certificates, template=rd.template_choice)

# ========== CODE PRACTICE ROUTES ==========
@app.route('/code_practice')
@login_required
def code_practice():
    return render_template('code_practice.html', problems=CODE_PROBLEMS)

import subprocess
import tempfile
import shutil
import re
import glob

_COMPILER_CACHE = {}

def _find_tool(tool_name, extra_paths=None):
    if tool_name in _COMPILER_CACHE: return _COMPILER_CACHE[tool_name]
    found = shutil.which(tool_name)
    if found: _COMPILER_CACHE[tool_name] = found; return found
    search_patterns = []
    if extra_paths: search_patterns.extend(extra_paths)
    common_dirs = [r"C:\msys64\mingw64\bin", r"C:\msys64\ucrt64\bin", r"C:\MinGW\bin", r"C:\mingw64\bin", r"C:\Program Files\Java\*\bin", r"C:\Program Files\Eclipse Adoptium\*\bin", r"C:\Program Files\Microsoft\jdk-*\bin", r"C:\Program Files\nodejs", r"C:\Program Files\dotnet", os.path.expanduser(r"~\scoop\shims"), os.path.expanduser(r"~\AppData\Local\Programs\Python")]
    for pattern in common_dirs:
        for directory in glob.glob(pattern):
            candidate = os.path.join(directory, tool_name)
            if os.path.isfile(candidate) or os.path.isfile(candidate + '.exe'):
                _COMPILER_CACHE[tool_name] = candidate; return candidate
    _COMPILER_CACHE[tool_name] = None; return None

def _build_env_with_tools():
    env = os.environ.copy()
    extra_dirs = set()
    for tool in ['gcc','g++','javac','java','node','dotnet','python']:
        path = _find_tool(tool)
        if path: extra_dirs.add(os.path.dirname(path))
    fallback_dirs = [r"C:\msys64\mingw64\bin", r"C:\msys64\ucrt64\bin", r"C:\MinGW\bin", r"C:\mingw64\bin", r"C:\Program Files\nodejs", r"C:\Program Files\dotnet"]
    for d in fallback_dirs:
        if os.path.isdir(d): extra_dirs.add(d)
    if extra_dirs: env['PATH'] = os.pathsep.join(extra_dirs) + os.pathsep + env.get('PATH', '')
    return env

def _execute_code_snippet(language, code, stdin_data=''):
    tmpdir = tempfile.mkdtemp()
    env = _build_env_with_tools()
    try:
        if language == 'python':
            fpath = os.path.join(tmpdir, 'main.py')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            r = subprocess.run(['python', fpath], input=stdin_data, capture_output=True, text=True, timeout=15, env=env)
            return {'stdout': r.stdout, 'stderr': r.stderr, 'exit_code': r.returncode}
        elif language == 'c':
            fpath = os.path.join(tmpdir, 'main.c')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            exe = os.path.join(tmpdir, 'main.exe')
            c = subprocess.run(['gcc', fpath, '-o', exe], capture_output=True, text=True, timeout=20, env=env)
            if c.returncode != 0: return {'error': c.stderr or 'Compilation error'}
            r = subprocess.run([exe], input=stdin_data, capture_output=True, text=True, timeout=10, env=env)
            return {'stdout': r.stdout, 'stderr': r.stderr, 'exit_code': r.returncode}
        elif language == 'cpp':
            fpath = os.path.join(tmpdir, 'main.cpp')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            exe = os.path.join(tmpdir, 'main.exe')
            c = subprocess.run(['g++', fpath, '-o', exe], capture_output=True, text=True, timeout=20, env=env)
            if c.returncode != 0: return {'error': c.stderr or 'Compilation error'}
            r = subprocess.run([exe], input=stdin_data, capture_output=True, text=True, timeout=10, env=env)
            return {'stdout': r.stdout, 'stderr': r.stderr, 'exit_code': r.returncode}
        elif language == 'java':
            match = re.search(r'public\s+class\s+(\w+)', code)
            cls = match.group(1) if match else 'Main'
            fpath = os.path.join(tmpdir, f'{cls}.java')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            c = subprocess.run(['javac', fpath], capture_output=True, text=True, timeout=25, env=env)
            if c.returncode != 0: return {'error': c.stderr or 'Compilation error'}
            r = subprocess.run(['java', '-cp', tmpdir, cls], input=stdin_data, capture_output=True, text=True, timeout=15, env=env)
            return {'stdout': r.stdout, 'stderr': r.stderr, 'exit_code': r.returncode}
        elif language == 'javascript':
            fpath = os.path.join(tmpdir, 'main.js')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            r = subprocess.run(['node', fpath], input=stdin_data, capture_output=True, text=True, timeout=10, env=env)
            return {'stdout': r.stdout, 'stderr': r.stderr, 'exit_code': r.returncode}
        else:
            return {'error': f'Unsupported language: {language}'}
    except subprocess.TimeoutExpired:
        return {'error': 'Execution timed out'}
    except Exception as e:
        return {'error': str(e)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

@app.route('/submit_code', methods=['POST'])
@login_required
def submit_code():
    data = request.get_json()
    problem_id = data.get('problem_id')
    code = data.get('answer', '').strip()
    language = data.get('language', 'python')
    problem = next((p for p in CODE_PROBLEMS if p['id'] == problem_id), None)
    if not problem: return jsonify({'error': 'Problem not found'}), 404
    if not code: return jsonify({'error': 'Code is empty'}), 400
    test_cases = problem.get('test_cases', [])
    passed = 0; total = len(test_cases); last_error = ''
    import time
    start = time.time()
    for tc in test_cases:
        stdin_data = tc.get('input', '')
        expected = str(tc.get('output', '')).strip()
        result = _execute_code_snippet(language, code, stdin_data)
        if result.get('error'): last_error = result['error']; continue
        stdout = (result.get('stdout') or '').strip()
        if expected and expected in stdout: passed += 1
    runtime = round(time.time() - start, 3)
    time_complexity = random.choice(['O(1)', 'O(log n)', 'O(n)', 'O(n log n)', 'O(n^2)'])
    return jsonify({'passed': passed, 'total': total, 'runtime': f'{runtime}s', 'time_complexity': time_complexity, 'error': last_error})

@app.route('/compiler')
@login_required
def compiler():
    return render_template('compiler.html')

@app.route('/run_code', methods=['POST'])
@login_required
def run_code():
    data = request.get_json() or {}
    language = data.get('language', 'python')
    code = data.get('code', '')
    if not code.strip(): return jsonify({'error': 'Code is empty'}), 400
    tmpdir = tempfile.mkdtemp()
    env = _build_env_with_tools()
    try:
        output = ''; stderr = ''; exit_code = 0
        if language == 'python':
            py = _find_tool('python') or _find_tool('python3') or 'python'
            fpath = os.path.join(tmpdir, 'main.py')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            result = subprocess.run([py, fpath], capture_output=True, text=True, timeout=15, env=env)
            output, stderr, exit_code = result.stdout, result.stderr, result.returncode
        elif language == 'c':
            gcc = _find_tool('gcc')
            if not gcc: return jsonify({'error': 'gcc not found.'}), 500
            fpath = os.path.join(tmpdir, 'main.c')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            exe = os.path.join(tmpdir, 'main.exe')
            compile_res = subprocess.run([gcc, fpath, '-o', exe], capture_output=True, text=True, timeout=20, env=env)
            if compile_res.returncode != 0: return jsonify({'error': 'Compilation error:\n' + (compile_res.stderr or 'Unknown error')}), 400
            result = subprocess.run([exe], capture_output=True, text=True, timeout=10, env=env)
            output, stderr, exit_code = result.stdout, result.stderr, result.returncode
        elif language == 'cpp':
            gpp = _find_tool('g++')
            if not gpp: return jsonify({'error': 'g++ not found.'}), 500
            fpath = os.path.join(tmpdir, 'main.cpp')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            exe = os.path.join(tmpdir, 'main.exe')
            compile_res = subprocess.run([gpp, fpath, '-o', exe], capture_output=True, text=True, timeout=20, env=env)
            if compile_res.returncode != 0: return jsonify({'error': 'Compilation error:\n' + (compile_res.stderr or 'Unknown error')}), 400
            result = subprocess.run([exe], capture_output=True, text=True, timeout=10, env=env)
            output, stderr, exit_code = result.stdout, result.stderr, result.returncode
        elif language == 'java':
            javac = _find_tool('javac'); java = _find_tool('java')
            if not javac or not java: return jsonify({'error': 'javac/java not found.'}), 500
            match = re.search(r'public\s+class\s+(\w+)', code)
            class_name = match.group(1) if match else 'Main'
            fpath = os.path.join(tmpdir, f'{class_name}.java')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            compile_res = subprocess.run([javac, fpath], capture_output=True, text=True, timeout=25, env=env)
            if compile_res.returncode != 0: return jsonify({'error': 'Compilation error:\n' + (compile_res.stderr or 'Unknown error')}), 400
            result = subprocess.run([java, '-cp', tmpdir, class_name], capture_output=True, text=True, timeout=15, env=env)
            output, stderr, exit_code = result.stdout, result.stderr, result.returncode
        elif language == 'javascript':
            node = _find_tool('node')
            if not node: return jsonify({'error': 'node not found.'}), 500
            fpath = os.path.join(tmpdir, 'main.js')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            result = subprocess.run([node, fpath], capture_output=True, text=True, timeout=10, env=env)
            output, stderr, exit_code = result.stdout, result.stderr, result.returncode
        elif language == 'csharp':
            dotnet = _find_tool('dotnet')
            if not dotnet: return jsonify({'error': 'dotnet not found.'}), 500
            csproj = os.path.join(tmpdir, 'app.csproj')
            with open(csproj, 'w', encoding='utf-8') as f: f.write("""<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net8.0</TargetFramework><Nullable>disable</Nullable><ImplicitUsings>disable</ImplicitUsings></PropertyGroup></Project>""")
            fpath = os.path.join(tmpdir, 'Program.cs')
            with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
            result = subprocess.run([dotnet, 'run', '--project', tmpdir, '--nologo', '--verbosity', 'quiet'], capture_output=True, text=True, timeout=90, cwd=tmpdir, env=env)
            output = result.stdout; stderr = result.stderr; exit_code = result.returncode
            if exit_code != 0 and 'error' in (stderr or '').lower(): return jsonify({'error': 'Compilation error:\n' + stderr}), 400
        else:
            return jsonify({'error': f'Unsupported language: {language}'}), 400
        full_output = output + (('\n' + stderr) if stderr and stderr not in output else '')
        return jsonify({'success': True, 'output': full_output.strip() or '(No output)', 'stdout': output, 'stderr': stderr, 'exit_code': exit_code})
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Execution timed out.'}), 504
    except FileNotFoundError as e:
        return jsonify({'error': f'Compiler not found: {e}.'}), 500
    except Exception as e:
        return jsonify({'error': f'Execution failed: {str(e)}'}), 500
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

@app.route('/compiler_diagnostics')
@login_required
def compiler_diagnostics():
    tools = ['gcc','g++','javac','java','node','dotnet','python']
    result = {}
    for t in tools:
        p = _find_tool(t)
        result[t] = p if p else '❌ NOT FOUND'
    return jsonify(result)

# ========== ROADMAP & TIPS ==========
@app.route('/get_roadmap')
@login_required
def get_roadmap():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis: return jsonify({'error': 'No resume'}), 400
    weak_topics = [w.topic for w in WeakArea.query.filter_by(user_id=current_user.id).all()]
    missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    avg = progress.average_score if progress else 0
    roadmap, platforms = AIEngine.generate_roadmap(weak_topics, missing, analysis.target_company, analysis.job_role, avg)
    existing = Roadmap.query.filter_by(user_id=current_user.id).first()
    if existing:
        existing.plan_data = json.dumps(roadmap); existing.updated_at = datetime.utcnow()
    else:
        db.session.add(Roadmap(user_id=current_user.id, plan_data=json.dumps(roadmap)))
    db.session.commit()
    return jsonify({'roadmap': roadmap, 'platforms': platforms, 'weak_areas': weak_topics[:5], 'avg_score': avg})

@app.route('/resume_suggestions')
@login_required
def resume_suggestions():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis: return jsonify({'error': 'No resume'}), 400
    skills = json.loads(analysis.skills) if analysis.skills else []
    missing = json.loads(analysis.missing_skills) if analysis.missing_skills else []
    sug = []
    if len(skills) < 5: sug.append("Add more relevant technical skills.")
    if missing: sug.append(f"Include projects demonstrating: {', '.join(missing[:3])}")
    sug.extend(["Use action verbs and quantify achievements.", "Tailor summary to job description.", "Add GitHub/LinkedIn links."])
    return jsonify({'suggestions': sug})

@app.route('/motivation_tip')
@login_required
def motivation_tip():
    tips = ["💪 Consistency beats intensity. Study 2 hours daily!", "🎯 Set small daily goals.", "📝 Review mistakes daily.", "🧠 Practice mock interviews.", "⏰ Use Pomodoro technique.", "🌟 Visualize success.", "🤝 Join study groups."]
    return jsonify({'tip': random.choice(tips)})

# ========== QUIZ SYSTEM ROUTES ==========
@app.route('/quiz_dashboard')
@login_required
def quiz_dashboard():
    initialize_quiz_questions()
    attempts = QuizAttempt.query.filter_by(user_id=current_user.id).order_by(QuizAttempt.day_number).all()
    total_attempts = len(attempts)
    completed = sum(1 for a in attempts if a.completed)
    total_correct = sum(a.correct_answers for a in attempts)
    total_questions = sum(a.total_questions for a in attempts)
    avg_score = (total_correct / total_questions * 100) if total_questions > 0 else 0
    stats = {'total_attempts': total_attempts,'completed': completed,'total_correct': total_correct,'total_questions': total_questions,'avg_score': round(avg_score, 1),'current_day': 1}
    return render_template('quiz_dashboard.html', attempts=attempts, stats=stats)

@app.route('/quiz_hint', methods=['POST'])
@login_required
def quiz_hint():
    data = request.get_json()
    question_text = data.get('question', '')
    if not question_text: return jsonify({'error': 'No question provided'}), 400
    # Local fallback hint instead of Groq
    hint = "Think carefully about the core concept involved. Eliminate the obviously wrong options first."
    return jsonify({'hint': hint})

@app.route('/quiz_explain', methods=['POST'])
@login_required
def quiz_explain():
    data = request.get_json()
    question_text = data.get('question', '')
    correct_answer = data.get('correct_answer', '')
    if not question_text or not correct_answer: return jsonify({'error': 'Missing data'}), 400
    # Local fallback explanation instead of Groq
    explanation = f"The correct answer is {correct_answer}. Review the core concept related to this question to understand why."
    return jsonify({'explanation': explanation})

@app.route('/start_quiz/<int:day_number>')
@login_required
def start_quiz(day_number):
    focus = request.args.get('focus', 'Personalized Quiz')
    existing = QuizAttempt.query.filter_by(user_id=current_user.id, day_number=day_number).first()
    if existing and existing.completed:
        flash(f'You have already completed Day {day_number} quiz!', 'warning')
        return redirect(url_for('preparation'))
    initialize_quiz_questions()
    questions = []
    try:
        questions = generate_ai_quiz_questions(current_user.id, count=10, day_number=day_number)
    except Exception as e:
        logger.error(f"AI gen error: {e}")
    if not questions or len(questions) < 5:
        all_qs = QuizQuestion.query.filter_by(category='AI').all() + QuizQuestion.query.filter(QuizQuestion.category != 'AI').all()
        random.seed(dt.date.today().toordinal())
        random.shuffle(all_qs)
        random.seed()
        questions = all_qs[:10]
    if not questions:
        flash('No quiz questions available. Please try again.', 'warning')
        return redirect(url_for('dashboard'))
    session['quiz_questions'] = [q.id for q in questions]
    session['quiz_day'] = day_number
    session['quiz_focus'] = focus
    return render_template('take_quiz.html', questions=questions, day_number=day_number, total_questions=len(questions), focus=focus)

@app.route('/submit_quiz', methods=['POST'])
@login_required
def submit_quiz():
    try:
        data = request.get_json()
        answers = data.get('answers', [])
        day_number = session.get('quiz_day', 1)
        question_ids = session.get('quiz_questions', [])
        if not question_ids:
            return jsonify({'error': 'Quiz session expired. Please refresh and try again.'}), 400
        correct = 0
        wrong_answers = []
        for idx, qid in enumerate(question_ids):
            question = QuizQuestion.query.get(qid)
            if question:
                user_answer = answers[idx] if idx < len(answers) else ''
                is_correct = user_answer == question.correct_answer
                if is_correct:
                    correct += 1
                else:
                    wrong_answers.append({
                        'id': qid,
                        'question': question.question_text,
                        'your_answer': user_answer,
                        'correct_answer': question.correct_answer,
                        'options': [question.option_a, question.option_b, question.option_c, question.option_d]
                    })
        score = (correct / len(question_ids)) * 100 if question_ids else 0
        attempt = QuizAttempt(
            user_id=current_user.id,
            day_number=day_number,
            total_questions=len(question_ids),
            correct_answers=correct,
            wrong_answers=json.dumps(wrong_answers),
            score=score,
            completed=True,
            question_ids=json.dumps(question_ids)
        )
        db.session.add(attempt)
        db.session.commit()
        session.pop('quiz_questions', None)
        session.pop('quiz_day', None)
        return jsonify({
            'score': round(score, 1),
            'correct': correct,
            'total': len(question_ids),
            'wrong_answers': wrong_answers
        })
    except Exception as e:
        print(f"❌ QUIZ SUBMIT ERROR: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz_result_details/<int:attempt_id>')
@login_required
def quiz_result_details(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id: return jsonify({'error': 'Unauthorized'}), 403
    question_ids = json.loads(attempt.question_ids) if attempt.question_ids else []
    wrong_data = json.loads(attempt.wrong_answers) if attempt.wrong_answers else []
    wrong_dict = {w.get('id'): w for w in wrong_data if 'id' in w}
    details = []
    for qid in question_ids:
        question = QuizQuestion.query.get(qid)
        if not question: continue
        if qid in wrong_dict:
            details.append({'question': question.question_text,'options': [question.option_a, question.option_b, question.option_c, question.option_d],'user_answer': wrong_dict[qid]['your_answer'],'correct_answer': question.correct_answer,'is_correct': False})
        else:
            details.append({'question': question.question_text,'options': [question.option_a, question.option_b, question.option_c, question.option_d],'user_answer': question.correct_answer,'correct_answer': question.correct_answer,'is_correct': True})
    return jsonify({'details': details})

@app.route('/quiz_results/<int:attempt_id>')
@login_required
def quiz_results(attempt_id):
    attempt = QuizAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('quiz_dashboard'))
    wrong_answers = json.loads(attempt.wrong_answers) if attempt.wrong_answers else []
    return render_template('quiz_results.html', attempt=attempt, wrong_answers=wrong_answers)

@app.route('/quiz_leaderboard')
@login_required
def quiz_leaderboard():
    users_data = []
    for u in User.query.all():
        attempts = QuizAttempt.query.filter_by(user_id=u.id, completed=True).all()
        if attempts:
            total_score = sum(a.score for a in attempts)
            avg_score = total_score / len(attempts)
            users_data.append({'name': u.name, 'email': u.email, 'avg_score': round(avg_score, 1), 'total_attempts': len(attempts), 'total_correct': sum(a.correct_answers for a in attempts)})
    users_data.sort(key=lambda x: x['avg_score'], reverse=True)
    return render_template('quiz_leaderboard.html', users=users_data)

# ========== NEW: DAILY JOB ROLE QUIZ ==========
@app.route('/job_quiz')
@login_required
def job_quiz():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis:
        flash('Please upload your resume first to get job-specific quizzes!', 'warning')
        return redirect(url_for('dashboard'))
    
    job_role = analysis.job_role.lower().replace(" ", "_")
    file_path = os.path.join(app.root_path, 'job_roles', f'{job_role}.json')
    
    if not os.path.exists(file_path):
        flash(f'No specific quiz found for "{analysis.job_role}". Showing general technical quiz.', 'info')
        file_path = os.path.join(app.root_path, 'job_roles', 'software_developer.json')
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        # --- BULLETPROOF PARSER FOR YOUR SPECIFIC JSON ---
        all_questions = []
        
        # 1. Look for the "questions" array inside the wrapper object
        if isinstance(raw_data, dict) and "questions" in raw_data:
            raw_data = raw_data["questions"]
                
        # 2. Process each question
        for item in raw_data:
            if not isinstance(item, dict): continue
            
            q_text = item.get('question')
            raw_opts = item.get('options', {}) # This is a dict like {"A": "...", "B": "..."}
            correct_ans = item.get('correct_answer')
            exp = item.get('explanation', 'No explanation provided.')
            
            # Format options: Convert {"A": "text"} to a simple list of texts ["text 1", "text 2", ...]
            formatted_options = []
            expected_correct_text = ""
            
            if isinstance(raw_opts, dict):
                # Sort keys (A, B, C, D) to ensure correct order
                for key in sorted(raw_opts.keys()):
                    text = raw_opts[key]
                    formatted_options.append(str(text))
                    # If this key matches the correct answer (e.g., "B"), save the text
                    if key == correct_ans:
                        expected_correct_text = str(text)
            elif isinstance(raw_opts, list):
                formatted_options = [str(o) for o in raw_opts]
                expected_correct_text = correct_ans
            
            if q_text and formatted_options:
                all_questions.append({
                    'question': q_text,
                    'options': formatted_options,
                    'answer': expected_correct_text, # Store the actual TEXT of the correct answer
                    'explanation': exp
                })

        print(f"✅ DEBUG: Loaded {len(all_questions)} valid questions from {job_role}.json")

        if len(all_questions) == 0:
            flash('The JSON file format is incorrect. No questions could be loaded.', 'danger')
            return redirect(url_for('preparation'))

        today_str = date.today().isoformat()
        seed_string = f"{today_str}_{current_user.id}_{job_role}"
        rng = random.Random(seed_string)
        
        shuffled_questions = list(all_questions)
        rng.shuffle(shuffled_questions)
        daily_questions = shuffled_questions[:10]
        
        session['current_quiz'] = daily_questions
        session['quiz_date'] = today_str
        
        client_questions = []
        for idx, q in enumerate(daily_questions):
            client_questions.append({
                'id': idx,
                'question': q['question'],
                'options': q['options']
            })
            
        return render_template('job_quiz.html', 
                               questions=client_questions, 
                               role_name=analysis.job_role,
                               quiz_date=today_str)
                               
    except Exception as e:
        print(f"❌ ERROR loading quiz: {e}")
        flash('Error loading the quiz. Please try again.', 'danger')
        return redirect(url_for('preparation'))


@app.route('/check_job_quiz', methods=['POST'])
@login_required
def check_job_quiz():
    data = request.get_json()
    user_answers = data.get('answers', {})
    
    current_quiz_date = session.get('quiz_date')
    today_str = date.today().isoformat()
    
    if current_quiz_date != today_str:
        return jsonify({'error': 'This quiz is expired. Please reload to get today\'s questions.'}), 400

    quiz_questions = session.get('current_quiz', [])
    if not quiz_questions:
        return jsonify({'error': 'Quiz session expired. Please reload the page.'}), 400
        
    results = []
    score = 0
    wrong_answers = [] # To save to database
    
    for idx_str, user_ans in user_answers.items():
        idx = int(idx_str)
        if idx >= len(quiz_questions):
            continue
            
        q = quiz_questions[idx]
        correct_text = q.get('answer') # This is now the text (e.g., "<main>")
        explanation = q.get('explanation', 'No explanation provided.')
        
        is_correct = (user_ans == correct_text)
        
        if is_correct:
            score += 1
        else:
            wrong_answers.append({
                'question': q.get('question'),
                'your_answer': user_ans,
                'correct_answer': correct_text,
                'explanation': explanation
            })
            
        results.append({
            'question': q.get('question'),
            'user_answer': user_ans,
            'correct_answer': correct_text,
            'is_correct': is_correct,
            'explanation': explanation
        })

    # --- SAVE TO QUIZ DASHBOARD DB ---
    try:
        # Calculate percentage score (0-100)
        percentage_score = (score / len(quiz_questions)) * 100 if quiz_questions else 0
        
        # Find if a quiz was already attempted today for this role
        # (We use day_number 1 here as a placeholder, or you can track the actual day)
        new_attempt = QuizAttempt(
            user_id=current_user.id,
            day_number=1, # You can change this logic if you track actual 28-day prep days
            total_questions=len(quiz_questions),
            correct_answers=score,
            wrong_answers=json.dumps(wrong_answers),
            score=percentage_score,
            completed=True,
            question_ids=json.dumps([]) # We don't strictly need IDs for job_quiz
        )
        db.session.add(new_attempt)
        db.session.commit()
        
        # Update UserProgress for Leaderboard
        progress = UserProgress.query.filter_by(user_id=current_user.id).first()
        if not progress:
            progress = UserProgress(user_id=current_user.id)
            db.session.add(progress)
            
        # Simple running average logic
        total_answered = progress.total_questions_answered + len(quiz_questions)
        current_avg = progress.average_score
        
        # Convert current_avg (out of 10) to raw score for calculation
        raw_current_total = (current_avg / 10.0) * progress.total_questions_answered
        new_raw_total = raw_current_total + score
        new_avg_out_of_10 = (new_raw_total / total_answered) * 10
        
        progress.total_questions_answered = total_answered
        progress.average_score = new_avg_out_of_10
        progress.last_active = datetime.utcnow()
        
        db.session.commit()
        print(f"✅ Saved Quiz Attempt. Score: {score}/{len(quiz_questions)}")
        
    except Exception as e:
        print(f"❌ ERROR saving quiz attempt: {e}")
        db.session.rollback()
    # ---------------------------------

    return jsonify({
        'score': score,
        'total': len(quiz_questions),
        'results': results
    })

# ========== MODULES 9–20, 23 ==========
@app.route('/company_dashboard')
@login_required
def company_dashboard():
    companies = ['TCS', 'Infosys', 'Google', 'Amazon', 'Microsoft', 'Wipro', 'Accenture']
    company_data = []
    for company in companies:
        data = CompanyPlacement.query.filter_by(user_id=current_user.id, company_name=company).first()
        if not data:
            data = CompanyPlacement(user_id=current_user.id, company_name=company, aptitude_score=random.randint(60,95), coding_score=random.randint(65,90), interview_score=random.randint(55,85))
            db.session.add(data); db.session.commit()
        data.overall_score = (data.aptitude_score + data.coding_score + data.interview_score) / 3
        company_data.append(data)
    return render_template('company_dashboard.html', companies=company_data)

@app.route('/ats_checker', methods=['GET','POST'])
@login_required
def ats_checker():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    result = None
    if analysis and analysis.resume_text:
        result = resume_optimizer.analyze_resume(analysis.resume_text, analysis.target_company or 'TCS')
    return render_template('ats_checker.html', result=result)

@app.route('/job_recommendations')
@login_required
def job_recommendations():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    answers = AnswerEvaluation.query.filter_by(user_id=current_user.id).all()
    skills = json.loads(analysis.skills) if analysis and analysis.skills else []
    interview_scores = [a.score for a in answers if a.score]
    job_requirements = {'Software Engineer': {'skills': ['python','java','sql','data structures','algorithms'], 'min_score':60},'Data Analyst': {'skills': ['python','sql','excel','statistics','tableau'], 'min_score':60},'Python Developer': {'skills': ['python','django','flask','sql','rest api'], 'min_score':65},'ML Engineer': {'skills': ['python','machine learning','tensorflow','sql','statistics'], 'min_score':70},'Web Developer': {'skills': ['javascript','react','html','css','node.js'], 'min_score':60}}
    avg_interview = sum(interview_scores)/len(interview_scores) if interview_scores else 50
    skills_lower = [s.lower() for s in skills]
    recommendations = []
    for job, req in job_requirements.items():
        match = sum(1 for rs in req['skills'] if any(rs in us for us in skills_lower))
        skill_perc = (match/len(req['skills']))*100
        fit = (skill_perc*0.6)+(avg_interview*0.4)
        if fit >= req['min_score']:
            recommendations.append({'job_title':job,'fit_percentage':round(fit,1),'required_skills':req['skills'][:4],'skill_match':f"{match}/{len(req['skills'])}"})
    recommendations.sort(key=lambda x:x['fit_percentage'], reverse=True)
    return render_template('job_recommendations.html', recommendations=recommendations[:5])

@app.route('/avatar_interview')
@login_required
def avatar_interview():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    company = analysis.target_company if analysis else 'Company'
    role = analysis.job_role if analysis else 'Role'
    return render_template('avatar_interview.html', company=company, role=role)

@app.route('/analytics_dashboard')
@login_required
def analytics_dashboard():
    answers = AnswerEvaluation.query.filter_by(user_id=current_user.id).all()
    weak_areas = WeakArea.query.filter_by(user_id=current_user.id).all()
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    scores = [a.score for a in answers if a.score]
    dates = [a.created_at.strftime('%Y-%m-%d') for a in answers]
    type_scores = {}
    for a in answers:
        q = InterviewQuestion.query.get(a.question_id)
        if q: type_scores.setdefault(q.question_type, []).append(a.score)
    avg_by_type = {k: sum(v)/len(v) for k,v in type_scores.items()}
    return render_template('analytics_dashboard.html', scores=scores, dates=dates, avg_score=progress.average_score if progress else 0, total_answers=len(answers), weak_areas=weak_areas[:5], type_scores=avg_by_type)

@app.route('/group_discussion')
@login_required
def group_discussion():
    topics = ["Artificial Intelligence vs Human Intelligence", "Remote Work: Future or Trend?", "Social Media Impact", "Cryptocurrency Risk", "Climate Change Responsibility"]
    return render_template('group_discussion.html', topics=topics)

@app.route('/evaluate_gd', methods=['POST'])
@login_required
def evaluate_gd():
    data = request.get_json()
    topic = data.get('topic', '')
    response = data.get('response', '')
    is_valid, error_msg = is_meaningful_answer(response, topic)
    if not is_valid:
        return jsonify({'error': True,'communication_score': 0,'grammar_score': 0,'confidence_score': 0,'overall_score': 0,'comm_feedback': f'❌ {error_msg}','word_count': len(response.split())})
    word_count = len(response.split())
    comm_score = 85 if word_count >= 100 else (65 if word_count >= 50 else 40)
    grammar_score = max(0, 100 - (response.lower().count('  ') * 5))
    conf_score = min(100, (word_count / 120) * 100)
    overall = (comm_score * 0.4) + (grammar_score * 0.3) + (conf_score * 0.3)
    gd = GroupDiscussion(user_id=current_user.id, topic=topic, user_response=response, communication_score=comm_score, grammar_score=grammar_score, confidence_score=conf_score, overall_score=overall)
    db.session.add(gd); db.session.commit()
    return jsonify({'communication_score': comm_score,'grammar_score': grammar_score,'confidence_score': conf_score,'overall_score': round(overall, 1),'comm_feedback': 'Good' if comm_score > 60 else 'Needs improvement','word_count': word_count})

@app.route('/linkedin_analyzer', methods=['GET','POST'])
@login_required
def linkedin_analyzer():
    result = None
    if request.method == 'POST':
        headline = request.form.get('headline','')
        skills = [s.strip() for s in request.form.get('skills','').split(',') if s.strip()]
        experience = [e.strip() for e in request.form.get('experience','').split(',') if e.strip()]
        headline_score = 100 if len(headline)>=60 else (70 if len(headline)>=30 else 40)
        skills_score = 100 if len(skills)>=10 else (60 if len(skills)>=5 else 30)
        exp_score = 100 if len(experience)>=2 else (50 if len(experience)>=1 else 20)
        overall = (headline_score+skills_score+exp_score)/3
        suggestions = []
        if headline_score<70: suggestions.append("Add a compelling headline with your key skills")
        if skills_score<60: suggestions.append(f"Add {10-len(skills)} more skills for better visibility")
        if exp_score<50: suggestions.append("Add detailed work experience descriptions")
        result = {'overall_score':round(overall,1), 'scores':{'headline':headline_score,'skills':skills_score,'experience':exp_score}, 'suggestions':suggestions}
    return render_template('linkedin_analyzer.html', result=result)

@app.route('/placement_tracker')
@login_required
def placement_tracker():
    apps = JobApplication.query.filter_by(user_id=current_user.id).order_by(JobApplication.application_date.desc()).all()
    stats = {'total':len(apps), 'applied':len([a for a in apps if a.status=='Applied']), 'interview':len([a for a in apps if a.status=='Interview Scheduled']), 'selected':len([a for a in apps if a.status=='Selected']), 'rejected':len([a for a in apps if a.status=='Rejected'])}
    return render_template('placement_tracker.html', applications=apps, stats=stats)

@app.route('/add_application', methods=['POST'])
@login_required
def add_application():
    data = request.get_json()
    app = JobApplication(user_id=current_user.id, company_name=data.get('company'), job_role=data.get('role'), status=data.get('status','Applied'))
    db.session.add(app); db.session.commit()
    return jsonify({'status':'success'})

@app.route('/update_application/<int:app_id>', methods=['POST'])
@login_required
def update_application(app_id):
    app = JobApplication.query.get_or_404(app_id)
    if app.user_id != current_user.id: return jsonify({'error':'Unauthorized'}),403
    data = request.get_json(); app.status = data.get('status'); db.session.commit()
    return jsonify({'status':'success'})

@app.route('/delete_application/<int:app_id>', methods=['DELETE'])
@login_required
def delete_application(app_id):
    app = JobApplication.query.get_or_404(app_id)
    if app.user_id != current_user.id: return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(app); db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/certificates')
@login_required
def certificates():
    certs = Certificate.query.filter_by(user_id=current_user.id).all()
    return render_template('certificates.html', certificates=certs)

@app.route('/upload_certificate', methods=['POST'])
@login_required
def upload_certificate():
    name = request.form.get('name')
    authority = request.form.get('authority')
    category = request.form.get('category')
    if not category:
        if 'python' in name.lower(): category='Python'
        elif 'java' in name.lower(): category='Java'
        elif 'aws' in name.lower() or 'cloud' in name.lower(): category='AWS/Cloud'
        elif 'data' in name.lower(): category='Data Analytics'
        else: category='Other'
    file = request.files.get('certificate_file')
    file_path = None
    if file and file.filename != '':
        if not allowed_cert_file(file.filename):
            flash('Invalid file type! Only PDF, JPG, JPEG, and PNG are allowed.', 'danger')
            return redirect(url_for('certificates'))
        filename = secure_filename(file.filename)
        unique_filename = f"cert_{current_user.id}_{int(datetime.now().timestamp())}_{filename}"
        cert_upload_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'certificates')
        os.makedirs(cert_upload_folder, exist_ok=True)
        file_path = os.path.join(cert_upload_folder, unique_filename)
        file.save(file_path)
        file_path = f"certificates/{unique_filename}"
    cert = Certificate(
        user_id=current_user.id,
        certificate_name=name,
        issuing_authority=authority,
        category=category,
        certificate_file=file_path,
        verified=True
    )
    db.session.add(cert)
    db.session.commit()
    flash('Certificate uploaded successfully!', 'success')
    return redirect(url_for('certificates'))

# ========== FIXED ROUTE ==========
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/career_predictor')
@login_required
def career_predictor():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    skills = json.loads(analysis.skills) if analysis and analysis.skills else []
    career_paths = {'Frontend Developer': ['html','css','javascript','react','angular'],'Backend Developer': ['python','java','node.js','sql','mongodb'],'Data Analyst': ['python','sql','excel','tableau','statistics'],'ML Engineer': ['python','machine learning','tensorflow','sql','statistics'],'DevOps Engineer': ['docker','kubernetes','aws','jenkins','linux']}
    skills_lower = [s.lower() for s in skills]
    predictions = []
    for career, req_skills in career_paths.items():
        match = sum(1 for rs in req_skills if any(rs in us for us in skills_lower))
        perc = (match/len(req_skills))*100
        predictions.append({'career':career, 'match_percentage':min(100,perc+10), 'required_skills':req_skills[:5]})
    predictions.sort(key=lambda x:x['match_percentage'], reverse=True)
    return render_template('career_predictor.html', predictions=predictions[:3])

@app.route('/coding_arena')
@login_required
def coding_arena():
    contests = [{'id':1,'name':'Weekly Challenge #1','difficulty':'Easy','participants':45,'top_score':95}, {'id':2,'name':'Weekly Challenge #2','difficulty':'Medium','participants':32,'top_score':88}, {'id':3,'name':'Weekly Challenge #3','difficulty':'Hard','participants':18,'top_score':76}]
    user_contests = CodingContest.query.filter_by(user_id=current_user.id).all()
    return render_template('coding_arena.html', contests=contests, user_contests=user_contests)

# ========== DAILY CODING CHALLENGE ==========
@app.route('/daily_challenge')
@login_required
def daily_challenge():
    today = dt.date.today()
    day_index = today.toordinal() % len(CODE_PROBLEMS)
    problem = CODE_PROBLEMS[day_index]
    existing = DailyCodingChallenge.query.filter_by(user_id=current_user.id, challenge_date=today).first()
    return render_template('daily_challenge.html', problem=problem, today=today.strftime('%A, %d %B %Y'), existing=existing)

@app.route('/submit_daily_challenge', methods=['POST'])
@login_required
def submit_daily_challenge():
    data = request.get_json() or {}
    code = data.get('code', '').strip()
    language = data.get('language', 'python')
    problem_id = data.get('problem_id')
    if not code: return jsonify({'error': 'Please write some code.'}), 400
    problem = next((p for p in CODE_PROBLEMS if p['id'] == problem_id), None)
    if not problem: return jsonify({'error': 'Problem not found'}), 404
    test_cases = problem.get('test_cases', [])
    passed = 0; total = len(test_cases); last_output = ''
    tmpdir = tempfile.mkdtemp()
    try:
        for tc in test_cases:
            stdin_data = tc.get('input', '')
            if language == 'python':
                fpath = os.path.join(tmpdir, 'main.py')
                with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
                cmd = ['python', fpath]
            elif language == 'c':
                fpath = os.path.join(tmpdir, 'main.c')
                with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
                exe = os.path.join(tmpdir, 'main.exe')
                subprocess.run(['gcc', fpath, '-o', exe], capture_output=True, text=True, timeout=15)
                cmd = [exe]
            elif language == 'cpp':
                fpath = os.path.join(tmpdir, 'main.cpp')
                with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
                exe = os.path.join(tmpdir, 'main.exe')
                subprocess.run(['g++', fpath, '-o', exe], capture_output=True, text=True, timeout=15)
                cmd = [exe]
            elif language == 'java':
                fpath = os.path.join(tmpdir, 'Main.java')
                with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
                subprocess.run(['javac', fpath], capture_output=True, text=True, timeout=20)
                cmd = ['java', '-cp', tmpdir, 'Main']
            elif language == 'javascript':
                fpath = os.path.join(tmpdir, 'main.js')
                with open(fpath, 'w', encoding='utf-8') as f: f.write(code)
                cmd = ['node', fpath]
            else:
                return jsonify({'error': f'Unsupported language: {language}'}), 400
            try:
                result = subprocess.run(cmd, input=stdin_data, capture_output=True, text=True, timeout=15)
                stdout = (result.stdout or '').strip(); stderr = (result.stderr or '').strip()
                last_output = stdout or stderr
                expected = str(tc.get('output', '')).strip()
                if expected and expected in stdout: passed += 1
            except subprocess.TimeoutExpired:
                last_output = 'Execution timed out'
            except Exception as e:
                last_output = f'Error: {e}'
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    score = round((passed / total) * 100, 1) if total > 0 else 0
    today = dt.date.today()
    existing = DailyCodingChallenge.query.filter_by(user_id=current_user.id, challenge_date=today).first()
    if existing:
        existing.user_code = code; existing.language = language; existing.score = score; existing.passed = passed; existing.total = total; existing.submitted_at = datetime.utcnow()
    else:
        db.session.add(DailyCodingChallenge(user_id=current_user.id, challenge_date=today, challenge_id=problem_id, user_code=code, language=language, score=score, passed=passed, total=total))
    db.session.commit()
    if score >= 80: award_badge(current_user.id, 'Code Master', 'Coding')
    if score == 100: award_badge(current_user.id, 'Coding Ninja', 'Coding')
    return jsonify({'score': score,'passed': passed,'total': total,'output': last_output,'message': f'{passed}/{total} test cases passed'})

@app.route('/coding_leaderboard')
@login_required
def coding_leaderboard():
    from sqlalchemy import func
    rows = (db.session.query(User.id, User.name, User.email, func.avg(DailyCodingChallenge.score).label('avg_score'), func.count(DailyCodingChallenge.id).label('days_attempted'), func.max(DailyCodingChallenge.score).label('best_score')).join(DailyCodingChallenge, DailyCodingChallenge.user_id == User.id).group_by(User.id).order_by(func.avg(DailyCodingChallenge.score).desc()).all())
    leaderboard = [{'rank': i + 1,'name': r.name,'email': r.email,'avg_score': round(r.avg_score, 1),'days_attempted': r.days_attempted,'best_score': round(r.best_score, 1)} for i, r in enumerate(rows)]
    return render_template('coding_leaderboard.html', users=leaderboard)

@app.route('/my_daily_submissions')
@login_required
def my_daily_submissions():
    submissions = (DailyCodingChallenge.query.filter_by(user_id=current_user.id).order_by(DailyCodingChallenge.challenge_date.desc()).all())
    enriched = []
    for s in submissions:
        prob = next((p for p in CODE_PROBLEMS if p['id'] == s.challenge_id), None)
        enriched.append({'date': s.challenge_date.strftime('%d %b %Y'),'title': prob['title'] if prob else 'Unknown','difficulty': prob['difficulty'] if prob else '-','language': s.language,'score': s.score,'passed': s.passed,'total': s.total,'code': s.user_code})
    return render_template('my_daily_submissions.html', submissions=enriched)

@app.route('/submit_contest/<int:contest_id>', methods=['POST'])
@login_required
def submit_contest(contest_id):
    data = request.get_json()
    code = data.get('code','')
    score = evaluate_code_quality(code)
    entry = CodingContest(contest_name=f'Weekly Challenge #{contest_id}', user_id=current_user.id, score=score)
    db.session.add(entry); db.session.commit()
    if score >= 90: award_badge(current_user.id, 'Coding Ninja', 'Coding')
    elif score >= 75: award_badge(current_user.id, 'Code Master', 'Coding')
    return jsonify({'score':score, 'message':'Submitted!'})

@app.route('/readiness_meter')
@login_required
def readiness_meter():
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    progress = UserProgress.query.filter_by(user_id=current_user.id).first()
    weak_areas = WeakArea.query.filter_by(user_id=current_user.id).all()
    coding = min(100, (progress.total_questions_answered*2) if progress else 0)
    interview = progress.average_score*10 if progress else 0
    aptitude = random.randint(65,95)
    resume = 70
    if analysis and analysis.skills:
        skills_count = len(json.loads(analysis.skills))
        resume = min(100, 50 + (skills_count*2))
    overall = (coding+interview+aptitude+resume)/4 - (len(weak_areas)*3)
    overall = max(0, min(100, overall))
    readiness = {'overall':round(overall,1), 'coding':round(coding,1), 'interview':round(interview,1), 'aptitude':round(aptitude,1), 'resume':round(resume,1), 'level':'Excellent' if overall>=80 else 'Good' if overall>=60 else 'Needs Improvement'}
    return render_template('readiness_meter.html', readiness=readiness)

@app.route('/resume_optimizer')
@login_required
def resume_optimizer_page():
    companies = ['TCS','Infosys','Wipro','Accenture','Cognizant','Google','Amazon','Microsoft','Meta','Adobe']
    return render_template('resume_optimizer.html', companies=companies)

@app.route('/analyze_company_resume', methods=['POST'])
@login_required
def analyze_company_resume():
    data = request.get_json()
    company_name = data.get('company')
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not analysis: return jsonify({'error':'Please upload your resume first'}),400
    result = resume_optimizer.analyze_resume(analysis.resume_text, company_name)
    result['suggestions'] = resume_optimizer.get_improvement_suggestions(result, company_name)
    return jsonify(result)

@app.route('/optimize_company_resume', methods=['POST'])
@login_required
def optimize_company_resume():
    data = request.get_json()
    company_name = data.get('company')
    rd = ResumeData.query.filter_by(user_id=current_user.id).first()
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not rd: return jsonify({'error':'Please build your resume first'}),400
    resume_data = {'summary':rd.summary or '', 'skills':json.loads(rd.skills) if rd.skills else [], 'projects':json.loads(rd.projects) if rd.projects else [], 'achievements':[]}
    resume_text = analysis.resume_text if analysis else ''
    analysis_result = resume_optimizer.analyze_resume(resume_text, company_name)
    optimized = resume_optimizer.generate_optimized_resume(resume_data, company_name, analysis_result)
    existing = CompanyResume.query.filter_by(user_id=current_user.id, company_name=company_name).first()
    if existing:
        existing.optimized_resume = json.dumps(optimized); existing.ats_score = analysis_result['ats_score']; existing.readiness_score = analysis_result['readiness_score']; existing.missing_skills = json.dumps(analysis_result['missing_keywords']); existing.optimized_sections = json.dumps(optimized)
    else:
        cr = CompanyResume(user_id=current_user.id, company_name=company_name, optimized_resume=json.dumps(optimized), ats_score=analysis_result['ats_score'], readiness_score=analysis_result['readiness_score'], missing_skills=json.dumps(analysis_result['missing_keywords']), optimized_sections=json.dumps(optimized))
        db.session.add(cr)
    db.session.commit()
    return jsonify({'analysis':analysis_result, 'optimized':optimized, 'message':f'Resume optimized for {company_name}!'})

@app.route('/compare_resume_companies')
@login_required
def compare_resume_companies():
    companies = ['TCS','Infosys','Google','Amazon','Microsoft','Wipro']
    rd = ResumeData.query.filter_by(user_id=current_user.id).first()
    analysis = ResumeAnalysis.query.filter_by(user_id=current_user.id).first()
    if not rd: return jsonify({'error':'Please build your resume first'}),400
    resume_data = {'summary':rd.summary or '', 'skills':json.loads(rd.skills) if rd.skills else [], 'projects':json.loads(rd.projects) if rd.projects else []}
    comparisons = resume_optimizer.compare_companies(resume_data, companies)
    return jsonify({'comparisons':comparisons})

@app.route('/save_resume_version', methods=['POST'])
@login_required
def save_resume_version():
    data = request.get_json()
    version = ResumeVersion(user_id=current_user.id, version_name=data.get('version_name'), resume_data=json.dumps(data.get('resume_data')))
    db.session.add(version); db.session.commit()
    return jsonify({'status':'success','version_id':version.id})

@app.route('/get_resume_versions')
@login_required
def get_resume_versions():
    versions = ResumeVersion.query.filter_by(user_id=current_user.id).order_by(ResumeVersion.created_at.desc()).all()
    return jsonify({'versions':[{'id':v.id,'name':v.version_name,'date':v.created_at.strftime('%Y-%m-%d %H:%M')} for v in versions]})

@app.route('/load_resume_version/<int:version_id>')
@login_required
def load_resume_version(version_id):
    version = ResumeVersion.query.get_or_404(version_id)
    if version.user_id != current_user.id: return jsonify({'error':'Unauthorized'}),403
    return jsonify({'resume_data':json.loads(version.resume_data)})

# ========== MISSING ROUTES ==========
@app.route('/hr_generator', methods=['POST'])
@login_required
def hr_generator():
    data = request.get_json()
    q = data.get('question','')
    ans = "Use STAR method. Be specific with metrics and examples."
    if 'yourself' in q.lower(): ans = "I am a passionate professional with strong skills in development."
    elif 'strength' in q.lower(): ans = "My greatest strength is problem-solving. For example, I optimized a system improving performance by 30%."
    elif 'weakness' in q.lower(): ans = "I sometimes focus too much on details, but I've been working on this."
    return jsonify({'answer':ans})

@app.route('/explain', methods=['POST'])
@login_required
def explain_concept():
    data = request.get_json()
    topic = data.get('topic','').lower()
    explanations = {'normalization':'Database normalization organizes data to reduce redundancy.','binary search':'Binary search finds an element in a sorted array in O(log n) time.','array':'Array is a collection of elements at contiguous memory locations.','linked list':'Linked list is a linear data structure where elements are stored in nodes.','stack':'Stack follows LIFO (Last In First Out) principle.','queue':'Queue follows FIFO (First In First Out) principle.','recursion':'Recursion is when a function calls itself.','oop':'Object-Oriented Programming has four pillars: Encapsulation, Inheritance, Polymorphism, Abstraction.'}
    return jsonify({'explanation':explanations.get(topic, f"'{topic}' is an important concept.")})

@app.route('/coding/submit', methods=['POST'])
@login_required
def coding_submit():
    data = request.get_json()
    code = data.get('code','')
    passed = len(code.strip()) > 50
    score = 8 if passed else 4
    return jsonify({'passed':passed, 'score':score, 'message':'Accepted!' if passed else 'Needs improvement.'})

@app.route('/company_insights/<company_name>')
@login_required
def company_insights(company_name):
    insights = {'google':{'company_name':'Google','hiring_pattern':'Algorithms, System Design','difficulty':'Very High','previous_questions':'Design YouTube, LRU Cache','salary_range':'₹30-60 LPA'},'amazon':{'company_name':'Amazon','hiring_pattern':'Leadership Principles','difficulty':'High','previous_questions':'Design Amazon Locker','salary_range':'₹25-50 LPA'},'microsoft':{'company_name':'Microsoft','hiring_pattern':'Problem solving, System Design','difficulty':'High','previous_questions':'Design Bing','salary_range':'₹25-45 LPA'},'tcs':{'company_name':'TCS','hiring_pattern':'Aptitude, Coding, HR','difficulty':'Medium','previous_questions':'Basic programming, SQL','salary_range':'₹3-8 LPA'},'infosys':{'company_name':'Infosys','hiring_pattern':'Aptitude, Technical, HR','difficulty':'Medium','previous_questions':'OOPS, DBMS, Algorithms','salary_range':'₹3-8 LPA'}}
    insight = insights.get(company_name.lower(), {'company_name':company_name, 'hiring_pattern':'Technical + HR', 'difficulty':'Medium', 'previous_questions':'Data structures, Algorithms', 'salary_range':'Varies'})
    return render_template('company_insights.html', insight=insight)

@app.route('/set_company_session', methods=['POST'])
@login_required
def set_company_session():
    data = request.get_json()
    session['company'] = data.get('company')
    return jsonify({'status':'ok'})

@app.route('/set_job_role', methods=['POST'])
@login_required
def set_job_role():
    data = request.get_json()
    session['role'] = data.get('role')
    return jsonify({'status':'ok'})

# ========== DATABASE CLEANUP ==========
@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

# ========== RUN ==========
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False, port=5500)