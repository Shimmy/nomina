# Nomina

Nomina is an autonomous coding assistant with a jailed shell environment. It allows you to interact with an AI-powered assistant that can read, modify, create files, and run shell commands within a sandboxed environment.

## Features

- AI-powered coding assistant
- Sandboxed shell execution
- File manipulation (read/write/delete/create)
- Terminal UI and command-line interface
- Secure execution environment

## Installation

You can install Nomina directly from GitHub:

```bash
pip install git+https://github.com/Shimmy/nomina.git
```

## Prerequisites

Nomina requires an OpenRouter API key to function. You can set it as an environment variable:

```bash
export OPENROUTER_API_KEY="your_api_key_here"
```

Alternatively, you can provide it directly when initializing the `NominaLlm` class.

## Usage

### Command Line Interface

After installation, you can run Nomina from the command line:

```bash
nomina
```

This will start Nomina in the current directory, which will be used as the "jail" directory. The assistant will only have access to files within this directory.

### Terminal UI

Nomina also comes with a terminal-based user interface:

```bash
python -m nomina.nomina_ui
```

### Python API

You can also use Nomina programmatically in your Python applications:

```python
from nomina.nominallm import NominaLlm

# Initialize with API key (or set OPENROUTER_API_KEY environment variable)
llm = NominaLlm(api_key="your_api_key_here")

# Add tools as needed
from nomina.cli import read_file, write_file
llm.add_tool(read_file)
llm.add_tool(write_file)

# Create messages
messages = [
    llm.make_text_message("system", "You are a helpful assistant."),
    llm.make_text_message("user", "Please read the content of example.txt")
]

# Get a response
response = llm.chat(messages)
```

## Safety Features

Nomina implements several safety features:

- Execution is confined to a "jail" directory
- File operations are restricted to within the jail
- Shell commands run with timeouts and inside the jail
- Path traversal attacks are prevented

## Examples

### Adding a Feature to a Project

```
I need to add a config file feature to the application. Can you implement a JSON configuration loader?
END
```

### Exploring a Codebase

```
Please analyze the code structure and explain how the main components interact.
END
```

### Running Tests

```
Can you create and run some unit tests for the NominaLlm class?
END
```

## Default Model

By default, Nomina uses the `openrouter/quasar-alpha` model. You can change this by setting the `default_model` parameter when initializing `NominaLlm`.

## License

[License information]

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
