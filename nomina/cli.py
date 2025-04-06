import os, subprocess
from .nominallm import NominaLlm
jail_dir = None
def multiline_input(prompt="Paste input (end with END):"):
    print(prompt)
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()

def confirm_or_create_dir(base_dir):
    base_dir = os.path.abspath(base_dir)
    if not os.path.exists(base_dir):
        os.makedirs(base_dir, exist_ok=True)
    return base_dir


def safe_path(path):
    abs_path = os.path.abspath(os.path.join(jail_dir, path))
    if not abs_path.startswith(jail_dir):
        raise Exception(f"Access outside jail is denied: {abs_path}")
    return abs_path

def read_file(filepath):
    """Read file contents."""
    try:
        print(f"ℹ️  Nomina called `read_file` with {filepath}")
        full = safe_path(filepath)
        with open(full) as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"

def write_file(filepath, content):
    """Write content to file, overwriting."""
    try:
        print(f"ℹ️  Nomina called `write_file` with {filepath}")
        print(content)
        full = safe_path(filepath)
        with open(full, "w") as f:
            f.write(content)
        return f"Wrote {len(content)} bytes to {filepath}"
    except Exception as e:
        return f"Error: {e}"

def delete_file(filepath):
    """Delete a file."""
    try:
        print(f"ℹ️  Nomina called `delete_file` with {filepath}")
        full = safe_path(filepath)
        os.remove(full)
        return f"Deleted {filepath}"
    except Exception as e:
        return f"Error: {e}"

def make_dir(path):
    """Create a directory."""
    try:
        print(f"ℹ️  Nomina called `make_dir` with {path}")
        full = safe_path(path)
        os.makedirs(full, exist_ok=True)
        return f"Created {path}"
    except Exception as e:
        return f"Error: {e}"

def run_shell_command(command):
    """Run a shell command inside jail directory.

WARNING: Dangerous. Returns stdout+stderr."""
    try:
        print(f"ℹ️  Nomina called `run_shell_command` with {command}")
        res = subprocess.run(command, shell=True, cwd=jail_dir,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             encoding='utf-8', timeout=30)
        return res.stdout
    except Exception as e:
        return f"Error: {e}"


def main():
    global jail_dir
    llm = NominaLlm()

    for func in [read_file, write_file, delete_file, make_dir, run_shell_command]:
        llm.add_tool(func)

    system_prompt = """
    You are Nomina, an autonomous coding and shell assistant.

    - You **only** have access to a jailed directory — don't try to access outside it.
    - You **must** use the tools to read, modify, write files and run shell commands.
    - When asked to add new features, do the following:
        1. Read relevant files.
        2. Modify and save files using tools.
        3. Use the shell tool to test your changes.
        4. If tests fail, refine and retry.
    - Repeat steps 1-4 until confident it works.
    - Avoid repeated narration; take action instead.
    - Always report your **final status** succinctly.
    - Be careful with shell commands.
    """

    history = [
        llm.make_text_message("system", system_prompt)
    ]
    # ==== Select working directory (aka jail) ====
    jail_dir = os.getcwd()
    print(f"Nomina is jailed inside!: {jail_dir}")    
    print("\n🤖 Nomina (sandboxed jail and shell ready!)")
    print(f"Using model: {llm.default_model}")
    print("Paste prompts (multi-line) and end with a line `END`.")
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        user_inp = multiline_input()
        if user_inp.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        if not user_inp.strip():
            continue
        history.append(llm.make_text_message("user", user_inp))

        try:
            print("Sending..")
            response = llm.chat(history, temperature=0)
            reply = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            print("\n🤖 Nomina:\n" + reply)
            history.append(llm.make_text_message("assistant", reply))
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
