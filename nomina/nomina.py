import os
import subprocess
from textual.app import App
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Static, TextArea, Input, Button
from textual import on
from textual.binding import Binding
from textual.worker import Worker
from .nominallm import NominaLlm
from textual.widgets import Static, TextArea, Tabs, Tab
import re
def _sanitize_id(title: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", title)
system_prompt2 = """
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

class StatusBar(Static):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.status = "Ready"

    def update_status(self, message: str) -> None:
        self.status = message
        self.update(f"Status: {self.status}")


class FileViewer(Container):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.added_tabs = set()
        self.tab_contents = {}

    def compose(self):
        yield Static("Files", id="file-title")
        yield Tabs(id="file-tabs")
        yield TextArea(id="file-content", read_only=True, language="python")

    def set_content(self, title: str, content: str, language: str = "python") -> None:
        tab_id = _sanitize_id(title)
        self.tab_contents[tab_id] = (title, content, language)

        #file_title = self.query_one("#file-title", Static)
        #file_title.update(title)

        file_content = self.query_one("#file-content", TextArea)
        file_content.text = content
        file_content.language = language

    def add_tab(self, title: str) -> None:
        tab_id = _sanitize_id(title)
        if tab_id in self.added_tabs:
            return  # Already added

        self.added_tabs.add(tab_id)

        tabs = self.query_one("#file-tabs", Tabs)
        tabs.add_tab(Tab(title, id=tab_id))

        if tabs.active is None:
            tabs.active = tab_id



    @on(Tabs.TabActivated)
    def on_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id
        if tab_id in self.tab_contents:
            title, content, lang = self.tab_contents[tab_id]
            self.set_content(title, content, lang)



class ChatPanel(Container):
    def compose(self):
        yield Static("Chat History", id="chat-title")
        yield TextArea(read_only=True, id="chat-history")
        yield Input(placeholder="Type your message and press Enter...", id="chat-input")

    def add_message(self, sender: str, message: str) -> None:
        chat_area = self.query_one("#chat-history", TextArea)
        prefix = "🤖 Assistant:" if sender == "assistant" else "You:"
        current_text = chat_area.text
        new_text = current_text + f"\n{prefix}\n{message}\n"
        chat_area.text = new_text

        line_count = new_text.count('\n')
        if hasattr(chat_area, 'scroll_home'):
            chat_area.scroll_home(animate=False)
            for _ in range(line_count + 10):
                chat_area.scroll_down(animate=False)

        self.query_one("#chat-input", Input).focus()

    @on(Input.Submitted, "#chat-input")
    def handle_message_submission(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return

        input_widget = self.query_one("#chat-input", Input)
        input_widget.value = ""

        if hasattr(self.app, 'on_message_submitted'):
            self.app.on_message_submitted(message)

        input_widget.focus()


class SimpleTUI(App):
    TITLE = "Simple TUI"
    BINDINGS = [
        Binding("q", "quit", "Quit", key_display="q"),
        Binding("f1", "help", "Help", key_display="F1"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.working_dir = os.getcwd()

    def compose(self) -> Container:
        yield Header()
        yield Container(
            Horizontal(
                ChatPanel(id="chat-panel"),
                FileViewer(id="file-viewer"),
                id="main-container"
            ),
            id="app-container"
        )
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        chat_panel = self.query_one("#chat-panel", ChatPanel)
        welcome_text = f"Welcome to Simple TUI!\n\nWorking in directory: {self.working_dir}"
        chat_panel.add_message("assistant", welcome_text)

        input_box = self.query_one("#chat-input")
        input_box.focus()

    def action_help(self) -> None:
        help_text = """
Simple TUI Help:

- Enter messages in the input box and press Enter to send
- The file pane on the right shows content
- Press 'q' to quit the application
- Press 'F1' to show this help
"""
        self.add_chat_message("assistant", help_text)

    def set_file_content(self, title: str, content: str) -> None:
        try:
            viewer = self.query_one("#file-viewer", FileViewer)
            viewer.add_tab(title)
            viewer.set_content(title, content)
        except Exception as e:
            self.update_status(f"UI update error: {e}")
            # Do not propagate the error



    def add_chat_message(self, sender: str, message: str) -> None:
        chat_panel = self.query_one("#chat-panel", ChatPanel)
        chat_panel.add_message(sender, message)

    def update_status(self, message: str) -> None:
        status_bar = self.query_one("#status-bar", StatusBar)
        status_bar.update_status(message)

def safe_path(path):
    jail_dir = os.getcwd()    
    abs_path = os.path.abspath(os.path.join(jail_dir, path))
    if not abs_path.startswith(jail_dir):
        raise Exception(f"Access outside jail is denied: {abs_path}")
    return abs_path

def make_write_file_tool(app):
    def write_file(filepath, content):
        try:
            full_path = safe_path(filepath)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

            # Safely update UI from background thread
            def update_ui():
                app.set_file_content(filepath, content)

            app.call_from_thread(update_ui)

            return f"File written successfully: {filepath}"
        except Exception as e:
            raise RuntimeError(f"write_file failed: {e}")
    return write_file

def make_read_file_tool(app):
    def read_file(filepath):
        """Read file contents."""
        try:
            
            full = safe_path(filepath)
            
            # Read the file
            with open(full) as f:
                content = f.read()
            
            # Safely update UI from background thread
            def update_ui():
                app.set_file_content(filepath, content)

            app.call_from_thread(update_ui)
                
            return content
        except Exception as e:
            raise RuntimeError(f"read_file failed: {e}")
    return read_file

def make_list_files_tool(app):
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

            def update_ui():
                app.set_file_content(f"ls {directory}/", output)

            app.call_from_thread(update_ui)

            return output
        except Exception as e:
            raise RuntimeError(f"list_files failed: {e}")
    return list_files



def make_delete_file_tool(app):
    def delete_file(filepath):
        try:
            full_path = safe_path(filepath)
            os.remove(full_path)

            return f"File deleted: {filepath}"
        except Exception as e:
            raise RuntimeError(f"delete_file failed: {e}")
    return delete_file

def make_create_directory_tool(app):
    def create_directory(directory):
        try:
            full_path = safe_path(directory)
            os.makedirs(full_path, exist_ok=True)

            return f"Directory created: {directory}"
        except Exception as e:
            raise RuntimeError(f"create_directory failed: {e}")
    return create_directory

def make_remove_directory_tool(app):
    def remove_directory(directory):
        try:
            full_path = safe_path(directory)
            os.rmdir(full_path)


            return f"Directory removed: {directory}"
        except Exception as e:
            raise RuntimeError(f"remove_directory failed: {e}")
    return remove_directory

def make_shell_command_tool(app):
    def shell_command(command):
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)

            def update_ui():
                app.set_file_content(command, f"{result.stdout}\n{result.stderr}")

            app.call_from_thread(update_ui)

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            raise RuntimeError(f"shell_command failed: {e}")
    return shell_command

class MyApp(SimpleTUI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm = NominaLlm()
        self.system_prompt = system_prompt
        self.history = [
            self.llm.make_text_message("system", self.system_prompt)
        ]

    def on_mount(self):
        super().on_mount()
        self.llm.add_tool(make_write_file_tool(self))
        self.llm.add_tool(make_read_file_tool(self))
        self.llm.add_tool(make_list_files_tool(self))
        self.llm.add_tool(make_delete_file_tool(self))
        self.llm.add_tool(make_create_directory_tool(self))
        self.llm.add_tool(make_remove_directory_tool(self))
        self.llm.add_tool(make_shell_command_tool(self))

    def on_message_submitted(self, message: str) -> None:
        self.add_chat_message("user", message)
        self.update_status("Thinking...")
        self.history = [
            self.llm.make_text_message("system", self.system_prompt),
            self.llm.make_text_message("user", message)
        ]
        self.run_worker(self.llm_worker, exclusive=True, name="llm")

    async def llm_worker(self) -> None:
        import asyncio
        async def run_in_thread(func, *args, **kwargs):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, func, *args, **kwargs)

        response = await run_in_thread(self.llm.chat, self.history)
        reply = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        self.add_chat_message("assistant", reply)
        self.update_status("Ready")


def main():
    app = MyApp()
    app.run()

if __name__ == "__main__":
    main()
