#!/usr/bin/env python3
import os
import json
import smtplib
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
import requests

IST = timezone(timedelta(hours=5, minutes=30))
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

SECTIONS = [
    "Digital Logic & RTL Fundamentals",
    "Verilog & SystemVerilog for Design",
    "SystemVerilog for Verification",
    "Verification Methodology & Testbench",
    "Synthesis & Timing",
    "Clock Domain Crossing (CDC) & Reset",
    "Low-Power Design",
    "Memory & Interfaces",
    "System Architecture",
    "Scripting & Tools",
    "Problem Solving & Debugging",
    "Interview Puzzles",
    "Soft Skills"
]

def get_level():
    days = (datetime.now(IST) - datetime(2024, 1, 1, tzinfo=IST)).days
    return (days % 5) + 1

def build_prompt(level, asked):
    asked_text = "\n".join(list(asked)[-30:]) if asked else "None"
    return f"""Generate exactly 13 VLSI interview questions (Level {level}/5).

PREVIOUSLY ASKED (DO NOT REPEAT):
{asked_text}

One question for each of these topics:
{chr(10).join(SECTIONS)}

Return ONLY JSON: {{"questions": [{{"section": 0, "question": "text"}}]}}"""

def get_questions(api_key, prompt):
    r = requests.post(DEEPSEEK_API_URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                      json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.9})
    return r.json()["choices"][0]["message"]["content"]

def send_email(to_, subject, html, cfg):
    msg = MIMEMultipart('alternative')
    msg['Subject'], msg['From'], msg['To'] = subject, cfg['from'], to_
    msg.attach(MIMEText(html, 'html'))
    with smtplib.SMTP(cfg['server'], cfg['port']) as s:
        s.starttls()
        s.login(cfg['from'], cfg['password'])
        s.sendmail(cfg['from'], [to_], msg.as_string())

def main():
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("Missing API key")
        return 1
    
    level = get_level()
    print(f"Level {level}/5 - {datetime.now(IST).strftime('%Y-%m-%d')}")
    
    # Load history
    history_file = "question_history.json"
    asked = set()
    if os.path.exists(history_file):
        with open(history_file) as f:
            for entry in json.load(f).get("questions", []):
                asked.add(entry.get("question", ""))
    print(f"History: {len(asked)} questions")
    
    # Generate
    prompt = build_prompt(level, asked)
    try:
        content = get_questions(api_key, prompt)
        data = json.loads(content)
        questions = data.get("questions", [])
    except:
        questions = [{"section": i, "question": f"Explain {SECTIONS[i]} concept"} for i in range(13)]
    
    # Save history
    history = {"questions": [{"date": datetime.now(IST).isoformat(), "level": level, "questions": questions}]}
    with open(history_file, "w") as f:
        json.dump(history, f)
    
    # Email
    if not os.environ.get('DRY_RUN'):
        html = "<html><body><h1>VLSI Mock Test</h1>" + "".join(f"<p><b>{q.get('section',i)+1}. {SECTIONS[q.get('section',i)]}</b><br>{q.get('question','')}</p>" for i,q in enumerate(questions)) + "</body></html>"
        send_email(os.environ['EMAIL_TO'], f"VLSI Test Level {level}", html,
                   {'server': os.environ.get('SMTP_SERVER','smtp.gmail.com'), 'port': int(os.environ.get('SMTP_PORT',587)),
                    'from': os.environ['EMAIL_FROM'], 'password': os.environ['EMAIL_PASSWORD']})
        print("Email sent")
    else:
        print("DRY RUN - Questions:", [q.get('question','')[:50] for q in questions])
    return 0

if __name__ == "__main__":
    exit(main())
