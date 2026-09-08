"""Start the local app, evaluation worker and optional ERP with one owned process tree."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent


@dataclass
class Service:
    name: str
    command: list[str]
    cwd: Path
    port: int | None = None
    health_url: str | None = None


@dataclass
class Child:
    service: Service
    process: subprocess.Popen
    log: BinaryIO
    log_path: Path


def ensure_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            raise RuntimeError(f"Port {port} is already in use. Stop its owner or change the relevant service setting.") from exc


def load_environment() -> dict[str, str]:
    env = dict(os.environ)
    dotenv = ROOT / ".env"
    if dotenv.exists():
        try:
            from dotenv import dotenv_values
        except ImportError as exc:
            raise RuntimeError("Reading .env requires python-dotenv; run this script with the project .venv Python after uv sync --locked.") from exc
        for name, value in dotenv_values(dotenv).items():
            if value is not None:
                env.setdefault(name, value)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + existing if existing else "")
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["ASU_DATA_DIR"] = str(Path(env.get("ASU_DATA_DIR", str(ROOT / ".local" / "asu"))).resolve())
    return env


def find_python(explicit: str | None) -> str:
    if explicit:
        candidate = Path(explicit)
        executable = str(candidate.resolve()) if candidate.exists() else shutil.which(explicit)
        if not executable:
            raise RuntimeError("The requested Python executable does not exist.")
        return executable
    candidate = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(candidate) if candidate.exists() else sys.executable


def plans(args: argparse.Namespace, env: dict[str, str]) -> list[Service]:
    python = find_python(args.python)
    result: list[Service] = []
    if args.erp:
        java = shutil.which("java")
        if not java and env.get("JAVA_HOME"):
            candidate = Path(env["JAVA_HOME"]) / "bin" / ("java.exe" if os.name == "nt" else "java")
            java = str(candidate) if candidate.exists() else None
        if not java:
            raise RuntimeError("Java is unavailable. Install Java 21 or set JAVA_HOME before --erp.")
        jar = Path(args.erp_jar).resolve() if args.erp_jar else ROOT / "erp-service/target/erp-service-1.0.0.jar"
        if not jar.is_file():
            raise RuntimeError(f"ERP jar missing: {jar}. Build it first with mvn -f erp-service/pom.xml package.")
        erp_port = int(env.get("ERP_PORT", "8080"))
        if not 1 <= erp_port <= 65535:
            raise RuntimeError("ERP_PORT must be between 1 and 65535.")
        env["ERP_API_BASE_URL"] = f"http://127.0.0.1:{erp_port}/api"
        env["ERP_BIND_ADDRESS"] = "127.0.0.1"
        result.append(Service("erp", [java, "-jar", str(jar)], ROOT / "erp-service", erp_port,
                              f"http://127.0.0.1:{erp_port}/actuator/health"))
    if args.quotes:
        quote_port = int(env.get("QUOTE_PORT", "8086"))
        if not 1 <= quote_port <= 65535:
            raise RuntimeError("QUOTE_PORT must be between 1 and 65535.")
        result.append(Service("quotes", [python, "-m", "mcp_server.quote_server"], ROOT, quote_port))
    if args.mode == "live":
        if not env.get("DEEPSEEK_API_KEY") or env["DEEPSEEK_API_KEY"].startswith("replace-"):
            raise RuntimeError("Live mode requires a real DEEPSEEK_API_KEY. Demo mode does not call a model.")
        secret = env.get("JWT_SECRET_KEY", "")
        if len(secret) < 32 or secret.startswith("replace-"):
            raise RuntimeError("Live mode requires JWT_SECRET_KEY with at least 32 characters.")
        mcp_port = int(env.get("MCP_PORT", "8000"))
        if not 1 <= mcp_port <= 65535:
            raise RuntimeError("MCP_PORT must be between 1 and 65535.")
        env["MCP_HOST"] = "127.0.0.1"
        env["ERP_MCP_URL"] = f"http://127.0.0.1:{mcp_port}/mcp"
        result.append(Service("mcp", [python, "-m", "mcp_server.server_main"], ROOT, mcp_port))
        env["ASYNC_AGENT_PROTOCOL_URL"] = f"http://127.0.0.1:{args.protocol_port}"
        result.append(Service("agent-protocol", [python, "-m", "langgraph_cli", "dev", "--host", "127.0.0.1",
                                                "--port", str(args.protocol_port), "--no-browser", "--no-reload", "--allow-blocking"],
                              ROOT, args.protocol_port, f"http://127.0.0.1:{args.protocol_port}/ok"))
    target = "asu_lab.app:create_app" if args.mode == "demo" else "api_view.web_main:app"
    env["API_PROXY_TARGET"] = f"http://127.0.0.1:{args.api_port}"
    command = [python, "-m", "uvicorn", target, "--host", "127.0.0.1", "--port", str(args.api_port)]
    if args.mode == "demo":
        command.append("--factory")
    result.append(Service("api", command, ROOT, args.api_port, f"http://127.0.0.1:{args.api_port}/health"))
    if not args.no_worker:
        if args.delivery == "langfuse" and not all(env.get(name) for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")):
            raise RuntimeError("Langfuse delivery requires project public and secret keys. Use offline for local evaluation.")
        result.append(Service("worker", [python, "-m", "asu_eval.worker", "--db",
                                        str(Path(env["ASU_DATA_DIR"]) / "evaluation.sqlite3"),
                                        "--delivery", args.delivery], ROOT))
    if not args.no_frontend:
        node = shutil.which("node")
        vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
        if not node or not vite.is_file():
            raise RuntimeError("Frontend dependencies are unavailable. Install Node 22, run npm ci in frontend, or pass --no-frontend.")
        version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10, **process_options())
        parts = version.stdout.strip().lstrip("v").split(".")
        if version.returncode or len(parts) < 2 or not all(part.isdigit() for part in parts[:2]) or tuple(map(int, parts[:2])) < (22, 12):
            raise RuntimeError("Frontend requires Node 22.12 or newer; use --no-frontend for the Python services only.")
        result.append(Service("frontend", [node, str(vite), "--host", "127.0.0.1", "--port", str(args.frontend_port), "--strictPort"],
                              ROOT / "frontend", args.frontend_port, f"http://127.0.0.1:{args.frontend_port}/"))
    return result


def process_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def start(service: Service, env: dict[str, str], log_dir: Path) -> Child:
    log_path = log_dir / f"{service.name}.log"
    handle = log_path.open("ab", buffering=0)
    try:
        process = subprocess.Popen(service.command, cwd=service.cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=handle, stderr=subprocess.STDOUT, **process_options())
    except BaseException:
        handle.close()
        raise
    return Child(service, process, handle, log_path)


def stop(child: Child) -> None:
    try:
        if child.process.poll() is None:
            if os.name == "nt":
                # Kill only the tree created and tracked by this launcher; no visible cmd window.
                subprocess.run(["taskkill", "/PID", str(child.process.pid), "/T", "/F"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=15, check=False)
            else:
                try:
                    os.killpg(child.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                child.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    try:
                        os.killpg(child.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    child.process.kill()
                child.process.wait(timeout=5)
    finally:
        child.log.close()


def assert_alive(children: list[Child]) -> None:
    for child in children:
        code = child.process.poll()
        if code is not None:
            raise RuntimeError(f"{child.service.name} exited with code {code}; see {child.log_path}")


def wait_ready(child: Child, children: list[Child], timeout: float) -> None:
    if child.service.port is None:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert_alive(children)
        try:
            if child.service.health_url:
                with urlopen(child.service.health_url, timeout=1) as response:
                    if response.status == 200:
                        return
            else:
                with socket.create_connection(("127.0.0.1", child.service.port), timeout=1):
                    return
        except (OSError, URLError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"{child.service.name} did not become ready within {timeout:g}s; see {child.log_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ASu Agent Lab locally; never installs dependencies or calls a model in demo mode")
    parser.add_argument("--mode", choices=("demo", "live"), default="demo")
    parser.add_argument("--erp", action="store_true", help="Also start the already-built synthetic Java ERP")
    parser.add_argument("--erp-jar", help="Path to an existing ERP jar, used with --erp")
    parser.add_argument("--quotes", action="store_true", help="Also serve the synthetic supplier quotation pages")
    parser.add_argument("--python", help="Python executable; defaults to the project .venv")
    parser.add_argument("--no-frontend", action="store_true")
    parser.add_argument("--no-worker", action="store_true")
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--api-port", type=int, default=8090)
    parser.add_argument("--protocol-port", type=int, default=2024, help="Local async Agent Protocol port in live mode")
    parser.add_argument("--delivery", choices=("offline", "langfuse"), default="offline")
    parser.add_argument("--wait-timeout", type=float, default=90)
    parser.add_argument("--check", action="store_true", help="Validate dependencies, settings and free ports without starting services")
    parser.add_argument("--stop-after", type=float, help="Stop cleanly after this many seconds of ready uptime; useful for local smoke checks")
    args = parser.parse_args(argv)
    if not all(1 <= port <= 65535 for port in (args.frontend_port, args.api_port, args.protocol_port)) or args.wait_timeout <= 0 or (args.stop_after is not None and args.stop_after <= 0):
        parser.error("ports and timeouts must be positive and valid")
    children: list[Child] = []
    previous_signals = {}

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    try:
        env = load_environment()
        selected = plans(args, env)
        ports = [service.port for service in selected if service.port is not None]
        if len(ports) != len(set(ports)):
            raise RuntimeError("Selected services have conflicting ports; choose different service settings.")
        for service in selected:
            if service.port is not None:
                ensure_port_free(service.port)
        python = find_python(args.python)
        imports = "import uvicorn; import asu_lab.app; import asu_eval.worker"
        if args.mode == "live":
            imports += "; import langgraph_cli; import fastmcp"
        probe = subprocess.run([python, "-c", imports],
                               cwd=ROOT, env=env, capture_output=True, text=True, timeout=30, **process_options())
        if probe.returncode:
            raise RuntimeError("Python dependencies are incomplete; run uv sync --locked before starting. Import probe failed: " + probe.stderr[-800:])
        if args.check:
            print("Preflight passed: " + ", ".join(service.name for service in selected))
            return 0
        log_dir = Path(env["ASU_DATA_DIR"]) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_signals[sig] = signal.signal(sig, interrupted)
        for service in selected:
            child = start(service, env, log_dir)
            children.append(child)
            wait_ready(child, children, args.wait_timeout)
            print(f"Started {service.name}; log: {child.log_path}", flush=True)
        print(f"Mode: {args.mode}; API: http://127.0.0.1:{args.api_port}/docs; delivery: {args.delivery}", flush=True)
        if not args.no_frontend:
            print(f"Frontend: http://127.0.0.1:{args.frontend_port}", flush=True)
        print("Press Ctrl+C to stop this launcher's services.", flush=True)
        deadline = time.monotonic() + args.stop_after if args.stop_after else None
        while deadline is None or time.monotonic() < deadline:
            assert_alive(children)
            time.sleep(0.25)
        return 0
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        for child in reversed(children):
            try:
                stop(child)
            except (OSError, subprocess.SubprocessError) as exc:
                print(f"Could not finish stopping {child.service.name}: {type(exc).__name__}", file=sys.stderr)
        for sig, previous in previous_signals.items():
            signal.signal(sig, previous)


if __name__ == "__main__":
    raise SystemExit(main())
