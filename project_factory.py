#!/usr/bin/env python3
"""
Unified AI Project Factory Studio (GUI + CLI)
Generates, cross-validates, and launches zero-dependency Python applications via local Ollama.
"""

from __future__ import annotations

import ast
import json
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
import urllib.error
import urllib.request
import webbrowser
from typing import Callable

# ==========================================
# CONFIGURATION & ENVIRONMENT DETECTION
# ==========================================
DEFAULT_MODEL = "qwen2.5-coder:14b"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
PROJECTS_ROOT = Path("projects")
CURRENT_OS = platform.system()  # 'Linux', 'Windows', or 'Darwin'

STDLIB_MODULES: frozenset[str] = frozenset(
    getattr(sys, "stdlib_module_names", set()) | {"backend", "__future__"}
)


class OllamaConnectionError(RuntimeError):
    """Raised when the local Ollama server cannot be reached or returns an error."""


@dataclass(frozen=True)
class ProjectConfig:
    raw_name: str
    folder_name: str
    project_dir: Path
    user_task: str
    model_name: str
    optimize_prompt: bool
    enable_dry_run: bool
    ui_choice: str  # "1" (GUI), "2" (Web), "3" (CLI)


@dataclass
class BuildResult:
    project_dir: Path
    optimized_spec: str
    backend_path: Path
    backend_code: str
    frontend_path: Path
    frontend_code: str
    ui_choice: str


# ==========================================
# OLLAMA API & STREAMING CLIENT
# ==========================================
def fetch_ollama_models() -> list[str]:
    """Queries local Ollama instance for installed models, falling back to DEFAULT_MODEL."""
    try:
        req = urllib.request.Request(OLLAMA_TAGS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            if DEFAULT_MODEL in models:
                models.remove(DEFAULT_MODEL)
                models.insert(0, DEFAULT_MODEL)
            return models or [DEFAULT_MODEL]
    except Exception:
        return [DEFAULT_MODEL]


def call_ollama_chat(
    messages: list[dict[str, str]],
    model_name: str = DEFAULT_MODEL,
    on_progress: Callable[[str], None] | None = None,
) -> str:
    """Streams responses from local Ollama /api/chat with multi-turn context support."""
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "options": {
            "keep_alive": "1h",
            "temperature": 0.15,
            "num_ctx": 8192,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    full_content: list[str] = []
    chunk_count = 0

    try:
        with urllib.request.urlopen(req, timeout=1800) as response:
            for raw_line in response:
                line = raw_line.strip()
                if not line:
                    continue

                try:
                    chunk = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                if "error" in chunk:
                    raise OllamaConnectionError(f"Ollama API Error: {chunk['error']}")

                msg_content = chunk.get("message", {}).get("content", "")
                if msg_content:
                    full_content.append(msg_content)
                    chunk_count += 1
                    if on_progress and chunk_count % 5 == 0:
                        on_progress(f"Generating... ({chunk_count} token chunks received)")

                if chunk.get("done"):
                    final_tokens = chunk.get("eval_count", chunk_count)
                    if on_progress:
                        on_progress(f"Generation step complete ({final_tokens} tokens).")

        return "".join(full_content)

    except (urllib.error.URLError, TimeoutError) as exc:
        raise OllamaConnectionError(
            f"Cannot connect to Ollama at {OLLAMA_CHAT_URL}: {exc}\n"
            f"Make sure Ollama is running and `{model_name}` is pulled (`ollama pull {model_name}`)."
        ) from exc


# ==========================================
# AST EXTRACTION, VALIDATION & SMOKE TESTING
# ==========================================
def extract_code(text: str) -> str:
    """Extracts Python code cleanly from Markdown fences without deleting module constants."""
    text = text.strip()

    fenced_blocks = re.findall(r"```(?:[a-zA-Z0-9_+-]*)?\s*\n(.*?)```", text, re.DOTALL)
    if fenced_blocks:
        return max(fenced_blocks, key=len).strip()

    unclosed_match = re.search(r"```(?:[a-zA-Z0-9_+-]*)?\s*\n(.*)$", text, re.DOTALL)
    if unclosed_match:
        return unclosed_match.group(1).strip()

    code_starters = (
        "#!",
        "#",
        '"""',
        "'''",
        "import ",
        "from ",
        "class ",
        "def ",
        "@",
        "if __name__",
    )
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith(code_starters) or re.match(
            r"^[A-Za-z_][A-Za-z0-9_]*\s*[:=]", stripped
        ):
            return "\n".join(lines[idx:]).strip()

    return text


def extract_backend_exports(backend_code: str) -> tuple[set[str], str]:
    """
    Parses backend.py to extract all public symbol names and formats a strict
    API signature summary so the frontend generator calls exact function names.
    """
    exports: set[str] = set()
    contract_lines: list[str] = []

    try:
        tree = ast.parse(backend_code)
    except SyntaxError:
        return exports, "Unable to parse backend AST."

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            exports.add(node.name)
            if not node.name.startswith("_"):
                args = [a.arg for a in node.args.args]
                doc = ast.get_docstring(node) or "No docstring."
                doc_first_line = doc.strip().splitlines()[0]
                contract_lines.append(
                    f"- def backend.{node.name}({', '.join(args)}): # {doc_first_line}"
                )
        elif isinstance(node, ast.ClassDef):
            exports.add(node.name)
            methods = [
                n.name
                for n in node.body
                if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
            ]
            contract_lines.append(
                f"- class backend.{node.name} (methods: {', '.join(methods)})"
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    exports.add(target.id)
                    contract_lines.append(f"- constant backend.{target.id}")

    summary = "\n".join(contract_lines) if contract_lines else "No public symbols found."
    return exports, summary


def validate_code_ast(
    code_str: str,
    *,
    requires_backend_import: bool = False,
    backend_exports: set[str] | None = None,
) -> tuple[bool, str]:
    """
    Validates syntax, enforces Python stdlib-only imports, and cross-checks
    that every `backend.<symbol>` call in the frontend actually exists in `backend.py`.
    """
    if not code_str.strip():
        return False, "Generated code is empty."

    try:
        tree = ast.parse(code_str)
    except SyntaxError as exc:
        return False, f"SyntaxError on line {exc.lineno}: {exc.msg}"

    imported_roots: set[str] = set()
    backend_aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_mod = alias.name.split(".")[0]
                imported_roots.add(root_mod)
                if root_mod == "backend":
                    backend_aliases.add(alias.asname or "backend")
                if STDLIB_MODULES and root_mod not in STDLIB_MODULES:
                    return (
                        False,
                        f"Forbidden third-party import '{alias.name}'. Use ONLY Python standard library modules.",
                    )

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_mod = node.module.split(".")[0]
                imported_roots.add(root_mod)
                if STDLIB_MODULES and root_mod not in STDLIB_MODULES:
                    return (
                        False,
                        f"Forbidden third-party import '{node.module}'. Use ONLY Python standard library modules.",
                    )
                if root_mod == "backend" and backend_exports:
                    for alias in node.names:
                        if alias.name != "*" and alias.name not in backend_exports:
                            return (
                                False,
                                f"`from backend import {alias.name}` failed: '{alias.name}' does not exist in backend.py. "
                                f"Available backend symbols: {sorted(backend_exports)}",
                            )

    if requires_backend_import and "backend" not in imported_roots:
        return (
            False,
            "Missing `import backend` statement. The frontend MUST import and use `backend`.",
        )

    # Cross-check attribute accesses like `backend.some_func()` against actual backend exports
    if backend_exports and backend_aliases:
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id in backend_aliases:
                    attr = node.attr
                    if not attr.startswith("__") and attr not in backend_exports:
                        return (
                            False,
                            f" Frontend references `{node.value.id}.{attr}`, which does NOT exist in `backend.py`. "
                            f"Valid symbols in `backend.py` are: {sorted(backend_exports)}",
                        )

    return True, "Valid AST and Cross-File Symbols"


def test_execute_backend(code_str: str, working_dir: Path) -> tuple[bool, str]:
    """
    Writes backend.py to the project folder and runs both an import check and
    `backend._self_test()` (if defined) inside a subprocess with a strict timeout.
    """
    backend_file = working_dir / "backend.py"
    backend_file.write_text(code_str, encoding="utf-8")

    runner_code = (
        "import backend\n"
        "if hasattr(backend, '_self_test') and callable(backend._self_test):\n"
        "    backend._self_test()\n"
    )
    try:
        res = subprocess.run(
            [sys.executable, "-c", runner_code],
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=6,
        )
        if res.returncode != 0:
            return False, f"Runtime Execution Error:\n{res.stderr.strip()}"
        return True, "Runtime & Smoke Test Executed Successfully"
    except subprocess.TimeoutExpired:
        return (
            False,
            "Execution timed out after 6 seconds. Remove blocking loops, slow commands, or input() calls.",
        )
    except OSError as exc:
        return False, f"Subprocess execution failed: {exc}"


def generate_self_healing_code(
    system_prompt: str,
    user_prompt: str,
    working_dir: Path,
    model_name: str,
    *,
    is_backend: bool = False,
    enable_dry_run: bool = False,
    requires_backend_import: bool = False,
    backend_exports: set[str] | None = None,
    max_retries: int = 4,
    log_fn: Callable[[str], None] = print,
    progress_fn: Callable[[str], None] | None = None,
) -> str:
    """
    Uses multi-turn conversation history to iteratively generate and repair Python code
    against AST rules, cross-file symbol verification, and live subprocess smoke tests.
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    cleaned_code = ""

    for attempt in range(1, max_retries + 1):
        raw_response = call_ollama_chat(
            messages, model_name=model_name, on_progress=progress_fn
        )
        cleaned_code = extract_code(raw_response)

        # 1. Static AST + Stdlib Whitelist + Cross-File Symbol Check
        is_ast_valid, ast_msg = validate_code_ast(
            cleaned_code,
            requires_backend_import=requires_backend_import,
            backend_exports=backend_exports,
        )
        if not is_ast_valid:
            log_fn(f"   [Auto-Repair {attempt}/{max_retries}] Validation Failed: {ast_msg}")
            messages.append({"role": "assistant", "content": cleaned_code})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your code failed static validation with the following error:\n{ast_msg}\n\n"
                        "Fix the exact issue above while keeping the rest of the implementation intact. "
                        "Return ONLY valid, complete executable Python code."
                    ),
                }
            )
            continue

        # 2. Subprocess Dry-Run & Smoke Test (Backend Only)
        if is_backend and enable_dry_run:
            is_run_valid, run_msg = test_execute_backend(cleaned_code, working_dir)
            if not is_run_valid:
                log_fn(f"   [Auto-Repair {attempt}/{max_retries}] Runtime Failure: {run_msg}")
                messages.append({"role": "assistant", "content": cleaned_code})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your `backend.py` threw a runtime error during smoke testing on {CURRENT_OS}:\n"
                            f"{run_msg}\n\n"
                            f"Fix this runtime bug for {CURRENT_OS}. Use cross-platform Python standard library "
                            "functions and defensive error handling. Return ONLY the complete fixed Python code."
                        ),
                    }
                )
                continue

        log_fn(f"   [Validation Passed on Attempt {attempt}/{max_retries}]")
        return cleaned_code

    log_fn("   [Warning] Max retries reached; saving best available code.")
    return cleaned_code


# ==========================================
# CORE GENERATION PIPELINE
# ==========================================
def sanitize_folder_name(raw_name: str) -> str:
    slug = re.sub(r"[^\w\-]", "", raw_name.strip().replace(" ", "_")).lower()
    return slug or "generated_project"


def run_generation_pipeline(
    config: ProjectConfig,
    log_fn: Callable[[str], None] = print,
    progress_fn: Callable[[str], None] | None = None,
) -> BuildResult:
    """Executes the end-to-end prompt optimization, backend build, API extraction, and frontend build."""
    config.project_dir.mkdir(parents=True, exist_ok=True)
    log_fn(f"-> Project directory ready: ./{config.project_dir.as_posix()}/")

    # Step 0: Optional Prompt Optimization
    if config.optimize_prompt:
        log_fn("\n[Step 1/3] Optimizing Technical Specification with AI...")
        optimizer_system = (
            f"You are a Principal Python Architect designing software for {CURRENT_OS}. "
            "Transform the user's request into a concise, unambiguous technical specification for `backend.py`. "
            "List exact public function names, parameter types, JSON-serializable return structures (dicts/lists), "
            "and edge-case handling using ONLY Python's standard library. Return ONLY the specification."
        )
        task_spec = call_ollama_chat(
            [
                {"role": "system", "content": optimizer_system},
                {"role": "user", "content": config.user_task},
            ],
            model_name=config.model_name,
            on_progress=progress_fn,
        ).strip()
        log_fn("   [Specification Optimized]")
    else:
        task_spec = config.user_task

    # Step 1: Generate & Smoke-Test backend.py
    log_fn(
        f"\n[Step 2/3] Generating `backend.py` (OS: {CURRENT_OS}, Smoke-Test: {config.enable_dry_run})..."
    )
    dev_system = (
        f"You are a Senior Python Engineer targeting {CURRENT_OS}. "
        "Write a clean, well-structured `backend.py` module using ONLY Python's standard library "
        "(os, sys, platform, subprocess, json, urllib, pathlib, tempfile, sqlite3, datetime, math, statistics, csv).\n"
        "STRICT ENGINEERING RULES:\n"
        "1. ZERO PIP PACKAGES: Do not import psutil, requests, flask, numpy, or any third-party library.\n"
        f"2. OS COMPATIBILITY: Target {CURRENT_OS}. Guard OS-specific shell commands with `platform.system()` and wrap "
        "subprocess calls in `try...except` blocks with `text=True, encoding='utf-8', errors='replace', timeout=5`.\n"
        "3. CLEAN PUBLIC API: Expose clear functions that return structured dicts/lists/primitives and never block on `input()`.\n"
        "4. BUILT-IN SMOKE TEST: Include a fast `def _self_test() -> None:` function that calls your main read-only functions "
        "with safe sample arguments to verify they do not raise unhandled exceptions.\n"
        "Return ONLY valid Python code."
    )

    backend_code = generate_self_healing_code(
        system_prompt=dev_system,
        user_prompt=f"Target OS: {CURRENT_OS}\nProject: {config.raw_name}\nSpecification:\n{task_spec}\n\nWrite `backend.py`.",
        working_dir=config.project_dir,
        model_name=config.model_name,
        is_backend=True,
        enable_dry_run=config.enable_dry_run,
        log_fn=log_fn,
        progress_fn=progress_fn,
    )

    backend_path = config.project_dir / "backend.py"
    backend_path.write_text(backend_code, encoding="utf-8")
    backend_exports, contract_summary = extract_backend_exports(backend_code)
    log_fn(f"   [Saved]: {backend_path}")
    log_fn(f"   [Detected Backend API]: {', '.join(sorted(backend_exports))}")

    # Step 2: Generate & Cross-Verify Frontend
    log_fn("\n[Step 3/3] Generating & Cross-Verifying Frontend Interface...")
    if config.ui_choice == "1":
        ui_file = "app_gui.py"
        ui_system = (
            f"You are a Python Desktop GUI Engineer targeting {CURRENT_OS}. "
            "Write a polished, responsive Tkinter application (`app_gui.py`) using `tkinter` and `tkinter.ttk`.\n"
            "CRITICAL REQUIREMENTS:\n"
            "1. Explicitly `import backend` at the top.\n"
            "2. Call ONLY functions/classes that actually exist in the provided `backend.py` API Contract.\n"
            "3. Use `ttk.Frame`, `ttk.Button`, `ttk.Label`, `ttk.Treeview`, or `scrolledtext.ScrolledText` with clean padding.\n"
            "4. Wrap backend calls in `try...except Exception as e:` and show errors nicely without crashing the UI.\n"
            "5. Start the application inside `if __name__ == '__main__':`.\n"
            "Return ONLY valid Python code."
        )
    elif config.ui_choice == "2":
        ui_file = "web_app.py"
        ui_system = (
            f"You are a Full-Stack Python Engineer targeting {CURRENT_OS}. "
            "Write a single-file Python web server (`web_app.py`) using `http.server` that serves a modern HTML/CSS/JS "
            "dashboard AND exposes JSON API endpoints backed by `backend.py`.\n"
            "CRITICAL REQUIREMENTS:\n"
            "1. Explicitly `import backend` at the top.\n"
            "2. Call ONLY functions that actually exist in the provided `backend.py` API Contract.\n"
            "3. Serve the HTML/CSS/JS dashboard on `GET /` and handle JSON API requests on `/api/...`.\n"
            "4. On `if __name__ == '__main__':`, bind to `127.0.0.1` on an open port (try 8000, or use port 0 and read `server_address[1]`), "
            "open the URL via `webbrowser.open()`, and run `serve_forever()`.\n"
            "Return ONLY valid Python code."
        )
    else:
        ui_file = "cli_app.py"
        ui_system = (
            f"You are a Systems CLI Engineer targeting {CURRENT_OS}. "
            "Write an interactive terminal dashboard (`cli_app.py`).\n"
            "CRITICAL REQUIREMENTS:\n"
            "1. Explicitly `import backend` at the top.\n"
            "2. Call ONLY functions that actually exist in the provided `backend.py` API Contract.\n"
            "3. Provide a clear numbered menu loop, formatted output tables, exception handling, and an option to exit.\n"
            "Return ONLY valid Python code."
        )

    ui_prompt = (
        f"Target OS: {CURRENT_OS}\n"
        f"Project Name: {config.raw_name}\n\n"
        f"STRICT BACKEND API CONTRACT (You may ONLY call these symbols on `backend`):\n"
        f"{contract_summary}\n\n"
        f"Full `backend.py` Implementation:\n```python\n{backend_code}\n```\n\n"
        f"Write `{ui_file}` that imports `backend` and provides a complete interactive interface for every feature above."
    )

    frontend_code = generate_self_healing_code(
        system_prompt=ui_system,
        user_prompt=ui_prompt,
        working_dir=config.project_dir,
        model_name=config.model_name,
        is_backend=False,
        enable_dry_run=False,
        requires_backend_import=True,
        backend_exports=backend_exports,
        log_fn=log_fn,
        progress_fn=progress_fn,
    )

    frontend_path = config.project_dir / ui_file
    frontend_path.write_text(frontend_code, encoding="utf-8")
    log_fn(f"   [Verified & Saved]: {frontend_path}")
    log_fn(f"\n[SUCCESS] Project ready! Run: python {frontend_path}")

    return BuildResult(
        project_dir=config.project_dir,
        optimized_spec=task_spec,
        backend_path=backend_path,
        backend_code=backend_code,
        frontend_path=frontend_path,
        frontend_code=frontend_code,
        ui_choice=config.ui_choice,
    )


# ==========================================
# TKINTER STUDIO UI FOR PROJECT FACTORY
# ==========================================
class ProjectFactoryStudioUI:
    """Built-in Desktop GUI for configuring, monitoring, inspecting, and launching AI-generated apps."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"Unified AI Project Factory Studio ({CURRENT_OS})")
        self.root.geometry("1120x780")
        self.root.minsize(960, 680)

        self.msg_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.last_result: BuildResult | None = None
        self.is_generating = False

        self._configure_styles()
        self._build_layout()
        self._poll_queue()

    def _configure_styles(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Subheader.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", font=("Consolas", 10))
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"), padding=6)

    def _build_layout(self) -> None:
        # Top Header Bar
        header_frame = ttk.Frame(self.root, padding=(14, 10))
        header_frame.pack(fill=tk.X)

        ttk.Label(
            header_frame,
            text=f"AI Project Factory Studio — {CURRENT_OS} (Zero-Pip Standard Library Builder)",
            style="Header.TLabel",
        ).pack(side=tk.LEFT)

        # Model Selector on Right of Header
        model_frame = ttk.Frame(header_frame)
        model_frame.pack(side=tk.RIGHT)
        ttk.Label(model_frame, text="Ollama Model:").pack(side=tk.LEFT, padx=(0, 6))
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_combo = ttk.Combobox(
            model_frame,
            textvariable=self.model_var,
            values=fetch_ollama_models(),
            width=24,
        )
        self.model_combo.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            model_frame, text="Refresh", command=self._refresh_models, width=8
        ).pack(side=tk.LEFT)

        # Main Horizontal Split Pane (Left: Config, Right: Output & Code Inspector)
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 10))

        left_frame = ttk.Frame(paned, padding=(0, 0, 10, 0))
        right_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=2)
        paned.add(right_frame, weight=3)

        # --- LEFT PANEL: Project Settings ---
        ttk.Label(left_frame, text="1. Project Name", style="Subheader.TLabel").pack(
            anchor=tk.W, pady=(0, 4)
        )
        self.name_var = tk.StringVar(value="System Resource Monitor")
        ttk.Entry(left_frame, textvariable=self.name_var, font=("Segoe UI", 10)).pack(
            fill=tk.X, pady=(0, 12)
        )

        ttk.Label(
            left_frame,
            text="2. Core Backend Logic & Features",
            style="Subheader.TLabel",
        ).pack(anchor=tk.W, pady=(0, 4))
        self.task_input = scrolledtext.ScrolledText(
            left_frame, height=10, font=("Consolas", 10), wrap=tk.WORD
        )
        self.task_input.pack(fill=tk.BOTH, expand=True, pady=(0, 12))
        self.task_input.insert(
            tk.END,
            "Build a system diagnostics tool that reports CPU architecture, OS details, "
            "disk usage per partition, active network interfaces, and top running processes.",
        )

        # Target UI Radio Buttons
        ui_group = ttk.LabelFrame(
            left_frame, text="3. Target Front-End Interface", padding=10
        )
        ui_group.pack(fill=tk.X, pady=(0, 12))
        self.ui_choice_var = tk.StringVar(value="1")
        ttk.Radiobutton(
            ui_group,
            text="[1] Desktop GUI (Python Tkinter Window)",
            variable=self.ui_choice_var,
            value="1",
        ).pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(
            ui_group,
            text="[2] Full-Stack Web Dashboard (http.server + HTML/JS)",
            variable=self.ui_choice_var,
            value="2",
        ).pack(anchor=tk.W, pady=2)
        ttk.Radiobutton(
            ui_group,
            text="[3] Interactive CLI Dashboard (Terminal Menu)",
            variable=self.ui_choice_var,
            value="3",
        ).pack(anchor=tk.W, pady=2)

        # AI Pipeline Options
        opt_group = ttk.LabelFrame(
            left_frame, text="4. Quality & Verification Options", padding=10
        )
        opt_group.pack(fill=tk.X, pady=(0, 12))
        self.optimize_var = tk.BooleanVar(value=True)
        self.dry_run_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opt_group,
            text="AI Prompt Optimizer (Expand into formal spec before coding)",
            variable=self.optimize_var,
        ).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(
            opt_group,
            text=f"Live Subprocess Smoke Test on {CURRENT_OS} (Executes code locally)",
            variable=self.dry_run_var,
        ).pack(anchor=tk.W, pady=2)

        # Action Buttons
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=(4, 0))
        self.generate_btn = ttk.Button(
            btn_frame,
            text="Generate Application",
            style="Action.TButton",
            command=self._start_generation,
        )
        self.generate_btn.pack(fill=tk.X, pady=(0, 6))

        self.launch_btn = ttk.Button(
            btn_frame,
            text="Launch Generated App",
            command=self._launch_generated_app,
            state=tk.DISABLED,
        )
        self.launch_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.open_dir_btn = ttk.Button(
            btn_frame,
            text="Open Project Folder",
            command=self._open_project_folder,
            state=tk.DISABLED,
        )
        self.open_dir_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))

        # --- RIGHT PANEL: Notebook Tabs for Logs, Spec, backend.py, Frontend ---
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.log_text = self._create_tab("Build Console")
        self.spec_text = self._create_tab("Optimized Spec")
        self.backend_text = self._create_tab("backend.py")
        self.frontend_text = self._create_tab("Frontend Code")

        # Bottom Status Bar + Progress Bar
        status_frame = ttk.Frame(self.root, padding=(14, 6))
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_var = tk.StringVar(value="Ready. Configure your project and click Generate.")
        ttk.Label(
            status_frame, textvariable=self.status_var, style="Status.TLabel"
        ).pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(
            status_frame, mode="indeterminate", length=220
        )
        self.progress.pack(side=tk.RIGHT)

    def _create_tab(self, title: str) -> scrolledtext.ScrolledText:
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        widget = scrolledtext.ScrolledText(
            frame,
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="#ffffff",
            wrap=tk.NONE,
        )
        widget.pack(fill=tk.BOTH, expand=True)
        return widget

    def _refresh_models(self) -> None:
        models = fetch_ollama_models()
        self.model_combo["values"] = models
        if models and self.model_var.get() not in models:
            self.model_var.set(models[0])
        self.status_var.set(f"Detected {len(models)} model(s) from local Ollama.")

    def _set_tab_content(
        self, widget: scrolledtext.ScrolledText, content: str
    ) -> None:
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, content)

    def _append_log(self, msg: str) -> None:
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)

    def _start_generation(self) -> None:
        if self.is_generating:
            return

        raw_name = self.name_var.get().strip()
        user_task = self.task_input.get("1.0", tk.END).strip()
        if not raw_name or not user_task:
            messagebox.showwarning(
                "Missing Input",
                "Please provide both a Project Name and Core Backend Logic description.",
            )
            return

        folder_name = sanitize_folder_name(raw_name)
        config = ProjectConfig(
            raw_name=raw_name,
            folder_name=folder_name,
            project_dir=PROJECTS_ROOT / folder_name,
            user_task=user_task,
            model_name=self.model_var.get().strip() or DEFAULT_MODEL,
            optimize_prompt=self.optimize_var.get(),
            enable_dry_run=self.dry_run_var.get(),
            ui_choice=self.ui_choice_var.get(),
        )

        self.is_generating = True
        self.generate_btn.config(state=tk.DISABLED)
        self.launch_btn.config(state=tk.DISABLED)
        self.open_dir_btn.config(state=tk.DISABLED)
        self.progress.start(12)
        self.notebook.select(0)

        self._set_tab_content(self.log_text, "")
        self._set_tab_content(self.spec_text, "")
        self._set_tab_content(self.backend_text, "")
        self._set_tab_content(self.frontend_text, "")

        worker = threading.Thread(
            target=self._run_worker, args=(config,), daemon=True
        )
        worker.start()

    def _run_worker(self, config: ProjectConfig) -> None:
        try:
            result = run_generation_pipeline(
                config,
                log_fn=lambda m: self.msg_queue.put(("log", m)),
                progress_fn=lambda s: self.msg_queue.put(("status", s)),
            )
            self.msg_queue.put(("done", result))
        except Exception as exc:
            self.msg_queue.put(("error", str(exc)))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "done" and isinstance(payload, BuildResult):
                    self._on_generation_complete(payload)
                elif kind == "error":
                    self._on_generation_error(str(payload))
        except queue.Empty:
            pass
        finally:
            self.root.after(80, self._poll_queue)

    def _on_generation_complete(self, result: BuildResult) -> None:
        self.is_generating = False
        self.last_result = result
        self.progress.stop()
        self.generate_btn.config(state=tk.NORMAL)
        self.launch_btn.config(state=tk.NORMAL)
        self.open_dir_btn.config(state=tk.NORMAL)
        self.status_var.set(f"Ready: {result.frontend_path.as_posix()}")

        self._set_tab_content(self.spec_text, result.optimized_spec)
        self._set_tab_content(self.backend_text, result.backend_code)
        self._set_tab_content(self.frontend_text, result.frontend_code)

    def _on_generation_error(self, err_msg: str) -> None:
        self.is_generating = False
        self.progress.stop()
        self.generate_btn.config(state=tk.NORMAL)
        self.status_var.set("Generation failed. See Build Console for details.")
        self._append_log(f"\n[ERROR] {err_msg}")
        messagebox.showerror("Generation Error", err_msg)

    def _launch_generated_app(self) -> None:
        if not self.last_result:
            return

        target_script = self.last_result.frontend_path.name
        work_dir = self.last_result.project_dir

        try:
            if self.last_result.ui_choice == "3":
                # CLI applications need a visible terminal emulator window
                if CURRENT_OS == "Windows":
                    subprocess.Popen(
                        ["cmd", "/c", "start", "cmd", "/k", sys.executable, target_script],
                        cwd=work_dir,
                    )
                elif CURRENT_OS == "Darwin":
                    apple_script = (
                        f'tell application "Terminal" to do script '
                        f'"cd {work_dir.resolve()} && {sys.executable} {target_script}"'
                    )
                    subprocess.Popen(["osascript", "-e", apple_script])
                else:
                    # Try common Linux terminal emulators, otherwise advise running in terminal
                    for term in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"):
                        try:
                            subprocess.Popen(
                                [term, "-e", f"{sys.executable} {target_script}"],
                                cwd=work_dir,
                            )
                            break
                        except FileNotFoundError:
                            continue
                    else:
                        messagebox.showinfo(
                            "Run in Terminal",
                            f"Launch your CLI app from a terminal:\n\ncd {work_dir}\npython {target_script}",
                        )
            else:
                subprocess.Popen([sys.executable, target_script], cwd=work_dir)
                self.status_var.set(f"Launched {target_script} (PID running).")
        except OSError as exc:
            messagebox.showerror("Launch Failed", f"Could not start app: {exc}")

    def _open_project_folder(self) -> None:
        if not self.last_result:
            return
        folder = self.last_result.project_dir.resolve()
        if CURRENT_OS == "Windows":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        elif CURRENT_OS == "Darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            webbrowser.open(folder.as_uri())


# ==========================================
# CLI FALLBACK MODE (`python project_factory.py --cli`)
# ==========================================
def run_cli_mode() -> int:
    print("\n==========================================")
    print(f"  UNIFIED AI PROJECT FACTORY ({CURRENT_OS.upper()})")
    print("==========================================")

    raw_name = input("1. Enter Project Name (e.g., Resource Monitor): ").strip()
    if not raw_name:
        print("Project name cannot be empty.", file=sys.stderr)
        return 1

    raw_task = input("\n2. Describe the Core Backend Logic: ").strip()
    if not raw_task:
        print("Task description cannot be empty.", file=sys.stderr)
        return 1

    optimize_prompt = (
        input("   Enhance prompt with AI for higher code accuracy? (Y/n): ")
        .strip()
        .lower()
        not in {"n", "no"}
    )
    enable_dry_run = (
        input(f"   Enable live subprocess smoke-testing on host ({CURRENT_OS})? (Y/n): ")
        .strip()
        .lower()
        not in {"n", "no"}
    )

    print("\n3. Select Front-End Interface Type:")
    print("   [1] Desktop GUI (Python Tkinter)")
    print("   [2] Local Web Dashboard (Python http.server + HTML/JS)")
    print("   [3] CLI Interactive Dashboard (Terminal menu)")
    ui_choice = input("Select choice (1, 2, or 3) [default: 1]: ").strip() or "1"
    if ui_choice not in {"1", "2", "3"}:
        ui_choice = "1"

    folder_name = sanitize_folder_name(raw_name)
    config = ProjectConfig(
        raw_name=raw_name,
        folder_name=folder_name,
        project_dir=PROJECTS_ROOT / folder_name,
        user_task=raw_task,
        model_name=DEFAULT_MODEL,
        optimize_prompt=optimize_prompt,
        enable_dry_run=enable_dry_run,
        ui_choice=ui_choice,
    )

    try:
        run_generation_pipeline(config)
        return 0
    except OllamaConnectionError as exc:
        print(f"\n[Error] {exc}", file=sys.stderr)
        return 1


def main() -> int:
    if "--cli" in sys.argv:
        return run_cli_mode()

    try:
        root = tk.Tk()
    except tk.TclError:
        print("[Notice] No display server detected; falling back to CLI mode.")
        return run_cli_mode()

    ProjectFactoryStudioUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
