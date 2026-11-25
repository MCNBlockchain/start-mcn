import argparse
from collections import deque
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("MCN_DATA_DIR", ROOT / ".mcn-data")).expanduser().resolve()
CONTROL = DATA / ".launcher"
LOCK = CONTROL / "lock"
STATE = CONTROL / "state.json"
LOGS = CONTROL / "logs"
NODE = [sys.executable, str(ROOT / "mcn-node")]
SELF = [sys.executable, str(ROOT / "launcher.py")]


def read_state():
    try:
        return json.loads(STATE.read_text())
    except FileNotFoundError:
        return {}


def save_state(phase, detail=None):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"pid": os.getpid(), "phase": phase, "detail": detail}) + "\n")
    temporary.replace(STATE)


def supervisor_pid():
    state = read_state()
    if state.get("phase") not in {"preparing", "running"} or not LOCK.exists():
        return None
    with LOCK.open("rb") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            return None
    try:
        pid = state["pid"]
        arguments = Path(f"/proc/{pid}/cmdline").read_bytes().rstrip(b"\0").split(b"\0")
    except FileNotFoundError:
        return None
    actual = [os.fsdecode(part) for part in arguments]
    background = actual[-3:-1] == [str(ROOT / "launcher.py"), "_serve"]
    foreground = actual[-2:] == [str(ROOT / "launcher.py"), "foreground"]
    if background or foreground:
        return pid
    return None


def launch(foreground=False):
    os.umask(0o077)
    LOGS.mkdir(mode=0o700, parents=True, exist_ok=True)
    with LOCK.open("ab") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Узел уже запущен. Статус: ./start status")
            return 0
        result = check_requirements()
        if result:
            return result
        if foreground:
            return serve(os.dup(lock.fileno()))
        with (LOGS / "launcher.log").open("ab") as log:
            process = subprocess.Popen(
                SELF + ["_serve", str(lock.fileno())],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, pass_fds=(lock.fileno(),), cwd=ROOT,
            )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and process.poll() is None:
            state = read_state()
            if state.get("pid") == process.pid and state.get("phase") in {"preparing", "running"}:
                print("Запуск начался в фоне. Статус: ./start status")
                return 0
            time.sleep(0.1)
        print(f"Проверь журнал запуска: {LOGS / 'launcher.log'}", file=sys.stderr)
        return 1


def node_process(command, filename):
    with (LOGS / filename).open("ab") as log:
        return subprocess.Popen(
            NODE + [command], stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True, cwd=ROOT,
        )


def stop_children(children):
    for child in children:
        if child.poll() is None:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for child in children:
        child.wait()


def serve(lock_fd):
    stopping = False
    children = []

    def request_stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, request_stop)
    try:
        save_state("preparing")
        preparation = node_process("prepare", "prepare.log")
        children.append(preparation)
        while not stopping and preparation.poll() is None:
            time.sleep(0.5)
        if not stopping and preparation.returncode:
            raise RuntimeError("Подготовка Geth остановилась. Подробности в prepare.log.")
        if not stopping:
            geth = node_process("geth", "geth.log")
            children.append(geth)
            beacon = node_process("beacon", "beacon.log")
            children.append(beacon)
            save_state("running")
            while not stopping:
                for label, child in (("Geth", geth), ("Prysm", beacon)):
                    if child.poll() is not None:
                        raise RuntimeError(f"{label} завершился с кодом {child.returncode}.")
                time.sleep(0.5)
    except (RuntimeError, OSError) as error:
        print(error, file=sys.stderr, flush=True)
        stop_children(children)
        save_state("failed", str(error))
        return 1
    else:
        stop_children(children)
        save_state("stopped")
        return 0
    finally:
        os.close(lock_fd)


def stop():
    pid = supervisor_pid()
    if pid is None:
        print("Узел остановлен.")
        return 0
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and supervisor_pid() == pid:
        time.sleep(0.5)
    if supervisor_pid() == pid:
        print("Остановка продолжается. Статус: ./start status")
    else:
        print("Узел остановлен.")
    return 0


def status():
    state = read_state()
    if supervisor_pid() is None:
        print(state.get("detail") or "Узел остановлен.")
        return 1
    if state["phase"] == "preparing":
        print("Geth готовит базу. Ход загрузки: ./start logs")
        return 0
    return subprocess.run(NODE + ["status"], cwd=ROOT).returncode


def show_logs():
    for filename in ("launcher.log", "prepare.log", "geth.log", "beacon.log"):
        path = LOGS / filename
        if path.is_file():
            with path.open(errors="replace") as log:
                lines = deque(log, maxlen=12)
            if lines:
                print(f"\n--- {filename} ---")
                print("".join(lines), end="")
    return 0


def check_requirements():
    return subprocess.run(NODE + ["verify", "--clients"], cwd=ROOT).returncode


def main():
    if sys.version_info < (3, 8):
        print("Требуется Python 3.8 или новее.", file=sys.stderr)
        return 1
    if len(sys.argv) == 3 and sys.argv[1] == "_serve":
        return serve(int(sys.argv[2]))
    parser = argparse.ArgumentParser(description="Локальный запуск полного узла MCN")
    parser.add_argument("command", nargs="?", default="run", choices=["run", "status", "stop", "logs", "check", "wait", "foreground"])
    command = parser.parse_args().command
    if command == "foreground":
        return launch(foreground=True)
    if command == "wait":
        return subprocess.run(NODE + ["wait-sync", "--timeout", "43200"], cwd=ROOT).returncode
    actions = {"run": launch, "status": status, "stop": stop, "logs": show_logs, "check": check_requirements}
    return actions[command]()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"MCN: {error}", file=sys.stderr)
        sys.exit(1)
