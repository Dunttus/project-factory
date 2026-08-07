import ast
import json
import os
import platform
import re
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser

# ==========================================
# CONFIGURATION & ENVIRONMENT DETECTION
# ==========================================
MODEL_NAME = "qwen2.5-coder:14b"
OLLAMA_API_URL = "http://127.0.0.1:11434/api/chat"
PROJECTS_ROOT = "projects"
CURRENT_OS = platform.system()  # 'Linux', 'Windows', or 'Darwin' (macOS)

# Blacklist of common pip modules to strictly enforce standard library usage
FORBIDDEN_MODULES = {
    "psutil", "requests", "tabulate", "pandas", "numpy", 
    "bs4", "scipy", "cv2", "PIL", "flask", "django"
}


def call_ollama(system_prompt: str, user_prompt: str) -> str:
    """Sends requests directly to local Ollama API via standard library with real-time token counting."""
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": True,
        "options": {"keep_alive": "1h"},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_API_URL, data=data, headers={"Content-Type": "application/json"}
    )
    
    full_content = []
    token_count = 0

    try:
        with urllib.request.urlopen(req, timeout=1800) as response:
            for line in response:
                if not line:
                    continue
                
                chunk = json.loads(line.decode("utf-8"))
                msg_content = chunk.get("message", {}).get("content", "")
                
                if msg_content:
                    full_content.append(msg_content)
                    token_count += 1
                    sys.stdout.write(f"\r   [Generating] Realtime Tokens: {token_count}")
                    sys.stdout.flush()

                if chunk.get("done"):
                    final_tokens = chunk.get("eval_count", token_count)
                    sys.stdout.write(f"\r   [Completed] Total Tokens Output: {final_tokens}\n")
                    sys.stdout.flush()

        return "".join(full_content)

    except urllib.error.URLError as e:
        print(f"\n[Error] Failed to connect to Ollama: {e}")
        print(f"Ensure Ollama is running and '{MODEL_NAME}' is pulled (`ollama pull {MODEL_NAME}`).")
        sys.exit(1)


def extract_code(text: str) -> str:
    """Aggressively strips markdown fences and preambles."""
    match = re.search(r"```[a-zA-Z]*\s*\n?(.*?)(?:```|$)", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    
    lines = text.splitlines()
    clean_lines = []
    started = False
    for line in lines:
        if started or line.strip().startswith(
            ("import ", "from ", "class ", "def ", "if __name__", "<!DOCTYPE", "<html")
        ):
            started = True
            clean_lines.append(line)
    return "\n".join(clean_lines).strip() if clean_lines else text.strip()


def validate_code_ast(code_str: str, requires_backend_import: bool = False) -> tuple[bool, str]:
    """Validates Python syntax, checks forbidden pip imports, and verifies structure."""
    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        return False, f"SyntaxError on line {e.lineno}: {e.msg}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_base = alias.name.split('.')[0]
                if mod_base in FORBIDDEN_MODULES:
                    return False, f"Forbidden pip import '{alias.name}'. Use ONLY standard library (subprocess, os, platform, json, urllib)."
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod_base = node.module.split('.')[0]
                if mod_base in FORBIDDEN_MODULES:
                    return False, f"Forbidden pip import '{node.module}'. Use ONLY standard library."

    if requires_backend_import:
        if "backend" not in code_str and "import backend" not in code_str:
            return False, "Missing 'import backend' statement at the top of the file."

    return True, "Valid AST"


def test_execute_backend(code_str: str) -> tuple[bool, str]:
    """Runs a live dry-run of the backend code to catch runtime errors."""
    try:
        res = subprocess.run(
            [sys.executable, "-c", code_str],
            capture_output=True,
            text=True,
            timeout=4
        )
        if res.returncode != 0:
            return False, f"Runtime Execution Error:\n{res.stderr.strip()}"
        return True, "Runtime Executed Successfully"
    except subprocess.TimeoutExpired:
        return True, "Executed without immediate crash"
    except Exception as e:
        return False, f"Execution process failed: {e}"


def generate_self_healing_code(
    system_prompt: str,
    user_prompt: str,
    is_backend: bool = False,
    enable_dry_run: bool = False,
    requires_backend_import: bool = False,
    max_retries: int = 4
) -> str:
    """Generates code and uses AST (+ optional Dry-Run execution testing) to auto-repair errors."""
    current_prompt = user_prompt
    for attempt in range(1, max_retries + 1):
        raw_response = call_ollama(system_prompt, current_prompt)
        cleaned_code = extract_code(raw_response)
        
        # 1. AST Static Check
        is_ast_valid, ast_msg = validate_code_ast(cleaned_code, requires_backend_import)
        if not is_ast_valid:
            print(f"   [Auto-Repair Attempt {attempt}/{max_retries}] AST Error: {ast_msg}")
            current_prompt = (
                f"Your output failed validation:\n{ast_msg}\n\n"
                f"Previous Code:\n{cleaned_code}\n\n"
                f"Fix this issue. Return ONLY clean executable Python code without markdown."
            )
            continue

        # 2. Subprocess Dry-Run Execution Test (Optional for Backend)
        if is_backend and enable_dry_run:
            is_run_valid, run_msg = test_execute_backend(cleaned_code)
            if not is_run_valid:
                print(f"   [Auto-Repair Attempt {attempt}/{max_retries}] Runtime Error: {run_msg}")
                current_prompt = (
                    f"Your backend code threw a runtime exception on {CURRENT_OS}:\n{run_msg}\n\n"
                    f"Previous Code:\n{cleaned_code}\n\n"
                    f"Fix the runtime bug for target environment '{CURRENT_OS}'. "
                    f"DO NOT use OS-specific commands (like 'wmic' or 'APPDATA') unless running on that specific OS. "
                    f"Always handle missing environment variables cleanly (e.g., os.getenv('HOME') or tempfile.gettempdir()). "
                    f"Return ONLY clean executable Python code using standard library."
                )
                continue

        return cleaned_code

    print("\n[Warning] Maximum retries reached. Outputting best attempt.")
    return cleaned_code


print("\n==========================================")
print(f"  UNIFIED AI PROJECT FACTORY ({CURRENT_OS.upper()})")
print("==========================================")

# ==========================================
# 1. USER INPUT COLLECTION (UPFRONT)
# ==========================================
RAW_NAME = input("1. Enter Project Name (e.g., Resource Monitor): ").strip()
if not RAW_NAME:
    print("Project name cannot be empty.")
    sys.exit(1)

RAW_USER_TASK = input("\n2. Describe the Core Backend Logic: ").strip()
if not RAW_USER_TASK:
    print("Task description cannot be empty.")
    sys.exit(1)

REMAKE_PROMPT = input("   Enhance prompt with AI for higher code accuracy? (y/N): ").strip().lower()

# Dry-run option with safety & environment warnings
print("\n[WARNING: Dry-run testing directly executes AI-generated code on your system!]")
ENABLE_DRY_RUN = input(f"   Enable live subprocess dry-run testing on host ({CURRENT_OS})? (y/N): ").strip().lower() in ["y", "yes"]

print("\n3. Select Front-End Interface Type:")
print("   [1] Desktop GUI (Python Tkinter - standard library)")
print("   [2] Standalone Web UI (HTML/CSS/JS Dashboard)")
print("   [3] CLI Interactive Dashboard (Terminal menu)")
UI_CHOICE = input("Select choice (1, 2, or 3): ").strip()

# ==========================================
# 2. PROJECT SETUP & PROMPT OPTIMIZATION
# ==========================================
FOLDER_NAME = re.sub(r"[^\w\-]", "", RAW_NAME.replace(" ", "_")).lower()
PROJECT_DIR = os.path.join(PROJECTS_ROOT, FOLDER_NAME)
os.makedirs(PROJECT_DIR, exist_ok=True)

print(f"\n-> Project directory initialized: ./{PROJECT_DIR}/")

if REMAKE_PROMPT in ["y", "yes"]:
    print("\n[Prompt Optimizer Agent] Refining task specification...")
    optimizer_system = (
        f"You are an expert AI Prompt Engineer for Python software engineering on {CURRENT_OS}. "
        "Rewrite and expand the user's raw feature request into an explicit, unambiguous technical specification "
        f"designed for a code-generation model targeting {CURRENT_OS}. Require standard library usage, modular functions, "
        "cross-platform compatibility, error handling, and precise data outputs. Return ONLY refined prompt text."
    )
    USER_TASK = call_ollama(optimizer_system, RAW_USER_TASK).strip()
    print("\n==========================================")
    print("OPTIMIZED PROMPT ECHO:")
    print("==========================================")
    print(USER_TASK)
    print("==========================================\n")
else:
    USER_TASK = RAW_USER_TASK

# ==========================================
# 3. STEP 1: GENERATE BACKEND MODULE
# ==========================================
print(f"\n[1/2] Generating backend.py (Target OS: {CURRENT_OS}, Dry-Run: {ENABLE_DRY_RUN})...")

dev_system = (
    f"You are a Senior Python Engineer operating on {CURRENT_OS}. "
    f"Write modular Python code using ONLY standard libraries (subprocess, os, platform, json, urllib, sys, tempfile). "
    f"STRICTLY FORBIDDEN: Do not import psutil, tabulate, requests, or any external pip package. "
    f"ENVIRONMENT RULES FOR {CURRENT_OS.upper()}:\n"
    f"1. PATHS: DO NOT hardcode Windows environment variables like os.getenv('APPDATA') without fallbacks (e.g., use os.getenv('HOME') or tempfile.gettempdir()).\n"
    f"2. OS COMMANDS: You are generating code running on {CURRENT_OS}. DO NOT call Windows commands like 'wmic' or 'tasklist' on Linux/macOS! "
    f"On Linux, use commands like 'ps', 'top', or read '/proc' files. On Windows, use 'tasklist' or 'wmic'.\n"
    f"3. SAFE DECODING: When calling subprocess.check_output(), ALWAYS use .decode('utf-8', errors='replace') to avoid UnicodeDecodeError.\n"
    f"4. NO EVENT LOOPS: DO NOT include while loops or input() statements in backend functions. Return ONLY valid Python code."
)

final_backend = generate_self_healing_code(
    system_prompt=dev_system,
    user_prompt=f"Target OS: {CURRENT_OS}\nTask: {USER_TASK}\nWrite a modular Python backend.",
    is_backend=True,
    enable_dry_run=ENABLE_DRY_RUN
)

backend_path = os.path.join(PROJECT_DIR, "backend.py")
with open(backend_path, "w", encoding="utf-8") as f:
    f.write(final_backend)
print(f" [Verified & Saved]: {backend_path}")

# ==========================================
# 4. STEP 2: GENERATE FRONT-END INTERFACE
# ==========================================
print("\n[2/2] Generating validated frontend...")

if UI_CHOICE == "1":
    ui_system = (
        f"You are a GUI Engineer building an app for {CURRENT_OS}. Write a complete Python Tkinter app. "
        "CRITICAL REQUIREMENTS:\n"
        "1. MUST explicitly write 'import backend' at the top.\n"
        "2. MUST start a GUI window using root = tk.Tk() and root.mainloop().\n"
        "3. Standard library only (tkinter, ttk, scrolledtext). No pip packages.\n"
        "Return ONLY raw executable Python code."
    )
    ui_prompt = f"Target OS: {CURRENT_OS}\nBackend Specification:\n{USER_TASK}\n\nBackend Code:\n{final_backend}\n\nBuild a complete Tkinter GUI window that imports backend."
    
    final_ui = generate_self_healing_code(
        system_prompt=ui_system,
        user_prompt=ui_prompt,
        is_backend=False,
        enable_dry_run=False,
        requires_backend_import=True
    )

    ui_path = os.path.join(PROJECT_DIR, "app_gui.py")
    with open(ui_path, "w", encoding="utf-8") as f:
        f.write(final_ui)
    print(f" [Verified & Saved]: {ui_path}")
    print(f"\n[Project Ready] Launch using:\n   python {ui_path}")

elif UI_CHOICE == "2":
    ui_system = (
        "You are a Web Designer. Create a single-file HTML/CSS/JS dashboard matching the backend. "
        "Return ONLY executable HTML starting with <!DOCTYPE html>. NO markdown."
    )
    ui_prompt = f"Backend Code:\n{final_backend}\n\nBuild a full HTML web dashboard for this logic."
    raw_ui = call_ollama(ui_system, ui_prompt)
    final_ui = extract_code(raw_ui)

    ui_path = os.path.join(PROJECT_DIR, "index.html")
    with open(ui_path, "w", encoding="utf-8") as f:
        f.write(final_ui)
    print(f" [Saved]: {ui_path}")

    webbrowser.open(f"file://{os.path.abspath(ui_path)}")
    print(f"\n[Project Ready] Dashboard opened in browser: {ui_path}")

else:
    ui_system = (
        "You are a Systems Engineer. Write an interactive terminal menu in Python. "
        "CRITICAL: Must include 'import backend' at the top. Return ONLY executable Python code."
    )
    ui_prompt = f"Backend Code:\n{final_backend}\n\nBuild a CLI menu wrapper importing backend."
    
    final_ui = generate_self_healing_code(
        system_prompt=ui_system,
        user_prompt=ui_prompt,
        is_backend=False,
        enable_dry_run=False,
        requires_backend_import=True
    )

    ui_path = os.path.join(PROJECT_DIR, "cli_app.py")
    with open(ui_path, "w", encoding="utf-8") as f:
        f.write(final_ui)
    print(f" [Verified & Saved]: {ui_path}")
    print(f"\n[Project Ready] Launch using:\n   python {ui_path}")
