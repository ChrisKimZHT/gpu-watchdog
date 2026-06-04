from __future__ import annotations

from contextlib import ExitStack
import os
import subprocess
from typing import Any, Dict, IO, Mapping, MutableMapping, Optional, Sequence, Union


CommandValue = Union[str, Sequence[str]]


COMMAND_KEYS = {
    "command",
    "env",
    "env_mode",
    "stdin",
    "stdout",
    "stderr",
    "cwd",
    "start_new_session",
}


class CommandRunner:
    @staticmethod
    def run(command: Any, env: Dict[str, str]) -> None:
        if not command:
            return

        if isinstance(command, list):  # allow list of strings for convenience, but join into a single string for subprocess
            command = " ".join(command)

        if isinstance(command, str):
            CommandRunner._popen(command, shell=True, env=CommandRunner._child_env(env))
        elif isinstance(command, dict):
            CommandRunner._run_advanced(command, env)
        else:
            raise TypeError("command must be a string, a list, or a dict")

    @staticmethod
    def _run_advanced(config: Mapping[str, Any], event_env: Dict[str, str]) -> None:
        unknown_keys = sorted(set(config) - COMMAND_KEYS)
        if unknown_keys:
            joined = ", ".join(unknown_keys)
            raise TypeError(f"command has unknown fields: {joined}")

        command = config.get("command")
        if not command:
            return
        if isinstance(command, list):  # allow list of strings for convenience, but join into a single string for subprocess
            command = " ".join(command)

        child_env = CommandRunner._child_env(
            event_env,
            custom_env=config.get("env"),
            env_mode=str(config.get("env_mode", "merge")),
        )

        with ExitStack() as stack:
            popen_kwargs: Dict[str, Any] = {
                "env": child_env,
                "cwd": config.get("cwd"),
                "start_new_session": bool(config.get("start_new_session", False)),
            }
            CommandRunner._add_stdio(popen_kwargs, config, stack)
            CommandRunner._popen(command, shell=True, **popen_kwargs)

    @staticmethod
    def _child_env(
        event_env: Dict[str, str],
        custom_env: Optional[Mapping[str, Any]] = None,
        env_mode: str = "merge",
    ) -> Dict[str, str]:
        if env_mode == "merge":
            child_env: Dict[str, str] = os.environ.copy()
            child_env.update(event_env)
            if custom_env:
                child_env.update(CommandRunner._string_env(custom_env))
            return child_env
        if env_mode == "replace":
            child_env = dict(event_env)
            if custom_env:
                child_env.update(CommandRunner._string_env(custom_env))
            return child_env
        raise TypeError("command.env_mode must be 'merge' or 'replace'")

    @staticmethod
    def _string_env(env: Mapping[str, Any]) -> Dict[str, str]:
        return {str(key): str(value) for key, value in env.items()}

    @staticmethod
    def _add_stdio(
        popen_kwargs: MutableMapping[str, Any],
        config: Mapping[str, Any],
        stack: ExitStack,
    ) -> None:
        stdin = CommandRunner._open_stdio(config.get("stdin"), "rb", stack)
        stdout = CommandRunner._open_stdio(config.get("stdout"), "ab", stack)
        stderr = CommandRunner._open_stdio(config.get("stderr"), "ab", stack)
        if stdin is not None:
            popen_kwargs["stdin"] = stdin
        if stdout is not None:
            popen_kwargs["stdout"] = stdout
        if stderr is not None:
            popen_kwargs["stderr"] = stderr

    @staticmethod
    def _open_stdio(path: Any, mode: str, stack: ExitStack) -> Optional[IO[Any]]:
        if path is None:
            return None
        return stack.enter_context(open(os.fspath(path), mode))

    @staticmethod
    def _popen(command: CommandValue, **kwargs: Any) -> None:
        subprocess.Popen(command, **kwargs)
