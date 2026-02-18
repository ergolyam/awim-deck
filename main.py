import asyncio
import ipaddress
import json
import os
from contextlib import suppress
from typing import Any

import decky


class Plugin:
    def __init__(self):
        self.settings_path = ""
        self.awim_process: asyncio.subprocess.Process | None = None
        self.awim_stdout_task: asyncio.Task[None] | None = None
        self.awim_stderr_task: asyncio.Task[None] | None = None
        self.config: dict[str, Any] = {
            "ip": "127.0.0.1",
            "port": 1242,
        }

    async def _main(self):
        os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
        self.settings_path = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")
        self.config = self._load_config()
        decky.logger.info("awim-deck initialized with %s:%s", self.config["ip"], self.config["port"])

    async def _unload(self):
        await self._stop_awim()
        decky.logger.info("awim-deck unloaded")

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

    async def set_enabled(self, enabled: bool) -> dict[str, Any]:
        try:
            if enabled:
                await self._start_awim()
            else:
                await self._stop_awim()
            return self._state()
        except Exception as error:
            decky.logger.exception("Failed to change AWiM state")
            raise RuntimeError(str(error)) from error

    def _state(self) -> dict[str, Any]:
        running = self._is_running()
        pid: int | None = self.awim_process.pid if running and self.awim_process is not None else None
        return {
            "ip": self.config["ip"],
            "port": self.config["port"],
            "running": running,
            "pid": pid,
        }

    def _load_config(self) -> dict[str, Any]:
        defaults = {
            "ip": "127.0.0.1",
            "port": 1242,
        }
        if not self.settings_path or not os.path.isfile(self.settings_path):
            return defaults

        try:
            with open(self.settings_path, "r", encoding="utf-8") as file:
                loaded = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            decky.logger.warning("Failed to read settings: %s", error)
            return defaults

        address = loaded.get("ip")
        if isinstance(address, str) and self._is_valid_ip(address):
            defaults["ip"] = address

        loaded_port = loaded.get("port")
        if isinstance(loaded_port, int) and self._is_valid_port(loaded_port):
            defaults["port"] = loaded_port

        return defaults

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
        primary = os.path.join(decky.DECKY_PLUGIN_DIR, "bin", "awim")
        fallback = os.path.join(decky.DECKY_PLUGIN_DIR, "backend", "out", "awim")
        if os.path.isfile(primary):
            return primary
        if os.path.isfile(fallback):
            return fallback
        raise FileNotFoundError("Could not find awim binary in bin/awim or backend/out/awim.")

    def _is_running(self) -> bool:
        if self.awim_process is None:
            return False
        if self.awim_process.returncode is not None:
            self.awim_process = None
            return False
        return True

    async def _start_awim(self):
        if self._is_running():
            return

        awim_path = self._awim_path()
        binary_dir = os.path.dirname(awim_path)
        env = self._build_awim_env()

        try:
            self.awim_process = await asyncio.create_subprocess_exec(
                "./awim",
                "--ip",
                self.config["ip"],
                "--port",
                str(self.config["port"]),
                cwd=binary_dir,
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

        await asyncio.sleep(0.4)
        if self.awim_process.returncode is not None:
            code = self.awim_process.returncode
            stdout = ""
            stderr = ""
            if self.awim_process.stdout is not None:
                stdout = (await self.awim_process.stdout.read()).decode(errors="replace").strip()
            if self.awim_process.stderr is not None:
                stderr = (await self.awim_process.stderr.read()).decode(errors="replace").strip()
            self.awim_process = None
            details = " ".join(part for part in [stderr, stdout] if part)
            if details:
                raise RuntimeError(
                    f"awim exited immediately with code {code}: {details} "
                    f"(PIPEWIRE_MODULE_DIR={env.get('PIPEWIRE_MODULE_DIR', '')}, "
                    f"SPA_PLUGIN_DIR={env.get('SPA_PLUGIN_DIR', '')})"
                )
            raise RuntimeError(f"awim exited immediately with code {code}.")

        self.awim_stdout_task = asyncio.create_task(self._consume_stream(self.awim_process.stdout, "stdout"))
        self.awim_stderr_task = asyncio.create_task(self._consume_stream(self.awim_process.stderr, "stderr"))

        decky.logger.info("awim started with PID %s", self.awim_process.pid)

    async def _stop_awim(self):
        if not self._is_running() or self.awim_process is None:
            self.awim_process = None
            await self._cancel_stream_tasks()
            return

        process = self.awim_process
        with suppress(ProcessLookupError):
            process.terminate()

        try:
            await asyncio.wait_for(process.wait(), timeout=3)
            decky.logger.info("awim stopped with SIGTERM")
        except TimeoutError:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()
            decky.logger.info("awim stopped with SIGKILL")
        finally:
            self.awim_process = None
            await self._cancel_stream_tasks()

    async def _consume_stream(self, stream: asyncio.StreamReader | None, stream_name: str):
        if stream is None:
            return

        while True:
            line = await stream.readline()
            if not line:
                return
            message = line.decode(errors="replace").strip()
            if message:
                decky.logger.info("awim %s: %s", stream_name, message)

    async def _cancel_stream_tasks(self):
        for task in [self.awim_stdout_task, self.awim_stderr_task]:
            if task is not None and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        self.awim_stdout_task = None
        self.awim_stderr_task = None

    @staticmethod
    def _first_existing_path(candidates: list[str]) -> str | None:
        for path in candidates:
            if os.path.isdir(path):
                return path
        return None

    def _build_awim_env(self) -> dict[str, str]:
        env = os.environ.copy()

        uid = os.getuid()
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")

        if "PIPEWIRE_MODULE_DIR" not in env:
            module_dir = self._first_existing_path(
                [
                    "/usr/lib/pipewire-0.3",
                    "/usr/lib64/pipewire-0.3",
                    "/lib/pipewire-0.3",
                ]
            )
            if module_dir is not None:
                env["PIPEWIRE_MODULE_DIR"] = module_dir

        if "SPA_PLUGIN_DIR" not in env:
            spa_dir = self._first_existing_path(
                [
                    "/usr/lib/spa-0.2",
                    "/usr/lib64/spa-0.2",
                    "/lib/spa-0.2",
                ]
            )
            if spa_dir is not None:
                env["SPA_PLUGIN_DIR"] = spa_dir

        return env
