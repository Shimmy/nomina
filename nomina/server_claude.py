"""
Flask API server for Nomina
"""
from flask import Flask, request, jsonify
from flask_cors import CORS  # Import CORS from flask_cors
import os
import subprocess
import traceback
import argparse
import re

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize global variables - will be set in main()
working_dir = None
history = []

# Simple message structure to replace LLM dependency
def make_text_message(role, content):
    """Create a simple message object with role and content"""
    return {
        "role": role,
        "content": content
    }

# API Routes
@app.route('/api/chat', methods=['POST'])
def chat():
    global history
    
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"error": "Message is required"}), 400
    
    message = data['message']
    history.append(make_text_message("user", message))
    
    env = os.environ.copy()
    env["PATH"] = "/usr/local/bin:/usr/bin:" + env["PATH"]
    
    # Import tempfile module if not already imported
    import tempfile
    try:
        # Create a temporary file to store the message
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write(message)
            message_file_path = temp_file.name
        
        # Use the file to pass the message content to Claude
        process = subprocess.run(
            ["/usr/bin/script", "-q", "-c", f"claude -f {message_file_path} --dangerously-skip-permissions", "/dev/null"],
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=600,
            env=env
        )
        
        # Clean up the temporary file
        os.unlink(message_file_path)
        
        # Check if the command was successful
        if process.returncode != 0:
            raise Exception(f"Claude Code failed with error: {process.stderr}")
            
        ANSI_ESCAPE_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')    
        reply = ANSI_ESCAPE_PATTERN.sub('', process.stdout).strip()
        history.append(make_text_message("assistant", reply))
        
        return jsonify({
            "success": True,
            "message": message,
            "reply": reply,
            "model": "Claude code"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    return jsonify({
        "history": [
            {"role": msg["role"], "content": msg["content"]} 
            for msg in history 
            if msg["role"] != "system"  # Exclude system messages
        ]
    })

@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    global history
    history = []  # No system message to keep anymore
    return jsonify({"success": True, "message": "History cleared"})

def main():
    """Entry point for the API server"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Nomina API Server")
    parser.add_argument("--dir", "-d", help="Working directory (default: current directory)", default=os.getcwd())
    parser.add_argument("--port", "-p", help="Port to run the server on", type=int, default=5000)
    parser.add_argument("--host", help="Host to run the server on", default="0.0.0.0")
    args = parser.parse_args()
    
    # Set working directory
    global working_dir
    working_dir = os.path.abspath(args.dir)
    if not os.path.isdir(working_dir):
        print(f"Error: {working_dir} is not a valid directory")
        return
    
    # Display startup message
    print(f"Nomina API Server")
    print(f"Working directory: {working_dir}")
    print(f"Starting server on http://{args.host}:{args.port}")
    
    # Start the Flask server
    app.run(debug=True, host=args.host, port=args.port)

if __name__ == '__main__':
    main()
