from __future__ import annotations

import os
import subprocess
from typing import Any, Dict


class CommandRunner:
    @staticmethod
    def run(command: Any, env: Dict[str, str]) -> None:
        if not command:
            return
        child_env = os.environ.copy()
        child_env.update(env)

        if isinstance(command, list):
            subprocess.Popen(command, env=child_env)
        elif isinstance(command, str):
            subprocess.Popen(command, shell=True, env=child_env)
        else:
            raise TypeError("command must be a string or a list")
