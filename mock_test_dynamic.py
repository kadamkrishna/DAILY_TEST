#!/usr/bin/env python3
"""
Dynamic VLSI Mock Test Generator using DeepSeek API
Generates fresh questions daily based on difficulty level cycle
Tracks question history to avoid repetition across days
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

# ── History file location ──────────────────────────────────────────────────────
# Stored next to this script by default.
# Override with env var VLSI_HISTORY_FILE=/path/to/history.json
HISTORY_FILE = os.environ.get(
    "VLSI_HISTORY_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "vlsi_questions_history.json")
)

# How many recent days of questions to include in the "don't repeat" prompt context.
# Older entries are kept in the file but not sent to the API (saves tokens).
HISTORY_CONTEXT_DAYS = 30

# Define the 13 sections
SECTIONS = [
    {"id": 1,  "name": "Common Digital Logic & RTL Fundamentals"},
    {"id": 2,  "name": "Verilog & SystemVerilog for Design"},
    {"id": 3,  "name": "SystemVerilog for Verification (Basic to Intermediate)"},
    {"id": 4,  "name": "Verification Methodology & Testbench Concepts"},
    {"id": 5,  "name": "Synthesis & Timing"},
    {"id": 6,  "name": "Clock Domain Crossing (CDC) & Reset"},
    {"id": 7,  "name": "Low-Power Design"},
    {"id": 8,  "name": "Memory & Interfaces (basic awareness)"},
    {"id": 9,  "name": "System Architecture (basic)"},
    {"id": 10, "name": "Scripting & Tools (Practical)"},
    {"id": 11, "name": "Problem Solving & Debugging"},
    {"id": 12, "name": "Interview Puzzles & Basics"},
    {"id": 13, "name": "Soft Skills & Resume Topics"}
]


# ══════════════════════════════════════════════════════════════════════════════
#  HISTORY  –  load / save / summarise
# ══════════════════════════════════════════════════════════════════════════════

def load_history() -> List[Dict]:
    """
    Load the full question history from disk.
    Returns a list of day-records, each shaped like:
        {
            "date":      "2025-05-07",
            "level":     3,
            "questions": [{"section_id": 1, "question": "..."}, ...]
        }
    Returns [] if the file doesn't exist yet.
    """
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        # Legacy format fallback (dict keyed by date)
        return list(data.values()) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  Could not load history file ({e}). Starting fresh.")
        return []


def save_history(history: List[Dict]) -> None:
    """Persist the full history list to disk (pretty-printed JSON)."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        print(f"💾  History saved → {HISTORY_FILE}  ({len(history)} day(s) stored)")
    except OSError as e:
        print(f"❌  Could not save history: {e}")


def append_to_history(history: List[Dict], questions: List[Dict], level: int) -> List[Dict]:
    """Add today's questions to the history list and return the updated list."""
    today = datetime.now(IST).strftime("%Y-%m-%d")

    # Remove any existing entry for today (re-run safety)
    history = [h for h in history if h.get("date") != today]

    history.append({
        "date":      today,
        "level":     level,
        "questions": questions
    })

    # Keep the list sorted newest-first for readability
    history.sort(key=lambda h: h.get("date", ""), reverse=True)
    return history


def build_history_context(history: List[Dict]) -> str:
    """
    Build a compact text block listing recent questions so the API knows
    what to avoid.  Only the most recent HISTORY_CONTEXT_DAYS days are used.
    """
    if not history:
        return "No previous questions exist. This is Day 1."

    recent = sorted(history, key=lambda h: h.get("date", ""), reverse=True)[:HISTORY_CONTEXT_DAYS]

    lines = [
        f"The following {len(recent)} day(s) of questions have already been asked.",
        "DO NOT repeat any of these questions. Topics may repeat but phrasing/content must differ.\n"
    ]
    for day in recent:
        lines.append(f"--- {day['date']} (Level {day.get('level', '?')}/10) ---")
        for q in day.get("questions", []):
            lines.append(f"  [Section {q['section_id']}] {q['question']}")
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  DIFFICULTY LEVEL
# ══════════════════════════════════════════════════════════════════════════════

def get_difficulty_level(base_date=None) -> Tuple[int, str]:
    """
    Calculate difficulty level based on 5-day cycle (levels 1–5 repeating).
    Returns: (level_number, level_description)
    """
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
        5: "ADVANCED - Complex designs, optimization problems, trade-off analysis.",
        6: "EXPERT - Pipeline design, verification strategies, tool-specific deep dives.",
        7: "ARCHITECT - System-level design, multi-domain problems, performance analysis.",
        8: "SENIOR ARCHITECT - Cutting-edge techniques, protocol intricacies, advanced optimizations.",
        9: "PRINCIPAL ENGINEER - Research-level problems, novel solutions, cross-domain integration.",
        10: "FELLOW/CTO - Speculative designs, industry future directions, extreme complexity."
    }

    return level, level_descriptions[level]


# ══════════════════════════════════════════════════════════════════════════════
#  PROMPT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_prompt(level: int, level_desc: str, sections: List[Dict], history: List[Dict]) -> str:
    """Build the prompt for DeepSeek API to generate fresh questions."""

    sections_text = "\n".join([f"{s['id']}. {s['name']}" for s in sections])
    history_context = build_history_context(history)

    prompt = f"""You are an expert VLSI interview coach generating a DAILY MOCK TEST.

═══════════════════════════════════════
PREVIOUS QUESTIONS (DO NOT REPEAT)
═══════════════════════════════════════
{history_context}

═══════════════════════════════════════
TODAY'S REQUIREMENTS
═══════════════════════════════════════
- Generate exactly {len(sections)} questions (one per section)
- Difficulty Level: {level}/10 - {level_desc}
- Questions must be UNIQUE — different wording and content from ALL previous days above
- Topics may recur (e.g. "flip-flop") but the specific question must be new
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

Generate {len(sections)} fresh, challenging questions at level {level}/10.
Return ONLY valid JSON, no other text."""

    return prompt


# ══════════════════════════════════════════════════════════════════════════════
#  API CALL
# ══════════════════════════════════════════════════════════════════════════════

def call_deepseek_api(prompt: str, api_key: str) -> Dict:
    """Call DeepSeek API and return parsed JSON response."""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a VLSI interview expert. Generate unique, high-quality interview questions. "
                    "Always respond with valid JSON only. Never repeat questions that appear in the prompt's history."
                )
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

    questions_data = json.loads(content)
    return questions_data


# ══════════════════════════════════════════════════════════════════════════════
#  FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

def generate_fallback_questions(level: int, history: List[Dict]) -> Dict:
    """Fallback question generator if API fails. Tries to avoid history."""

    fallback_pools = {
        1: [
            "Explain the difference between synchronous and asynchronous reset.",
            "Write Verilog code for a D flip-flop with active-low reset.",
            "What is the difference between $display and $monitor in Verilog?",
            "Explain the difference between directed and constrained-random testing.",
            "Define setup time and hold time in digital design.",
            "What is metastability and how do synchronizers mitigate it?",
            "What is clock gating and why is it used in low-power designs?",
            "List the basic signals of the AHB-Lite protocol.",
            "Draw and explain a 5-stage pipeline diagram.",
            "Write a Python function to read a file and count lines.",
            "How do you debug a simulation that shows 'X' propagation on a signal?",
            "Design a divide-by-2 clock divider using a D flip-flop.",
            "Tell me about a project you worked on and the challenges you faced.",
        ],
        3: [
            "Implement a parameterized shift register in SystemVerilog.",
            "Explain the difference between fork-join and fork-join_any in SV.",
            "What is an assertion? Write a simple SVA for a handshake protocol.",
            "Describe the stages of logic synthesis.",
            "What is a false path? Give a real-world example.",
            "Explain two-flop synchronizer design for single-bit CDC.",
            "What is power domain? How does UPF define isolation cells?",
            "Compare SRAM and DRAM architectures.",
            "Explain branch prediction in a 5-stage pipeline.",
            "Write a Tcl script to loop over a list and print each item.",
            "How would you isolate a failing assertion to find the root cause?",
            "Design a Moore FSM to detect the sequence '101'.",
            "What is the STAR method for answering behavioral interview questions?",
        ],
        5: [
            "Design a 4-bit carry lookahead adder and derive the equations.",
            "Write SystemVerilog code for a parameterized FIFO with full/empty flags.",
            "Implement a UVM testbench with a scoreboard and functional coverage.",
            "Explain false path and multicycle path with timing diagram examples.",
            "Design a gray-code based CDC synchronizer for a multi-bit counter.",
            "Explain power gating using UPF retention flip-flops.",
            "Describe AXI4 protocol channels and handshaking mechanism.",
            "Design a 5-stage pipeline with hazard detection and forwarding.",
            "Write a Python script to parse a synthesis report and flag violations.",
            "Debug a setup time violation: given a critical path report, propose fixes.",
            "Design a sequence detector FSM for '1101' with overlapping detection.",
            "Explain out-of-order transaction checking in a scoreboard.",
            "Describe your approach to verifying a DMA controller end-to-end.",
        ],
    }

    # Collect all previously asked questions for dedup
    past_questions = set()
    for day in history:
        for q in day.get("questions", []):
            past_questions.add(q["question"].lower().strip())

    # Pick closest pool
    available = sorted(fallback_pools.keys())
    closest = min(available, key=lambda x: abs(x - level))
    pool = fallback_pools[closest]

    questions = []
    pool_idx = 0
    for section in SECTIONS:
        # Try to find one not in history
        chosen = None
        for _ in range(len(pool)):
            candidate = pool[pool_idx % len(pool)]
            pool_idx += 1
            if candidate.lower().strip() not in past_questions:
                chosen = candidate
                break
        if chosen is None:
            chosen = pool[pool_idx % len(pool)]
            pool_idx += 1

        questions.append({"section_id": section["id"], "question": f"[Fallback L{closest}] {chosen}"})

    return {"questions": questions}


# ══════════════════════════════════════════════════════════════════════════════
#  EMAIL HTML GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def generate_email_html(questions: List[Dict], level: int, level_desc: str,
                        date_str: str, history_count: int) -> str:
    """Generate professional HTML email content."""

    section_map = {s["id"]: s["name"] for s in SECTIONS}

    next_level = (level % 5) + 1
    next_desc_map = {
        1: "Fundamental", 2: "Basic", 3: "Intermediate",
        4: "Upper Intermediate", 5: "Advanced"
    }
    next_desc = next_desc_map.get(next_level, "Next Level")

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
        }}
        .section-title {{
            font-weight: bold;
            color: #1a1a2e;
            margin-bottom: 10px;
            font-size: 16px;
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
        .history-badge {{
            background: #6c5ce7;
            color: white;
            display: inline-block;
            padding: 4px 14px;
            border-radius: 20px;
            font-size: 12px;
            margin-top: 8px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎯 AI-Generated VLSI Mock Test</h1>
        <div class="level-badge">Difficulty: Level {level}/10</div>
        <div class="level-desc">{level_desc}</div>
        <p style="margin-top: 15px;">📅 {date_str}</p>
        <span class="ai-badge">✨ Freshly generated by DeepSeek AI ✨</span><br>
        <span class="history-badge">📚 Unique across {history_count} previous day(s)</span>
    </div>

    <div class="timer">
        ⏱️ Recommended Time: 90 minutes (7-8 minutes per question)
    </div>

    <p><strong>📋 Instructions:</strong></p>
    <ul>
        <li>Answer all <strong>13 questions</strong> (one from each domain)</li>
        <li>Questions are unique — AI checks history before generating</li>
        <li>Tomorrow's difficulty will be <strong>Level {next_level}/10 – {next_desc}</strong></li>
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
        <p>🚀 <strong>Daily practice with fresh questions is the fastest way to master VLSI interviews.</strong></p>
        <p>📈 Tomorrow: Level {next_level}/10 — {next_desc} Level</p>
        <p>🤖 Questions generated uniquely for today by DeepSeek AI (history-aware)</p>
        <p>❄️ Keep grinding — Your future VLSI engineer self will thank you!</p>
    </div>
</body>
</html>
"""

    return html


# ══════════════════════════════════════════════════════════════════════════════
#  EMAIL SENDER
# ══════════════════════════════════════════════════════════════════════════════

def send_email(to_email: str, subject: str, html_content: str, smtp_config: Dict) -> None:
    """Send email using SMTP."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = smtp_config['from_email']
    msg['To']      = to_email

    msg.attach(MIMEText(html_content, 'html'))

    with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port']) as server:
        server.starttls()
        server.login(smtp_config['from_email'], smtp_config['password'])
        server.sendmail(smtp_config['from_email'], [to_email], msg.as_string())

    print(f"✅ Email sent to {to_email} at {datetime.now(IST)}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='Generate and send daily VLSI mock test using DeepSeek AI'
    )
    parser.add_argument('--to',          help='Recipient email address',
                        default=os.environ.get('EMAIL_TO'))
    parser.add_argument('--dry-run',     action='store_true',
                        help="Generate questions but don't send email")
    parser.add_argument('--show-prompt', action='store_true',
                        help='Show the prompt sent to DeepSeek')
    parser.add_argument('--show-history', action='store_true',
                        help='Print question history summary and exit')
    parser.add_argument('--history-file', default=None,
                        help='Override path to history JSON file')
    args = parser.parse_args()

    # Allow CLI override of history file path
    global HISTORY_FILE
    if args.history_file:
        HISTORY_FILE = args.history_file

    # ── Show history and exit ───────────────────────────────────────────────
    if args.show_history:
        history = load_history()
        print(f"\n📚 Question History  ({HISTORY_FILE})")
        print(f"   Total days stored: {len(history)}\n")
        for day in history[:10]:
            print(f"  {day['date']}  Level {day.get('level', '?')}/10  "
                  f"({len(day.get('questions', []))} questions)")
        if len(history) > 10:
            print(f"  ... and {len(history) - 10} more days")
        return 0

    # ── Validate DeepSeek API key ───────────────────────────────────────────
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("❌ Error: DEEPSEEK_API_KEY environment variable not set")
        print("   Get your API key from: https://platform.deepseek.com/")
        return 1

    # ── SMTP configuration ──────────────────────────────────────────────────
    smtp_port_raw = os.environ.get('SMTP_PORT', '587')
    try:
        smtp_port = int(smtp_port_raw) if smtp_port_raw and smtp_port_raw.strip() else 587
    except ValueError:
        print(f"⚠️  Invalid SMTP_PORT '{smtp_port_raw}', using default 587")
        smtp_port = 587

    smtp_config = {
        'smtp_server': os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port':   smtp_port,
        'from_email':  os.environ.get('EMAIL_FROM'),
        'password':    os.environ.get('EMAIL_PASSWORD'),
    }
    to_email = args.to or os.environ.get('EMAIL_TO')

    if not args.dry_run:
        missing = [k for k in ('EMAIL_FROM', 'EMAIL_PASSWORD', 'EMAIL_TO')
                   if not os.environ.get(k) and k != 'EMAIL_TO']
        if not to_email:
            missing.append('EMAIL_TO')
        if missing:
            print(f"❌ Error: Missing required env vars: {', '.join(missing)}")
            print("   Use --dry-run for testing without email")
            return 1

    # ── Load history ────────────────────────────────────────────────────────
    history = load_history()
    print(f"📚 Loaded history: {len(history)} previous day(s) of questions")

    # ── Determine difficulty level ──────────────────────────────────────────
    level, level_desc = get_difficulty_level()
    date_str = datetime.now(IST).strftime("%A, %B %d, %Y - %I:%M %p IST")

    print(f"🎯 Generating Mock Test")
    print(f"   Date:  {date_str}")
    print(f"   Level: {level}/10")

    # ── Build prompt (with history) ─────────────────────────────────────────
    prompt = build_prompt(level, level_desc, SECTIONS, history)

    if args.show_prompt:
        print("\n" + "=" * 70)
        print("PROMPT SENT TO DEEPSEEK:")
        print("=" * 70)
        print(prompt)
        print("=" * 70 + "\n")

    # ── Call DeepSeek API ───────────────────────────────────────────────────
    try:
        print("🔄 Calling DeepSeek API...")
        questions_data = call_deepseek_api(prompt, api_key)
        questions = questions_data.get('questions', [])
        print(f"✅ Generated {len(questions)} fresh questions from DeepSeek")
    except Exception as e:
        print(f"❌ DeepSeek API failed: {e}")
        print("🔄 Using fallback question generator...")
        questions_data = generate_fallback_questions(level, history)
        questions = questions_data.get('questions', [])
        print(f"✅ Generated {len(questions)} fallback questions")

    # Pad to exactly 13 if needed
    while len(questions) < len(SECTIONS):
        idx = len(questions) + 1
        questions.append({
            "section_id": idx,
            "question": "Explain a VLSI concept you're most confident about and give a design example."
        })

    # ── Save questions to history ───────────────────────────────────────────
    history = append_to_history(history, questions, level)
    save_history(history)

    # ── Generate email content ──────────────────────────────────────────────
    subject = (f"🎯 VLSI Mock Test – Level {level}/10 – "
               f"{datetime.now(IST).strftime('%d %b %Y')} (AI-Generated)")
    html_content = generate_email_html(questions, level, level_desc, date_str, len(history))

    # ── Dry run preview ─────────────────────────────────────────────────────
    if args.dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN – Email content preview")
        print("=" * 60)
        print(f"To:      {to_email or 'Not set'}")
        print(f"Subject: {subject}")
        print("\n--- Questions Preview (first 5) ---")
        for q in questions[:5]:
            print(f"\n  [{q['section_id']}] {q['question'][:120]}...")
        if len(questions) > 5:
            print(f"\n  ... and {len(questions) - 5} more questions")
        print(f"\nHistory file: {HISTORY_FILE}")
        print("=" * 60)
        return 0

    # ── Send email ──────────────────────────────────────────────────────────
    send_email(to_email, subject, html_content, smtp_config)
    print(f"\n✨ Mock test sent successfully at {datetime.now(IST)}")
    print(f"   Level:     {level}/10")
    print(f"   Questions: {len(questions)}")
    print(f"   History:   {len(history)} day(s) stored in {HISTORY_FILE}")

    return 0


if __name__ == "__main__":
    exit(main())
