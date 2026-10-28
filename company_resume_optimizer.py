# company_resume_optimizer.py
# Simplified version - No ML dependencies required

import re
import json
from datetime import datetime

class CompanyResumeOptimizer:
    """Company-specific resume optimization engine (Simplified)"""
    
    def __init__(self):
        self.company_requirements = {
            'TCS': {
                'keywords': ['java', 'sql', 'communication', 'teamwork', 'problem solving', 'agile', 'html', 'css', 'javascript'],
                'min_ats_score': 60
            },
            'Infosys': {
                'keywords': ['python', 'java', 'sql', 'system design', 'agile', 'scrum', 'microservices', 'rest api'],
                'min_ats_score': 60
            },
            'Wipro': {
                'keywords': ['c++', 'java', 'sql', 'communication', 'leadership', 'project management', 'oracle', 'mysql'],
                'min_ats_score': 60
            },
            'Accenture': {
                'keywords': ['cloud', 'aws', 'azure', 'ai', 'ml', 'digital', 'innovation', 'consulting', 'python'],
                'min_ats_score': 60
            },
            'Cognizant': {
                'keywords': ['digital', 'automation', 'ai', 'data analytics', 'cloud', 'cybersecurity', 'python', 'java'],
                'min_ats_score': 60
            },
            'Google': {
                'keywords': ['data structures', 'algorithms', 'system design', 'python', 'java', 'go', 'scalability', 'performance'],
                'min_ats_score': 70
            },
            'Amazon': {
                'keywords': ['aws', 'scalability', 'customer', 'ownership', 'java', 'python', 'distributed systems', 'frugality'],
                'min_ats_score': 70
            },
            'Microsoft': {
                'keywords': ['azure', 'c#', '.net', 'cloud', 'innovation', 'growth mindset', 'python', 'typescript'],
                'min_ats_score': 70
            },
            'Meta': {
                'keywords': ['react', 'php', 'python', 'social media', 'scale', 'distributed systems', 'javascript', 'graphql'],
                'min_ats_score': 70
            },
            'Adobe': {
                'keywords': ['javascript', 'typescript', 'react', 'node.js', 'creative', 'design', 'cloud', 'ai'],
                'min_ats_score': 65
            }
        }
        
        self.action_verbs = [
            'achieved', 'accomplished', 'developed', 'created', 'implemented', 'designed',
            'led', 'managed', 'improved', 'enhanced', 'optimized', 'built', 'architected',
            'delivered', 'launched', 'scaled', 'transformed', 'innovated', 'modernized'
        ]
    
    def analyze_resume(self, resume_text, company_name):
        """Analyze resume against company requirements"""
        company = self.company_requirements.get(company_name, self.company_requirements['TCS'])
        text_lower = resume_text.lower()
        
        # Keyword analysis
        found_keywords = []
        missing_keywords = []
        for keyword in company['keywords']:
            if keyword in text_lower:
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)
        
        keyword_score = (len(found_keywords) / len(company['keywords'])) * 100 if company['keywords'] else 0
        ats_score = round(keyword_score, 1)
        readiness_score = round(min(100, keyword_score * 1.2), 1)
        
        return {
            'ats_score': ats_score,
            'readiness_score': readiness_score,
            'keyword_score': round(keyword_score, 1),
            'found_keywords': found_keywords,
            'missing_keywords': missing_keywords[:10],
            'meets_threshold': ats_score >= company['min_ats_score']
        }
    
    def generate_optimized_resume(self, resume_data, company_name, analysis_result):
        """Generate optimized resume for company"""
        company = self.company_requirements.get(company_name, self.company_requirements['TCS'])
        
        # Simple optimization
        skills = resume_data.get('skills', [])
        skills_str = ', '.join(skills[:3]) if skills else 'technology'
        
        optimized = {
            'summary': f"Dedicated professional with strong skills in {skills_str}. Passionate about {company_name} and eager to contribute to innovative projects with a focus on {', '.join(company['keywords'][:3])}.",
            'skills': skills,
            'recommended_skills': [k for k in company['keywords'][:4] if k not in [s.lower() for s in skills]],
            'projects': resume_data.get('projects', []),
            'recommended_projects': [
                f"Build a project using {company['keywords'][0].title() if company['keywords'] else 'modern'} technologies",
                f"Create a {company_name}-inspired application",
                "Contribute to open source projects"
            ],
            'recommended_certifications': [
                f"{company_name} Certification",
                f"{company['keywords'][0].title() if company['keywords'] else 'Technical'} Certification",
                "Cloud Computing Certification"
            ],
            'resume_tips': [
                "Use strong action verbs like: " + ', '.join(self.action_verbs[:5]),
                "Quantify achievements with numbers and percentages",
                "Tailor your resume for each company application",
                "Include relevant projects and internships",
                "Add links to GitHub and LinkedIn profiles"
            ],
            'action_verbs_to_use': self.action_verbs[:5]
        }
        
        return optimized
    
    def get_improvement_suggestions(self, analysis_result, company_name):
        """Get personalized improvement suggestions"""
        company = self.company_requirements.get(company_name, self.company_requirements['TCS'])
        suggestions = []
        
        if analysis_result['missing_keywords']:
            suggestions.append(f"Add these keywords to your resume: {', '.join(analysis_result['missing_keywords'][:5])}")
        
        if analysis_result['ats_score'] < 60:
            suggestions.append(f"Aim for ATS score above {company['min_ats_score']}%")
        
        suggestions.extend([
            "Quantify achievements with numbers (e.g., 'Increased performance by 30%')",
            "Use action verbs like: " + ', '.join(self.action_verbs[:5]),
            "Use standard section headings (Experience, Education, Skills)",
            "Include measurable outcomes and results",
            "Add GitHub/LinkedIn links to your resume"
        ])
        
        return suggestions[:8]
    
    def compare_companies(self, resume_data, companies):
        """Compare resume compatibility across multiple companies"""
        comparisons = []
        for company in companies:
            if company in self.company_requirements:
                resume_text = json.dumps(resume_data.get('skills', [])) + ' ' + resume_data.get('summary', '')
                analysis = self.analyze_resume(resume_text, company)
                comparisons.append({
                    'company': company,
                    'ats_score': analysis['ats_score'],
                    'readiness_score': analysis['readiness_score'],
                    'meets_threshold': analysis['meets_threshold']
                })
        
        comparisons.sort(key=lambda x: x['ats_score'], reverse=True)
        return comparisons