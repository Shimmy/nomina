"""
Flask API server for Nomina
"""
from flask import Flask, request, jsonify
from flask_cors import CORS  # Import CORS from flask_cors
import os
import subprocess
import traceback
import argparse
from nomina.nominallm import NominaLlm

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Initialize global variables - will be set in main()
working_dir = None
llm = None
history = None
system_prompt = """
You are Nomina, an autonomous coding and shell assistant.

- You **must** use the tools to read, modify, list and write files.
- When asked to add new features, do the following:
    1. Read relevant files.
    2. Modify and save files using tools.
    - Repeat steps 1-2 until confident it works.
- Avoid repeated narration; take action instead.
- Always report your **final status** succinctly.
- Be careful with shell commands.
"""

# Safety function for paths
def safe_path(path):
    jail_dir = working_dir
    abs_path = os.path.abspath(os.path.join(jail_dir, path))
    if not abs_path.startswith(jail_dir):
        raise Exception(f"Access outside jail is denied: {abs_path}")
    return abs_path

# Tool functions - copied from nomina.py to maintain consistency
def write_file(filepath, content):
    try:
        full_path = safe_path(filepath)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w") as f:
            f.write(content)
        return f"File written successfully: {filepath}"
    except Exception as e:
        raise RuntimeError(f"write_file failed: {e}")

def read_file(filepath):
    try:
        full = safe_path(filepath)
        with open(full) as f:
            content = f.read()
        return content
    except Exception as e:
        raise RuntimeError(f"read_file failed: {e}")

def list_files(directory):
    try:
        full_path = safe_path(directory)
        entries = os.listdir(full_path)
        lines = []
        for entry in entries:
            entry_path = os.path.join(full_path, entry)
            if os.path.isdir(entry_path):
                lines.append(entry + "/")
            else:
                lines.append(entry)
        output = "The directory contains:\n" + "\n".join(sorted(lines))
        return output
    except Exception as e:
        raise RuntimeError(f"list_files failed: {e}")

def delete_file(filepath):
    try:
        full_path = safe_path(filepath)
        os.remove(full_path)
        return f"File deleted: {filepath}"
    except Exception as e:
        raise RuntimeError(f"delete_file failed: {e}")

def create_directory(directory):
    try:
        full_path = safe_path(directory)
        os.makedirs(full_path, exist_ok=True)
        return f"Directory created: {directory}"
    except Exception as e:
        raise RuntimeError(f"create_directory failed: {e}")

def remove_directory(directory):
    try:
        full_path = safe_path(directory)
        os.rmdir(full_path)
        return f"Directory removed: {directory}"
    except Exception as e:
        raise RuntimeError(f"remove_directory failed: {e}")

def shell_command(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=working_dir)
        return {
            "stdout": result.stdout, 
            "stderr": result.stderr, 
            "returncode": result.returncode
        }
    except Exception as e:
        raise RuntimeError(f"shell_command failed: {e}")

# Initialize LLM and add tools
def initialize_llm(model="openrouter/optimus-alpha"):
    global llm, history, system_prompt
    
    llm = NominaLlm(default_model=model)
    
    # Append contents of nomina-rules.txt if it exists
    rules_path = os.path.join(working_dir, 'nomina-rules.txt')
    if os.path.isfile(rules_path):
        with open(rules_path, 'r') as f:
            rules = f.read()
            system_prompt += "\n" + rules
    
    # Initialize chat history
    history = [llm.make_text_message("system", system_prompt)]
    
    # Add tools to LLM
    llm.add_tool(write_file)
    llm.add_tool(read_file)
    llm.add_tool(list_files)
    llm.add_tool(delete_file)
    llm.add_tool(create_directory)
    llm.add_tool(remove_directory)
    llm.add_tool(shell_command)

# API Routes
@app.route('/api/chat', methods=['POST'])
def chat():
    global history
    
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"error": "Message is required"}), 400
    
    message = data['message']
    history.append(llm.make_text_message("user", message))
    
    try:
        response = llm.chat(history)
        reply = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        history.append(llm.make_text_message("assistant", reply))
        
        return jsonify({
            "success": True,
            "message": message,
            "reply": reply,
            "model": llm.default_model
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
            {"role": msg.role, "content": msg.content} 
            for msg in history 
            if msg.role != "system"  # Exclude system messages
        ]
    })

@app.route('/api/history/clear', methods=['POST'])
def clear_history():
    global history
    history = [history[0]]  # Keep only the system message
    return jsonify({"success": True, "message": "History cleared"})

@app.route('/api/reset', methods=['POST'])
def reset_memory():
    global llm, history
    
    model = llm.default_model  # Keep the current model
    initialize_llm(model)
    
    return jsonify({"success": True, "message": "Memory and LLM completely reset"})

@app.route('/api/models', methods=['GET'])
def get_models():
    try:
        models = llm.list_models()
        return jsonify({"models": models})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/model', methods=['GET'])
def get_current_model():
    return jsonify({"model": llm.default_model})

@app.route('/api/model', methods=['POST'])
def set_model():
    data = request.json
    if not data or 'model' not in data:
        return jsonify({"error": "Model ID is required"}), 400
    
    llm.default_model = data['model']
    return jsonify({"success": True, "model": llm.default_model})

@app.route('/api/files', methods=['GET'])
def get_file_list():
    directory = request.args.get('dir', '.')
    try:
        files = list_files(directory)
        return jsonify({"success": True, "files": files})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/files', methods=['POST'])
def create_file():
    data = request.json
    if not data or 'filepath' not in data or 'content' not in data:
        return jsonify({"error": "Filepath and content are required"}), 400
    
    try:
        result = write_file(data['filepath'], data['content'])
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/files', methods=['DELETE'])
def delete_file_route():
    data = request.json
    if not data or 'filepath' not in data:
        return jsonify({"error": "Filepath is required"}), 400
    
    try:
        result = delete_file(data['filepath'])
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/files/content', methods=['GET'])
def get_file_content():
    filepath = request.args.get('filepath')
    if not filepath:
        return jsonify({"error": "Filepath is required"}), 400
    
    try:
        content = read_file(filepath)
        return jsonify({"success": True, "content": content, "filepath": filepath})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/dir', methods=['POST'])
def create_dir():
    data = request.json
    if not data or 'directory' not in data:
        return jsonify({"error": "Directory path is required"}), 400
    
    try:
        result = create_directory(data['directory'])
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/dir', methods=['DELETE'])
def delete_dir():
    data = request.json
    if not data or 'directory' not in data:
        return jsonify({"error": "Directory path is required"}), 400
    
    try:
        result = remove_directory(data['directory'])
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/shell', methods=['POST'])
def run_shell():
    data = request.json
    if not data or 'command' not in data:
        return jsonify({"error": "Command is required"}), 400
    
    try:
        result = shell_command(data['command'])
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/api/info', methods=['GET'])
def get_info():
    return jsonify({
        "working_directory": working_dir,
        "model": llm.default_model,
        "version": "0.1.0"
    })

def main():
    """Entry point for the API server"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Nomina API Server")
    parser.add_argument("--dir", "-d", help="Working directory (default: current directory)", default=os.getcwd())
    parser.add_argument("--port", "-p", help="Port to run the server on", type=int, default=5000)
    parser.add_argument("--host", help="Host to run the server on", default="0.0.0.0")
    parser.add_argument("--model", "-m", help="Default model to use", default="openrouter/optimus-alpha")
    args = parser.parse_args()
    
    # Set working directory
    global working_dir
    working_dir = os.path.abspath(args.dir)
    if not os.path.isdir(working_dir):
        print(f"Error: {working_dir} is not a valid directory")
        return
    
    # Initialize LLM
    initialize_llm(args.model)
    
    # Display startup message
    print(f"Nomina API Server")
    print(f"Working directory: {working_dir}")
    print(f"Default model: {llm.default_model}")
    print(f"Starting server on http://{args.host}:{args.port}")
    
    # Start the Flask server
    app.run(debug=True, host=args.host, port=args.port)

if __name__ == '__main__':
    main()
