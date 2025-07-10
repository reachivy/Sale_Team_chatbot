import subprocess
import os
import sys
import webbrowser
import time
import socket

def start_language_tool():
    """Start the LanguageTool server."""
    language_tool_path = "/Users/juhi/Downloads/Sale_Team_chatbot/LanguageTool-6.6/languagetool-server.jar"
    if not os.path.exists(language_tool_path):
        print(f"Error: LanguageTool JAR not found at {language_tool_path}")
        sys.exit(1)

    lt_command = ["java", "-cp", language_tool_path, "org.languagetool.server.HTTPServer", "--port", "8081"]
    lt_process = subprocess.Popen(lt_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print("Starting LanguageTool server...")
    return lt_process

def start_flask_app():
    """Start the Flask app."""
    app_path = "/Users/juhi/Downloads/Sale_Team_chatbot/app.py"
    if not os.path.exists(app_path):
        print(f"Error: app.py not found at {app_path}")
        sys.exit(1)

    python_exec = "/Users/juhi/Downloads/Sale_Team_chatbot/venv/bin/python"
    if not os.path.exists(python_exec):
        print(f"Error: Python executable not found at {python_exec}")
        sys.exit(1)

    flask_command = [python_exec, app_path]
    flask_process = subprocess.Popen(flask_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
    print("Starting Flask app...")
    return flask_process

def check_port_availability(port):
    """Check if a port is in use."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result != 0

def check_server_ready(process, timeout=30):
    """Check if the server is running by polling stdout for a success message."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        output = process.stdout.readline()
        if output:
            print("Flask Output:", output.strip())
            if "Running on" in output or "Debugger is active" in output:
                return True
        error = process.stderr.readline()
        if error:
            print("Flask Error:", error.strip())
        time.sleep(0.1)  # Small delay to prevent CPU overuse
    return False

def open_browser():
    """Open the chatbot in the default web browser."""
    url = "http://localhost:5000"
    print(f"Attempting to open chatbot in browser at {url}...")
    try:
        webbrowser.open(url)
        print(f"Browser opened successfully at {url}")
    except Exception as e:
        print(f"Failed to open browser: {e}")

def main():
    # Check port 5000 availability
    if not check_port_availability(5000):
        print("Error: Port 5000 is in use. Please free the port and try again.")
        sys.exit(1)

    # Start LanguageTool server
    lt_process = start_language_tool()
    
    # Start Flask app
    flask_process = start_flask_app()
    
    # Check if Flask server is ready
    if not check_server_ready(flask_process):
        print("Error: Flask server failed to start within 30 seconds.")
        lt_process.terminate()
        flask_process.terminate()
        lt_process.wait()
        flask_process.wait()
        sys.exit(1)
    
    # Open browser
    open_browser()
    
    print("Chatbot is running. Press Ctrl+C to stop.")
    
    try:
        # Keep the script running and print process output
        while True:
            lt_output = lt_process.stdout.readline()
            if lt_output:
                print("LanguageTool:", lt_output.strip())
            flask_output = flask_process.stdout.readline()
            if flask_output:
                print("Flask:", flask_output.strip())
            lt_error = lt_process.stderr.readline()
            if lt_error:
                print("LanguageTool Error:", lt_error.strip())
            flask_error = flask_process.stderr.readline()
            if flask_error:
                print("Flask Error:", flask_error.strip())
            if lt_process.poll() is not None or flask_process.poll() is not None:
                print("One or both processes have stopped.")
                break
            time.sleep(0.1)  # Small delay to prevent CPU overuse
    except KeyboardInterrupt:
        print("\nShutting down...")
        lt_process.terminate()
        flask_process.terminate()
        lt_process.wait()
        flask_process.wait()
        print("Server and app terminated.")

if __name__ == "__main__":
    main()