from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    resume_analysis = db.relationship('ResumeAnalysis', backref='user', uselist=False)
    answers = db.relationship('AnswerEvaluation', backref='user', lazy=True)
    weak_areas = db.relationship('WeakArea', backref='user', lazy=True)
    roadmap = db.relationship('Roadmap', backref='user', uselist=False)
    resume_data = db.relationship('ResumeData', backref='user', uselist=False)
    company_resumes = db.relationship('CompanyResume', backref='user', lazy=True)
    resume_versions = db.relationship('ResumeVersion', backref='user', lazy=True)
    job_applications = db.relationship('JobApplication', backref='user', lazy=True)
    certificates = db.relationship('Certificate', backref='user', lazy=True)
    gd_sessions = db.relationship('GroupDiscussion', backref='user', lazy=True)
    contest_entries = db.relationship('CodingContest', backref='user', lazy=True)
    achievements = db.relationship('Achievement', backref='user', lazy=True)
    company_placements = db.relationship('CompanyPlacement', backref='user', lazy=True)
    quiz_attempts = db.relationship('QuizAttempt', backref='user', lazy=True)

class ResumeAnalysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    resume_text = db.Column(db.Text, nullable=False)
    target_company = db.Column(db.String(100), nullable=False)
    job_role = db.Column(db.String(100), nullable=False)
    skills = db.Column(db.Text)
    projects = db.Column(db.Text)
    education = db.Column(db.String(200))
    strengths = db.Column(db.Text)
    weak_areas_resume = db.Column(db.Text)
    missing_skills = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InterviewQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AnswerEvaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('interview_question.id'))
    user_answer = db.Column(db.Text, nullable=False)
    score = db.Column(db.Float)
    feedback = db.Column(db.Text)
    improved_answer = db.Column(db.Text)
    clarity_score = db.Column(db.Float)
    confidence_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WeakArea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic = db.Column(db.String(200), nullable=False)
    source = db.Column(db.String(50))
    severity = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Roadmap(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plan_data = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_questions_answered = db.Column(db.Integer, default=0)
    average_score = db.Column(db.Float, default=0)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)

class ResumeData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    summary = db.Column(db.Text)
    target_company = db.Column(db.String(100), default='TCS')
    job_role = db.Column(db.String(100), default='Software Engineer')
    skills = db.Column(db.Text)
    projects = db.Column(db.Text)
    education = db.Column(db.Text)
    experience = db.Column(db.Text)
    template_choice = db.Column(db.String(50), default='professional')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ========== MODULES 9–20, 23 ==========

class CompanyPlacement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_name = db.Column(db.String(100), nullable=False)
    aptitude_score = db.Column(db.Float, default=0)
    coding_score = db.Column(db.Float, default=0)
    interview_score = db.Column(db.Float, default=0)
    overall_score = db.Column(db.Float, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

class JobApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_name = db.Column(db.String(100), nullable=False)
    job_role = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default='Applied')
    application_date = db.Column(db.DateTime, default=datetime.utcnow)
    interview_date = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)

class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    certificate_name = db.Column(db.String(200), nullable=False)
    issuing_authority = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    certificate_file = db.Column(db.String(500), nullable=True)
    verified = db.Column(db.Boolean, default=False)

class GroupDiscussion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic = db.Column(db.String(200), nullable=False)
    user_response = db.Column(db.Text, nullable=False)
    communication_score = db.Column(db.Float, default=0)
    grammar_score = db.Column(db.Float, default=0)
    confidence_score = db.Column(db.Float, default=0)
    overall_score = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class CodingContest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contest_name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Float, default=0)
    rank = db.Column(db.Integer, default=0)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    badge_name = db.Column(db.String(100), nullable=False)
    badge_type = db.Column(db.String(50))
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)

class CompanyResume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    company_name = db.Column(db.String(100), nullable=False)
    optimized_resume = db.Column(db.Text, nullable=True)
    ats_score = db.Column(db.Float, default=0)
    readiness_score = db.Column(db.Float, default=0)
    missing_skills = db.Column(db.Text, nullable=True)
    optimized_sections = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ResumeVersion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    version_name = db.Column(db.String(100), nullable=False)
    resume_data = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========== QUIZ SYSTEM MODELS ==========

class QuizQuestion(db.Model):
    """Quiz questions database"""
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(500), nullable=False)
    option_b = db.Column(db.String(500), nullable=False)
    option_c = db.Column(db.String(500), nullable=False)
    option_d = db.Column(db.String(500), nullable=False)
    correct_answer = db.Column(db.String(1), nullable=False)  # A, B, C, D
    category = db.Column(db.String(50), nullable=False)  # Web, Data, ML, DevOps, General
    difficulty = db.Column(db.String(20), default='Medium')
    explanation = db.Column(db.Text, nullable=True)  # <--- ADDED EXPLANATION
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    day_number = db.Column(db.Integer, nullable=False)
    total_questions = db.Column(db.Integer, default=0)
    correct_answers = db.Column(db.Integer, default=0)
    wrong_answers = db.Column(db.Text)
    score = db.Column(db.Float, default=0)
    completed = db.Column(db.Boolean, default=False)
    question_ids = db.Column(db.Text)  # <-- Make sure this line is here!
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ========== DAILY CODING CHALLENGE ==========
class DailyChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day_number = db.Column(db.Integer, unique=True, nullable=False)  # Day 1, 2, 3...
    title = db.Column(db.String(150), nullable=False)
    difficulty = db.Column(db.String(20))
    statement = db.Column(db.Text, nullable=False)
    sample_input = db.Column(db.Text)
    sample_output = db.Column(db.Text)
    constraints = db.Column(db.Text)
    starter_python = db.Column(db.Text)
    starter_java = db.Column(db.Text)
    starter_cpp = db.Column(db.Text)
    starter_c = db.Column(db.Text)
    starter_csharp = db.Column(db.Text)
    starter_javascript = db.Column(db.Text)
    test_cases = db.Column(db.Text)  # JSON string of [{input, output}]
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChallengeSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    challenge_id = db.Column(db.Integer, db.ForeignKey('daily_challenge.id'), nullable=False)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(20), default='python')
    score = db.Column(db.Float, default=0)  # 0-100
    status = db.Column(db.String(20), default='submitted')  # submitted / passed / failed
    output = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='challenge_submissions')
    challenge = db.relationship('DailyChallenge', backref='submissions')


# ========== DAILY CODING CHALLENGE (NEW) ==========
class DailyCodingChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    challenge_date = db.Column(db.Date, nullable=False)
    challenge_id = db.Column(db.Integer, nullable=False)
    user_code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(30), default='python')
    score = db.Column(db.Float, default=0)
    passed = db.Column(db.Integer, default=0)
    total = db.Column(db.Integer, default=0)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'challenge_date', name='unique_user_day'),
    )

# ========== VOICE INTERVIEW HISTORY ==========
class VoiceInterviewSession(db.Model):
    __tablename__ = "voice_interview_session"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    interview_type = db.Column(db.String(40), nullable=False, default="HR")
    company = db.Column(db.String(120), nullable=False, default="General")
    job_role = db.Column(db.String(120), nullable=False, default="Software Engineer")
    difficulty = db.Column(db.String(20), nullable=False, default="Adaptive")
    voice_gender = db.Column(db.String(20), nullable=False, default="female")
    question_count = db.Column(db.Integer, nullable=False, default=5)
    custom_questions = db.Column(db.Text)
    question_data = db.Column(db.Text)
    overall_score = db.Column(db.Float, default=0)
    completed = db.Column(db.Boolean, default=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    responses = db.relationship(
        "VoiceInterviewResponse",
        backref="interview",
        lazy=True,
        cascade="all, delete-orphan",
        order_by="VoiceInterviewResponse.question_number",
    )


class VoiceInterviewResponse(db.Model):
    __tablename__ = "voice_interview_response"
    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey("voice_interview_session.id"), nullable=False, index=True)
    question_number = db.Column(db.Integer, nullable=False)
    question_type = db.Column(db.String(40), nullable=False, default="HR")
    question_text = db.Column(db.Text, nullable=False)
    user_answer = db.Column(db.Text, nullable=False, default="")
    score = db.Column(db.Float, default=0)
    correctness_score = db.Column(db.Float, default=0)
    clarity_score = db.Column(db.Float, default=0)
    communication_score = db.Column(db.Float, default=0)
    feedback = db.Column(db.Text)
    ideal_answer = db.Column(db.Text)
    strengths = db.Column(db.Text)
    weaknesses = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        db.UniqueConstraint("interview_id", "question_number", name="uq_voice_interview_question"),
    )

# ========== APTITUDE RESULT MODEL (ADDED) ==========
class AptitudeResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    day_number = db.Column(db.Integer, nullable=False)
    section = db.Column(db.String(50), nullable=False) # quantitative, reasoning, verbal
    question_text = db.Column(db.Text, nullable=False)
    correct_option = db.Column(db.String(200), nullable=False)
    user_option = db.Column(db.String(200), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)