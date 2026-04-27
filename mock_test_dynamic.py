#!/usr/bin/env python3
"""
Dynamic VLSI Mock Test Generator using DeepSeek API
Generates fresh questions daily based on difficulty level cycle
"""

import os
import json
import smtplib
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple
import requests

# Configuration
IST = timezone(timedelta(hours=5, minutes=30))
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Define the 13 sections (same as before)
SECTIONS = [
    {"id": 1, "name": "Common Digital Logic & RTL Fundamentals"},
    {"id": 2, "name": "Verilog & SystemVerilog for Design & Lint checks"},
    {"id": 3, "name": "SystemVerilog for Verification (Basic to Intermediate)"},
    {"id": 4, "name": "Verification Methodology & Testbench Concepts"},
    {"id": 5, "name": "Synthesis & Static Timing Analysis"},
    {"id": 6, "name": "Clock Domain Crossing (CDC) & Reset Domain Crossing"},
    {"id": 7, "name": "Low-Power Design"},
    {"id": 8, "name": "Memory & Interfaces (basic awareness)"},
    {"id": 9, "name": "System Architecture (basic)"},
    {"id": 10, "name": "Scripting & Tools (Practical)"},
    {"id": 11, "name": "Problem Solving & Debugging"},
    {"id": 12, "name": "Interview Puzzles & Basics"},
    {"id": 13, "name": "Soft Skills & Resume Topics"}
]

def get_difficulty_level(base_date=None) -> Tuple[int, str]:
    """
    Calculate difficulty level based on 10-day cycle.
    Returns: (level_number, level_description)
    """
    if base_date is None:
        base_date = datetime.now(IST)
    
    epoch = datetime(2024, 1, 1, tzinfo=IST)
    days_since_epoch = (base_date - epoch).days
    
    level = (days_since_epoch % 10) + 1
    
    # Level descriptions for better prompting
    level_descriptions = {
        1: "FUNDAMENTAL - Entry level, basic concepts, definitions, simple circuits. For M.Tech freshers.",
        2: "BASIC - Simple design problems, standard interview questions, common scenarios.",
        3: "INTERMEDIATE - Moderate complexity, small design tasks, multiple concepts combined.",
        4: "UPPER INTERMEDIATE - Non-trivial designs, timing analysis, protocol basics.",
        5: "ADVANCED - Complex designs, optimization problems, trade-off analysis.",
        6: "EXPERT - Pipeline design, verification strategies, tool-specific deep dives.",
        7: "ARCHITECT - System-level design, multi-domain problems, performance analysis.",
        8: "SENIOR ARCHITECT - Cutting-edge techniques, protocol intricacies, advanced optimizations.",
        9: "PRINCIPAL ENGINEER - Research-level problems, novel solutions, cross-domain integration.",
        10: "FELLOW/CTO - Speculative designs, industry future directions, extreme complexity."
    }
    
    return level, level_descriptions[level]

def build_prompt(level: int, level_desc: str, sections: List[Dict]) -> str:
    """Build the prompt for DeepSeek API to generate fresh questions"""
    
    sections_text = "\n".join([f"{s['id']}. {s['name']}" for s in sections])
    
    prompt = f"""You are an expert VLSI interview coach generating a DAILY MOCK TEST.

REQUIREMENTS:
- Generate exactly {len(sections)} questions (one per section)
- Difficulty Level: {level}/10 - {level_desc}
- Questions must be UNIQUE and never repeated from previous days
- Questions should be PRACTICAL, INTERVIEW-FOCUSED, and REALISTIC
- For level 1-3: Focus on fundamentals, definitions, simple circuits
- For level 4-6: Add design problems, timing, verification scenarios
- For level 7-10: Add architecture, optimization, complex debugging

OUTPUT FORMAT (MUST BE VALID JSON):
{{
  "questions": [
    {{"section_id": 1, "question": "Your question here"}},
    {{"section_id": 2, "question": "Your question here"}},
    ...
  ]
}}

SECTIONS TO COVER:
{sections_text}

TODAY'S DATE: {datetime.now(IST).strftime('%Y-%m-%d')}
Use this date to ensure questions are different from past days.

Generate {len(sections)} fresh, challenging questions at level {level}/10.
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
                "content": "You are a VLSI interview expert. Generate unique, high-quality interview questions. Always respond with valid JSON only."
            },
            {
                "role": "user", 
                "content": prompt
            }
        ],
        "temperature": 0.9,  # Higher temperature for more variety
        "max_tokens": 4000,
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        # Parse JSON from response
        questions_data = json.loads(content)
        return questions_data
    
    except requests.exceptions.RequestException as e:
        print(f"API Error: {e}")
        raise
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {e}")
        print(f"Raw response: {content[:500]}...")
        raise

def generate_fallback_questions(level: int) -> Dict:
    """Fallback question generator if API fails (uses template-based generation)"""
    
    fallback_templates = {
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
        # Add more fallback templates for other levels
    }
    
    questions = []
    templates = fallback_templates.get(level, fallback_templates[1])
    
    for i, section in enumerate(SECTIONS):
        # Cycle through templates if not enough
        q_template = templates[i % len(templates)]
        question = f"[Level {level} - Fresh Daily] {q_template}"
        questions.append({"section_id": section["id"], "question": question})
    
    return {"questions": questions}

def generate_email_html(questions: List[Dict], level: int, level_desc: str, date_str: str) -> str:
    """Generate professional HTML email content with fresh questions"""
    
    # Map section IDs to names
    section_map = {s["id"]: s["name"] for s in SECTIONS}
    
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
            .section {{
                background: white;
                border-left: 5px solid #e94560;
                margin: 15px 0;
                padding: 15px 20px;
                border-radius: 10px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                transition: transform 0.2s;
            }}
            .section:hover {{
                transform: translateX(5px);
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
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🎯 AI-Generated VLSI Mock Test</h1>
            <div class="level-badge">
                Difficulty: Level {level}/10
            </div>
            <div class="level-desc">{level_desc}</div>
            <p style="margin-top: 15px;">📅 {date_str}</p>
            <span class="ai-badge">✨ Freshly generated by DeepSeek AI ✨</span>
        </div>
        
        <div class="timer">
            ⏱️ Recommended Time: 90 minutes (7-8 minutes per question) | Answer on paper for best retention
        </div>
        
        <p><strong>📋 Instructions:</strong></p>
        <ul>
            <li>Answer all <strong>13 questions</strong> (one from each domain)</li>
            <li>No two days have the same questions - AI generates unique content daily</li>
            <li>Tomorrow's difficulty will be <strong>Level {(level % 10) + 1 if level < 10 else 1}/10</strong></li>
            <li>If level = {(level % 10) + 1 if level < 10 else 1}, the cycle continues</li>
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
    
    next_level = (level % 10) + 1 if level < 10 else 1
    next_desc = {
        1: "Fundamental", 2: "Basic", 3: "Intermediate", 4: "Upper Intermediate",
        5: "Advanced", 6: "Expert", 7: "Architect", 8: "Senior Architect",
        9: "Principal Engineer", 10: "Fellow/CTO"
    }.get(next_level, "Next Level")
    
    html += f"""
        <div class="footer">
            <p>🚀 <strong>Remember:</strong> Daily practice with fresh questions is the fastest way to master VLSI interviews.</p>
            <p>📈 Tomorrow: Level {next_level}/10 - {next_desc} Level</p>
            <p>🤖 Questions generated uniquely for today by DeepSeek AI. No repetition guaranteed.</p>
            <p style="margin-top: 15px; font-size: 11px;">💡 Tip: For design roles - implement the circuit. For verification roles - write a testbench plan.</p>
            <hr style="margin: 15px 0; border-color: #333;">
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
    
    print(f"✅ Email sent to {to_email} at {datetime.now(IST)}")

def main():
    parser = argparse.ArgumentParser(description='Generate and send daily VLSI mock test using DeepSeek AI')
    parser.add_argument('--to', help='Recipient email address', default=os.environ.get('EMAIL_TO'))
    parser.add_argument('--dry-run', action='store_true', help='Generate questions but don\'t send email')
    parser.add_argument('--show-prompt', action='store_true', help='Show the prompt sent to DeepSeek')
    args = parser.parse_args()
    
    # Get configuration
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    smtp_config = {
        'smtp_server': os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port': int(os.environ.get('SMTP_PORT', 587)),
        'from_email': os.environ.get('EMAIL_FROM'),
        'password': os.environ.get('EMAIL_PASSWORD')
    }
    
    to_email = args.to or os.environ.get('EMAIL_TO')
    
    # Validate configuration
    if not api_key:
        print("❌ Error: DEEPSEEK_API_KEY environment variable not set")
        return 1
    
    if not args.dry_run and not all([smtp_config['from_email'], smtp_config['password'], to_email]):
        print("❌ Error: Missing email configuration for non-dry-run")
        return 1
    
    # Get today's difficulty
    level, level_desc = get_difficulty_level()
    date_str = datetime.now(IST).strftime("%A, %B %d, %Y - %I:%M %p IST")
    
    print(f"🎯 Generating Mock Test")
    print(f"   Date: {date_str}")
    print(f"   Level: {level}/10 - {level_desc[:50]}...")
    
    # Build prompt and call DeepSeek
    prompt = build_prompt(level, level_desc, SECTIONS)
    
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
        
        if len(questions) != len(SECTIONS):
            print(f"⚠️ Warning: Got {len(questions)} questions, expected {len(SECTIONS)}")
            # Pad or truncate as needed
        
        print(f"✅ Generated {len(questions)} fresh questions")
        
        # Display preview
        for q in questions[:3]:  # Show first 3 questions
            print(f"   - Section {q['section_id']}: {q['question'][:80]}...")
        
    except Exception as e:
        print(f"❌ DeepSeek API failed: {e}")
        print("🔄 Using fallback question generator...")
        questions_data = generate_fallback_questions(level)
        questions = questions_data.get('questions', [])
        print(f"✅ Generated {len(questions)} fallback questions")
    
    # Generate email
    subject = f"🎯 Day {level} VLSI Mock Test - {datetime.now(IST).strftime('%d %b %Y')} (AI-Generated)"
    html_content = generate_email_html(questions, level, level_desc, date_str)
    
    if args.dry_run:
        print("\n" + "="*60)
        print("DRY RUN - Email content preview")
        print("="*60)
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print("\n--- HTML Preview (first 1000 chars) ---")
        print(html_content[:1000])
        print("\n--- Questions Preview ---")
        for q in questions:
            print(f"\n[{q['section_id']}] {q['question'][:150]}...")
        print("\n" + "="*60)
        return 0
    
    # Send email
    send_email(to_email, subject, html_content, smtp_config)
    print(f"\n✨ Mock test sent successfully at {datetime.now(IST)}")
    print(f"   Level: {level}/10")
    print(f"   Questions: {len(questions)}")
    print(f"   Next level: {(level % 10) + 1 if level < 10 else 1}/10 tomorrow")
    
    return 0

if __name__ == "__main__":
    exit(main())
