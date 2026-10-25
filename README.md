# Unified AI Project Factory (`project_factory.py`)

A 100% local, zero-dependency Python application generator powered by **Ollama**. Describe an app in plain English, pick your interface, and the factory designs, cross-validates, smoke-tests, and packages a complete working project (`backend.py` + interactive frontend) using only Python's standard library.

---

## Key Features

- **Built-in Studio GUI & Headless CLI:** Launch the interactive **Tkinter Studio UI** (with live Ollama model discovery, real-time streaming logs, code inspector tabs, and one-click app launching) or run in terminal mode via `--cli`.
- **100% Standard Library (`zero pip`):** Enforces Python's native `sys.stdlib_module_names` whitelist via AST inspection—generated apps never require `pip install` or virtual environments.
- **3 Target Front-End Interfaces:**
  1. **Desktop GUI (`app_gui.py`):** Native `tkinter` / `ttk` desktop window.
  2. **Full-Stack Web Dashboard (`web_app.py`):** Local Python `http.server` with JSON API endpoints and an embedded HTML/CSS/JS frontend.
  3. **Interactive CLI (`cli_app.py`):** Structured terminal menu interface.
- **Cross-File AST Contract Verification:** Automatically extracts public function and class signatures from `backend.py` and verifies that the generated frontend only calls symbols that actually exist.
- **Multi-Turn Self-Healing & Smoke Testing:** Validates syntax with `ast.parse()` and optionally runs `backend._self_test()` in a sandboxed subprocess on your host OS (Windows, Linux, or macOS), feeding tracebacks into a multi-turn repair loop.
- **AI Prompt Optimizer:** Optional pre-processing step that expands brief ideas into strict technical specifications before code generation.

---

## How the Generation Pipeline Works

```text
[ User Input (Studio GUI / --cli) ] ──> [ Host OS Auto-Detection (Win / Linux / macOS) ]
                                                        │
                                                        ▼
                                        [ AI Prompt Optimizer ] (Optional)
                                                        │
                                                        ▼
                                        [ Stage 1: Generate backend.py ]
                                                        │
                                                        ▼
                                  ┌───> [ AST Syntax & Stdlib Whitelist Check ]
                                  │                     │
      Multi-Turn Auto-Repair      │                     ▼
        (Up to 4 Retries)         │     [ Subprocess _self_test() Smoke Run ] (Optional)
                                  │                     │
                                  └─────── Fail ────────┼─────── Pass
                                                        │
                                                        ▼
                                        [ AST Public API Contract Extraction ]
                                        (Extracts exact functions & classes)
                                                        │
                                                        ▼
                                        [ Stage 2: Generate Frontend UI ]
                                        (app_gui.py / web_app.py / cli_app.py)
                                                        │
                                                        ▼
                                  ┌───> [ Cross-File AST Symbol Verification ]
                                  │     (Verifies every backend.<func> exists)
      Multi-Turn Auto-Repair      │                     │
        (Up to 4 Retries)         └─────── Fail ────────┼─────── Pass
                                                        │
                                                        ▼
                                        [ Saved to ./projects/<project_name>/ ]
                                        (One-Click Launch from Studio GUI)
```

---

## Requirements & Quick Setup

| Component | Requirement |
| :--- | :--- |
| **OS** | Windows 10/11, Linux, or macOS |
| **Python** | Python 3.10+ (Standard Library + `tkinter`) |
| **LLM Engine** | [Ollama](https://ollama.com/) running locally (`http://127.0.0.1:11434`) |
| **Default Model** | `qwen2.5-coder:14b` (or any coding model installed in Ollama) |

### Installation

```bash
# 1. Linux (Ubuntu/Debian) only: ensure Tkinter is installed
sudo apt update && sudo apt install -y python3 python3-tk

# 2. Pull the recommended coding model in Ollama
ollama pull qwen2.5-coder:14b

# 3. Clone the repository
git clone [https://github.com/Dunttus/project-factory.git](https://github.com/Dunttus/project-factory.git)
cd project-factory
```

---

## Usage

### 1. Studio GUI Mode (Default)
```bash
python project_factory.py
```
1. Select your **Ollama Model**, enter a **Project Name**, and describe the **Core Backend Logic**.
2. Choose your target interface (**Desktop GUI**, **Web Dashboard**, or **CLI**) and verification toggles.
3. Click **Generate Application**, inspect the generated code in the tabs, and click **Launch Generated App**.

### 2. Terminal CLI Mode
```bash
python project_factory.py --cli
```
Follow the interactive terminal prompts to configure and generate your project in headless environments.

---

## Generated Project Structure

Each generated app is saved in an isolated folder under `./projects/`:

```text
project_factory.py             # AI Project Factory Studio (GUI + CLI)
└── projects/
    └── <project_name>/
        ├── backend.py         # Stdlib Python backend + _self_test()
        ├── app_gui.py         # Tkinter Desktop GUI (Choice 1)
        ├── web_app.py         # http.server + HTML/JS Dashboard (Choice 2)
        └── cli_app.py         # Interactive Terminal Menu (Choice 3)
```

---

## ⚠️ Safety Notice

> [!WARNING]
> - **Local Subprocess Execution:** Enabling the live smoke test executes AI-generated Python code locally on your machine. Always review generated scripts in `./projects/<project_name>/` before running them with elevated privileges.
> - **No Warranty:** Provided *"as is"* without warranty of any kind. The authors are not liable for any data loss or system issues resulting from executing AI-generated code.

---

## 🤝 Credits & License

- **Project Creator:** [Dunttus](https://github.com/Dunttus/project-factory)
- **AI Assistance:** Built with Gemini
- **Ecosystem:** Powered by [Ollama](https://ollama.com/) & [Qwen 2.5 Coder](https://github.com/QwenLM/Qwen2.5-Coder)
- **License:** [GPL-3.0 License](LICENSE)
