#!/usr/bin/env python3
"""
Dynamic VLSI Mock Test Generator using DeepSeek API
Generates fresh questions daily with NO repetition using persistent history
"""

import os
import json
import smtplib
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Set
import requests
import subprocess

# Configuration
IST = timezone(timedelta(hours=5, minutes=30))
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
HISTORY_FILE = "question_history.json"

# Define the 13 sections
SECTIONS = [
    {"id": 1, "name": "Common Digital Logic & RTL Fundamentals"},
    {"id": 2, "name": "Verilog & SystemVerilog for Design"},
    {"id": 3, "name": "SystemVerilog for Verification (Basic to Intermediate)"},
    {"id": 4, "name": "Verification Methodology & Testbench Concepts"},
    {"id": 5, "name": "Synthesis & Timing"},
    {"id": 6, "name": "Clock Domain Crossing (CDC) & Reset"},
    {"id": 7, "name": "Low-Power Design"},
    {"id": 8, "name": "Memory & Interfaces (basic awareness)"},
    {"id": 9, "name": "System Architecture (basic)"},
    {"id": 10, "name": "Scripting & Tools (Practical)"},
    {"id": 11, "name": "Problem Solving & Debugging"},
    {"id": 12, "name": "Interview Puzzles & Basics"},
    {"id": 13, "name": "Soft Skills & Resume Topics"}
]

def get_difficulty_level(base_date=None) -> Tuple[int, str]:
    """Calculate difficulty level based on 5-day cycle."""
    if base_date is None:
        base_date = datetime.now(IST)
    
    epoch = datetime(2024, 1, 1, tzinfo=IST)
    days_since_epoch = (base_date - epoch).days
    
    level = (days_since_epoch % 5) + 1
    
    level_descriptions = {
        1: "FUNDAMENTAL - Entry level, basic concepts, definitions, simple circuits.",
        2: "BASIC - Simple design problems, standard interview questions.",
        3: "INTERMEDIATE - Moderate complexity, small design tasks.",
        4: "UPPER INTERMEDIATE - Non-trivial designs, timing analysis.",
        5: "ADVANCED - Complex designs, optimization problems."
    }
    
    return level, level_descriptions[level]

def load_question_history() -> Dict:
    """Load previously asked questions from JSON file"""
    if not os.path.exists(HISTORY_FILE):
        empty_history = {
            "questions": [],
            "last_updated": None,
            "total_questions": 0
        }
        with open(HISTORY_FILE, 'w') as f:
            json.dump(empty_history, f, indent=2)
        return empty_history
    
    with open(HISTORY_FILE, 'r') as f:
        return json.load(f)

def save_question_history(history: Dict) -> None:
    """Save updated question history to JSON file"""
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def get_asked_questions_set(history: Dict) -> Set[str]:
    """Return set of all previously asked questions"""
    asked = set()
    for entry in history.get("questions", []):
        for q in entry.get("questions", []):
            asked.add(q.get("question", ""))
    return asked

def build_prompt(level: int, level_desc: str, sections: List[Dict], asked_questions: Set[str]) -> str:
    """Build the prompt for DeepSeek API"""
    sections_text = "\n".join([f"{s['id']}. {s['name']}" for s in sections])
    
    asked_list = list(asked_questions)
    if len(asked_list) > 50:
        asked_list = asked_list[-50:]
    
    asked_text = "\n".join([f"- {q}" for q in asked_list]) if asked_list else "No questions asked yet."
    
    prompt = f"""You are an expert VLSI interview coach generating a DAILY MOCK TEST.

CRITICAL: Do NOT repeat these previously asked questions:
{asked_text}

Generate exactly {len(sections)} questions (one per section)
Difficulty Level: {level}/10 - {level_desc}
Each question must be completely NEW and never asked before

OUTPUT FORMAT (JSON only):
{{
  "questions": [
    {{"section_id": 1, "question": "Your question here"}},
    {{"section_id": 2, "question": "Your question here"}}
  ]
}}

SECTIONS:
{sections_text}

Today's date: {datetime.now(IST).strftime('%Y-%m-%d')}
Return ONLY valid JSON, no other text."""
    
    return prompt

def call_deepseek_api(prompt: str, api_key: str) -> Dict:
    """Call DeepSeek API"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.9,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"}
    }
    
    response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()
    content = result['choices'][0]['message']['content']
    return json.loads(content)

def generate_fallback_questions(level: int, asked_questions: Set[str]) -> Dict:
    """Fallback question generator"""
    fallback_pool = {
        1: [
            "Explain the difference between synchronous and asynchronous reset.",
            "Write Verilog code for a D flip-flop with active-low reset.",
            "What is the difference between $display and $monitor?",
            "Explain directed vs constrained-random testing.",
            "Define setup time and hold time."
        ],
        2: [
            "Design a 4-bit synchronous counter with enable.",
            "Explain blocking vs non-blocking assignments.",
            "What is code coverage vs functional coverage?",
            "Design a two-flop synchronizer.",
            "What are power optimization techniques?"
        ],
        3: [
            "Design a 4-bit carry lookahead adder.",
            "Write SystemVerilog interface for AHB-Lite.",
            "Explain UVM phases.",
            "Design a glitch-free clock gate.",
            "Explain Gray code FIFO synchronization."
        ],
        4: [
            "Design a parameterized FIFO.",
            "Build a UVM environment.",
            "Identify false paths and multicycle paths.",
            "Design a handshake-based CDC.",
            "Explain AXI4 differences."
        ],
        5: [
            "Design a 16-bit Wallace tree multiplier.",
            "Implement a UVM sequence with random traffic.",
            "Perform STA on a design with multiple clocks.",
            "Design a FIFO-based CDC.",
            "Explain UPF power intent."
        ]
    }
    
    available_levels = sorted(fallback_pool.keys())
    closest = min(available_levels, key=lambda x: abs(x - level))
    templates = fallback_pool[closest]
    
    questions = []
    for i, section in enumerate(SECTIONS):
        q = templates[i % len(templates)]
        if q in asked_questions:
            q = f"[Alternative] {q}"
        questions.append({"section_id": section["id"], "question": q})
    
    return {"questions": questions}

def generate_email_html(questions: List[Dict], level: int, level_desc: str, date_str: str, history_count: int) -> str:
    """Generate HTML email content"""
    section_map = {s["id"]: s["name"] for s in SECTIONS}
    next_level = (level % 5) + 1 if level < 5 else 1
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        .header {{ background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; padding: 25px; border-radius: 15px; text-align: center; }}
        .level-badge {{ background: #e94560; padding: 8px 20px; border-radius: 30px; display: inline-block; }}
        .section {{ background: white; border-left: 5px solid #e94560; margin: 15px 0; padding: 15px; border-radius: 10px; }}
        .section-title {{ font-weight: bold; color: #1a1a2e; }}
        .question {{ color: #333; margin-left: 20px; }}
        .footer {{ text-align: center; margin-top: 30px; padding: 20px; background: #1a1a2e; color: white; border-radius: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 VLSI Mock Test</h1>
        <div class="level-badge">Level {level}/5</div>
        <div class="level-desc">{level_desc}</div>
        <p>📅 {date_str}</p>
        <p>📚 Total unique questions: {history_count}</p>
    </div>
"""
    
    for q in questions:
        section_name = section_map.get(q["section_id"], "Unknown")
        html += f"""
    <div class="section">
        <div class="section-title">Section {q['section_id']}: {section_name}</div>
        <div class="question">❓ {q['question']}</div>
    </div>
"""
    
    html += f"""
    <div class="footer">
        <p>Tomorrow: Level {next_level}/5 | No questions repeat ever!</p>
    </div>
</body>
</html>
"""
    return html

def send_email(to_email: str, subject: str, html_content: str, smtp_config: Dict) -> None:
    """Send email"""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = smtp_config['from_email']
    msg['To'] = to_email
    msg.attach(MIMEText(html_content, 'html'))
    
    with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port']) as server:
        server.starttls()
        server.login(smtp_config['from_email'], smtp_config['password'])
        server.sendmail(smtp_config['from_email'], [to_email], msg.as_string())

def commit_and_push_history():
    """Commit and push history to GitHub"""
    try:
        subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=False)
        subprocess.run(["git", "add", HISTORY_FILE], check=False)
        subprocess.run(["git", "commit", "-m", f"Update history - {datetime.now(IST).strftime('%Y-%m-%d')}"], check=False)
        subprocess.run(["git", "push"], check=False)
        print("✅ History committed")
    except Exception as e:
        print(f"⚠️ Commit failed: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--to', default=os.environ.get('EMAIL_TO'))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--show-prompt', action='store_true')
    args = parser.parse_args()
    
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ Missing DEEPSEEK_API_KEY")
        return 1
    
    smtp_config = {
        'smtp_server': os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port': int(os.environ.get('SMTP_PORT', '587') or 587),
        'from_email': os.environ.get('EMAIL_FROM'),
        'password': os.environ.get('EMAIL_PASSWORD')
    }
    to_email = args.to or os.environ.get('EMAIL_TO')
    
    if not args.dry_run:
        if not all([smtp_config['from_email'], smtp_config['password'], to_email]):
            print("❌ Missing email config")
            return 1
    
    print("📚 Loading history...")
    history = load_question_history()
    asked_questions = get_asked_questions_set(history)
    print(f"   Found {len(asked_questions)} asked questions")
    
    level, level_desc = get_difficulty_level()
    date_str = datetime.now(IST).strftime("%A, %B %d, %Y")
    
    print(f"🎯 Generating Level {level}/5 test")
    prompt = build_prompt(level, level_desc, SECTIONS, asked_questions)
    
    if args.show_prompt:
        print("\nPROMPT:\n", prompt, "\n")
    
    try:
        print("🔄 Calling DeepSeek API...")
        questions_data = call_deepseek_api(prompt, api_key)
        questions = questions_data.get('questions', [])
        print(f"✅ Generated {len(questions)} questions")
    except Exception as e:
        print(f"❌ API failed: {e}, using fallback")
        questions_data = generate_fallback_questions(level, asked_questions)
        questions = questions_data.get('questions', [])
    
    # Save to history
    history["questions"].append({
        "date": datetime.now(IST).strftime("%Y-%m-%d"),
        "level": level,
        "questions": questions
    })
    history["total_questions"] = len(history["questions"])
    save_question_history(history)
    
    if os.environ.get('GITHUB_ACTIONS') == 'true' and not args.dry-run:
        commit_and_push_history()
    
    subject = f"VLSI Mock Test - Level {level}/5 - {datetime.now(IST).strftime('%d %b %Y')}"
    html_content = generate_email_html(questions, level, level_desc, date_str, history['total_questions'] * 13)
    
    if args.dry-run:
        print("\nDRY RUN - Questions:")
        for q in questions[:3]:
            print(f"  - {q['question'][:80]}...")
        return 0
    
    send_email(to_email, subject, html_content, smtp_config)
    print(f"✅ Email sent to {to_email}")
    return 0

if __name__ == "__main__":
    exit(main())
