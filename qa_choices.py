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
    db_path = Path("quiz_data.db")
    conn = sqlite3.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()

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
    quiz_files = sorted(glob.glob("qa/*.json"))
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
        # Select user to view
        selected_user = st.selectbox(
            "Select User",
            options=list(user_scores.keys()),
            key="user_selector_sidebar"
        )
        
        if selected_user:
            user_entries = user_scores[selected_user]
            
            # Calculate statistics
            all_scores = [entry["score"] for entry in user_entries]
            best_score = max(all_scores)
            avg_score = sum(all_scores) / len(all_scores)
            total_attempts = len(user_entries)
            
            # Display user statistics
            st.metric("Total Attempts", total_attempts)
            st.metric("Best Score", f"{best_score:.1f}%")
            st.metric("Average Score", f"{avg_score:.1f}%")
            
            # Display recent attempts
            st.subheader("Recent Attempts")
            for entry in sorted(user_entries, key=lambda x: x["timestamp"], reverse=True)[:5]:
                st.write(f"📝 {entry['quiz_name']}")
                st.write(f"Score: {entry['score']:.1f}%")
                st.write(f"Time: {format_time(entry['time_taken'])}")
                st.write(f"Date: {entry['timestamp']}")
                st.divider()
    
    with tab2:
        # Calculate and display leaderboard
        leaderboard_data = []
        for user, entries in user_scores.items():
            scores = [entry["score"] for entry in entries]
            leaderboard_data.append({
                "User": user,
                "Best Score": max(scores),
                "Average Score": sum(scores) / len(scores),
                "Total Attempts": len(entries)
            })
        
        # Sort by best score
        leaderboard_data.sort(key=lambda x: x["Best Score"], reverse=True)
        
        # Display leaderboard
        st.subheader("🏆 Leaderboard")
        for i, entry in enumerate(leaderboard_data, 1):
            st.write(f"{i}. {entry['User']}")
            st.write(f"   Best: {entry['Best Score']:.1f}% | Avg: {entry['Average Score']:.1f}%")
            st.write(f"   Attempts: {entry['Total Attempts']}")
            st.divider()
    
    return selected_user

def display_saved_sessions():
    """Display saved sessions that can be resumed."""
    sessions = list_sessions()
    
    if not sessions:
        return
    
    st.divider()
    st.subheader("💾 Saved Sessions")
    
    # Create a container for the sessions list
    sessions_container = st.container()
    
    # Display sessions in a grid layout
    cols = st.columns(3)  # Adjust the number of columns as needed
    for i, session in enumerate(sessions):
        with cols[i % 3]:
            # Create a unique key using timestamp and session ID
            unique_key = f"session_{session['timestamp'].replace(' ', '_')}_{session['id']}"
            try:
                if st.button(
                    f"📝 {session['user_name']}\n"
                    f"Quiz: {session['quiz_name']}\n"
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
                        st.session_state.user_name = session_data['user_name']
                        st.rerun()
            except Exception as e:
                # Skip this session if there's a key conflict
                continue

def display_quiz_selection(quiz_files):
    """Display available quizzes as clickable buttons."""
    st.subheader("Available Quizzes")
    st.write("Click on any quiz below to start:")
    
    # Create a container for quiz links
    quiz_container = st.container()
    
    # Display quiz links in a grid layout
    cols = st.columns(3)  # Adjust the number of columns as needed
    for i, quiz_file in enumerate(quiz_files):
        quiz_name = Path(quiz_file).stem
        with cols[i % 3]:
            if st.button(
                f"📝 {quiz_name}",
                key=f"quiz_link_{i}",
                use_container_width=True
            ):
                st.session_state.is_exam = False
                select_quiz(i, quiz_files)
    
    # Add 50-question exam button
    st.divider()
    if st.button("📚 Start 50-Question Exam", use_container_width=True):
        start_exam()

def display_quiz_questions(current_quiz_file=None):
    """Display the current quiz questions."""
    # Display current quiz info
    if st.session_state.is_exam:
        st.subheader("📚 50-Question Exam")
    else:
        st.subheader(f"Current Quiz: {Path(current_quiz_file).stem} (20 Questions)")
    
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
    
    # User name input and score saving
    st.divider()
    st.subheader("Save Your Results")
    
    # Get user name from input or use selected user
    user_name = st.text_input("Enter your name to save your results:", value=st.session_state.user_name or st.session_state.selected_user)
    if user_name:
        st.session_state.user_name = user_name
        
        # Save score to database
        save_user_scores(
            user_name=user_name,
            quiz_name=quiz_name,
            score=score_percentage,
            time_taken=final_time,
            total_quizzes=completed_quizzes,
            average_score=average_score
        )
        st.success(f"Results saved for {user_name}!")
        
        # Display user statistics
        st.subheader("User Statistics")
        user_scores = load_user_scores()
        user_entries = user_scores.get(user_name, [])
        if len(user_entries) > 1:
            all_scores = [entry["score"] for entry in user_entries]
            st.write(f"Total Attempts: {len(user_entries)}")
            st.write(f"Best Score: {max(all_scores):.1f}%")
            st.write(f"Average Score: {sum(all_scores)/len(all_scores):.1f}%")
    
    # Create two columns for buttons
    col1, col2 = st.columns(2)
    
    with col1:
        # Restart current quiz button
        if st.button("Restart Current Quiz"):
            if st.session_state.is_exam:
                start_exam()
            else:
                select_quiz(st.session_state.current_quiz_index, quiz_files)
    
    with col2:
        # Next quiz button (only show if there are more quizzes and not in exam mode)
        if not st.session_state.is_exam and st.session_state.current_quiz_index < len(quiz_files) - 1:
            if st.button("Next Quiz"):
                st.session_state.current_quiz_index += 1
                select_quiz(st.session_state.current_quiz_index, quiz_files)

###################
# Main Application
###################

def main():
    """Main application function."""
    # Display user statistics in sidebar and get selected user
    selected_user = display_user_statistics()
    
    # Store selected user in session state
    if 'selected_user' not in st.session_state:
        st.session_state.selected_user = selected_user
    
    st.title("Quiz for Habu Gummama!")
    
    # Initialize user name in session state
    if 'user_name' not in st.session_state:
        st.session_state.user_name = selected_user if selected_user else ""
    
    # Initialize exam state
    if 'is_exam' not in st.session_state:
        st.session_state.is_exam = False
    
    # Get all quiz files
    quiz_files = get_quiz_files()
    
    if not quiz_files:
        st.error("No quiz files found in the qa folder!")
        return
    
    # Initialize session state for current quiz index
    if 'current_quiz_index' not in st.session_state:
        st.session_state.current_quiz_index = 0
    
    # Initialize timer
    if 'start_time' not in st.session_state:
        st.session_state.start_time = time.time()
    
    # Initialize quiz scores tracking
    if 'quiz_scores' not in st.session_state:
        st.session_state.quiz_scores = {}
    
    # Load current quiz if not in exam mode
    current_quiz_file = None
    if not st.session_state.is_exam:
        current_quiz_file = quiz_files[st.session_state.current_quiz_index]
        questions = load_questions(current_quiz_file)
        
        if questions is None:
            st.error("Failed to load the current quiz. Please try selecting another quiz.")
            return
        
        # Get 20 random questions if not already set
        if 'current_questions' not in st.session_state:
            st.session_state.current_questions = get_random_questions(questions, 20)
    else:
        # For exam mode, ensure we have questions
        if 'current_questions' not in st.session_state:
            start_exam()
    
    # Initialize or update session state for storing answers
    if 'user_answers' not in st.session_state or len(st.session_state.user_answers) != len(st.session_state.current_questions):
        reset_quiz_state(st.session_state.current_questions)
    
    if 'submitted' not in st.session_state:
        st.session_state.submitted = False
    
    # Display timer
    if not st.session_state.submitted:
        elapsed_time = time.time() - st.session_state.start_time
        st.markdown(f"### ⏱️ Time Elapsed: {format_time(elapsed_time)}")
    
    # Display quiz questions or results
    if st.session_state.submitted:
        display_quiz_results(current_quiz_file, quiz_files)
    else:
        display_quiz_questions(current_quiz_file)
    
    # Add a divider before the quiz selection section
    st.divider()
    
    # Display available quizzes
    display_quiz_selection(quiz_files)
    
    # Display saved sessions at the bottom
    display_saved_sessions()

if __name__ == "__main__":
    main()
