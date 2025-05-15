import streamlit as st
import json
import random
from pathlib import Path
import pandas as pd
import glob
import time
from datetime import datetime, timedelta
import uuid
import os
import sqlite3
from contextlib import contextmanager
# Add these imports at the top
import hashlib
import os

# Set page configuration
st.set_page_config(
    page_title="Quiz App",
    page_icon="📝",
    layout="centered"
)

###################
# Database Operations
###################

@contextmanager
def get_db_connection():
    """Create a database connection."""
    db_path = Path("quiz.db")
    conn = sqlite3.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()



# Replace the register_user function
def register_user(username, password):
    """Register a new user in the database with hashed password."""
    try:
        # Generate a random salt
        salt = os.urandom(32)
        # Hash the password with the salt
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            100000
        )
        # Store both salt and password hash
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO users (username, password, salt)
            VALUES (?, ?, ?)
            ''', (username, password_hash.hex(), salt.hex()))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        # Username already exists
        return False

# Replace the authenticate_user function
def authenticate_user(username, password):
    """Authenticate a user against the database using hashed password."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT password, salt FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if user:
            stored_password, salt = user
            # Hash the provided password with the stored salt
            password_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                bytes.fromhex(salt),
                100000
            ).hex()
            # Compare the hashed password with the stored hash
            return password_hash == stored_password
        return False

# Update the init_db function to add salt column
def init_db():
    """Initialize the database with required tables."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Create user_scores table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            quiz_name TEXT NOT NULL,
            score REAL NOT NULL,
            time_taken REAL NOT NULL,
            total_quizzes INTEGER NOT NULL,
            average_score REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create quiz_sessions table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_sessions (
            session_id TEXT PRIMARY KEY,
            user_name TEXT NOT NULL,
            quiz_name TEXT NOT NULL,
            questions TEXT NOT NULL,
            user_answers TEXT NOT NULL,
            start_time REAL NOT NULL,
            is_exam BOOLEAN NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create users table for authentication with salt column
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Add achievements table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            achievement_name TEXT NOT NULL,
            achievement_description TEXT NOT NULL,
            earned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_name, achievement_name)
        )
        ''')
        
        # Add detailed analytics table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS detailed_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            quiz_name TEXT NOT NULL,
            question_id TEXT NOT NULL,
            time_spent REAL,
            attempts INTEGER,
            correct BOOLEAN,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Add quiz feedback table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            quiz_name TEXT NOT NULL,
            rating INTEGER CHECK (rating >= 1 AND rating <= 5),
            feedback_text TEXT,
            difficulty_rating INTEGER CHECK (difficulty_rating >= 1 AND difficulty_rating <= 5),
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Add learning paths table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS learning_paths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            path_name TEXT NOT NULL,
            current_level INTEGER DEFAULT 1,
            completed_quizzes TEXT,
            next_quiz TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()

def load_user_scores():
    """Load user scores from the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT user_name, quiz_name, score, time_taken, total_quizzes, average_score, timestamp
        FROM user_scores
        ORDER BY timestamp DESC
        ''')
        rows = cursor.fetchall()
        
        # Convert to dictionary format
        scores = {}
        for row in rows:
            user_name, quiz_name, score, time_taken, total_quizzes, average_score, timestamp = row
            if user_name not in scores:
                scores[user_name] = []
            
            scores[user_name].append({
                "timestamp": timestamp,
                "quiz_name": quiz_name,
                "score": score,
                "time_taken": time_taken,
                "total_quizzes": total_quizzes,
                "average_score": average_score
            })
        
        return scores

def save_user_scores(user_name, quiz_name, score, time_taken, total_quizzes, average_score):
    """Save user score to the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO user_scores (user_name, quiz_name, score, time_taken, total_quizzes, average_score)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_name, quiz_name, score, time_taken, total_quizzes, average_score))
        conn.commit()

def save_session(session_id, session_data):
    """Save the current quiz session to the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Convert questions and answers to JSON strings
        questions_json = json.dumps(session_data['questions'])
        answers_json = json.dumps(session_data['user_answers'])
        
        cursor.execute('''
        INSERT OR REPLACE INTO quiz_sessions 
        (session_id, user_name, quiz_name, questions, user_answers, start_time, is_exam)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            session_id,
            session_data['user_name'],
            session_data['quiz_name'],
            questions_json,
            answers_json,
            session_data['start_time'],
            session_data['is_exam']
        ))
        conn.commit()

def load_session(session_id):
    """Load a saved quiz session from the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT user_name, quiz_name, questions, user_answers, start_time, is_exam
        FROM quiz_sessions
        WHERE session_id = ?
        ''', (session_id,))
        row = cursor.fetchone()
        
        if row:
            user_name, quiz_name, questions_json, answers_json, start_time, is_exam = row
            return {
                'user_name': user_name,
                'quiz_name': quiz_name,
                'questions': json.loads(questions_json),
                'user_answers': json.loads(answers_json),
                'start_time': start_time,
                'is_exam': bool(is_exam)
            }
        return None

def list_sessions():
    """List all available saved sessions from the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT session_id, user_name, quiz_name, user_answers, timestamp
        FROM quiz_sessions
        ORDER BY timestamp DESC
        ''')
        rows = cursor.fetchall()
        
        sessions = []
        for row in rows:
            session_id, user_name, quiz_name, answers_json, timestamp = row
            user_answers = json.loads(answers_json)
            sessions.append({
                'id': session_id,
                'user_name': user_name,
                'quiz_name': quiz_name,
                'timestamp': timestamp,
                'progress': f"{len(user_answers)} answers",
                'filename': session_id
            })
        
        return sessions

# User authentication functions
def get_all_users():
    """Get a list of all registered usernames."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT username FROM users ORDER BY username')
        users = cursor.fetchall()
        return [user[0] for user in users]

# Initialize database on startup
init_db()

###################
# Utility Functions
###################

def format_time(seconds):
    """Format seconds into a readable time string."""
    return str(timedelta(seconds=int(seconds)))

###################
# File Operations
###################

def get_quiz_files():
    """Get all quiz files from the qa directory."""
    quiz_files = sorted(glob.glob("qa/**/*.json", recursive=True))
    return quiz_files

def load_questions(file_path):
    """Load questions from a JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            questions = json.load(f)
            if not isinstance(questions, list):
                st.error(f"Invalid quiz format in {Path(file_path).name}. Quiz must be a list of questions.")
                return None
            return questions
    except json.JSONDecodeError as e:
        st.error(f"Error loading quiz {Path(file_path).name}: Invalid JSON format")
        return None
    except Exception as e:
        st.error(f"Error loading quiz {Path(file_path).name}: {str(e)}")
        return None

def load_all_questions():
    """Load and combine all questions from all quiz files."""
    quiz_files = get_quiz_files()
    all_questions = []
    
    for quiz_file in quiz_files:
        questions = load_questions(quiz_file)
        if questions is not None:
            all_questions.extend(questions)
    
    return all_questions

###################
# Quiz Logic
###################

def get_random_questions(questions, num_questions=20):
    """Get a random subset of questions with shuffled options."""
    if not questions:
        return None
    
    # If we have fewer questions than requested, use all available
    num_questions = min(num_questions, len(questions))
    
    # Randomly select questions
    selected_questions = random.sample(questions, num_questions)
    
    # Shuffle the options for each question
    for question in selected_questions:
        options = question['options']
        correct_answer = question['correct_answer']
        
        # Create a list of (option, is_correct) pairs
        option_pairs = [(opt, opt == correct_answer) for opt in options]
        random.shuffle(option_pairs)
        
        # Update the question with shuffled options
        question['options'] = [pair[0] for pair in option_pairs]
        # Find the correct answer in the shuffled options
        for opt, is_correct in option_pairs:
            if is_correct:
                question['correct_answer'] = opt
                break
    
    return selected_questions

def reset_quiz_state(questions):
    """Reset the quiz state for a new quiz."""
    st.session_state.user_answers = [""] * len(questions)
    st.session_state.submitted = False
    st.session_state.start_time = time.time()
    
    # Generate new session ID if not exists
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

def select_quiz(quiz_index, quiz_files):
    """Handle quiz selection and initialization."""
    st.session_state.current_quiz_index = quiz_index
    new_questions = load_questions(quiz_files[quiz_index])
    if new_questions is not None:
        # Get 20 random questions from the loaded quiz
        random_questions = get_random_questions(new_questions, 20)
        if random_questions is not None:
            st.session_state.current_questions = random_questions
            reset_quiz_state(random_questions)
            st.rerun()
    else:
        # If loading failed, try to load the first valid quiz
        for i, quiz_file in enumerate(quiz_files):
            questions = load_questions(quiz_file)
            if questions is not None:
                st.session_state.current_quiz_index = i
                random_questions = get_random_questions(questions, 20)
                if random_questions is not None:
                    st.session_state.current_questions = random_questions
                    reset_quiz_state(random_questions)
                    st.rerun()
                break

def start_exam():
    """Start a 50-question exam with questions from all quizzes."""
    all_questions = load_all_questions()
    if all_questions:
        exam_questions = get_random_questions(all_questions, 50)
        if exam_questions is not None:
            st.session_state.current_questions = exam_questions
            st.session_state.is_exam = True
            reset_quiz_state(exam_questions)
            st.rerun()

###################
# UI Components
###################

def display_login_page():
    """Display the login and registration page."""
    st.title("📝 Quiz App - Login")
    
    # Create tabs for login and registration
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        st.subheader("Login to Your Account")
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        
        if st.button("Login"):
            if username and password:
                if authenticate_user(username, password):
                    st.session_state.logged_in = True
                    st.session_state.user_name = username
                    st.success(f"Welcome back, {username}!")
                    st.rerun()
                else:
                    st.error("Invalid username or password. Please try again.")
            else:
                st.warning("Please enter both username and password.")
    
    with tab2:
        st.subheader("Create a New Account")
        new_username = st.text_input("Choose a Username", key="register_username")
        new_password = st.text_input("Choose a Password", type="password", key="register_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
        
        if st.button("Register"):
            if new_username and new_password:
                if new_password != confirm_password:
                    st.error("Passwords do not match. Please try again.")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters long.")
                else:
                    if register_user(new_username, new_password):
                        st.success("Registration successful! You can now log in.")
                        # Switch to login tab
                        st.session_state.active_tab = "Login"
                        st.rerun()
                    else:
                        st.error("Username already exists. Please choose a different username.")
            else:
                st.warning("Please fill in all fields.")

def display_profile_page():
    """Display the user profile page."""
    st.title(f"👤 Profile: {st.session_state.user_name}")
    
    # Create tabs for different profile sections
    tab1, tab2 = st.tabs(["My Statistics", "Account Settings"])
    
    with tab1:
        # Load user scores
        user_scores = load_user_scores()
        if st.session_state.user_name in user_scores:
            user_entries = user_scores[st.session_state.user_name]
            
            # Calculate statistics
            all_scores = [entry["score"] for entry in user_entries]
            best_score = max(all_scores) if all_scores else 0
            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
            total_attempts = len(user_entries)
            
            # Display user statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Attempts", total_attempts)
            with col2:
                st.metric("Best Score", f"{best_score:.1f}%")
            with col3:
                st.metric("Average Score", f"{avg_score:.1f}%")
            
            # Display quiz history
            st.subheader("Quiz History")
            history_df = pd.DataFrame([
                {
                    "Date": entry["timestamp"],
                    "Quiz": entry["quiz_name"],
                    "Score": f"{entry['score']:.1f}%",
                    "Time": format_time(entry["time_taken"])
                }
                for entry in user_entries
            ])
            st.dataframe(history_df, use_container_width=True)
        else:
            st.info("You haven't completed any quizzes yet. Take a quiz to see your statistics!")
    
    with tab2:
        st.subheader("Change Password")
        current_password = st.text_input("Current Password", type="password", key="current_password")
        new_password = st.text_input("New Password", type="password", key="new_password")
        confirm_password = st.text_input("Confirm New Password", type="password", key="confirm_new_password")
        
        if st.button("Update Password"):
            if not current_password or not new_password or not confirm_password:
                st.warning("Please fill in all password fields.")
            elif new_password != confirm_password:
                st.error("New passwords do not match.")
            elif len(new_password) < 6:
                st.error("New password must be at least 6 characters long.")
            elif not authenticate_user(st.session_state.user_name, current_password):
                st.error("Current password is incorrect.")
            else:
                # Update password
                if update_user_password(st.session_state.user_name, new_password):
                    st.success("Password updated successfully!")
                else:
                    st.error("Failed to update password. Please try again.")

def update_user_password(username, new_password):
    """Update a user's password."""
    try:
        # Generate a new salt
        salt = os.urandom(32)
        # Hash the new password with the salt
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            new_password.encode('utf-8'),
            salt,
            100000
        )
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            UPDATE users
            SET password = ?, salt = ?
            WHERE username = ?
            ''', (password_hash.hex(), salt.hex(), username))
            conn.commit()
            return cursor.rowcount > 0
    except Exception:
        return False

def display_quiz_questions(current_quiz_file=None):
    """Display the current quiz questions with timer and progress bar."""
    # Create a container for the fixed header
    header_container = st.container()
    
    # Create a container for the questions
    questions_container = st.container()
    
    with header_container:
        # Display current quiz info
        if st.session_state.is_exam:
            st.subheader("📚 50-Question Exam")
        else:
            quiz_name = st.session_state.current_quiz_name if current_quiz_file is None else Path(current_quiz_file).stem
            st.subheader(f"Current Quiz: {quiz_name} (20 Questions)")
        
        # Calculate progress
        total_questions = len(st.session_state.current_questions)
        answered_questions = sum(1 for answer in st.session_state.user_answers if answer)
        progress_percentage = int((answered_questions / total_questions) * 100)
        
        # Create three columns for progress indicators
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            # Display progress bar
            st.progress(progress_percentage / 100)
        
        with col2:
            # Display progress text
            st.write(f"Progress: {answered_questions}/{total_questions}")
        
        with col3:
            # Display timer
            elapsed_time = time.time() - st.session_state.start_time
            st.write(f"⏱️ {format_time(elapsed_time)}")
        
        # Add a divider to separate header from questions
        st.divider()
    
    with questions_container:
        # Display questions
        for i, q in enumerate(st.session_state.current_questions):
            st.subheader(f"Question {i+1}: {q['question']}")
            
            # Use radio buttons for options
            answer = st.radio(
                f"Select your answer for question {i+1}:",
                q['options'],
                key=f"q_{i}",
                index=None if not st.session_state.user_answers[i] else q['options'].index(st.session_state.user_answers[i]),
                disabled=st.session_state.submitted
            )
            
            # Store the answer in session state and save session
            if answer and answer != st.session_state.user_answers[i]:
                st.session_state.user_answers[i] = answer
                
                # Save session after each answer
                if not st.session_state.submitted:
                    session_data = {
                        'user_name': st.session_state.user_name,
                        'quiz_name': "50-Question Exam" if st.session_state.is_exam else Path(current_quiz_file).stem,
                        'questions': st.session_state.current_questions,
                        'user_answers': st.session_state.user_answers,
                        'start_time': st.session_state.start_time,
                        'is_exam': st.session_state.is_exam,
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_session(st.session_state.session_id, session_data)
            
            st.divider()
        
        # Create two columns for submit and skip buttons
        col1, col2 = st.columns(2)
        
        # Submit button
        if not st.session_state.submitted:
            with col1:
                if st.button("Submit Quiz"):
                    # Check if all questions are answered
                    if "" in st.session_state.user_answers:
                        st.error("Please answer all questions before submitting!")
                    else:
                        st.session_state.submitted = True
                        st.rerun()

def display_quiz_results(current_quiz_file=None, quiz_files=None):
    """Display quiz results after submission."""
    correct_count = 0
    results_data = []
    
    for i, q in enumerate(st.session_state.current_questions):
        user_answer = st.session_state.user_answers[i]
        correct = user_answer == q['correct_answer']
        if correct:
            correct_count += 1
        
        results_data.append({
            "Question": q['question'],
            "Your Answer": user_answer,
            "Correct Answer": q['correct_answer'],
            "Result": "✅ Correct" if correct else "❌ Wrong"
        })
    
    # Calculate score and time
    score_percentage = (correct_count / len(st.session_state.current_questions)) * 100
    final_time = time.time() - st.session_state.start_time
    
    # Store the score for this quiz
    quiz_name = "50-Question Exam" if st.session_state.is_exam else Path(current_quiz_file).stem
    st.session_state.quiz_scores[quiz_name] = score_percentage
    
    # Calculate average score across all completed quizzes
    completed_quizzes = len(st.session_state.quiz_scores)
    total_score = sum(st.session_state.quiz_scores.values())
    average_score = total_score / completed_quizzes if completed_quizzes > 0 else 0
    
    # Display score and time
    st.header("Quiz Results")
    st.subheader(f"Your Score: {correct_count}/{len(st.session_state.current_questions)} ({score_percentage:.1f}%)")
    st.subheader(f"Time Taken: {format_time(final_time)}")
    
    # Display cumulative results
    st.subheader("Cumulative Results")
    st.write(f"Completed Quizzes: {completed_quizzes}")
    st.write(f"Average Score: {average_score:.1f}%")
    
    # Display individual quiz scores
    st.write("Individual Quiz Scores:")
    for quiz, score in st.session_state.quiz_scores.items():
        st.write(f"- {quiz}: {score:.1f}%")
    
    # Display results table
    st.dataframe(pd.DataFrame(results_data), use_container_width=True)
    
    # Save score to database (using the logged-in username)
    user_name = st.session_state.user_name
    if user_name:
        # Save score to database
        save_user_scores(
            user_name=user_name,
            quiz_name=quiz_name,
            score=score_percentage,
            time_taken=final_time,
            total_quizzes=completed_quizzes,
            average_score=average_score
        )
        st.success(f"Results saved for user: {user_name}")
        
        # After saving score to database, check for achievements
        check_achievements(user_name, score_percentage, quiz_name)
    
    # Button to start a new quiz
    if st.button("Start a New Quiz"):
        # Reset session state for a new quiz
        st.session_state.current_questions = None
        st.session_state.user_answers = None
        st.session_state.submitted = False
        st.session_state.session_id = str(uuid.uuid4())
        st.rerun()

def display_logout_button():
    """Display a logout button in the sidebar."""
    if st.sidebar.button("Logout"):
        # Clear session state
        for key in list(st.session_state.keys()):
            if key != 'quiz_scores':  # Keep quiz scores across sessions
                del st.session_state[key]
        st.session_state.logged_in = False
        st.rerun()

###################
# UI Components
###################

def display_user_statistics():
    """Display user statistics in the sidebar."""
    user_scores = load_user_scores()

    st.sidebar.title("📊 User Statistics")

    if not user_scores:
        st.sidebar.info("No scores recorded yet. Complete a quiz to see your statistics!")
        return None

    # Create tabs for different views
    tab1, tab2 = st.sidebar.tabs(["User Scores", "Leaderboard"])

    with tab1:
        # Select user to view - use all registered users for the dropdown
        all_users = get_all_users()
        user_options = [user for user in all_users if user in user_scores]

        if not user_options:
            st.sidebar.info("No users with scores yet.")
            return None

        selected_user = st.sidebar.selectbox(
            "Select User",
            options=user_options,
            key="user_selector_sidebar"
        )

        if selected_user:
            user_entries = user_scores[selected_user]

            # Calculate statistics
            all_scores = [entry["score"] for entry in user_entries]
            best_score = max(all_scores) if all_scores else 0
            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
            total_attempts = len(user_entries)

            # Display user statistics
            st.sidebar.metric("Total Attempts", total_attempts)
            st.sidebar.metric("Best Score", f"{best_score:.1f}%")
            st.sidebar.metric("Average Score", f"{avg_score:.1f}%")

            # Display recent attempts
            st.sidebar.subheader("Recent Attempts")
            for entry in sorted(user_entries, key=lambda x: x["timestamp"], reverse=True)[:5]:
                st.sidebar.write(f"📝 {entry['quiz_name']}")
                st.sidebar.write(f"Score: {entry['score']:.1f}%")
                st.sidebar.write(f"Time: {format_time(entry['time_taken'])}")
                st.sidebar.write(f"Date: {entry['timestamp']}")
                st.sidebar.divider()
    
    with tab2:
        # Calculate and display leaderboard
        leaderboard_data = []
        for user, entries in user_scores.items():
            scores = [entry["score"] for entry in entries]
            leaderboard_data.append({
                "User": user,
                "Best Score": max(scores) if scores else 0,
                "Average Score": sum(scores) / len(scores) if scores else 0,
                "Total Attempts": len(entries)
            })
        
        # Sort by best score
        leaderboard_data.sort(key=lambda x: x["Best Score"], reverse=True)
        
        # Display leaderboard
        st.sidebar.subheader("🏆 Leaderboard")
        for i, entry in enumerate(leaderboard_data, 1):
            st.sidebar.write(f"{i}. {entry['User']}")
            st.sidebar.write(f"   Best: {entry['Best Score']:.1f}% | Avg: {entry['Average Score']:.1f}%")
            st.sidebar.write(f"   Attempts: {entry['Total Attempts']}")
            st.sidebar.divider()
    
    return selected_user

def display_saved_sessions_page():
    """Display the saved sessions page with navigation."""
    st.title("💾 Saved Sessions")
    
    # Add a back button
    if st.button("← Back to Home"):
        st.session_state.current_page = "Home"
        st.rerun()
    
    # Only show sessions for the current logged-in user
    sessions = list_sessions()
    current_user = st.session_state.user_name
    user_sessions = [s for s in sessions if s['user_name'] == current_user]
    
    if not user_sessions:
        st.info("You don't have any saved sessions yet.")
        return
    
    # Display sessions in a grid layout
    cols = st.columns(3)  # Adjust the number of columns as needed
    for i, session in enumerate(user_sessions):
        with cols[i % 3]:
            # Create a unique key using timestamp and session ID
            unique_key = f"session_{session['timestamp'].replace(' ', '_')}_{session['id']}"
            try:
                if st.button(
                    f"📝 {session['quiz_name']}\n"
                    f"Progress: {session['progress']}\n"
                    f"Saved: {session['timestamp']}",
                    key=unique_key,
                    use_container_width=True
                ):
                    # Load and restore session
                    session_data = load_session(session['id'])
                    if session_data:
                        st.session_state.current_questions = session_data['questions']
                        st.session_state.user_answers = session_data['user_answers']
                        st.session_state.start_time = session_data['start_time']
                        st.session_state.is_exam = session_data.get('is_exam', False)
                        st.session_state.session_id = session['id']
                        st.session_state.current_quiz_name = session_data['quiz_name']
                        # Switch back to home page after loading session
                        st.session_state.current_page = "Home"
                        st.rerun()
            except Exception as e:
                # Skip this session if there's a key conflict
                continue

def display_quiz_review(current_quiz_file=None):
    """Display quiz review mode with explanations and learning resources."""
    st.title("📖 Quiz Review")
    
    for i, q in enumerate(st.session_state.current_questions):
        st.subheader(f"Question {i+1}: {q['question']}")
        
        # Display user's answer and correct answer
        user_answer = st.session_state.user_answers[i]
        correct_answer = q['correct_answer']
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("Your Answer:", "✅ " if user_answer == correct_answer else "❌ ")
            st.write(user_answer)
        with col2:
            st.write("Correct Answer:")
            st.write(correct_answer)
        
        # Display explanation if available
        if 'explanation' in q:
            st.info(f"Explanation: {q['explanation']}")
        
        # Display learning resources if available
        if 'resources' in q:
            st.write("Learning Resources:")
            for resource in q['resources']:
                st.write(f"- {resource}")
        
        st.divider()
    
    if st.button("Back to Quiz Selection"):
        st.session_state.current_questions = None
        st.session_state.user_answers = None
        st.session_state.submitted = False
        st.rerun()

def check_achievements(user_name, score, quiz_name):
    """Check and award achievements based on user performance."""
    achievements = []
    
    # Score-based achievements
    if score >= 90:
        achievements.append(("Perfect Score", "Achieved 90% or higher in a quiz"))
    elif score >= 80:
        achievements.append(("Great Performance", "Achieved 80% or higher in a quiz"))
    
    # Quiz-specific achievements
    if quiz_name == "50-Question Exam":
        achievements.append(("Exam Master", "Completed the 50-question exam"))
    
    # Save achievements
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for achievement_name, description in achievements:
            try:
                cursor.execute('''
                INSERT INTO achievements (user_name, achievement_name, achievement_description)
                VALUES (?, ?, ?)
                ''', (user_name, achievement_name, description))
            except sqlite3.IntegrityError:
                # Achievement already earned
                pass
        conn.commit()

def display_achievements(user_name):
    """Display user achievements."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT achievement_name, achievement_description, earned_at
        FROM achievements
        WHERE user_name = ?
        ORDER BY earned_at DESC
        ''', (user_name,))
        achievements = cursor.fetchall()
        
        if achievements:
            st.subheader("🏆 Your Achievements")
            for name, description, earned_at in achievements:
                st.write(f"**{name}**")
                st.write(f"_{description}_")
                st.write(f"Earned: {earned_at}")
                st.divider()
        else:
            st.info("Complete quizzes to earn achievements!")

###################
# Main Application
###################

def display_quiz_selection(quiz_files):
    """Display the quiz selection interface."""
    st.subheader("📚 Select a Quiz to Start")
    
    # Create a grid layout for quiz selection
    cols = st.columns(3)  # Adjust number of columns as needed
    
    # Add a button for the 50-question exam
    with cols[0]:
        if st.button("📝 Take 50-Question Exam", use_container_width=True):
            start_exam()
    
    # Add buttons for individual quizzes
    for i, quiz_file in enumerate(quiz_files):
        with cols[(i+1) % 3]:  # +1 to account for the exam button
            quiz_name = Path(quiz_file).stem
            if st.button(f"📝 {quiz_name}", key=f"quiz_{i}", use_container_width=True):
                select_quiz(i, quiz_files)

def display_analytics_dashboard():
    """Display comprehensive analytics dashboard."""
    st.title("📊 Analytics Dashboard")
    
    # Get user scores
    user_scores = load_user_scores()
    if st.session_state.user_name in user_scores:
        user_entries = user_scores[st.session_state.user_name]
        
        # Performance over time
        st.subheader("Performance Over Time")
        performance_data = pd.DataFrame([
            {
                "Date": entry["timestamp"],
                "Score": entry["score"],
                "Quiz": entry["quiz_name"]
            }
            for entry in user_entries
        ])
        st.line_chart(performance_data.set_index("Date")["Score"])
        
        # Quiz performance
        st.subheader("Performance by Quiz")
        quiz_data = pd.DataFrame([
            {
                "Quiz": entry["quiz_name"],
                "Score": entry["score"]
            }
            for entry in user_entries
        ])
        st.bar_chart(quiz_data.groupby("Quiz")["Score"].mean())
        
        # Time analysis
        st.subheader("Time Analysis")
        time_data = pd.DataFrame([
            {
                "Quiz": entry["quiz_name"],
                "Time Taken": entry["time_taken"]
            }
            for entry in user_entries
        ])
        st.bar_chart(time_data.set_index("Quiz")["Time Taken"])
        
        # Overall statistics
        st.subheader("Overall Statistics")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Quizzes", len(user_entries))
        with col2:
            st.metric("Average Score", f"{sum(e['score'] for e in user_entries)/len(user_entries):.1f}%")
        with col3:
            st.metric("Total Time", format_time(sum(e['time_taken'] for e in user_entries)))
    else:
        st.info("Complete quizzes to see your analytics!")

def main():
    # Initialize session state variables if they don't exist
    if 'current_questions' not in st.session_state:
        st.session_state.current_questions = None
    if 'user_answers' not in st.session_state:
        st.session_state.user_answers = None
    if 'submitted' not in st.session_state:
        st.session_state.submitted = False
    if 'start_time' not in st.session_state:
        st.session_state.start_time = None
    if 'current_quiz_index' not in st.session_state:
        st.session_state.current_quiz_index = None
    if 'is_exam' not in st.session_state:
        st.session_state.is_exam = False
    if 'quiz_scores' not in st.session_state:
        st.session_state.quiz_scores = {}
    if 'user_name' not in st.session_state:
        st.session_state.user_name = None
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'current_page' not in st.session_state: # If you've implemented navigation
        st.session_state.current_page = "Home"
    
    # Check if user is logged in
    if not st.session_state.logged_in:
        display_login_page()
        return
    
    # Display logout button in sidebar
    display_logout_button()
    
    # Display user statistics in sidebar
    st.session_state.selected_user = display_user_statistics()
    
    # Get quiz files
    quiz_files = get_quiz_files()
    
    # Main content
    st.title("📝 Quiz App")
    st.write(f"Welcome, {st.session_state.user_name}!")
    
    # Add navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Home", "Saved Sessions", "Analytics", "Achievements"])
    
    if page == "Home":
        # Existing quiz functionality
        if st.session_state.current_questions is None:
            display_quiz_selection(quiz_files)
        else:
            if not st.session_state.submitted:
                current_quiz_file = None
                if not st.session_state.is_exam and st.session_state.current_quiz_index is not None:
                    current_quiz_file = quiz_files[st.session_state.current_quiz_index]
                display_quiz_questions(current_quiz_file)
            else:
                current_quiz_file = None
                if not st.session_state.is_exam and st.session_state.current_quiz_index is not None:
                    current_quiz_file = quiz_files[st.session_state.current_quiz_index]
                display_quiz_results(current_quiz_file, quiz_files)
                display_quiz_review(current_quiz_file)
    
    elif page == "Saved Sessions":
        display_saved_sessions_page()
    
    elif page == "Analytics":
        display_analytics_dashboard()
    
    elif page == "Achievements":
        display_achievements(st.session_state.user_name)

def track_question_performance(user_name, quiz_name, question_id, time_spent, attempts, correct):
    """Track detailed performance for each question."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO detailed_analytics 
        (user_name, quiz_name, question_id, time_spent, attempts, correct)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_name, quiz_name, question_id, time_spent, attempts, correct))
        conn.commit()

def export_quiz(quiz_name):
    """Export a quiz to a shareable format."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT questions, user_answers, quiz_name
        FROM quiz_sessions
        WHERE quiz_name = ?
        ''', (quiz_name,))
        quiz_data = cursor.fetchone()
        
        if quiz_data:
            return {
                "quiz_name": quiz_data[2],
                "questions": json.loads(quiz_data[0]),
                "answers": json.loads(quiz_data[1])
            }
        return None

def import_quiz(quiz_data):
    """Import a quiz from exported data."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO quiz_sessions 
        (session_id, user_name, quiz_name, questions, user_answers, start_time, is_exam)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(uuid.uuid4()),
            "imported",
            quiz_data["quiz_name"],
            json.dumps(quiz_data["questions"]),
            json.dumps(quiz_data["answers"]),
            time.time(),
            False
        ))
        conn.commit()

def submit_quiz_feedback(user_name, quiz_name, rating, feedback_text, difficulty_rating):
    """Submit feedback for a completed quiz."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO quiz_feedback (user_name, quiz_name, rating, feedback_text, difficulty_rating)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_name, quiz_name, rating, feedback_text, difficulty_rating))
        conn.commit()

def create_learning_path(user_name, path_name):
    """Create a personalized learning path for a user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO learning_paths (user_name, path_name)
        VALUES (?, ?)
        ''', (user_name, path_name))
        conn.commit()

if __name__ == "__main__":
    main()
