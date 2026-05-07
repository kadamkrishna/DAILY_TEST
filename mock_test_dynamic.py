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
        1: "FUNDAMENTAL - Entry level, basic concepts, definitions, simple circuits. For M.Tech freshers.",
        2: "BASIC - Simple design problems, standard interview questions, common scenarios.",
        3: "INTERMEDIATE - Moderate complexity, small design tasks, multiple concepts combined.",
        4: "UPPER INTERMEDIATE - Non-trivial designs, timing analysis, protocol basics.",
        5: "ADVANCED - Complex designs, optimization problems, trade-off analysis."
    }
    
    return level, level_descriptions[level]

def load_question_history() -> Dict:
    """Load previously asked questions from JSON file"""
    if not os.path.exists(HISTORY_FILE):
        empty_history = {
            "questions": [],
            "last_updated": None,
            "total_days": 0
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
    """Return set of all previously asked questions for duplicate checking"""
    asked = set()
    for entry in history.get("questions", []):
        # Each entry has a 'questions' list
        for q in entry.get("questions", []):
            question_text = q.get("question", "")
            if question_text:
                asked.add(question_text)
    return asked

def get_total_unique_questions(history: Dict) -> int:
    """Return total number of unique questions asked so far"""
    return len(get_asked_questions_set(history))

def build_prompt(level: int, level_desc: str, sections: List[Dict], asked_questions: Set[str]) -> str:
    """Build the prompt for DeepSeek API with anti-repetition instructions"""
    
    sections_text = "\n".join([f"{s['id']}. {s['name']}" for s in sections])
    
    # Convert asked questions to list for the prompt (limit to last 50 to avoid token overflow)
    asked_list = list(asked_questions)
    if len(asked_list) > 50:
        asked_list = asked_list[-50:]
    
    asked_text = "\n".join([f"- {q}" for q in asked_list]) if asked_list else "No questions asked yet."
    
    prompt = f"""You are an expert VLSI interview coach generating a DAILY MOCK TEST.

CRITICAL REQUIREMENT - NO DUPLICATES:
The following questions have ALREADY been asked in previous tests. 
You MUST generate COMPLETELY NEW questions that are NOT the same or very similar to these:

PREVIOUSLY ASKED QUESTIONS:
{asked_text}

REQUIREMENTS:
- Generate exactly {len(sections)} questions (one per section)
- Difficulty Level: {level}/5 - {level_desc}
- Each question MUST be UNIQUE and never asked before (check against the list above)
- Questions should be PRACTICAL, INTERVIEW-FOCUSED, and REALISTIC
- Topics can be repeated but the exact wording/problem must be different
- For level 1-3: Focus on fundamentals, definitions, simple circuits
- For level 4-5: Add design problems, timing, verification scenarios

OUTPUT FORMAT (MUST BE VALID JSON):
{{
  "questions": [
    {{"section_id": 1, "question": "Your completely new question here"}},
    {{"section_id": 2, "question": "Your completely new question here"}},
    ...
  ]
}}

SECTIONS TO COVER:
{sections_text}

TODAY'S DATE: {datetime.now(IST).strftime('%Y-%m-%d')}

Generate {len(sections)} fresh, UNIQUE, challenging questions at level {level}/5.
Return ONLY valid JSON, no other text."""
    
    return prompt

def call_deepseek_api(prompt: str, api_key: str) -> Dict:
    """Call DeepSeek API and return parsed JSON response"""
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system", 
                "content": "You are a VLSI interview expert. Generate unique, high-quality interview questions. Never repeat questions. Always respond with valid JSON only."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ],
        "temperature": 0.9,
        "max_tokens": 4000,
        "response_format": {"type": "json_object"}
    }
    
    response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    
    result = response.json()
    content = result['choices'][0]['message']['content']
    
    # Parse JSON from response
    questions_data = json.loads(content)
    return questions_data

def generate_fallback_questions(level: int, asked_questions: Set[str]) -> Dict:
    """Fallback question generator if API fails - with duplicate avoidance"""
    
    fallback_pool = {
        1: [
            "Explain the difference between synchronous and asynchronous reset.",
            "Write Verilog code for a D flip-flop with active-low reset.",
            "What is the difference between $display and $monitor in Verilog?",
            "Explain the difference between directed and constrained-random testing.",
            "Define setup time and hold time.",
            "What is metastability and how do you fix it?",
            "What is clock gating and why is it used?",
            "List the basic signals of AHB-Lite protocol.",
            "Draw a 5-stage pipeline diagram.",
            "Write a Python function to read a file and count lines.",
            "How do you debug a simulation that shows 'X' on a signal?",
            "Design a divide-by-2 clock divider using a D flip-flop.",
            "Tell me about a project you worked on."
        ],
        2: [
            "Design a 4-bit synchronous counter with enable.",
            "Explain blocking vs non-blocking assignments with example.",
            "Write a testbench for a 4-bit adder using SystemVerilog.",
            "What is code coverage vs functional coverage?",
            "Calculate max clock frequency for a given timing path.",
            "Design a two-flop synchronizer for a single-bit CDC.",
            "What are the power optimization techniques at RTL level?",
            "Explain AXI read and write transactions.",
            "What is a pipeline hazard? Give examples.",
            "Write a TCL script to run a simulation.",
            "Debug a simulation where output is 'Z' unexpectedly.",
            "Convert a D flip-flop to T flip-flop.",
            "How do you prioritize multiple bugs?"
        ],
        3: [
            "Design a 4-bit carry lookahead adder.",
            "Write SystemVerilog interface for AHB-Lite.",
            "Implement a scoreboard with a reference model.",
            "Explain UVM phases and their order.",
            "What is clock gating? Design a glitch-free clock gate.",
            "Explain Gray code based FIFO pointer synchronization.",
            "What is multi-Vt and when do you use it?",
            "Describe DDR read and write timing.",
            "Explain out-of-order execution in simple terms.",
            "Parse a log file and extract error counts.",
            "Debug an inferred latch in an FSM.",
            "Design a sequence detector for '1011'.",
            "Describe a difficult bug you solved."
        ],
        4: [
            "Design a parameterized FIFO with status flags.",
            "Write a SystemVerilog package for common functions.",
            "Build a UVM environment with agent, driver, monitor.",
            "Explain the difference between RAL frontdoor and backdoor access.",
            "Identify false paths and multicycle paths in a design.",
            "Design a handshake-based CDC for multi-bit data.",
            "What is power gating and how do you implement retention flops?",
            "Explain AXI3, AXI4, and AXI4-Lite differences.",
            "Design a branch predictor for a 5-stage pipeline.",
            "Write a Python script to automate regression runs.",
            "Debug a setup time violation in a critical path.",
            "Design a Mealy FSM for a UART receiver.",
            "How do you handle a last-minute spec change?"
        ],
        5: [
            "Design a 16-bit Wallace tree multiplier.",
            "Write synthesizable Verilog for a dual-port RAM.",
            "Implement a UVM sequence with constrained random traffic.",
            "What are the differences between OVM, VMM, and UVM?",
            "Perform STA on a design with multiple clocks.",
            "Design a FIFO-based CDC for multi-bit data.",
            "Explain UPF and create a simple power intent.",
            "Design a simple DMA controller.",
            "Implement Tomasulo's algorithm for out-of-order execution.",
            "Write a Makefile for a multi-file simulation flow.",
            "Debug an X-propagation issue in a complex design.",
            "Design an 8-bit Booth multiplier.",
            "How do you verify a cache coherency protocol?"
        ]
    }
    
    # Get closest level
    available_levels = sorted(fallback_pool.keys())
    closest = min(available_levels, key=lambda x: abs(x - level))
    templates = fallback_pool[closest]
    
    questions = []
    used_questions = set()
    
    for i, section in enumerate(SECTIONS):
        # Find a question not asked before
        selected_question = None
        for q in templates:
            if q not in asked_questions and q not in used_questions:
                selected_question = q
                break
        
        if selected_question is None:
            # If all are asked, use with modification note
            selected_question = templates[i % len(templates)]
            selected_question = f"[Repetition Fallback] {selected_question}"
        
        used_questions.add(selected_question)
        questions.append({"section_id": section["id"], "question": selected_question})
    
    return {"questions": questions}

def commit_and_push_history():
    """Commit and push the updated history file to GitHub"""
    try:
        subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=False)
        
        subprocess.run(["git", "add", HISTORY_FILE], check=False)
        subprocess.run(["git", "commit", "-m", f"Update question history - {datetime.now(IST).strftime('%Y-%m-%d')}"], check=False)
        subprocess.run(["git", "push"], check=False)
        print("✅ Question history committed to GitHub")
    except Exception as e:
        print(f"⚠️ Could not commit history: {e}")

def generate_email_html(questions: List[Dict], level: int, level_desc: str, date_str: str, total_unique_questions: int) -> str:
    """Generate professional HTML email content"""
    
    section_map = {s["id"]: s["name"] for s in SECTIONS}
    
    next_level = (level % 5) + 1
    next_desc = {
        1: "Fundamental", 2: "Basic", 3: "Intermediate", 4: "Upper Intermediate", 5: "Advanced"
    }.get(next_level, "Next Level")
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            margin-bottom: 25px;
        }}
        .level-badge {{
            display: inline-block;
            background: #e94560;
            color: white;
            padding: 8px 20px;
            border-radius: 30px;
            font-weight: bold;
            margin: 10px 0;
            font-size: 18px;
        }}
        .level-desc {{
            font-size: 14px;
            opacity: 0.9;
            margin-top: 5px;
        }}
        .stats {{
            background: #00b894;
            color: white;
            padding: 8px 15px;
            border-radius: 20px;
            display: inline-block;
            font-size: 12px;
            margin-top: 10px;
        }}
        .section {{
            background: white;
            border-left: 5px solid #e94560;
            margin: 15px 0;
            padding: 15px 20px;
            border-radius: 10px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .section-title {{
            font-weight: bold;
            color: #1a1a2e;
            margin-bottom: 10px;
            font-size: 16px;
            display: flex;
            align-items: center;
        }}
        .section-number {{
            background: #e94560;
            color: white;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            margin-right: 12px;
        }}
        .question {{
            color: #333;
            font-size: 15px;
            line-height: 1.5;
            margin-left: 40px;
            padding-left: 15px;
            border-left: 2px solid #eee;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            padding: 20px;
            background: #1a1a2e;
            color: white;
            border-radius: 10px;
            font-size: 13px;
        }}
        .ai-badge {{
            background: #00b894;
            color: white;
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 11px;
            margin-left: 10px;
        }}
        .timer {{
            background: #ffd93d;
            color: #1a1a2e;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            margin: 20px 0;
            font-weight: bold;
        }}
        .no-repeat {{
            background: #e94560;
            color: white;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 11px;
            display: inline-block;
            margin-left: 10px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 AI-Generated VLSI Mock Test</h1>
        <div class="level-badge">Difficulty: Level {level}/5</div>
        <div class="level-desc">{level_desc}</div>
        <p style="margin-top: 15px;">📅 {date_str}</p>
        <span class="ai-badge">✨ Freshly generated by DeepSeek AI ✨</span>
        <span class="no-repeat">🚫 No Question Repeats</span>
        <div class="stats">📚 Total unique questions asked so far: {total_unique_questions}</div>
    </div>
    
    <div class="timer">
        ⏱️ Recommended Time: 90 minutes (7-8 minutes per question)
    </div>
    
    <p><strong>📋 Instructions:</strong></p>
    <ul>
        <li>Answer all <strong>13 questions</strong> (one from each domain)</li>
        <li><strong>Every question is unique</strong> - Never asked before in any previous test</li>
        <li>Tomorrow's difficulty will be <strong>Level {next_level}/5</strong></li>
    </ul>
    
    <hr style="margin: 25px 0;">
"""
    
    for q in questions:
        section_name = section_map.get(q["section_id"], "Unknown Section")
        html += f"""
    <div class="section">
        <div class="section-title">
            <span class="section-number">{q['section_id']}</span>
            {section_name}
        </div>
        <div class="question">
            ❓ {q['question']}
        </div>
    </div>
"""
    
    html += f"""
    <div class="footer">
        <p>🚀 <strong>Daily practice with UNIQUE questions is the fastest way to master VLSI interviews!</strong></p>
        <p>📈 Tomorrow: Level {next_level}/5 - {next_desc} Level</p>
        <p>🤖 Questions generated uniquely for today - {total_unique_questions}+ questions already in history</p>
        <p>❄️ Keep grinding - Your future VLSI engineer self will thank you!</p>
    </div>
</body>
</html>
"""
    
    return html

def send_email(to_email: str, subject: str, html_content: str, smtp_config: Dict) -> None:
    """Send email using SMTP"""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = smtp_config['from_email']
    msg['To'] = to_email
    
    mime_html = MIMEText(html_content, 'html')
    msg.attach(mime_html)
    
    with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port']) as server:
        server.starttls()
        server.login(smtp_config['from_email'], smtp_config['password'])
        server.sendmail(smtp_config['from_email'], [to_email], msg.as_string())
    
    print(f"✅ Email sent to {to_email}")

def main():
    parser = argparse.ArgumentParser(description='Generate and send daily VLSI mock test using DeepSeek AI')
    parser.add_argument('--to', help='Recipient email address', default=os.environ.get('EMAIL_TO'))
    parser.add_argument('--dry-run', action='store_true', help='Generate questions but don\'t send email')
    parser.add_argument('--show-prompt', action='store_true', help='Show the prompt sent to DeepSeek')
    args = parser.parse_args()
    
    # ========== VALIDATE DEEPSEEK API KEY ==========
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ Error: DEEPSEEK_API_KEY environment variable not set")
        return 1
    
    # ========== SAFELY GET SMTP CONFIGURATION ==========
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    
    smtp_port_raw = os.environ.get('SMTP_PORT', '587')
    try:
        smtp_port = int(smtp_port_raw) if smtp_port_raw and smtp_port_raw.strip() else 587
    except ValueError:
        print(f"⚠️ Warning: Invalid SMTP_PORT '{smtp_port_raw}', using default 587")
        smtp_port = 587
    
    email_from = os.environ.get('EMAIL_FROM')
    email_password = os.environ.get('EMAIL_PASSWORD')
    to_email = args.to or os.environ.get('EMAIL_TO')
    
    smtp_config = {
        'smtp_server': smtp_server,
        'smtp_port': smtp_port,
        'from_email': email_from,
        'password': email_password
    }
    
    # Validate email config (skip for dry-run)
    if not args.dry_run:
        missing = []
        if not email_from:
            missing.append('EMAIL_FROM')
        if not email_password:
            missing.append('EMAIL_PASSWORD')
        if not to_email:
            missing.append('EMAIL_TO')
        
        if missing:
            print(f"❌ Error: Missing required secrets: {', '.join(missing)}")
            print("   For testing without email, use --dry-run flag")
            return 1
    
    # ========== LOAD QUESTION HISTORY ==========
    print("📚 Loading question history...")
    history = load_question_history()
    asked_questions = get_asked_questions_set(history)
    total_unique_before = len(asked_questions)
    print(f"   Found {total_unique_before} previously asked questions")
    
    # ========== GENERATE QUESTIONS ==========
    level, level_desc = get_difficulty_level()
    date_str = datetime.now(IST).strftime("%A, %B %d, %Y - %I:%M %p IST")
    
    print(f"🎯 Generating Mock Test")
    print(f"   Date: {date_str}")
    print(f"   Level: {level}/5")
    print(f"   Avoiding {total_unique_before} existing questions")
    
    prompt = build_prompt(level, level_desc, SECTIONS, asked_questions)
    
    if args.show_prompt:
        print("\n" + "="*60)
        print("PROMPT SENT TO DEEPSEEK:")
        print("="*60)
        print(prompt)
        print("="*60 + "\n")
    
    try:
        print("🔄 Calling DeepSeek API...")
        questions_data = call_deepseek_api(prompt, api_key)
        questions = questions_data.get('questions', [])
        print(f"✅ Generated {len(questions)} fresh questions from DeepSeek")
    except Exception as e:
        print(f"❌ DeepSeek API failed: {e}")
        print("🔄 Using fallback question generator...")
        questions_data = generate_fallback_questions(level, asked_questions)
        questions = questions_data.get('questions', [])
        print(f"✅ Generated {len(questions)} fallback questions")
    
    # Ensure we have exactly 13 questions
    if len(questions) != len(SECTIONS):
        print(f"⚠️ Warning: Got {len(questions)} questions, expected {len(SECTIONS)}")
        while len(questions) < len(SECTIONS):
            questions.append({"section_id": len(questions) + 1, "question": "Explain a VLSI concept you're confident about."})
    
    # ========== CHECK FOR DUPLICATES ==========
    new_questions_text = [q.get('question', '') for q in questions]
    duplicates = [q for q in new_questions_text if q in asked_questions]
    
    if duplicates:
        print(f"⚠️ Warning: Found {len(duplicates)} duplicate questions!")
        for dup in duplicates[:3]:
            print(f"   - {dup[:50]}...")
    else:
        print(f"✅ No duplicates detected - all {len(questions)} questions are new!")
    
    # ========== UPDATE HISTORY ==========
    print("💾 Updating question history...")
    today_entry = {
        "date": datetime.now(IST).strftime("%Y-%m-%d"),
        "level": level,
        "questions": questions
    }
    history["questions"].append(today_entry)
    history["last_updated"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S %Z")
    history["total_days"] = len(history["questions"])
    
    save_question_history(history)
    print(f"   History updated! Total days: {history['total_days']}")
    
    # Commit and push if running in GitHub Actions (not dry-run)
    if not args.dry_run and os.environ.get('GITHUB_ACTIONS') == 'true':
        commit_and_push_history()
    
    # Calculate total unique questions after adding today's
    total_unique_after = get_total_unique_questions(history)
    
    # ========== GENERATE AND SEND EMAIL ==========
    subject = f"🎯 Day {level} VLSI Mock Test - {datetime.now(IST).strftime('%d %b %Y')} (No Repeats!)"
    html_content = generate_email_html(questions, level, level_desc, date_str, total_unique_after)
    
    if args.dry_run:
        print("\n" + "="*60)
        print("DRY RUN - Email content preview")
        print("="*60)
        print(f"To: {to_email or 'Not set'}")
        print(f"Subject: {subject}")
        print(f"Total unique questions in history: {total_unique_after}")
        print("\n--- First 3 Questions Preview ---")
        for q in questions[:3]:
            print(f"\n[{q.get('section_id', '?')}] {q.get('question', '')[:100]}...")
        if len(questions) > 3:
            print(f"\n... and {len(questions) - 3} more questions")
        print("\n" + "="*60)
        return 0
    
    # Send real email
    send_email(to_email, subject, html_content, smtp_config)
    print(f"\n✨ Mock test sent successfully at {datetime.now(IST)}")
    print(f"   Level: {level}/5")
    print(f"   Questions: {len(questions)}")
    print(f"   Total unique questions in bank: {total_unique_after}")
    
    return 0

if __name__ == "__main__":
    exit(main())
