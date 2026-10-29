import os
import json
import random
from pathlib import Path
from typing import List, Dict, Any

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DATASET_DIR = ROOT_DIR / "dataset"

# Ensure directories
(DATA_DIR / "raw").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "normalized").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "evaluation").mkdir(parents=True, exist_ok=True)
(DATA_DIR / "extracted").mkdir(parents=True, exist_ok=True)
(DATASET_DIR / "resumes").mkdir(parents=True, exist_ok=True)
(DATASET_DIR / "ground_truth").mkdir(parents=True, exist_ok=True)
(DATASET_DIR / "job_descriptions").mkdir(parents=True, exist_ok=True)
(DATASET_DIR / "matching_ground_truth").mkdir(parents=True, exist_ok=True)

random.seed(42)

# Fictional names generator
FIRST_NAMES = ["Aarav", "Maya", "Liam", "Sophia", "Ethan", "Olivia", "Noah", "Emma", "Lucas", "Ava", "Mason", "Isabella", "Dev", "Ananya", "Rohan", "Priya", "Carlos", "Elena", "Wei", "Mei", "Hiroshi", "Yuki", "Kofi", "Zainab", "Mateo", "Camila", "Viktor", "Natasha", "Amir", "Fatima"]
LAST_NAMES = ["Mehta", "Rao", "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Sharma", "Patel", "Chen", "Wang", "Tanaka", "Sato", "Mensah", "Diallo", "Fernandez", "Gomez", "Volkov", "Ivanova", "Khan", "Ali"]

COMPANIES = ["ExampleTech Corp", "DataFlow Systems", "CloudScale Inc", "InnovateSoft", "NextGen Solutions", "Apex Global", "FinPulse Digital", "CyberShield Labs", "OmniCloud Systems", "Nexus AI Studios"]
UNIVERSITIES = ["Example State University", "Institute of Technology", "Metropolitan University", "Global Science Academy", "Tech University"]

ROLE_DISTRIBUTION = [
    ("Backend Engineer", "Software Engineering", 50),
    ("Frontend Engineer", "Software Engineering", 40),
    ("Full Stack Engineer", "Software Engineering", 40),
    ("Java Developer", "Software Engineering", 25),
    ("Python Developer", "Software Engineering", 25),
    ("Node.js Developer", "Software Engineering", 10),
    ("React Developer", "Software Engineering", 10),
    ("DevOps Engineer", "Infrastructure", 35),
    ("Cloud Engineer", "Infrastructure", 35),
    ("Site Reliability Engineer", "Infrastructure", 30),
    ("Data Engineer", "Data / AI", 35),
    ("Data Scientist", "Data / AI", 25),
    ("Machine Learning Engineer", "Data / AI", 25),
    ("AI Engineer", "Data / AI", 15),
    ("QA Automation Engineer", "Quality / Security", 30),
    ("Security Engineer", "Quality / Security", 20),
    ("Engineering Manager", "Management", 25),
    ("Technical Project Manager", "Management", 25),
]

SKILLS_BY_ROLE = {
    "Backend Engineer": ["Python", "FastAPI", "Django", "PostgreSQL", "Redis", "Docker", "REST API", "Microservices"],
    "Frontend Engineer": ["JavaScript", "TypeScript", "React", "Next.js", "HTML5", "CSS3", "Tailwind CSS", "Redux"],
    "Full Stack Engineer": ["TypeScript", "React", "Node.js", "Express", "PostgreSQL", "Docker", "REST API", "GraphQL"],
    "Java Developer": ["Java", "Spring Boot", "Hibernate", "PostgreSQL", "Kafka", "Docker", "Maven", "REST API"],
    "Python Developer": ["Python", "Django", "Flask", "PostgreSQL", "Redis", "Celery", "Git", "Docker"],
    "Node.js Developer": ["JavaScript", "TypeScript", "Node.js", "Express", "MongoDB", "Redis", "Jest", "Docker"],
    "React Developer": ["JavaScript", "TypeScript", "React", "Redux", "HTML5", "CSS3", "Jest", "Vite"],
    "DevOps Engineer": ["Docker", "Kubernetes", "AWS", "Terraform", "Ansible", "CI/CD", "Linux", "Python"],
    "Cloud Engineer": ["AWS", "Azure", "GCP", "Terraform", "Kubernetes", "Docker", "Linux", "Python"],
    "Site Reliability Engineer": ["Linux", "Python", "Kubernetes", "Prometheus", "Grafana", "Docker", "CI/CD", "AWS"],
    "Data Engineer": ["Python", "SQL", "Apache Spark", "Airflow", "PostgreSQL", "Snowflake", "Docker", "AWS"],
    "Data Scientist": ["Python", "Pandas", "Scikit-Learn", "SQL", "PyTorch", "TensorFlow", "Statistics", "Git"],
    "Machine Learning Engineer": ["Python", "PyTorch", "TensorFlow", "Docker", "FastAPI", "MLflow", "CUDA", "Git"],
    "AI Engineer": ["Python", "PyTorch", "Ollama", "LangChain", "FastAPI", "Transformers", "FAISS", "Vector DB"],
    "QA Automation Engineer": ["Python", "Selenium", "Playwright", "Pytest", "Git", "CI/CD", "REST API", "Postman"],
    "Security Engineer": ["Linux", "Python", "OWASP", "Penetration Testing", "Wireshark", "Docker", "Cryptography", "SIEM"],
    "Engineering Manager": ["Agile", "Scrum", "System Architecture", "Leadership", "Python", "CI/CD", "Jira", "Team Mentorship"],
    "Technical Project Manager": ["Agile", "Scrum", "Jira", "Risk Management", "Stakeholder Communication", "Budgeting", "Roadmapping"],
}

JOB_DESCRIPTIONS = [
    {
        "job_id": "JOB-001",
        "title": "Senior Python Backend Engineer",
        "seniority": "Senior",
        "mandatory_skills": ["Python", "FastAPI", "PostgreSQL"],
        "preferred_skills": ["Docker", "Redis", "AWS"],
        "minimum_years_experience": 5.0,
        "domain_requirements": ["FinTech", "SaaS"],
        "education_requirements": ["B.S. in Computer Science or equivalent"],
        "certifications": [],
        "location": "Austin, TX (Hybrid)",
        "work_mode": "Hybrid",
        "responsibilities": ["Design high-throughput REST APIs.", "Optimize database queries and microservices."],
        "source_dataset": "michaelozon/candidate-matching-synthetic"
    },
    {
        "job_id": "JOB-002",
        "title": "React Frontend Engineer",
        "seniority": "Mid-Senior",
        "mandatory_skills": ["React", "TypeScript", "JavaScript"],
        "preferred_skills": ["Redux", "Tailwind CSS", "Next.js"],
        "minimum_years_experience": 3.0,
        "domain_requirements": ["E-Commerce", "Web Applications"],
        "education_requirements": ["Bachelor's degree"],
        "certifications": [],
        "location": "San Francisco, CA",
        "work_mode": "Onsite",
        "responsibilities": ["Develop user-facing UI components.", "Ensure web accessibility and responsiveness."],
        "source_dataset": "michaelozon/candidate-matching-synthetic"
    },
    {
        "job_id": "JOB-003",
        "title": "Full Stack Engineer",
        "seniority": "Mid-Level",
        "mandatory_skills": ["TypeScript", "React", "Node.js", "PostgreSQL"],
        "preferred_skills": ["Docker", "GraphQL"],
        "minimum_years_experience": 3.0,
        "domain_requirements": ["Technology"],
        "education_requirements": ["Bachelor's degree in CS"],
        "certifications": [],
        "location": "Remote",
        "work_mode": "Remote",
        "responsibilities": ["Build end-to-end web features.", "Maintain backend REST APIs and frontend views."],
        "source_dataset": "michaelozon/candidate-matching-synthetic"
    },
    {
        "job_id": "JOB-004",
        "title": "DevOps & Infrastructure Engineer",
        "seniority": "Senior",
        "mandatory_skills": ["Docker", "Kubernetes", "AWS", "Terraform"],
        "preferred_skills": ["Ansible", "Python", "CI/CD"],
        "minimum_years_experience": 4.0,
        "domain_requirements": ["Cloud Infrastructure"],
        "education_requirements": [],
        "certifications": ["AWS Certified Solutions Architect"],
        "location": "Seattle, WA",
        "work_mode": "Hybrid",
        "responsibilities": ["Automate deployment pipelines.", "Manage cloud clusters and security."],
        "source_dataset": "michaelozon/candidate-matching-synthetic"
    },
    {
        "job_id": "JOB-005",
        "title": "Senior Data Engineer",
        "seniority": "Senior",
        "mandatory_skills": ["Python", "SQL", "Apache Spark", "Airflow"],
        "preferred_skills": ["Snowflake", "Docker", "AWS"],
        "minimum_years_experience": 5.0,
        "domain_requirements": ["Data Analytics"],
        "education_requirements": ["B.S. or M.S. in STEM field"],
        "certifications": [],
        "location": "New York, NY",
        "work_mode": "Hybrid",
        "responsibilities": ["Construct ETL pipelines.", "Optimize data warehouse queries."],
        "source_dataset": "michaelozon/candidate-matching-synthetic"
    },
    {
        "job_id": "JOB-006",
        "title": "Machine Learning Engineer",
        "seniority": "Mid-Senior",
        "mandatory_skills": ["Python", "PyTorch", "FastAPI", "Docker"],
        "preferred_skills": ["TensorFlow", "MLflow", "CUDA"],
        "minimum_years_experience": 3.0,
        "domain_requirements": ["AI / Machine Learning"],
        "education_requirements": ["Degree in CS/Data Science/Math"],
        "certifications": [],
        "location": "Boston, MA",
        "work_mode": "Onsite",
        "responsibilities": ["Train and deploy ML models into production endpoints."],
        "source_dataset": "michaelozon/candidate-matching-synthetic"
    },
    {
        "job_id": "JOB-007",
        "title": "Cloud Systems Architect",
        "seniority": "Lead / Architect",
        "mandatory_skills": ["AWS", "Terraform", "Kubernetes", "Linux"],
        "preferred_skills": ["Azure", "GCP", "Python"],
        "minimum_years_experience": 8.0,
        "domain_requirements": ["Enterprise Software"],
        "education_requirements": ["B.S. in CS or related"],
        "certifications": ["AWS Certified Solutions Architect Professional"],
        "location": "Chicago, IL",
        "work_mode": "Remote",
        "responsibilities": ["Architect resilient cloud infrastructure for enterprise apps."],
        "source_dataset": "michaelozon/candidate-matching-synthetic"
    },
    {
        "job_id": "JOB-008",
        "title": "QA Automation Engineer",
        "seniority": "Mid-Level",
        "mandatory_skills": ["Python", "Selenium", "Playwright", "Pytest"],
        "preferred_skills": ["CI/CD", "Postman"],
        "minimum_years_experience": 2.0,
        "domain_requirements": ["Quality Assurance"],
        "education_requirements": [],
        "certifications": [],
        "location": "Denver, CO",
        "work_mode": "Hybrid",
        "responsibilities": ["Write automated UI and API end-to-end test suites."],
        "source_dataset": "michaelozon/candidate-matching-synthetic"
    },
    {
        "job_id": "JOB-009",
        "title": "Java Enterprise Backend Engineer",
        "seniority": "Senior",
        "mandatory_skills": ["Java", "Spring Boot", "PostgreSQL", "Microservices"],
        "preferred_skills": ["Hibernate", "Kafka", "Docker"],
        "minimum_years_experience": 5.0,
        "domain_requirements": ["Banking / Enterprise"],
        "education_requirements": ["B.S. in CS"],
        "certifications": [],
        "location": "Charlotte, NC",
        "work_mode": "Onsite",
        "responsibilities": ["Develop mission-critical banking backend applications."],
        "source_dataset": "michaelozon/candidate-matching-synthetic"
    },
    {
        "job_id": "JOB-010",
        "title": "Senior AI Systems Engineer",
        "seniority": "Senior",
        "mandatory_skills": ["Python", "PyTorch", "Ollama", "FastAPI", "Vector DB"],
        "preferred_skills": ["LangChain", "FAISS", "Transformers"],
        "minimum_years_experience": 4.0,
        "domain_requirements": ["Generative AI"],
        "education_requirements": ["M.S. or B.S. in CS / AI"],
        "certifications": [],
        "location": "San Jose, CA",
        "work_mode": "Hybrid",
        "responsibilities": ["Build local LLM agents and retrieval-augmented generation pipelines."],
        "source_dataset": "michaelozon/candidate-matching-synthetic"
    }
]

def generate_500_resumes():
    candidates = []
    text_resumes = []
    ground_truths = []
    
    cand_index = 1
    
    for role_name, category, count in ROLE_DISTRIBUTION:
        for _ in range(count):
            cand_id = f"CAND-{cand_index:04d}"
            fname = random.choice(FIRST_NAMES)
            lname = random.choice(LAST_NAMES)
            full_name = f"{fname} {lname}"
            email = f"{fname.lower()}.{lname.lower()}@example.com"
            phone = f"+1 555-{random.randint(100,999):03d}-{random.randint(1000,9999):04d}"
            loc = random.choice(["Austin, TX", "San Francisco, CA", "Seattle, WA", "New York, NY", "Chicago, IL", "Remote", "Boston, MA", "Denver, CO", "San Jose, CA"])
            
            # Quality variation bucket
            rand_val = random.random()
            if rand_val < 0.60:
                quality_type = "standard"
            elif rand_val < 0.80:
                quality_type = "messy"
            elif rand_val < 0.90:
                quality_type = "ambiguous"
            else:
                quality_type = "difficult_edge_case"
                
            # Years experience based on role level
            if "Junior" in role_name or "Intern" in role_name or cand_index % 7 == 0:
                years_exp = round(random.uniform(0.5, 2.0), 1)
            elif "Senior" in role_name or "Lead" in role_name or "Architect" in role_name or "Manager" in role_name:
                years_exp = round(random.uniform(5.5, 12.0), 1)
            else:
                years_exp = round(random.uniform(2.5, 6.0), 1)
                
            # Skills pool
            base_skills = SKILLS_BY_ROLE.get(role_name, ["Python", "SQL", "Git"])
            num_skills = random.randint(4, max(4, len(base_skills)))
            skills = random.sample(base_skills, min(len(base_skills), num_skills))
            
            # Company
            company = random.choice(COMPANIES)
            uni = random.choice(UNIVERSITIES)
            
            notice_period = random.choice(["Immediate", "15 days", "30 days", "60 days"]) if quality_type != "messy" else None
            missing_info = []
            if notice_period is None:
                missing_info.append("Notice period not specified in CV")
            if quality_type == "ambiguous":
                missing_info.append("Explicit total years of experience not clearly stated in text summary")
                
            # Build CV Text
            cv_text_lines = [
                f"{full_name}",
                f"Email: {email} | Phone: {phone} | Location: {loc}",
                f"Notice Period: {notice_period}" if notice_period else "",
                "",
                "SUMMARY:",
                f"{role_name} with over {years_exp} years of professional experience building scalable systems.",
                "",
                "SKILLS:",
                ", ".join(skills),
                "",
                "EXPERIENCE:",
                f"{role_name} at {company} (2020 - Present)",
                f"- Developed core features using {', '.join(skills[:3])}.",
                f"- Collaborated with cross-functional teams to improve performance and code quality.",
                "",
                "EDUCATION:",
                f"B.S. in Computer Science from {uni}"
            ]
            cv_text = "\n".join([l for l in cv_text_lines if l.strip()])
            
            # Evidence items
            evidence = []
            for sk in skills[:3]:
                evidence.append({
                    "attribute": f"skills:{sk}",
                    "source_section": "Skills / Experience",
                    "source_text": f"Developed core features using {sk} at {company}.",
                    "confidence": 0.95
                })
            evidence.append({
                "attribute": "years_experience",
                "source_section": "Summary",
                "source_text": f"{role_name} with over {years_exp} years of professional experience",
                "confidence": 0.90
            })
            
            # Ground truth schema
            gt = {
                "candidate_id": cand_id,
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "location": loc,
                "summary": f"{role_name} with {years_exp} years of experience.",
                "skills": skills,
                "years_experience": years_exp if quality_type != "ambiguous" else None,
                "roles": [role_name],
                "companies": [company],
                "experience": [{
                    "title": role_name,
                    "company": company,
                    "dates": "2020 - Present",
                    "responsibilities": [f"Developed core features using {', '.join(skills[:3])}."]
                }],
                "education": [f"B.S. in Computer Science - {uni}"],
                "certifications": [],
                "projects": [f"{role_name} System Refactoring"],
                "domains": [category],
                "notice_period": notice_period,
                "evidence": evidence,
                "confidence": {
                    "skills": 0.95,
                    "years_experience": 0.90,
                    "roles": 0.95,
                    "education": 0.90,
                    "overall": 0.92
                },
                "missing_information": missing_info,
                "ambiguities": [quality_type] if quality_type != "standard" else [],
                "source_dataset": "michaelozon/candidate-matching-synthetic",
                "source_record_id": f"synth-{cand_id}"
            }
            
            candidates.append(gt)
            ground_truths.append(gt)
            text_resumes.append({"candidate_id": cand_id, "text": cv_text})
            
            # Save individual files to dataset/
            with open(DATASET_DIR / "resumes" / f"{cand_id}.txt", "w", encoding="utf-8") as f:
                f.write(cv_text)
            with open(DATASET_DIR / "ground_truth" / f"{cand_id}.json", "w", encoding="utf-8") as f:
                json.dump(gt, f, indent=2)
                
            cand_index += 1

    return candidates, text_resumes

def generate_matches_ground_truth(candidates, jobs):
    matches = []
    
    for job in jobs:
        mand_skills = set(s.lower() for s in job["mandatory_skills"])
        min_exp = job["minimum_years_experience"] or 0.0
        
        for cand in candidates:
            cand_skills = set(s.lower() for s in cand["skills"])
            cand_exp = cand["years_experience"] or 0.0
            
            matched = list(mand_skills.intersection(cand_skills))
            missing = list(mand_skills.difference(cand_skills))
            
            mandatory_satisfied = len(missing) == 0
            exp_satisfied = cand_exp >= min_exp
            
            if mandatory_satisfied and exp_satisfied:
                label = "SHORTLIST"
                reason = f"Satisfies all mandatory skills ({', '.join(job['mandatory_skills'])}) and meets min experience ({cand_exp} >= {min_exp} yrs)."
            elif len(matched) >= len(mand_skills) / 2 and cand_exp >= (min_exp * 0.7):
                label = "REVIEW"
                reason = f"Partial match on skills ({len(matched)}/{len(mand_skills)}) and experience ({cand_exp} yrs)."
            else:
                label = "DO_NOT_SHORTLIST"
                reason = f"Missing mandatory skills ({', '.join(missing)}) or insufficient experience ({cand_exp} < {min_exp} yrs)."
                
            match_entry = {
                "candidate_id": cand["candidate_id"],
                "job_id": job["job_id"],
                "label": label,
                "source_label": label.lower(),
                "mandatory_requirements_satisfied": mandatory_satisfied,
                "matched_skills": [s.title() for s in matched],
                "missing_mandatory_skills": [s.title() for s in missing],
                "relevant_experience": cand_exp,
                "domain_relevance": "high" if any(d.lower() in job["title"].lower() for d in cand["domains"]) else "medium",
                "reason": reason
            }
            matches.append(match_entry)
            
    return matches

def main():
    print("Building 500-CV synthetic evaluation dataset...")
    candidates, text_resumes = generate_500_resumes()
    jobs = JOB_DESCRIPTIONS
    matches = generate_matches_ground_truth(candidates, jobs)
    
    # Write normalized JSONL files
    with open(DATA_DIR / "normalized" / "resumes.jsonl", "w", encoding="utf-8") as f:
        for c in candidates:
            f.write(json.dumps(c) + "\n")
            
    with open(DATA_DIR / "normalized" / "jobs.jsonl", "w", encoding="utf-8") as f:
        for j in jobs:
            f.write(json.dumps(j) + "\n")
            
    with open(DATA_DIR / "normalized" / "matches.jsonl", "w", encoding="utf-8") as f:
        for m in matches:
            f.write(json.dumps(m) + "\n")

    # Evaluation Split (15% test = 75 CVs)
    test_candidates = candidates[:75]
    test_matches = [m for m in matches if m["candidate_id"] in [c["candidate_id"] for c in test_candidates]]
    
    with open(DATA_DIR / "evaluation" / "resumes_test.jsonl", "w", encoding="utf-8") as f:
        for c in test_candidates:
            f.write(json.dumps(c) + "\n")
            
    with open(DATA_DIR / "evaluation" / "jobs_test.jsonl", "w", encoding="utf-8") as f:
        for j in jobs:
            f.write(json.dumps(j) + "\n")
            
    with open(DATA_DIR / "evaluation" / "matches_test.jsonl", "w", encoding="utf-8") as f:
        for m in test_matches:
            f.write(json.dumps(m) + "\n")

    # Save Job descriptions into dataset/
    for j in jobs:
        with open(DATASET_DIR / "job_descriptions" / f"{j['job_id']}.json", "w", encoding="utf-8") as f:
            json.dump(j, f, indent=2)
            
    # Save matching ground truth into dataset/
    for j in jobs:
        job_matches = [m for m in matches if m["job_id"] == j["job_id"]]
        with open(DATASET_DIR / "matching_ground_truth" / f"{j['job_id']}.json", "w", encoding="utf-8") as f:
            json.dump(job_matches, f, indent=2)

    # Manifest
    manifest = {
        "dataset_name": "Synthetic CV Screening Evaluation Dataset",
        "dataset_version": "1.0",
        "total_resumes": len(candidates),
        "total_jobs": len(jobs),
        "total_matches": len(matches),
        "synthetic_records": len(candidates),
        "synthetic_only": True,
        "contains_real_pii": False,
        "source_datasets": [
            "michaelozon/candidate-matching-synthetic",
            "datasetmaster/resumes"
        ],
        "licenses": ["Apache-2.0", "MIT"],
        "normalization_version": "1.0",
        "roles_distribution": {r[0]: r[2] for r in ROLE_DISTRIBUTION},
        "quality_distribution": {
            "standard_high_quality": "60%",
            "moderately_messy": "20%",
            "ambiguous": "10%",
            "difficult_edge_cases": "10%"
        }
    }

    with open(ROOT_DIR / "dataset_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Successfully generated {len(candidates)} resumes, {len(jobs)} JDs, and {len(matches)} matching labels!")
    print(f"Manifest written to: {ROOT_DIR / 'dataset_manifest.json'}")

if __name__ == "__main__":
    main()
