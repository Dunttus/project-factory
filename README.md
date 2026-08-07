# Unified AI Project Factory (`project_factory.py`)

A local, command-line tool that turns plain-English app descriptions into fully working Python applications with customized user interfaces—all running 100% locally on your machine with zero `pip` dependencies.

Describe a tool you want (e.g., *"a tool that monitors CPU usage and active processes"*), choose your preferred interface, and the factory generates, tests, and packages your new app into a dedicated project folder ready to launch.

---

### What it Does for You

* **Generates Complete, Working Applications:** Takes your high-level ideas and builds both the core logic (`backend.py`) and an interactive front-end.
* **Zero Dependency Installs (`zero pip`):** Every generated app uses Python's built-in standard library. You can run any created project out-of-the-box on standard Python without running `pip install` or managing virtual environments.
* **Your Choice of Interface:** Automatically wraps your tool in the interface style you prefer:
  * **Desktop GUI:** A native graphical window (Tkinter).
  * **Web Dashboard:** A single-file HTML/CSS/JS interface that auto-launches in your browser.
  * **Interactive CLI:** A structured terminal menu.
* **Self-Testing & Auto-Repair:** Automatically checks the generated code against your operating system (Windows, Linux, or macOS) to fix syntax errors and runtime bugs before saving the final app.
* **100% Local & Private:** Connects directly to your local **Ollama** instance (powered by `qwen2.5-coder:14b`).
* **Optional AI Prompt Optimization:** Refines simple or vague descriptions into detailed technical specifications before code generation begins, improving the quality of the final app.


## Key Features

* **Zero Third-Party Dependencies (`zero pip`):** Built 100% on Python's standard library (`urllib`, `ast`, `subprocess`, `json`, `re`, `platform`, `tkinter`, `webbrowser`, `tempfile`). No heavy orchestration frameworks (LangChain, CrewAI) or external API keys required.
* **Host OS Auto-Detection:** Automatically senses your operating system (`platform.system()`)—Linux, Windows, or macOS—and instructs the AI model to generate platform-native commands (`ps`/`/proc` on Linux vs. `tasklist` on Windows) and safe environment paths (`HOME` vs. `APPDATA`).
* **Optional Subprocess Dry-Run Testing:** User-controlled safety toggle upfront. When enabled, it executes generated backend code in an isolated subprocess to catch runtime errors (`KeyError`, `UnicodeDecodeError`, invalid file paths) and feeds tracebacks back to the AI for self-correction.
* **Upfront Prompt Collection:** Collects all project configuration choices at launch (Name, Backend Description, AI Spec Optimization, Dry-Run Toggle, UI Selection) before triggering AI generation.
* **Self-Healing Code Pipeline:** Uses Python's Abstract Syntax Tree (`ast.parse`) and optional runtime execution to validate code structure and repair syntax errors or broken imports dynamically.
* **Real-Time Token Output Tracker:** Streams LLM responses live to your terminal using Ollama's streaming API, displaying an active token counter and final generation metrics upon completion.
* **AI Prompt Optimizer Agent:** Optional pre-generation phase that passes raw user requests through a prompt engineer agent, expanding simple ideas into detailed, unambiguous technical specifications tailored to your host OS.
* **Strict Standard-Library Enforcement:** AST import inspection blocks forbidden third-party libraries (e.g., `psutil`, `requests`, `pandas`, `tabulate`), forcing the LLM to use native Python equivalents (`subprocess`, `urllib`, `sys`, `os`).
* **Multi-Interface Front-End Generator:** Choice of three front-end paradigms matching your generated backend logic:
  1. **Desktop GUI:** Native Python `tkinter` / `ttk` window application.
  2. **Standalone Web Dashboard:** Modern single-file `HTML/CSS/JS` dashboard auto-opened in your default browser.
  3. **Interactive CLI:** Structured terminal menu interface.
* **Isolated Project Workspaces:** Automatically structures generated apps into clean, dedicated directories (`./projects/<project_name>/`).


## Prerequisites & Requirements

| Component | Requirement |
| :--- | :--- |
| **Operating System** | Windows 10/11, Linux (Ubuntu/Debian), or macOS |
| **Python** | Python 3.10 or higher (Standard Library only) |
| **Local LLM Engine** | [Ollama](https://ollama.com/) running locally |
| **Recommended Model** | `qwen2.5-coder:14b` |


## Installation Guide

Follow these steps to set up the software factory on a new computer from scratch.

### Step 1: Install Python & GUI Dependencies
Ensure Python 3.10 or newer is installed on your machine.
* **Windows:** Download from [python.org](https://www.python.org/downloads/). **Check the box to "Add Python to PATH"** during installation.
* **Linux (Ubuntu/Debian):**
  ```bash
  sudo apt update
  sudo apt install python3 python3-pip python3-tk
  ```

### Step 2: Install and Configure Ollama
1. Download and install Ollama from [ollama.com](https://ollama.com/).
2. Verify Ollama is running in the background. If running manually on Linux/macOS, start it via terminal:
   ```bash
   ollama serve
   ```
3. Open a terminal and pull the recommended coding model (`qwen2.5-coder:14b`):
   ```bash
   ollama pull qwen2.5-coder:14b
   ```

### Step 3: Clone the Repository
Clone this repository to your local system and navigate into the folder:
```bash
git clone [https://github.com/Dunttus/agent-team-2.git](https://github.com/Dunttus/agent-team-2.git)
cd agent-team-2
```


## Quick Start / Usage

Run the factory script directly using Python:

```bash
python project_factory.py
```

### Step-by-Step Upfront Workflow

1. **Enter Project Name:**
   ```text
   1. Enter Project Name (e.g., Resource Monitor): resource_monitor
   ```
   *Automatically initializes `./projects/resource_monitor/`.*

2. **Describe Core Backend Logic:**
   ```text
   2. Describe the Core Backend Logic: Create a tool that monitors active process IDs and CPU/Memory usage.
   ```

3. **Optional AI Prompt Optimization:**
   ```text
   Enhance prompt with AI for higher code accuracy? (y/N): y
   ```

4. **Optional Subprocess Dry-Run Toggle:**
   ```text
   [WARNING: Dry-run testing directly executes AI-generated code on your system!]
      Enable live subprocess dry-run testing on host (Linux)? (y/N): n
   ```

5. **Select Front-End Interface:**
   ```text
   3. Select Front-End Interface Type:
      [1] Desktop GUI (Python Tkinter - standard library)
      [2] Standalone Web UI (HTML/CSS/JS Dashboard)
      [3] CLI Interactive Dashboard (Terminal menu)
   Select choice (1, 2, or 3): 1
   ```

6. **Automatic Assembly & Launch:**
   * **Backend Generation:** Writes `backend.py` with live token counters and OS-specific prompts.
   * **Frontend Generation:** Generates `app_gui.py` with AST-validated `import backend` linkages.
   * **Launch:** Run your new application:
     ```bash
     python projects/resource_monitor/app_gui.py
     ```


## Project Output Structure

All generated projects are isolated inside the `projects/` directory:

```text
project_factory.py          # Main autonomous software factory script
└── projects/                   # Generated projects directory
    └── resource_monitor/       # Isolated project folder
        ├── backend.py          # Modular Python backend (tested & verified)
        ├── app_gui.py          # Tkinter Desktop App (if Choice 1)
        ├── index.html          # Web UI Dashboard (if Choice 2)
        └── cli_app.py          # Terminal CLI Menu (if Choice 3)
```

---

## How It Works Under the Hood

```
[ User Input ] ──> [ Upfront Config Collection ]
                   (OS Auto-Detected: Linux/Win/Mac)
                          │
                          ▼
             [ Prompt Optimizer Agent ] (Optional)
                          │
                          ▼
            [ Dev Agent: Backend Generation ]
             (Live Streaming Token Tracker)
                          │
                          ▼
             [ AST Inspection & Blacklist Check ]
           (Rejects psutil, requests, pandas, etc.)
                          │
                          ▼
            [ Subprocess Dry-Run Test (Optional) ]
            (Executes code in host OS runtime)
                          │
            ├── Fail? ──> [ Auto-Repair Feedback Loop ] (Max 4 Retries)
            └── Pass? ──> [ Save backend.py ]
                          │
                          ▼
            [ UI Agent: Front-End Generation ]
             (Tkinter GUI / Web HTML / Terminal CLI)
                          │
                          ▼
             [ AST Validation & Import Verification ]
                          │
                          ▼
             [ Final Project Assembly & Launch ]
```

---

## ⚠️ Safety Disclaimer & Risk Notice

> [!WARNING]
> **PLEASE READ CAREFULLY BEFORE EXECUTING GENERATED CODE:**
>
> 1. **AI Hallucinations & Flaws:** Generative AI models (including local LLMs) can produce code containing logic errors, security vulnerabilities, infinite loops, or unhandled exceptions despite self-healing AST checks.
> 2. **Local Execution Risk:** When dry-run testing is enabled, `project_factory.py` automatically executes generated Python code in a local `subprocess` on your machine. While standard-library enforcement blocks external packages, LLM code can still execute terminal commands or file system operations (e.g., via `subprocess` or `os`).
> 3. **Environment Differences:** Commands written for Windows (`wmic`, `tasklist`, `%APPDATA%`) will fail on Linux/macOS. Always verify that your host OS detection matches your execution environment.
> 4. **Manual Inspection Recommended:** Always review the generated scripts in `./projects/<project_name>/` before running them with administrator/root privileges or on production machines.
> 5. **No Warranty & Limitation of Liability:** This software is provided "as is", without warranty of any kind. The authors and contributors are not liable for any data loss, system instability, or hardware/software damage resulting from running AI-generated code.


## 🤝 Credits

### 🧠 Project Team
* **Project Creator:** Dunttus
* **AI Assistance:** Built with Gemini

### 📚 Open Source Ecosystem
* **[Ollama](https://ollama.com/)** - Local LLM serving engine
* **[Qwen 2.5 Coder](https://github.com/QwenLM/Qwen2.5-Coder)** - Tested with base LLM model by Alibaba Cloud

---

## 📄 License

This project is licensed under the **GPL-3.0 License**.
