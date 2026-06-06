import os
import re
import json
import zipfile
import tempfile
import shutil
import struct
import subprocess
import asyncio
import logging
from pathlib import Path
from dataclasses import dataclass

try:
    import pty
    import tty
    import fcntl
    import termios
    import signal
    PTY_AVAILABLE = True
except ImportError:
    PTY_AVAILABLE = False

logger = logging.getLogger(__name__)

from config import WORKSPACES_DIR

_PTY_PID_FILE = os.path.join(str(WORKSPACES_DIR), ".pty_pids.json")


def get_user_workspace(user_id: int) -> Path:
    path = Path(WORKSPACES_DIR) / str(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_project_path(user_id: int, project_name: str) -> Path:
    safe_name = re.sub(r'[^\w\-]', '_', project_name)
    return get_user_workspace(user_id) / safe_name


def create_project_dir(user_id: int, project_name: str) -> Path:
    path = get_project_path(user_id, project_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_project_tree(project_path: str, max_depth: int = 4) -> str:
    root = Path(project_path)
    if not root.exists():
        return "(пустой проект)"

    lines = []

    def _walk(path: Path, prefix: str = "", depth: int = 0):
        if depth > max_depth:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name))
        except PermissionError:
            return

        for i, entry in enumerate(entries):
            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)

    lines.append(root.name + "/")
    _walk(root)
    return "\n".join(lines)


def read_project_files(project_path: str, max_chars: int = 16000) -> str:
    root = Path(project_path)
    if not root.exists():
        return ""

    CODE_EXTS = {'.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css',
                 '.json', '.yaml', '.yml', '.toml', '.md', '.txt', '.sh',
                 '.go', '.rs', '.java', '.c', '.cpp', '.h', '.ini', '.cfg',
                 '.env.example', '.sql', '.xml', '.php', '.rb', '.swift'}

    collected = []
    total = 0

    for fpath in sorted(root.rglob("*")):
        if not fpath.is_file():
            continue
        if fpath.suffix not in CODE_EXTS:
            continue
        parts = fpath.relative_to(root).parts
        if any(p.startswith('.') or p in ('__pycache__', 'node_modules', '.git') for p in parts):
            continue

        try:
            content = fpath.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue

        rel = fpath.relative_to(root)
        snippet = f"### {rel}\n```\n{content}\n```\n"

        if total + len(snippet) > max_chars:
            remaining = max_chars - total
            if remaining > 200:
                collected.append(f"### {rel}\n```\n{content[:remaining]}...\n```\n")
            break

        collected.append(snippet)
        total += len(snippet)

    return "\n".join(collected)


def list_all_files(project_path: str) -> str:
    root = Path(project_path)
    if not root.exists():
        return "(пусто)"

    files = []
    for fpath in sorted(root.rglob("*")):
        if not fpath.is_file():
            continue
        parts = fpath.relative_to(root).parts
        if any(p.startswith('.') or p in ('__pycache__', 'node_modules', '.git') for p in parts):
            continue
        files.append(str(fpath.relative_to(root)))

    if not files:
        return "(пусто — нет файлов)"

    return "\n".join(f"  • {f}" for f in files)


def delete_file(project_path: str, relative_path: str) -> bool:
    root = Path(project_path).resolve()
    target = (root / relative_path).resolve()

    if not str(target).startswith(str(root)):
        return False
    if not target.is_file():
        return False

    target.unlink()
    try:
        for parent in target.parents:
            if parent == root or parent.parent == root:
                break
            if not any(parent.iterdir()):
                parent.rmdir()
    except OSError:
        pass
    return True


FILE_BLOCK_PATTERN = re.compile(
    r'```([^\n`]+)\n([\s\S]*?)```',
    re.MULTILINE
)


def looks_like_path(lang_hint: str) -> bool:
    hint = lang_hint.strip()
    return '/' in hint or (
        '.' in hint and
        not hint.lower() in {
            'python', 'javascript', 'typescript', 'js', 'ts',
            'html', 'css', 'bash', 'sh', 'json', 'yaml', 'toml',
            'rust', 'go', 'java', 'c', 'cpp', 'plaintext', 'text',
            'markdown', 'md', 'sql', 'xml', 'php', 'ruby', 'rb',
        }
    )


def parse_ai_response(response: str, project_path: str) -> tuple[str, list[str]]:
    root = Path(project_path).resolve()
    created_files = []
    text_parts = []
    last_end = 0

    for match in FILE_BLOCK_PATTERN.finditer(response):
        start, end = match.span()
        lang_hint = match.group(1).strip()
        code = match.group(2)

        if start > last_end:
            text_parts.append(response[last_end:start].strip())

        if lang_hint.upper().startswith("DELETE"):
            parts = lang_hint.split(None, 1)
            if len(parts) >= 2:
                file_to_delete = parts[1].strip()
                if delete_file(str(root), file_to_delete):
                    created_files.append(f"[удалён] {file_to_delete}")
                    text_parts.append(f"🗑 <code>{file_to_delete}</code> — удалён")
                else:
                    text_parts.append(f"⚠️ Не удалось удалить <code>{file_to_delete}</code>: файл не найден")
            else:
                text_parts.append(f"```{lang_hint}\n{code}```")
            last_end = end
            continue

        if looks_like_path(lang_hint):
            file_path = (root / lang_hint.lstrip('/')).resolve()
            if not str(file_path).startswith(str(root)):
                text_parts.append(f"⚠️ <code>{lang_hint}</code> — путь вне проекта, сохранение запрещено")
                last_end = end
                continue
            file_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                file_path.write_text(code, encoding='utf-8')
                created_files.append(lang_hint)
                text_parts.append(f"📄 <code>{lang_hint}</code> — сохранён")
            except Exception as e:
                text_parts.append(f"⚠️ Не удалось сохранить <code>{lang_hint}</code>: {e}")
        else:
            text_parts.append(f"```{lang_hint}\n{code}```")

        last_end = end

    if last_end < len(response):
        text_parts.append(response[last_end:].strip())

    final_text = "\n\n".join(p for p in text_parts if p)
    return final_text, created_files


def zip_project(project_path: str, project_name: str) -> str:
    tmp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(tmp_dir, f"{project_name}.zip")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        root = Path(project_path)
        for fpath in root.rglob("*"):
            if not fpath.is_file():
                continue
            arcname = os.path.join(project_name, str(fpath.relative_to(root)))
            zf.write(fpath, arcname)

    return zip_path


def unzip_to_project(zip_path: str, project_path: str) -> list[str]:
    root = Path(project_path)
    root.mkdir(parents=True, exist_ok=True)
    extracted = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.namelist():
            target = (root / member).resolve()
            if not str(target).startswith(str(root.resolve())):
                continue
            zf.extract(member, root)
            if not member.endswith('/'):
                extracted.append(member)

    return extracted


_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[>=]|\([AB0-9]')


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


@dataclass
class PTYSession:
    process: subprocess.Popen
    master_fd: int
    slave_fd: int
    user_id: int
    chat_id: int = 0
    output_buf: str = ""
    finished: bool = False
    exit_code: int | None = None
    interactive: bool = False
    start_time: float = 0.0
    label: str = ""


_pty_sessions: dict[int, PTYSession] = {}


def _read_pid_file() -> dict[str, list[int]]:
    try:
        with open(_PTY_PID_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_pid_file(data: dict[str, list[int]]):
    with open(_PTY_PID_FILE, "w") as f:
        json.dump(data, f)


def cleanup_orphans():
    if not PTY_AVAILABLE:
        return
    pids = _read_pid_file()
    total = 0
    for key, pid_list in pids.items():
        for pid in pid_list:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
                total += 1
            except (ProcessLookupError, OSError):
                pass
    if total:
        logger.info(f"Cleaned up {total} orphaned PTY processes")
    _write_pid_file({})


def _make_nonblocking(fd: int):
    if not PTY_AVAILABLE:
        return
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def _set_pty_size(fd: int, rows: int = 40, cols: int = 120):
    if not PTY_AVAILABLE:
        return
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        pass


def start_pty(user_id: int, chat_id: int, cmd: list[str], cwd: str, label: str = "") -> PTYSession:
    if not PTY_AVAILABLE:
        raise RuntimeError("PTY is not available on this platform")
    kill_pty(user_id)

    master_fd, slave_fd = os.openpty()
    _set_pty_size(slave_fd)

    proc = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=cwd,
        preexec_fn=os.setsid,
        close_fds=True,
    )

    os.close(slave_fd)
    _make_nonblocking(master_fd)

    session = PTYSession(
        process=proc,
        master_fd=master_fd,
        slave_fd=-1,
        user_id=user_id,
        chat_id=chat_id,
        start_time=asyncio.get_event_loop().time(),
        label=label or " ".join(cmd),
    )
    _pty_sessions[user_id] = session

    pids = _read_pid_file()
    key = str(user_id)
    pids.setdefault(key, []).append(proc.pid)
    _write_pid_file(pids)

    return session


def get_pty_session(user_id: int) -> PTYSession | None:
    return _pty_sessions.get(user_id)


def list_active_pty() -> list[PTYSession]:
    return [s for s in _pty_sessions.values() if not s.finished]


def write_pty(user_id: int, data: str) -> bool:
    session = _pty_sessions.get(user_id)
    if not session or session.finished:
        return False
    try:
        os.write(session.master_fd, data.encode())
        return True
    except (OSError, BrokenPipeError):
        return False


def kill_pty(user_id: int):
    if not PTY_AVAILABLE:
        return
    session = _pty_sessions.pop(user_id, None)
    if not session:
        return
    try:
        if session.process.poll() is None:
            os.killpg(os.getpgid(session.process.pid), signal.SIGTERM)
            try:
                session.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(session.process.pid), signal.SIGKILL)
                session.process.wait()
    except (ProcessLookupError, OSError):
        pass
    try:
        os.close(session.master_fd)
    except OSError:
        pass
    session.finished = True

    pids = _read_pid_file()
    key = str(user_id)
    pids.pop(key, None)
    _write_pid_file(pids)


def signal_pty(user_id: int, sig: int):
    session = _pty_sessions.get(user_id)
    if not session or session.finished:
        return
    try:
        os.killpg(os.getpgid(session.process.pid), sig)
    except (ProcessLookupError, OSError):
        pass


async def read_pty(user_id: int, max_read: int = 4096) -> str:
    session = _pty_sessions.get(user_id)
    if not session or session.finished:
        return ""
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, lambda: os.read(session.master_fd, max_read))
        decoded = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        return _strip_ansi(decoded)
    except (BlockingIOError, OSError):
        return ""


async def stream_pty_output(user_id: int):
    """
    Async generator that yields PTY output chunks for SSE streaming.
    Yields: {"type": "output", "text": str} or {"type": "done", "exit_code": int}
    """
    if not PTY_AVAILABLE:
        yield {"type": "error", "message": "PTY not available on this platform"}
        return

    session = _pty_sessions.get(user_id)
    if not session:
        yield {"type": "error", "message": "No active process"}
        return

    HEARTBEAT_INTERVAL = 120.0
    TIMEOUT_INTERVAL = 300.0
    last_output_time = asyncio.get_event_loop().time()
    timeout_warned = False

    while True:
        data = await read_pty(user_id)
        if data:
            yield {"type": "output", "text": data}
            last_output_time = asyncio.get_event_loop().time()
            timeout_warned = False

        poll = session.process.poll()
        if poll is not None:
            try:
                while True:
                    chunk = await read_pty(user_id, 65536)
                    if not chunk:
                        break
                    yield {"type": "output", "text": chunk}
            except Exception:
                pass
            session.finished = True
            session.exit_code = poll
            _pty_sessions.pop(user_id, None)
            try:
                os.close(session.master_fd)
            except OSError:
                pass
            pids = _read_pid_file()
            pids.pop(str(user_id), None)
            _write_pid_file(pids)
            yield {"type": "done", "exit_code": poll}
            return

        now = asyncio.get_event_loop().time()
        idle = now - last_output_time

        if not session.output_buf and idle > TIMEOUT_INTERVAL and not timeout_warned:
            yield {"type": "heartbeat", "message": f"Process running {int(now - session.start_time)}s without output"}
            timeout_warned = True
        elif idle > HEARTBEAT_INTERVAL and not timeout_warned:
            yield {"type": "heartbeat", "message": f"Running... ({int(now - session.start_time)}s)"}

        await asyncio.sleep(0.1)
