import asyncio
import ipaddress
import json
import os
import re
import time
from contextlib import suppress
from typing import Any

import decky

DEFAULT_CONFIG: dict[str, Any] = {
    "ip": "127.0.0.1",
    "port": 1242,
    "tcp_mode": False,
}

WAITING_ATTEMPT_RE = re.compile(
    r"timed out waiting for data from server(?:; attempt (\d+))?",
    re.IGNORECASE,
)
WAITING_STATUS_PREFIX = "Wait for server attempt: "
WAITING_TO_CONNECTED_QUIET_SECONDS = 1.5
AWIM_STARTUP_EXIT_TIMEOUT_SECONDS = 1.2
AWIM_STOP_TIMEOUT_SECONDS = 3.0
PIPEWIRE_MODULE_DIR_CANDIDATES = [
    "/usr/lib/pipewire-0.3",
    "/usr/lib64/pipewire-0.3",
    "/lib/pipewire-0.3",
]
SPA_PLUGIN_DIR_CANDIDATES = [
    "/usr/lib/spa-0.2",
    "/usr/lib64/spa-0.2",
    "/lib/spa-0.2",
]


class Plugin:
    def __init__(self):
        self.settings_path = ""
        self.config: dict[str, Any] = DEFAULT_CONFIG.copy()

        self.awim_process: asyncio.subprocess.Process | None = None
        self.awim_stdout_task: asyncio.Task[None] | None = None
        self.awim_stderr_task: asyncio.Task[None] | None = None
        self.awim_exit_task: asyncio.Task[None] | None = None
        self._stopping_awim = False

        self.connection_status = "Stopped"
        self.waiting_attempt: int | None = None
        self.error_code: int | None = None
        self.last_waiting_signal_at: float | None = None

    async def _main(self):
        os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
        self.settings_path = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")
        self.config = self._load_config()
        decky.logger.info("AWiM Deck initialized with %s:%s", self.config["ip"], self.config["port"])

    async def _unload(self):
        await self._stop_awim()
        decky.logger.info("AWiM Deck unloaded")

    async def _uninstall(self):
        await self._stop_awim()

    async def _migration(self):
        # No migration required yet.
        return

    async def get_state(self) -> dict[str, Any]:
        return self._state()

    async def validate_ip(self, address: str) -> bool:
        return self._is_valid_ip(address)

    async def validate_port(self, port: int) -> bool:
        return self._is_valid_port(port)

    async def update_config(self, address: str, port: int) -> dict[str, Any]:
        if not self._is_valid_ip(address):
            raise ValueError("IP must be a valid IPv4 or IPv6 address.")

        if not self._is_valid_port(port):
            raise ValueError("Port must be in range 1024-65535.")

        self.config["ip"] = address
        self.config["port"] = port
        self._save_config()
        return self._state()

    async def set_tcp_mode(self, tcp_mode: bool) -> dict[str, Any]:
        if not isinstance(tcp_mode, bool):
            raise ValueError("tcp_mode must be a boolean value.")

        self.config["tcp_mode"] = tcp_mode
        self._save_config()
        return self._state()

    async def set_enabled(self, enabled: bool) -> dict[str, Any]:
        try:
            if enabled:
                await self._start_awim()
            else:
                await self._stop_awim()
            return self._state()
        except Exception as error:
            decky.logger.exception("Failed to change AWiM Deck state")
            raise RuntimeError(str(error)) from error

    def _state(self) -> dict[str, Any]:
        self._refresh_process_state()
        self._infer_connected_after_waiting_quiet_period()

        process = self.awim_process
        return {
            "ip": self.config["ip"],
            "port": self.config["port"],
            "tcp_mode": self.config["tcp_mode"],
            "running": process is not None,
            "pid": process.pid if process is not None else None,
            "status": self.connection_status,
            "attempt": self.waiting_attempt,
            "error_code": self.error_code,
        }

    def _set_status(
        self,
        status: str,
        *,
        waiting_attempt: int | None = None,
        error_code: int | None = None,
        mark_waiting: bool = False,
    ):
        self.connection_status = status
        self.waiting_attempt = waiting_attempt
        self.error_code = error_code
        self.last_waiting_signal_at = time.monotonic() if mark_waiting else None

    def _set_stopped_status(self):
        self._set_status("Stopped")

    def _set_connected_status(self):
        self._set_status("Connected")

    def _set_waiting_status(self, attempt: int):
        self._set_status(
            f"{WAITING_STATUS_PREFIX}{attempt}",
            waiting_attempt=attempt,
            mark_waiting=True,
        )

    def _set_error_status(self, code: int):
        self._set_status(f"Error code: {code}", error_code=code)

    def _apply_exit_code(self, code: int, details: str = ""):
        details = details.strip()
        if code == 0:
            self._set_stopped_status()
            if details:
                decky.logger.info("awim exited with code 0: %s", details)
            else:
                decky.logger.info("awim exited with code 0")
            return

        self._set_error_status(code)
        if details:
            decky.logger.warning("awim exited with code %s: %s", code, details)
        else:
            decky.logger.warning("awim exited with code %s", code)

    def _refresh_process_state(self):
        process = self.awim_process
        if process is None or process.returncode is None:
            return

        self.awim_process = None
        if self._stopping_awim:
            return

        self._apply_exit_code(process.returncode)

    def _infer_connected_after_waiting_quiet_period(self):
        if self.awim_process is None:
            return
        if not self.connection_status.startswith(WAITING_STATUS_PREFIX):
            return
        if self.last_waiting_signal_at is None:
            return

        quiet_seconds = time.monotonic() - self.last_waiting_signal_at
        if quiet_seconds < WAITING_TO_CONNECTED_QUIET_SECONDS:
            return

        self._set_connected_status()

    def _load_config(self) -> dict[str, Any]:
        config = DEFAULT_CONFIG.copy()
        if not self.settings_path or not os.path.isfile(self.settings_path):
            return config

        try:
            with open(self.settings_path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            decky.logger.warning("Failed to read settings: %s", error)
            return config

        if not isinstance(loaded, dict):
            return config

        address = loaded.get("ip")
        if isinstance(address, str) and self._is_valid_ip(address):
            config["ip"] = address

        loaded_port = loaded.get("port")
        if isinstance(loaded_port, int) and self._is_valid_port(loaded_port):
            config["port"] = loaded_port

        loaded_tcp_mode = loaded.get("tcp_mode")
        if isinstance(loaded_tcp_mode, bool):
            config["tcp_mode"] = loaded_tcp_mode

        return config

    def _save_config(self):
        with open(self.settings_path, "w", encoding="utf-8") as file:
            json.dump(self.config, file, indent=2)

    @staticmethod
    def _is_valid_ip(address: str) -> bool:
        if not isinstance(address, str):
            return False
        try:
            ipaddress.ip_address(address)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_valid_port(port: int) -> bool:
        if not isinstance(port, int):
            return False
        return 1024 <= port <= 65535

    def _awim_path(self) -> str:
        candidates = [
            os.path.join(decky.DECKY_PLUGIN_DIR, "bin", "awim"),
            os.path.join(decky.DECKY_PLUGIN_DIR, "backend", "out", "awim"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path

        raise FileNotFoundError("Could not find awim binary in bin/awim or backend/out/awim.")

    def _is_running(self) -> bool:
        self._refresh_process_state()
        return self.awim_process is not None

    async def _start_awim(self):
        if self._is_running():
            return

        await self._cancel_process_tasks()

        awim_path = self._awim_path()
        env = self._build_awim_env()
        args = [awim_path, "--ip", self.config["ip"], "--port", str(self.config["port"])]
        if self.config["tcp_mode"]:
            args.append("--tcp-mode")

        self._set_waiting_status(1)
        self._stopping_awim = False

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as error:
            if os.path.isfile(awim_path):
                raise RuntimeError(
                    "awim exists but failed to start. Likely incompatible binary for SteamOS "
                    "(libc/architecture mismatch). Rebuild backend in Decky Docker/holo-base."
                ) from error
            raise RuntimeError("awim binary was not found in plugin bin directory.") from error
        except OSError as error:
            raise RuntimeError(f"OS error while starting awim: {error}") from error

        self.awim_process = process
        self.awim_stdout_task = asyncio.create_task(self._consume_stream(process.stdout, "stdout"))
        self.awim_stderr_task = asyncio.create_task(self._consume_stream(process.stderr, "stderr"))

        code = await self._wait_for_exit(process, AWIM_STARTUP_EXIT_TIMEOUT_SECONDS)
        if code is not None:
            await self._handle_early_exit(process, code, env)
            return

        if self.awim_process is not process:
            return

        self.awim_exit_task = asyncio.create_task(self._watch_process_exit(process))
        decky.logger.info("awim started with PID %s", process.pid)

    async def _wait_for_exit(
        self,
        process: asyncio.subprocess.Process,
        timeout_seconds: float,
    ) -> int | None:
        try:
            return await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            return None

    async def _handle_early_exit(
        self,
        process: asyncio.subprocess.Process,
        code: int,
        env: dict[str, str],
    ):
        details = await self._read_process_details(process)
        if self.awim_process is process:
            self.awim_process = None

        await self._cancel_process_tasks()

        if code == 0:
            self._set_stopped_status()
            if details:
                decky.logger.info("awim exited immediately with code 0: %s", details)
            else:
                decky.logger.info("awim exited immediately with code 0")
            return

        self._set_error_status(code)
        if details:
            decky.logger.warning(
                "awim exited immediately with code %s: %s "
                "(PIPEWIRE_MODULE_DIR=%s, SPA_PLUGIN_DIR=%s)",
                code,
                details,
                env.get("PIPEWIRE_MODULE_DIR", ""),
                env.get("SPA_PLUGIN_DIR", ""),
            )
        else:
            decky.logger.warning("awim exited immediately with code %s", code)

    async def _read_process_details(self, process: asyncio.subprocess.Process) -> str:
        stdout = ""
        stderr = ""
        if process.stdout is not None:
            stdout = (await process.stdout.read()).decode(errors="replace").strip()
        if process.stderr is not None:
            stderr = (await process.stderr.read()).decode(errors="replace").strip()

        return " ".join(part for part in [stderr, stdout] if part)

    async def _watch_process_exit(self, process: asyncio.subprocess.Process):
        current_task = asyncio.current_task()
        try:
            code = await process.wait()
        except asyncio.CancelledError:
            return
        finally:
            if self.awim_exit_task is current_task:
                self.awim_exit_task = None

        if self.awim_process is not process:
            return

        self.awim_process = None

        if self._stopping_awim:
            return

        await self._cancel_stream_tasks()
        self._apply_exit_code(code)

    async def _stop_awim(self):
        process = self.awim_process
        if process is None:
            self._set_stopped_status()
            await self._cancel_process_tasks()
            return

        self._stopping_awim = True
        with suppress(ProcessLookupError):
            process.terminate()

        try:
            await asyncio.wait_for(process.wait(), timeout=AWIM_STOP_TIMEOUT_SECONDS)
            decky.logger.info("awim stopped with SIGTERM")
        except TimeoutError:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            decky.logger.info("awim stopped with SIGKILL")
        finally:
            self.awim_process = None
            self._stopping_awim = False
            self._set_stopped_status()
            await self._cancel_process_tasks()

    async def _consume_stream(self, stream: asyncio.StreamReader | None, stream_name: str):
        if stream is None:
            return

        while True:
            line = await stream.readline()
            if not line:
                return

            message = line.decode(errors="replace").strip()
            if not message:
                continue

            decky.logger.info("awim %s: %s", stream_name, message)
            self._update_connection_status_from_log(message)

    def _update_connection_status_from_log(self, message: str):
        if re.fullmatch(r"Connected", message, re.IGNORECASE):
            self._set_connected_status()
            return

        waiting_match = WAITING_ATTEMPT_RE.search(message)
        if waiting_match is not None:
            raw_attempt = waiting_match.group(1)
            attempt = int(raw_attempt) if raw_attempt is not None else self._next_waiting_attempt()
            self._set_waiting_status(attempt)
            return

        lowered = message.lower()
        if "connection reset" in lowered or "connection closed" in lowered:
            self._set_waiting_status(self._next_waiting_attempt())

    def _next_waiting_attempt(self) -> int:
        if self.waiting_attempt is None:
            return 1
        return self.waiting_attempt + 1

    async def _cancel_stream_tasks(self):
        for task in [self.awim_stdout_task, self.awim_stderr_task]:
            if task is None:
                continue
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        self.awim_stdout_task = None
        self.awim_stderr_task = None

    async def _cancel_exit_task(self):
        task = self.awim_exit_task
        if task is None:
            return

        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        self.awim_exit_task = None

    async def _cancel_process_tasks(self):
        await self._cancel_stream_tasks()
        await self._cancel_exit_task()

    @staticmethod
    def _first_existing_path(candidates: list[str]) -> str | None:
        for path in candidates:
            if os.path.isdir(path):
                return path
        return None

    def _set_env_path_if_missing(self, env: dict[str, str], key: str, candidates: list[str]):
        if key in env:
            return

        discovered = self._first_existing_path(candidates)
        if discovered is not None:
            env[key] = discovered

    def _build_awim_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

        self._set_env_path_if_missing(env, "PIPEWIRE_MODULE_DIR", PIPEWIRE_MODULE_DIR_CANDIDATES)
        self._set_env_path_if_missing(env, "SPA_PLUGIN_DIR", SPA_PLUGIN_DIR_CANDIDATES)
        return env
