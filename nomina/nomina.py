import os
import subprocess
from textual.app import App
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, TextArea, Input, Button, Label, Select, Tabs
from textual import on
from textual.binding import Binding
from textual.worker import Worker
from .nominallm import NominaLlm
from . import TabsWithClose
from textual.widgets import Tab
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
        yield Static("Activity", id="file-title")
        yield TabsWithClose(id="file-tabs")
        yield TextArea.code_editor(id="file-content", read_only=True, soft_wrap=True)

    def set_content(self, title: str, content: str, language: str = "python") -> None:
        tab_id = _sanitize_id(title)
        self.tab_contents[tab_id] = (title, content, language)
        file_content = self.query_one("#file-content", TextArea)
        file_content.text = content
        file_content.language = language

        tabs = self.query_one("#file-tabs", TabsWithClose)
        if tabs.active != tab_id:
            tabs.active = tab_id

    def add_tab(self, title: str) -> None:
        tab_id = _sanitize_id(title)
        if tab_id in self.added_tabs:
            return
        self.added_tabs.add(tab_id)
        tabs = self.query_one("#file-tabs", TabsWithClose)
        tabs.add_tab(Tab(title, id=tab_id))
        if tabs.active is None:
            tabs.active = tab_id

    def close_tab(self, tab_id: str):
        tabs = self.query_one("#file-tabs", TabsWithClose)
        tabs.remove_tab(tab_id)
        if tab_id in self.added_tabs:
            self.added_tabs.remove(tab_id)
        if tab_id in self.tab_contents:
            del self.tab_contents[tab_id]

        if tabs.tabs:
            first_tab = next(iter(tabs.tabs))
            tabs.active = first_tab
            t, c, l = self.tab_contents.get(first_tab, ("", "", "python"))
            self.set_content(t, c, l)
        else:
            file_content = self.query_one("#file-content", TextArea)
            file_content.text = ""
    @on(Tabs.TabActivated)
    def on_tab_activated(self, event: Tabs.TabActivated) -> None:
        tab_id = event.tab.id
        if tab_id in self.tab_contents:
            title, content, lang = self.tab_contents[tab_id]
            self.set_content(title, content, lang)

class ChatPanel(Container):
    def compose(self):
        yield Static("Chat History", id="chat-title")
        yield TextArea.code_editor(read_only=True, show_line_numbers=False, soft_wrap=True, id="chat-history", language="markdown")
        yield Horizontal(
            TextArea(id="chat-input", classes="chat-input"),
            Button("Send", id="send-button"),
            id="chat-input-container"
        )
        #yield Label("Type your message... (or click Send)", id="chat-hint")

    def add_message(self, sender: str, message: str) -> None:
        chat_area = self.query_one("#chat-history", TextArea)
        #prefix = "\U0001F916 Assistant:" if sender == "assistant" else "You:"
        prefix = sender
        current_text = chat_area.text
        new_text = current_text + f"\n{prefix}\n{message}\n"
        chat_area.text = new_text

        line_count = new_text.count('\n')
        if hasattr(chat_area, 'scroll_home'):
            chat_area.scroll_home(animate=False)
            for _ in range(line_count + 10):
                chat_area.scroll_down(animate=False)
        self.query_one("#chat-input", TextArea).focus()

    @on(Button.Pressed, "#send-button")
    def send_button_pressed(self):
        self.submit_message()

    def submit_message(self):
        input_widget = self.query_one("#chat-input", TextArea)
        message = input_widget.text.strip()
        if not message:
            return
        input_widget.text = ""
        if hasattr(self.app, 'on_message_submitted'):
            self.app.on_message_submitted(message)
        input_widget.focus()


class ModelPicker(Container):
    def compose(self):
        yield Label("Select OpenRouter Model:", id="model-label")
        self.select = Select(options=[], id="model-select")
        yield self.select
        yield Button("Set Model", id="set-model-btn")
        yield Button("Cancel", id="cancel-model-btn")

    async def on_mount(self) -> None:
        self.app.update_status("Fetching models...")
        self.app.run_worker(self.load_models, exclusive=True, name="fetch_models")

    async def load_models(self) -> None:
        import asyncio

        def blocking_fetch():
            try:
                models = self.app.llm.list_models()
                return [(m["name"], m["id"]) for m in models]
            except Exception as e:
                return f"Model fetch failed: {e}"

        loop = asyncio.get_event_loop()
        options = await loop.run_in_executor(None, blocking_fetch)
        if isinstance(options, str):
            self.app.update_status(options)
            return
        container = self
        old_select = container.query_one("#model-select", Select)
        await old_select.remove()
        new_select = Select(options=options, id="model-select")
        self.select = new_select
        cancel_btn = container.query_one("#cancel-model-btn", Button)
        await container.mount(new_select, before=cancel_btn)
        self.app.update_status("Models loaded." if options else "No models found.")

    @on(Button.Pressed, "#set-model-btn")
    def set_model(self):
        sel = self.query_one("#model-select", Select)
        selected = sel.value
        self.app.llm.default_model = selected
        self.app.update_status(f"Model set to: {selected}")
        self.remove()

    @on(Button.Pressed, "#cancel-model-btn")
    def cancel_picker(self):
        self.remove()


class SimpleTUI(App):
    CSS_PATH = "style.css"
    TITLE = "Nomina"
    BINDINGS = [
        Binding("q", "quit", "Quit", key_display="q"),
        Binding("f1", "help", "Help", key_display="F1"),
        Binding("f2", "pick_model", "Select Model", key_display="F2"),
        Binding("f3", "close_tab", "Close Tab", key_display="F3"),
        Binding("ctrl+w", "close_tab", "Close Tab", key_display="Ctrl+W"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.working_dir = os.getcwd()
        self.mounted = False
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
        if not self.mounted:
            chat_panel = self.query_one("#chat-panel", ChatPanel)
            welcome_text = f"Welcome to Nomina!\n\nWorking in directory: {self.working_dir}"
            chat_panel.add_message("assistant", welcome_text)
            input_box = self.query_one("#chat-input")
            input_box.focus()
            self.mounted = True


    def action_help(self) -> None:
        help_text = """Nomina Help:

- Enter messages then click Send
- The file pane on the right shows content
- Press 'q' to quit the application
- Press 'F1' to show this help
- Press F2 to pick the OpenRouter model
- Press F3 or Ctrl+W to close the active file tab"""
        self.add_chat_message("assistant", help_text)

    def action_pick_model(self):
        self.mount(ModelPicker(), before="#status-bar")

    def action_close_tab(self):
        try:
            viewer = self.query_one("#file-viewer", FileViewer)
            tabs = viewer.query_one("#file-tabs", TabsWithClose)
            tab_id = tabs.active
            if tab_id:
                viewer.close_tab(tab_id)
                self.update_status(f"Closed tab: {tab_id}")
            else:
                self.update_status("No active tab to close.")
        except Exception as e:
            self.update_status(f"Close tab error: {e}")

    def set_file_content(self, title: str, content: str) -> None:
        try:
            viewer = self.query_one("#file-viewer", FileViewer)
            viewer.add_tab(title)
            viewer.set_content(title, content)
        except Exception as e:
            self.update_status(f"UI update error: {e}")

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

            def update_ui():
                app.set_file_content(filepath, content)
            app.call_from_thread(update_ui)
            return f"File written successfully: {filepath}"
        except Exception as e:
            raise RuntimeError(f"write_file failed: {e}")

    return write_file


def make_read_file_tool(app):
    def read_file(filepath):
        try:
            full = safe_path(filepath)
            with open(full) as f:
                content = f.read()

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
            return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
        except Exception as e:
            raise RuntimeError(f"shell_command failed: {e}")

    return shell_command


class MyApp(SimpleTUI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llm = NominaLlm()
        self.system_prompt = system_prompt
        self.history = [self.llm.make_text_message("system", self.system_prompt)]

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
        self.update_status(f"{self.llm.default_model} is thinking... ")
        self.history.append(self.llm.make_text_message("user", message))
        self.run_worker(self.llm_worker, exclusive=True, name="llm")

    async def llm_worker(self) -> None:
        import asyncio

        async def run_in_thread(func, *args, **kwargs):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, func, *args, **kwargs)

        response = await run_in_thread(self.llm.chat, self.history)
        reply = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        self.add_chat_message(self.llm.default_model, reply)
        self.history.append(self.llm.make_text_message("assistant", reply))
        self.update_status("Ready")


def main():
    app = MyApp()
    app.run()


if __name__ == "__main__":
    main()
