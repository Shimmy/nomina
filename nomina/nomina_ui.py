import npyscreen
import curses
import threading
import queue
import os
import sys

sys.path.insert(0, os.path.abspath('.'))
from nomina.nominallm import NominaLlm

MIN_ROWS = 15
MIN_COLS = 60

class NominaUI(npyscreen.NPSAppManaged):
    def onStart(self):
        max_y, max_x = self._get_term_size()
        if max_y < MIN_ROWS or max_x < MIN_COLS:
            npyscreen.notify_wait(f"Terminal too small! Min: {MIN_ROWS}x{MIN_COLS}, Now: {max_y}x{max_x}", title="Resize Terminal")
            exit(1)
        self.addForm('MAIN', MainForm, name='Nomina TUI')

    def _get_term_size(self):
        try:
            stdscr = curses.initscr()
            max_y, max_x = stdscr.getmaxyx()
            curses.endwin()
            return max_y, max_x
        except:
            return 0, 0

class MainForm(npyscreen.FormBaseNew):
    def create(self):
        self.output = self.add(npyscreen.Pager, name='Nomina Output', max_height=-6)
        self.input = self.add(npyscreen.MultiLineEdit, name='Your Prompt (end with END)', max_height=4)
        self.send_button = self.add(npyscreen.ButtonPress, name='Send')
        self.send_button.whenPressed = self.send_prompt

        self.history = []
        self.displayed_history = []
        self.prompt_queue = queue.Queue()
        self.lock = threading.Lock()

        self.llm = NominaLlm()
        import nomina.cli as cli
        cli.jail_dir = os.getcwd()
        for func in [cli.read_file, cli.write_file, cli.delete_file, cli.make_dir, cli.run_shell_command]:
            self.llm.add_tool(func)

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
        self.chat_history = [self.llm.make_text_message("system", system_prompt)]

        threading.Thread(target=self.llm_loop, daemon=True).start()

    def while_waiting(self):
        max_y, max_x = self.parent.curses_pad.getmaxyx()
        if max_y < MIN_ROWS or max_x < MIN_COLS:
            npyscreen.notify_wait(f"Terminal resized too small! Min: {MIN_ROWS}x{MIN_COLS}, Now: {max_y}x{max_x}", title="Resize Terminal")

    def send_prompt(self):
        prompt = self.input.value.strip()
        if not prompt:
            return
        if not prompt.endswith('END'):
            prompt += '\nEND'
        self.prompt_queue.put(prompt)
        self.input.value = ''
        self.display()

    def llm_loop(self):
        while True:
            prompt = self.prompt_queue.get()
            if prompt.lower() in ('exit', 'quit'):
                break
            self.append_output(f"You: {prompt}")
            self.chat_history.append(self.llm.make_text_message("user", prompt))
            try:
                response = self.llm.chat(self.chat_history, temperature=0)
                reply = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                self.chat_history.append(self.llm.make_text_message("assistant", reply))
                self.append_output(f"Nomina:\n{reply}")
            except Exception as e:
                self.append_output(f"[Error: {e}]")

    def append_output(self, text):
        with self.lock:
            self.displayed_history.extend(text.splitlines())
            self.output.values = self.displayed_history[-200:]
            self.display()

if __name__ == '__main__':
    NominaUI().run()
