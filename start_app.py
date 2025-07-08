import subprocess
import webbrowser
import time
import os
import signal
import sys
from threading import Thread
import psutil  # For process management

# Paths and configurations
BASE_DIR = r"D:\Sale_Team_chatbot"
LANGUAGE_TOOL_JAR = os.path.join(BASE_DIR, "languageTool-6.6", "languagetool-server.jar")
FLASK_APP = os.path.join(BASE_DIR, "app.py")
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"  # Adjust if Chrome is elsewhere
URL = "http://localhost:5000"

# Global variables to store processes
language_tool_process = None
flask_process = None

def start_language_tool():
    """Start the LanguageTool server."""
    global language_tool_process
    try:
        print("Starting LanguageTool server...")
        language_tool_process = subprocess.Popen(
            ["java", "-cp", LANGUAGE_TOOL_JAR, "org.languagetool.server.HTTPServer", "--port", "8081"],
            cwd=os.path.dirname(LANGUAGE_TOOL_JAR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP  # Windows-specific for process group
        )
        # Wait briefly to ensure server starts
        time.sleep(3)
        if language_tool_process.poll() is None:
            print("LanguageTool server started successfully.")
        else:
            print("Failed to start LanguageTool server.")
            sys.exit(1)
    except Exception as e:
        print(f"Error starting LanguageTool server: {e}")
        sys.exit(1)

def start_flask():
    """Start the Flask application."""
    global flask_process
    try:
        print("Starting Flask server...")
        flask_process = subprocess.Popen(
            ["python", FLASK_APP],
            cwd=BASE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        # Wait briefly to ensure Flask starts
        time.sleep(3)
        if flask_process.poll() is None:
            print("Flask server started successfully.")
        else:
            print("Failed to start Flask server.")
            sys.exit(1)
    except Exception as e:
        print(f"Error starting Flask server: {e}")
        sys.exit(1)

def open_browser():
    """Open the Chrome browser at the Flask app URL."""
    try:
        print(f"Opening Chrome at {URL}...")
        webbrowser.register('chrome', None, webbrowser.BackgroundBrowser(CHROME_PATH))
        webbrowser.get('chrome').open(URL)
    except Exception as e:
        print(f"Error opening browser: {e}")
        sys.exit(1)

def cleanup():
    """Clean up by terminating LanguageTool and Flask processes."""
    global language_tool_process, flask_process
    try:
        if language_tool_process and language_tool_process.poll() is None:
            print("Terminating LanguageTool server...")
            parent = psutil.Process(language_tool_process.pid)
            for child in parent.children(recursive=True):
                child.terminate()
            parent.terminate()
            language_tool_process.wait(timeout=5)
    except Exception as e:
        print(f"Error terminating LanguageTool server: {e}")

    try:
        if flask_process and flask_process.poll() is None:
            print("Terminating Flask server...")
            parent = psutil.Process(flask_process.pid)
            for child in parent.children(recursive=True):
                child.terminate()
            parent.terminate()
            flask_process.wait(timeout=5)
    except Exception as e:
        print(f"Error terminating Flask server: {e}")

def signal_handler(sig, frame):
    """Handle termination signals."""
    print("Received termination signal. Cleaning up...")
    cleanup()
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers for clean exit
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start LanguageTool server
    start_language_tool()

    # Start Flask server
    start_flask()

    # Open browser
    open_browser()

    # Keep the script running and monitor processes
    try:
        while True:
            if language_tool_process.poll() is not None or flask_process.poll() is not None:
                print("One of the processes has stopped unexpectedly.")
                cleanup()
                sys.exit(1)
            time.sleep(1)
    except KeyboardInterrupt:
        print("Application closed by user.")
        cleanup()
        sys.exit(0)