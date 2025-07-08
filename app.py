# -*- coding: utf-8 -*-
import pandas as pd
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_mail import Mail, Message  # Added for email sending
from sentence_transformers import SentenceTransformer, util
import re
from collections import Counter
import language_tool_python
import time
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import os
from dotenv import load_dotenv  # Added for loading .env

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configure session secret key (required for session management)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')  # Fallback if not set in .env

# Configure Flask-Mail for sending emails
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT'))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

# Initialize Flask-Mail
mail = Mail(app)

# Make sessions non-permanent to enforce login on every run
app.config['SESSION_PERMANENT'] = False


# Initialize database
def init_db():
    conn = sqlite3.connect('chatbot.db')
    c = conn.cursor()
    # Create users table
    c.execute('''
              CREATE TABLE IF NOT EXISTS users
              (
                  email
                  TEXT
                  PRIMARY
                  KEY,
                  password_hash
                  TEXT
                  NOT
                  NULL
              )
              ''')
    # Create password_resets table
    c.execute('''
              CREATE TABLE IF NOT EXISTS password_resets
              (
                  email
                  TEXT
                  NOT
                  NULL,
                  token
                  TEXT
                  PRIMARY
                  KEY,
                  expires_at
                  INTEGER
                  NOT
                  NULL,
                  FOREIGN
                  KEY
              (
                  email
              ) REFERENCES users
              (
                  email
              )
                  )
              ''')
    # Insert default user if not exists
    email = 'harshjaiswal91985@gmail.com'  # Updated as per your change
    password = 'sale@reachivy.team'
    password_hash = generate_password_hash(password)
    c.execute('INSERT OR IGNORE INTO users (email, password_hash) VALUES (?, ?)', (email, password_hash))
    conn.commit()
    conn.close()


# Initialize LanguageTool using local server
try:
    tool = language_tool_python.LanguageTool('en-US', remote_server='http://localhost:8081')
except Exception as e:
    app.logger.error(f"LanguageTool initialization failed: {e}. Grammar checks will be skipped.")
    tool = None

# Load dataset
try:
    df = pd.read_csv('data/questions.csv', encoding='cp1252')
    print("CSV Columns:", df.columns.tolist())
    required_columns = ['section', 'question_number', 'question', 'correct_answer', 'keywords']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns in CSV: {missing_columns}")
except Exception as e:
    app.logger.error(f"Failed to load questions.csv: {str(e)}")
    raise

# Define sections with topics
sections = {
    1: {'name': 'Generic', 'questions': list(range(1, 9))},
    2: {'name': 'Team', 'questions': list(range(9, 18))},
    3: {'name': 'Study Abroad - Counseling', 'questions': list(range(18, 32))},
    4: {'name': 'Study Abroad - Application', 'questions': list(range(32, 55))},
    5: {'name': 'Interview Prep', 'questions': list(range(55, 65))},
    6: {'name': 'Technical', 'questions': list(range(65, 67))},
    7: {'name': 'Pricing', 'questions': list(range(67, 76))},
    8: {'name': 'Hubspot', 'questions': list(range(76, 88))},
    9: {'name': 'College Deadlines', 'questions': list(range(88, 95))},
    10: {'name': 'Hook Points', 'questions': list(range(95, 110))},
    11: {'name': 'Lead Classification', 'questions': list(range(110, 125))},
    12: {'name': 'Deferred MBA', 'questions': list(range(125, 140))},
    13: {'name': 'Important to Know', 'questions': list(range(140, 205))},
    14: {'name': 'International Payment & Remittance', 'questions': list(range(205, 210))},
    15: {'name': 'Payment Policy & GST', 'questions': list(range(210, 221))},
    16: {'name': 'Add Pricing & Services Through CRM', 'questions': list(range(221, 234))}
}

# Load sentence transformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Precompute embeddings for all correct answers
correct_answer_embeddings = {}
start_precompute = time.time()
for _, row in df.iterrows():
    question_num = row['question_number']
    correct_answer = row['correct_answer']
    embedding = model.encode(correct_answer)
    correct_answer_embeddings[question_num] = embedding
app.logger.info(f"Precomputing correct answer embeddings took {time.time() - start_precompute:.2f} seconds")

# Store user progress
user_progress = {}

# Prepare questions data for each section
section_questions = {}
for section, info in sections.items():
    section_questions[section] = []
    section_start_question = info['questions'][0]
    for q_num in info['questions']:
        question_row = df[df['question_number'] == q_num].iloc[0]
        display_question_number = q_num - section_start_question + 1
        section_questions[section].append({
            'question_number': q_num,
            'display_question_number': display_question_number,
            'question': question_row['question']
        })


def evaluate_answer(user_answer, question_num):
    start_time = time.time()

    # Compute semantic similarity using SentenceTransformer
    start_semantic = time.time()
    user_embedding = model.encode(user_answer)
    correct_embedding = correct_answer_embeddings[question_num]
    semantic_similarity = util.cos_sim(user_embedding, correct_embedding).item() * 100
    app.logger.info(f"Semantic similarity computation took {time.time() - start_semantic:.2f} seconds")

    # Compute content accuracy (penalizes missing keywords)
    start_content = time.time()
    correct_answer = df[df['question_number'] == question_num].iloc[0]['correct_answer']
    content_accuracy = generate_content_accuracy_feedback(user_answer, question_num)
    content_accuracy_score = content_accuracy["score"]
    app.logger.info(f"Content accuracy computation took {time.time() - start_content:.2f} seconds")

    # Compute clarity and language scores (penalizes vagueness and language issues)
    start_clarity = time.time()
    clarity_feedback = evaluate_clarity(user_answer)
    app.logger.info(f"Clarity evaluation took {time.time() - start_clarity:.2f} seconds")

    start_language = time.time()
    language_feedback = evaluate_language(user_answer)
    app.logger.info(f"Language evaluation took {time.time() - start_language:.2f} seconds")

    clarity_score = clarity_feedback["score"]
    language_score = language_feedback["score"]

    # Combine scores
    start_combine = time.time()
    base_match_percentage = (semantic_similarity + content_accuracy_score) / 2

    # Apply penalties based on clarity and language
    clarity_penalty = max(0, (70 - clarity_score) * 0.3)  # Max penalty of 30% if clarity is 0
    language_penalty = max(0, (70 - language_score) * 0.3)  # Max penalty of 30% if language is 0
    final_match_percentage = base_match_percentage - clarity_penalty - language_penalty

    # Apply scoring matrix
    final_match_percentage = max(0, min(100, round(final_match_percentage)))
    if final_match_percentage >= 70:
        score = 100
    elif 65 <= final_match_percentage < 70:
        score = 90
    elif 60 <= final_match_percentage < 65:
        score = 80
    elif 55 <= final_match_percentage < 60:
        score = 70
    elif 50 <= final_match_percentage < 55:
        score = 60
    elif 45 <= final_match_percentage < 50:
        score = 50
    else:
        score = final_match_percentage
    app.logger.info(f"Score combination took {time.time() - start_combine:.2f} seconds")

    app.logger.info(f"Total evaluate_answer took {time.time() - start_time:.2f} seconds")
    return score


def normalize_text(text):
    text = re.sub(r'[^\w\s]', '', text)
    text = text.lower()
    return text


def keyword_present(keyword, user_answer):
    keyword = normalize_text(keyword.strip())
    user_answer = normalize_text(user_answer)
    # Check if the keyword (or its significant words) is present in the user answer
    keyword_words = set(keyword.split())
    user_answer_words = set(user_answer.split())
    if not keyword_words:
        return True
    overlap = len(keyword_words.intersection(user_answer_words))
    overlap_ratio = overlap / len(keyword_words)
    return overlap_ratio >= 0.7  # Consider the keyword present if 70% of its words are found


def generate_content_accuracy_feedback(user_answer, question_num):
    # Fetch the keywords for the question
    question_row = df[df['question_number'] == question_num].iloc[0]
    keywords_str = question_row['keywords']
    if not keywords_str or pd.isna(keywords_str):
        return {"score": 100,
                "comment": "Content Accuracy: Excellent - No keywords to evaluate, but your response aligns well."}

    # Split keywords by '|' and clean them
    keywords = [keyword.strip() for keyword in keywords_str.split('|') if keyword.strip()]
    if not keywords:
        return {"score": 100,
                "comment": "Content Accuracy: Excellent - No keywords to evaluate, but your response aligns well."}

    # Check which keywords are present in the user's answer
    present_keywords = [keyword for keyword in keywords if keyword_present(keyword, user_answer)]
    missing_keywords = [keyword for keyword in keywords if keyword not in present_keywords]

    # Calculate accuracy score based on the percentage of keywords present
    total_keywords = len(keywords)
    present_count = len(present_keywords)
    accuracy_score = (present_count / total_keywords) * 100 if total_keywords > 0 else 100

    # Generate feedback based on the score
    if accuracy_score >= 90:
        comment = "Content Accuracy: Excellent - Your response captures almost all key keywords."
    elif accuracy_score >= 70:
        comment = "Content Accuracy: Good - You included most of the key keywords, but some are missing."
    elif accuracy_score >= 50:
        comment = "Content Accuracy: Fair - You captured some key keywords, but several are missing."
    else:
        comment = "Content Accuracy: Needs Improvement - Many key keywords are missing from your response."

    # Append missing keywords to the comment if any
    if missing_keywords:
        comment += "\nMissing keywords: " + ", ".join([f"'{keyword}'" for keyword in missing_keywords])

    return {"score": accuracy_score, "comment": comment}


def evaluate_clarity(user_answer):
    sentences = re.split(r'[.!?]+', user_answer)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return {"score": 0, "details": "No valid sentences found in your response."}
    sentence_lengths = [len(s.split()) for s in sentences]
    avg_sentence_length = sum(sentence_lengths) / len(sentence_lengths)
    vague_words = {'stuff', 'things', 'maybe', 'something', 'somehow', 'whatever'}
    words = normalize_text(user_answer).split()
    vague_word_count = sum(1 for word in words if word in vague_words)
    vague_word_ratio = vague_word_count / len(words) if words else 0
    clarity_score = 100
    detailed_feedback = []
    if avg_sentence_length < 10:
        clarity_score -= 20
        detailed_feedback.append(
            "Your sentences are too short, which may make your response feel abrupt or incomplete.")
    elif avg_sentence_length > 20:
        clarity_score -= 20
        detailed_feedback.append("Your sentences are too long, which may make your response hard to follow.")
    if vague_word_ratio > 0.1:
        clarity_score -= 30
        detailed_feedback.append("Your response contains vague words (e.g., 'stuff', 'things'), which reduces clarity.")
    clarity_score = max(0, clarity_score)
    if clarity_score >= 90:
        comment = "Clarity: Excellent - Your response is clear and easy to understand."
    elif clarity_score >= 70:
        comment = "Clarity: Good - Your response is mostly clear, but could be improved."
    elif clarity_score >= 50:
        comment = "Clarity: Fair - Your response has some clarity issues that need attention."
    else:
        comment = "Clarity: Needs Improvement - Your response is unclear and hard to follow."
    detailed_feedback = "\n".join(detailed_feedback) if detailed_feedback else "No specific clarity issues identified."
    return {"score": clarity_score, "comment": comment, "details": detailed_feedback}


def evaluate_language(user_answer):
    start_time = time.time()
    words = normalize_text(user_answer).split()
    if not words:
        return {"score": 0, "details": "No words found in your response."}

    # Repeated words check
    start_repeated = time.time()
    word_counts = Counter(words)
    repeated_words = {word: count for word, count in word_counts.items() if count > 2}
    repetition_ratio = sum(count for count in repeated_words.values()) / len(words) if words else 0
    app.logger.info(f"Repeated words check took {time.time() - start_repeated:.2f} seconds")

    # Complex words check
    start_complex = time.time()
    complex_words = [word for word in words if len(word) > 12]
    complex_word_ratio = len(complex_words) / len(words) if words else 0
    app.logger.info(f"Complex words check took {time.time() - start_complex:.2f} seconds")

    language_score = 100
    detailed_feedback = []

    # Check for repeated words
    if repetition_ratio > 0.2:
        language_score -= 30
        detailed_feedback.append(
            f"Your response has repeated words (e.g., {list(repeated_words.keys())[:2]}), which suggests limited vocabulary.")

    # Check for very long words
    if complex_word_ratio > 0.1:
        language_score -= 20
        detailed_feedback.append("Your response contains very long words, which may make it harder to understand.")

    # Check for grammatical errors using LanguageTool, with fallback
    grammar_issues = []
    if tool:
        start_grammar = time.time()
        try:
            matches = tool.check(user_answer)
            # Log the first match's attributes for debugging
            if matches:
                app.logger.debug(f"LanguageTool match attributes: {dir(matches[0])}")
                app.logger.debug(f"First match: {matches[0].__dict__}")
            for match in matches:
                # Use category to filter grammar and spelling issues
                category = getattr(match, 'category', '').upper()
                if category in ['GRAMMAR', 'SPELLING', 'TYPOS']:
                    grammar_issues.append(match)
        except Exception as e:
            app.logger.error(f"LanguageTool check failed: {e}. Skipping grammar check.")
            detailed_feedback.append("Grammar check unavailable due to a server error.")
        app.logger.info(f"Grammar check took {time.time() - start_grammar:.2f} seconds")

    # Deduct 10 points per grammar issue, up to a maximum deduction of 40 points for grammar
    grammar_deduction = min(len(grammar_issues) * 10, 40)
    language_score -= grammar_deduction

    # Add grammar issues to feedback
    for issue in grammar_issues:
        context = issue.context
        error_text = context[issue.offsetInContext:issue.offsetInContext + issue.errorLength]
        suggestion = issue.replacements[0] if issue.replacements else "no suggestion available"
        detailed_feedback.append(
            f"Grammar issue: '{error_text}' in '{context}'. Suggestion: '{suggestion}' ({issue.message})"
        )

    language_score = max(0, language_score)
    if language_score >= 90:
        comment = "Language: Excellent - Your language use is precise and effective."
    elif language_score >= 70:
        comment = "Language: Good - Your language is generally effective, but could be improved."
    elif language_score >= 50:
        comment = "Language: Fair - Your language use has some issues that need attention."
    else:
        comment = "Language: Needs Improvement - Your language use needs significant improvement."
    detailed_feedback = "\n".join(detailed_feedback) if detailed_feedback else "No specific language issues identified."
    app.logger.info(f"Total evaluate_language took {time.time() - start_time:.2f} seconds")
    return {"score": language_score, "comment": comment, "details": detailed_feedback}


def evaluate_tone_and_confidence(tone_score, confidence_score, tone_details, confidence_details):
    return {
        "tone_feedback": f"Tone: {tone_score}%",
        "confidence_feedback": f"Confidence: {confidence_score}%",
        "tone_details": tone_details,
        "confidence_details": confidence_details
    }


def generate_detailed_feedback(user_answer, correct_answer, score):
    start_time = time.time()
    # Use question_num to fetch keywords in generate_content_accuracy_feedback
    question_num = df[df['correct_answer'] == correct_answer].iloc[0]['question_number']
    content_accuracy = generate_content_accuracy_feedback(user_answer, question_num)
    clarity_feedback = evaluate_clarity(user_answer)
    language_feedback = evaluate_language(user_answer)
    detailed_feedback = ""
    if score < 70:
        # Since content_accuracy feedback now includes missing keywords, we can simplify this
        detailed_feedback = "Review the missing keywords listed in the Content Accuracy feedback to improve your response."
    app.logger.info(f"Generate detailed feedback took {time.time() - start_time:.2f} seconds")
    return {
        "content_accuracy": content_accuracy["comment"],
        "detailed_feedback": detailed_feedback,
        "clarity_feedback": clarity_feedback["comment"],
        "clarity_details": clarity_feedback["details"],
        "language_feedback": language_feedback["comment"],
        "language_details": language_feedback["details"],
        "score_points": score
    }


# Middleware to check if user is authenticated
def login_required(f):
    def wrap(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    wrap.__name__ = f.__name__
    return wrap


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # Validate credentials against database
        conn = sqlite3.connect('chatbot.db')
        c = conn.cursor()
        c.execute('SELECT password_hash FROM users WHERE email = ?', (email,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[0], password):
            session['logged_in'] = True
            session.permanent = False  # Session expires when browser closes
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid email or password.')

    return render_template('login.html')


@app.route('/logout', methods=['GET'])
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        # Check if email exists
        conn = sqlite3.connect('chatbot.db')
        c = conn.cursor()
        c.execute('SELECT email FROM users WHERE email = ?', (email,))
        user = c.fetchone()

        if user:
            # Generate a reset token
            token = secrets.token_urlsafe(32)
            expires_at = int(time.time()) + 3600  # Token expires in 1 hour
            c.execute('INSERT INTO password_resets (email, token, expires_at) VALUES (?, ?, ?)',
                      (email, token, expires_at))
            conn.commit()

            # Send password reset email
            reset_link = url_for('reset_password', token=token, _external=True)
            msg = Message('Password Reset Request',
                          recipients=[email],
                          body=f'Click the following link to reset your password: {reset_link}\nThis link will expire in 1 hour.')
            try:
                mail.send(msg)
                conn.close()
                return render_template('forgot_password.html',
                                       message='A password reset link has been sent to your email.')
            except Exception as e:
                conn.close()
                app.logger.error(f"Failed to send email: {str(e)}")
                return render_template('forgot_password.html', error='Failed to send email. Please try again later.')
        else:
            conn.close()
            return render_template('forgot_password.html', error='Email not found.')

    return render_template('forgot_password.html')


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token')

    if not token:
        return redirect(url_for('login'))

    # Validate token
    conn = sqlite3.connect('chatbot.db')
    c = conn.cursor()
    current_time = int(time.time())
    c.execute('SELECT email, expires_at FROM password_resets WHERE token = ?', (token,))
    reset_request = c.fetchone()

    if not reset_request or reset_request[1] < current_time:
        conn.close()
        return render_template('reset_password.html', error='Invalid or expired token.')

    email = reset_request[0]

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            return render_template('reset_password.html', token=token, error='Passwords do not match.')

        # Update password
        password_hash = generate_password_hash(new_password)
        c.execute('UPDATE users SET password_hash = ? WHERE email = ?', (password_hash, email))
        # Delete the used token
        c.execute('DELETE FROM password_resets WHERE token = ?', (token,))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))

    conn.close()
    return render_template('reset_password.html', token=token)


@app.route('/')
@login_required
def index():
    return render_template('index.html', sections=sections, section_questions=section_questions)


@app.route('/start_assessment', methods=['POST'])
@login_required
def start_assessment():
    user_id = request.json.get('user_id', 'default_user')
    requested_section = request.json.get('section')
    if user_id not in user_progress:
        user_progress[user_id] = {
            'current_section': 1,
            'section_scores': {},
            'current_questions': [],
            'current_index': 0,
            'scores': [],
            'answered_question_numbers': []
        }
    if requested_section is not None:
        requested_section = int(requested_section)
        if requested_section in sections:
            user_progress[user_id]['current_section'] = requested_section
            user_progress[user_id]['current_questions'] = []
            user_progress[user_id]['current_index'] = 0
            user_progress[user_id]['scores'] = []
            user_progress[user_id]['answered_question_numbers'] = []
        else:
            app.logger.error(f"Invalid section requested: {requested_section}")
            return jsonify({'error': f"Invalid section: {requested_section}"}), 400
    section = user_progress[user_id]['current_section']
    app.logger.info(f"Starting assessment for user {user_id}, current_section: {section}")
    expected_questions = sections[section]['questions']
    if not user_progress[user_id]['current_questions']:
        user_progress[user_id]['current_questions'] = expected_questions.copy()
        user_progress[user_id]['current_index'] = 0
        app.logger.info(
            f"Initialized current_questions for section {section}: {user_progress[user_id]['current_questions']}")
    if user_progress[user_id]['current_questions'] != expected_questions:
        app.logger.warning(
            f"current_questions mismatch for section {section}. Expected: {expected_questions}, Got: {user_progress[user_id]['current_questions']}")
        user_progress[user_id]['current_questions'] = expected_questions.copy()
        user_progress[user_id]['current_index'] = 0
    if not user_progress[user_id]['current_questions']:
        return jsonify({'error': 'No questions available for this section'}), 500
    question_num = user_progress[user_id]['current_questions'][0]
    question_row = df[df['question_number'] == question_num].iloc[0]
    question_section = question_row['section']
    if question_section != section:
        app.logger.error(
            f"Question {question_num} is from section {question_section}, but user is in section {section}")
        return jsonify({'error': f"Question {question_num} does not belong to section {section}"}), 500
    total_questions = len(sections[section]['questions'])
    section_start_question = sections[section]['questions'][0]
    display_question_number = question_num - section_start_question + 1
    response = {
        'section': section,
        'section_name': sections[section]['name'],
        'question_number': question_num,
        'display_question_number': display_question_number,
        'question': question_row['question'],
        'answered': user_progress[user_id]['current_index'],
        'total_questions': total_questions
    }
    app.logger.info(f"Sending response for section {section}: {response}")
    return jsonify(response)


@app.route('/get_question', methods=['POST'])
@login_required
def get_question():
    user_id = request.json.get('user_id', 'default_user')
    question_num = int(request.json.get('question_number'))

    # Find the section for this question
    section = None
    for sec, info in sections.items():
        if question_num in info['questions']:
            section = sec
            break
    if section is None:
        app.logger.error(f"Question {question_num} does not belong to any section")
        return jsonify({'error': f"Question {question_num} does not belong to any section"}), 400

    # Ensure user_progress is initialized
    if user_id not in user_progress:
        user_progress[user_id] = {
            'current_section': section,
            'section_scores': {},
            'current_questions': [],
            'current_index': 0,
            'scores': [],
            'answered_question_numbers': []
        }

    # Update user_progress
    user_progress[user_id]['current_section'] = section
    expected_questions = sections[section]['questions']
    user_progress[user_id]['current_questions'] = expected_questions.copy()
    current_index = expected_questions.index(question_num)
    user_progress[user_id]['current_index'] = current_index

    # Fetch the question
    question_row = df[df['question_number'] == question_num].iloc[0]
    question_section = question_row['section']
    if question_section != section:
        app.logger.error(f"Question {question_num} is from section {question_section}, but expected section {section}")
        return jsonify({'error': f"Question {question_num} does not belong to section {section}"}), 500

    total_questions = len(sections[section]['questions'])
    section_start_question = sections[section]['questions'][0]
    display_question_number = question_num - section_start_question + 1
    response = {
        'section': section,
        'section_name': sections[section]['name'],
        'question_number': question_num,
        'display_question_number': display_question_number,
        'question': question_row['question'],
        'answered': user_progress[user_id]['current_index'],
        'total_questions': total_questions
    }
    app.logger.info(f"Sending response for question {question_num}: {response}")
    return jsonify(response)


@app.route('/submit_answer', methods=['POST'])
@login_required
def submit_answer():
    start_time = time.time()

    user_id = request.json.get('user_id', 'default_user')
    user_answer = request.json.get('answer')
    question_num = request.json.get('question_number')
    tone_score = int(request.json.get('tone_score', 50))
    confidence_score = int(request.json.get('confidence_score', 50))
    tone_details = request.json.get('tone_details', "No tone analysis available.")
    confidence_details = request.json.get('confidence_details', "No confidence analysis available.")
    response_time = int(request.json.get('response_time', 0))  # New field for response time

    # Fetch question and correct answer
    start_fetch = time.time()
    question_row = df[df['question_number'] == question_num].iloc[0]
    try:
        correct_answer = question_row['correct_answer']
    except KeyError as e:
        app.logger.error(f"KeyError: {str(e)} - Available columns: {question_row.index.tolist()}")
        return jsonify({'error': 'Internal server error: Missing correct_answer column'}), 500
    app.logger.info(f"Fetching question data took {time.time() - start_fetch:.2f} seconds")

    # Validate section
    start_validate = time.time()
    current_section = user_progress[user_id]['current_section']
    question_section = question_row['section']
    if question_section != current_section:
        app.logger.error(
            f"Submitted question {question_num} is from section {question_section}, but user is in section {current_section}")
        return jsonify({'error': f"Question {question_num} does not belong to section {current_section}"}), 500
    app.logger.info(f"Section validation took {time.time() - start_validate:.2f} seconds")

    # Evaluate answer
    score = evaluate_answer(user_answer, question_num)

    # Generate feedback
    start_feedback = time.time()
    feedback_data = generate_detailed_feedback(user_answer, correct_answer, score)
    app.logger.info(f"Feedback generation took {time.time() - start_feedback:.2f} seconds")

    # Evaluate tone and confidence
    start_tone_conf = time.time()
    tone_confidence_data = evaluate_tone_and_confidence(tone_score, confidence_score, tone_details, confidence_details)
    app.logger.info(f"Tone and confidence evaluation took {time.time() - start_tone_conf:.2f} seconds")

    # Update user progress
    start_progress = time.time()
    user_progress[user_id]['scores'].append(score)
    user_progress[user_id]['answered_question_numbers'].append(question_num)
    if user_progress[user_id]['current_questions'] and user_progress[user_id]['current_questions'][0] == question_num:
        user_progress[user_id]['current_questions'].pop(0)
        user_progress[user_id]['current_index'] += 1
    else:
        app.logger.error(
            f"Question {question_num} does not match expected next question in current_questions: {user_progress[user_id]['current_questions']}")
        user_progress[user_id]['current_questions'] = sections[current_section]['questions'].copy()[
                                                      user_progress[user_id]['current_index']:]
    app.logger.info(f"User progress update took {time.time() - start_progress:.2f} seconds")

    # Check if section is completed
    start_section_check = time.time()
    if not user_progress[user_id]['current_questions']:
        section_score = sum(user_progress[user_id]['scores']) / len(
            sections[user_progress[user_id]['current_section']]['questions'])
        user_progress[user_id]['section_scores'][user_progress[user_id]['current_section']] = section_score
        feedback = ""
        low_score_questions = [(q_num, score) for q_num, score in
                               zip(user_progress[user_id]['answered_question_numbers'],
                                   user_progress[user_id]['scores']) if score <= 60]
        # Prepare question scores for display
        question_scores = [
            {'question_number': q_num, 'score': score}
            for q_num, score in zip(user_progress[user_id]['answered_question_numbers'],
                                    user_progress[user_id]['scores'])
        ]
        if low_score_questions:
            feedback = "Feedback: Your responses for the following questions scored 60 points or less:\n"
            feedback += ", ".join([f"Question {q_num} ({score} points)" for q_num, score in low_score_questions])
            feedback += "\nConsider reviewing these topics to improve your answers."
        user_progress[user_id]['scores'] = []
        user_progress[user_id]['answered_question_numbers'] = []
        user_progress[user_id]['current_index'] = 0
        current_section = user_progress[user_id]['current_section']
        if section_score >= 75:
            user_progress[user_id]['current_section'] += 1
            if user_progress[user_id]['current_section'] > 16:
                app.logger.info(f"Assessment completed: {user_progress[user_id]['section_scores']}")
                app.logger.info(f"Total submit_answer took {time.time() - start_time:.2f} seconds")
                return jsonify({
                    'status': 'completed',
                    'scores': user_progress[user_id]['section_scores']
                })
        else:
            user_progress[user_id]['current_questions'] = sections[current_section]['questions'].copy()
        new_section = user_progress[user_id]['current_section']
        user_progress[user_id]['current_questions'] = sections[new_section]['questions'].copy()
        app.logger.info(
            f"After section {current_section} completion, reset current_questions for section {new_section}: {user_progress[user_id]['current_questions']}")
        app.logger.info(f"Total submit_answer took {time.time() - start_time:.2f} seconds")
        return jsonify({
            'status': 'section_completed',
            'section': user_progress[user_id]['current_section'],
            'section_name': sections[user_progress[user_id]['current_section']]['name'],
            'section_score': section_score,
            'feedback': feedback,
            'question_scores': question_scores  # Add question scores to the response
        })
    app.logger.info(f"Section completion check took {time.time() - start_section_check:.2f} seconds")

    # Prepare next question
    start_next_question = time.time()
    question_num = user_progress[user_id]['current_questions'][0]
    question_row = df[df['question_number'] == question_num].iloc[0]
    question_section = question_row['section']
    if question_section != user_progress[user_id]['current_section']:
        app.logger.error(
            f"Next question {question_num} is from section {question_section}, but user is in section {user_progress[user_id]['current_section']}")
        return jsonify({
            'error': f"Question {question_num} does not belong to section {user_progress[user_id]['current_section']}"}), 500
    total_questions = len(sections[user_progress[user_id]['current_section']]['questions'])
    answered = user_progress[user_id]['current_index']
    section_start_question = sections[user_progress[user_id]['current_section']]['questions'][0]
    display_question_number = question_num - section_start_question + 1
    response = {
        'section': user_progress[user_id]['current_section'],
        'section_name': sections[user_progress[user_id]['current_section']]['name'],
        'question_number': question_num,
        'display_question_number': display_question_number,
        'question': question_row['question'],
        'answered': answered,
        'total_questions': total_questions,
        'match_percentage': score,
        'score_points': score,
        'content_accuracy': feedback_data['content_accuracy'],
        'detailed_feedback': feedback_data['detailed_feedback'],
        'clarity_feedback': feedback_data['clarity_feedback'],
        'clarity_details': feedback_data['clarity_details'],
        'language_feedback': feedback_data['language_feedback'],
        'language_details': feedback_data['language_details'],
        'tone_feedback': tone_confidence_data['tone_feedback'],
        'confidence_feedback': tone_confidence_data['confidence_feedback'],
        'tone_details': tone_confidence_data['tone_details'],
        'confidence_details': tone_confidence_data['confidence_details'],
        'response_time': response_time  # Include response time in the response
    }
    app.logger.info(f"Preparing next question took {time.time() - start_next_question:.2f} seconds")

    app.logger.info(f"Moving to next question: {question_num}, display number: {display_question_number}")
    app.logger.info(f"Feedback data being sent: {feedback_data}")
    app.logger.info(f"Tone and Confidence data being sent: {tone_confidence_data}")
    app.logger.info(f"Full response being sent: {response}")
    app.logger.info(f"Total submit_answer took {time.time() - start_time:.2f} seconds")
    return jsonify(response)


if __name__ == '__main__':
    init_db()  # Initialize database on app start
    try:
        app.run(debug=True)
    finally:
        if tool:
            tool.close()