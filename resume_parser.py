import re

class ResumeParser:
    @staticmethod
    def extract_skills(text):
        # Expanded list of skills
        skill_keywords = [
            'python', 'java', 'javascript', 'typescript', 'sql', 'c++', 'c#', 'ruby', 'go', 'rust', 'php',
            'html', 'css', 'sass', 'react', 'angular', 'vue', 'node.js', 'express', 'django', 'flask', 'spring',
            'mongodb', 'mysql', 'postgresql', 'oracle', 'redis', 'aws', 'azure', 'gcp', 'docker', 'kubernetes',
            'git', 'jenkins', 'terraform', 'machine learning', 'deep learning', 'data analysis', 'nlp',
            'excel', 'tableau', 'power bi', 'pandas', 'numpy', 'scikit-learn', 'tensorflow', 'pytorch',
            'communication', 'teamwork', 'problem solving', 'leadership', 'time management', 'agile', 'scrum',
            'rest api', 'graphql', 'microservices', 'system design', 'data structures', 'algorithms'
        ]
        found = []
        text_lower = text.lower()
        for s in skill_keywords:
            # Use regex to match whole words only to avoid matching 'c' in 'cat'
            if re.search(r'\b' + re.escape(s) + r'\b', text_lower):
                found.append(s)
        return found
    
    @staticmethod
    def extract_projects(text):
        projects = []
        lines = text.split('\n')
        for line in lines:
            if 'project' in line.lower():
                if len(line.strip()) > 5 and len(line.strip()) < 200:
                    projects.append(line.strip())
        return projects[:5]
    
    @staticmethod
    def extract_education(text):
        patterns = [r'B\.?Tech', r'M\.?Tech', r'B\.?E', r'M\.?E', r'BCA', r'MCA', 
                   r'B\.?Sc', r'M\.?Sc', r'MBA', r'Ph\.?D', r'Bachelor', r'Master']
        for pat in patterns:
            if re.search(pat.lower(), text.lower()):
                match = re.search(r'.{0,30}' + pat + r'.{0,30}', text, re.IGNORECASE)
                if match:
                    return match.group().strip()
        return "Not specified"
    
    @staticmethod
    def analyze_strengths(skills, job_role):
        strengths = []
        role_keywords = {
            'software engineer': ['python', 'java', 'javascript', 'sql', 'data structures', 'algorithms', 'system design', 'git'],
            'data analyst': ['python', 'sql', 'excel', 'data analysis', 'statistics', 'tableau', 'power bi', 'pandas'],
            'web developer': ['html', 'css', 'javascript', 'react', 'node.js', 'typescript', 'git'],
            'data scientist': ['python', 'machine learning', 'statistics', 'sql', 'tensorflow', 'pandas']
        }
        role_lower = job_role.lower()
        relevant = []
        for role, kw in role_keywords.items():
            if role in role_lower:
                relevant = kw
                break
        if not relevant:
            relevant = ['python', 'sql', 'communication', 'problem solving', 'teamwork']
            
        for s in skills:
            if s in relevant:
                strengths.append(f"Strong {s} skill for {job_role}")
        if not strengths:
            strengths.append("Good foundational knowledge")
        return strengths[:4]
    
    @staticmethod
    def identify_weak_areas(skills, job_role):
        weak = []
        required = {
            'software engineer': ['data structures', 'algorithms', 'system design', 'sql', 'git', 'rest api'],
            'data analyst': ['sql', 'excel', 'python', 'statistics', 'tableau', 'data visualization'],
            'web developer': ['html', 'css', 'javascript', 'react', 'node.js', 'git'],
            'data scientist': ['python', 'machine learning', 'statistics', 'sql', 'pandas']
        }
        role_lower = job_role.lower()
        req_list = []
        for r, lst in required.items():
            if r in role_lower:
                req_list = lst
                break
        if not req_list:
            req_list = ['technical skills', 'problem solving', 'communication']
            
        for req in req_list:
            found = any(req.lower() in s.lower() or s.lower() in req.lower() for s in skills)
            if not found:
                weak.append(f"Missing {req}")
        return weak
    
    @staticmethod
    def get_missing_skills(skills, company):
        # If the company is not recognized, fallback to extracting typical technical skills based on the job role
        target_skills = {
            'tcs': ['java', 'sql', 'communication', 'aptitude', 'logical reasoning', 'python', 'dsa'],
            'infosys': ['python', 'java', 'sql', 'system design', 'agile', 'dsa'],
            'google': ['data structures', 'algorithms', 'system design', 'python', 'java', 'c++', 'problem solving'],
            'amazon': ['data structures', 'algorithms', 'leadership principles', 'scalability', 'oop', 'java', 'python'],
            'microsoft': ['c#', 'azure', 'system design', 'problem solving', 'team collaboration', 'c++', 'dsa'],
            'wipro': ['java', 'sql', 'communication', 'python', 'dsa'],
            'accenture': ['java', 'sql', 'communication', 'python', 'dsa'],
        }
        
        company_lower = company.lower() if company else ""
        target = target_skills.get(company_lower, ['technical skills', 'problem solving', 'communication', 'teamwork', 'data structures'])
        
        missing = []
        for t in target:
            # Check if skill is present in any of the extracted skills
            if not any(t.lower() in s.lower() or s.lower() in t.lower() for s in skills):
                missing.append(t)
                
        return missing[:5]