from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, MutableMapping


RULE_TYPES = {"cpu", "memory", "disk", "gpu", "process"}
RULE_KINDS = {"busy", "idle"}
MATCH_MODES = {"any", "all"}
EVENT_KINDS = {"alert", "reminder"}
BARK_KEYS = {"enabled", "server", "device_key", "timeout_seconds", "level", "passthrough"}
SMTP_KEYS = {
    "enabled",
    "host",
    "port",
    "username",
    "password",
    "from_addr",
    "to_addrs",
    "timeout_seconds",
    "ssl",
    "starttls",
}
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
COMMAND_ENV_MODES = {"merge", "replace"}

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_BARK_SERVER = "https://api.day.app"
DEFAULT_BARK_TIMEOUT_SECONDS = 10.0
DEFAULT_BARK_LEVEL = "active"
DEFAULT_SMTP_TIMEOUT_SECONDS = 10.0


def normalize_config(raw_config: Any) -> Dict[str, Any]:
    """Validate config and return a copy with implicit defaults filled."""
    config = _require_object(raw_config, "config")

    normalized: Dict[str, Any] = dict(config)
    normalized["interval_seconds"] = _positive_number(config.get("interval_seconds"), "interval_seconds")
    normalized["cooldown_seconds"] = _non_negative_number(config.get("cooldown_seconds"), "cooldown_seconds")
    normalized["log_level"] = str(config.get("log_level", DEFAULT_LOG_LEVEL))
    normalized["notifiers"] = _normalize_notifiers(config.get("notifiers", {}))
    normalized["rules"] = _normalize_rules(config.get("rules", []), normalized["cooldown_seconds"])
    return normalized


def _normalize_notifiers(raw_notifiers: Any) -> Dict[str, Any]:
    notifiers = _require_object(raw_notifiers, "notifiers")
    normalized: Dict[str, Any] = dict(notifiers)

    if "bark" in notifiers:
        bark = _require_object(notifiers["bark"], "notifiers.bark")
        normalized["bark"] = _normalize_bark(bark)

    if "smtp" in notifiers:
        smtp = _require_object(notifiers["smtp"], "notifiers.smtp")
        normalized["smtp"] = _normalize_smtp(smtp)

    return normalized


def _normalize_bark(raw_bark: Mapping[str, Any]) -> Dict[str, Any]:
    unknown_keys = sorted(set(raw_bark) - BARK_KEYS)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise ValueError(f"notifiers.bark passthrough fields must be inside passthrough: {joined}")

    enabled = _bool_value(raw_bark.get("enabled", True), "notifiers.bark.enabled")
    passthrough = _require_object(raw_bark.get("passthrough", {}), "notifiers.bark.passthrough")
    bark = {
        "enabled": enabled,
        "server": str(raw_bark.get("server", DEFAULT_BARK_SERVER)).rstrip("/"),
        "timeout_seconds": _positive_number(
            raw_bark.get("timeout_seconds", DEFAULT_BARK_TIMEOUT_SECONDS),
            "notifiers.bark.timeout_seconds",
        ),
        "level": str(raw_bark.get("level", DEFAULT_BARK_LEVEL)),
        "device_key": str(raw_bark.get("device_key", "")).strip(),
        "passthrough": {
            key: value
            for key, value in passthrough.items()
            if value is not None
        },
    }
    if enabled and not bark["device_key"]:
        raise ValueError("notifiers.bark.device_key is required when Bark is enabled")
    return bark


def _normalize_smtp(raw_smtp: Mapping[str, Any]) -> Dict[str, Any]:
    unknown_keys = sorted(set(raw_smtp) - SMTP_KEYS)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise ValueError(f"notifiers.smtp has unknown fields: {joined}")

    enabled = _bool_value(raw_smtp.get("enabled", True), "notifiers.smtp.enabled")
    use_ssl = _bool_value(raw_smtp.get("ssl", False), "notifiers.smtp.ssl")
    starttls = _bool_value(raw_smtp.get("starttls", not use_ssl), "notifiers.smtp.starttls")
    if use_ssl and starttls:
        raise ValueError("notifiers.smtp.ssl and notifiers.smtp.starttls cannot both be true")

    smtp = {
        "enabled": enabled,
        "host": str(raw_smtp.get("host", "")).strip(),
        "port": _port_number(raw_smtp.get("port", 465 if use_ssl else 587), "notifiers.smtp.port"),
        "username": str(raw_smtp.get("username", "")),
        "password": str(raw_smtp.get("password", "")),
        "from_addr": str(raw_smtp.get("from_addr", "")).strip(),
        "to_addrs": _non_empty_string_list(raw_smtp.get("to_addrs", []), "notifiers.smtp.to_addrs"),
        "timeout_seconds": _positive_number(
            raw_smtp.get("timeout_seconds", DEFAULT_SMTP_TIMEOUT_SECONDS),
            "notifiers.smtp.timeout_seconds",
        ),
        "ssl": use_ssl,
        "starttls": starttls,
    }
    if enabled:
        if not smtp["host"]:
            raise ValueError("notifiers.smtp.host is required when SMTP is enabled")
        if not smtp["from_addr"]:
            raise ValueError("notifiers.smtp.from_addr is required when SMTP is enabled")
        if not smtp["to_addrs"]:
            raise ValueError("notifiers.smtp.to_addrs is required when SMTP is enabled")
    return smtp


def _normalize_rules(raw_rules: Any, default_cooldown_seconds: float) -> List[Dict[str, Any]]:
    if not isinstance(raw_rules, list):
        raise ValueError("rules must be a list")
    return [
        _normalize_rule(rule, index, default_cooldown_seconds)
        for index, rule in enumerate(raw_rules)
    ]


def _normalize_rule(raw_rule: Any, index: int, default_cooldown_seconds: float) -> Dict[str, Any]:
    path = f"rules[{index}]"
    rule = _require_object(raw_rule, path)
    normalized: Dict[str, Any] = dict(rule)

    rule_id = str(_required(rule, "id", path))
    rule_type = str(_required(rule, "type", path))
    if rule_type not in RULE_TYPES:
        raise ValueError(f"{path}.type must be one of {sorted(RULE_TYPES)}")

    options = _require_object(_required(rule, "options", path), f"{path}.options")
    normalized["id"] = rule_id
    normalized["type"] = rule_type
    normalized["notify"] = _bool_value(rule.get("notify", True), f"{path}.notify")
    normalized["cooldown_seconds"] = _non_negative_number(
        rule.get("cooldown_seconds", default_cooldown_seconds),
        f"{path}.cooldown_seconds",
    )
    normalized["pending_period"] = _non_negative_number(rule.get("pending_period", 0), f"{path}.pending_period")
    normalized["options"] = _normalize_rule_options(rule_type, options, path)
    normalized["event"] = _normalize_rule_event(rule, normalized["options"], rule_type, path)

    if "title" in rule:
        normalized["title"] = str(rule["title"])
    if "body" in rule:
        normalized["body"] = str(rule["body"])
    if "command" in rule:
        normalized["command"] = _normalize_command(rule["command"], f"{path}.command")

    return normalized


def _normalize_rule_options(rule_type: str, raw_options: Mapping[str, Any], path: str) -> Dict[str, Any]:
    options: Dict[str, Any] = dict(raw_options)
    options_path = f"{path}.options"

    if rule_type == "cpu":
        kind = _rule_kind(options.get("kind", "busy"), f"{options_path}.kind")
        options["kind"] = kind
        options["metric"] = str(options.get("metric", "some.avg10"))
        options["threshold"] = _percentage(_required(options, "threshold", options_path), f"{options_path}.threshold")
        return options

    if rule_type == "memory":
        kind = _rule_kind(options.get("kind", "busy"), f"{options_path}.kind")
        options["kind"] = kind
        options["threshold"] = _percentage(_required(options, "threshold", options_path), f"{options_path}.threshold")
        return options

    if rule_type == "disk":
        kind = _rule_kind(options.get("kind", "busy"), f"{options_path}.kind")
        mount = str(_required(options, "mount", options_path))
        if not mount:
            raise ValueError(f"{options_path}.mount is required")
        options["kind"] = kind
        options["mount"] = mount
        options["threshold"] = _percentage(_required(options, "threshold", options_path), f"{options_path}.threshold")
        return options

    if rule_type == "gpu":
        kind = _rule_kind(options.get("kind", "idle"), f"{options_path}.kind")
        options["kind"] = kind
        options["gpu_match"] = _match_mode(options.get("gpu_match", "any"), f"{options_path}.gpu_match")
        options["threshold_match"] = _match_mode(
            options.get("threshold_match", "any" if kind == "busy" else "all"),
            f"{options_path}.threshold_match",
        )
        if "gpus" in options:
            options["gpus"] = _string_list(options["gpus"], f"{options_path}.gpus")
        if "idle_count" in options:
            if kind != "idle":
                raise ValueError(f"{options_path}.idle_count is only supported for idle GPU rules")
            options["idle_count"] = _non_negative_int(options["idle_count"], f"{options_path}.idle_count")
        options["threshold"] = _normalize_gpu_thresholds(
            _required(options, "threshold", options_path),
            f"{options_path}.threshold",
        )
        return options

    if rule_type == "process":
        pids = _required(options, "pids", options_path)
        options["pids"] = _int_list(pids, f"{options_path}.pids")
        options["name"] = str(options.get("name", ",".join(str(pid) for pid in options["pids"])))
        return options

    raise ValueError(f"{path}.type must be one of {sorted(RULE_TYPES)}")


def _normalize_rule_event(
    raw_rule: Mapping[str, Any],
    options: Mapping[str, Any],
    rule_type: str,
    path: str,
) -> str:
    if "event" in raw_rule:
        event = str(raw_rule["event"])
        if event not in EVENT_KINDS:
            raise ValueError(f"{path}.event must be 'alert' or 'reminder'")
        return event
    rule_kind = "busy" if rule_type == "process" else str(options["kind"])
    return "alert" if rule_kind == "busy" else "reminder"


def _normalize_gpu_thresholds(raw_thresholds: Any, path: str) -> Dict[str, float]:
    thresholds = _require_object(raw_thresholds, path)
    normalized: Dict[str, float] = {}

    if "compute" in thresholds:
        normalized["compute"] = _percentage(thresholds["compute"], f"{path}.compute")
    if "memory" in thresholds:
        normalized["memory"] = _percentage(thresholds["memory"], f"{path}.memory")
    if not normalized:
        raise ValueError(f"{path} requires compute, memory, or both")
    return normalized


def _require_object(value: Any, path: str) -> MutableMapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a JSON object")
    return value


def _required(obj: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in obj:
        raise ValueError(f"{path}.{key} is required")
    return obj[key]


def _bool_value(value: Any, path: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{path} must be true or false")


def _positive_number(value: Any, path: str) -> float:
    number = _number(value, path)
    if number <= 0:
        raise ValueError(f"{path} must be greater than 0")
    return number


def _non_negative_number(value: Any, path: str) -> float:
    number = _number(value, path)
    if number < 0:
        raise ValueError(f"{path} must be greater than or equal to 0")
    return number


def _non_negative_int(value: Any, path: str) -> int:
    number = _number(value, path)
    if not number.is_integer():
        raise ValueError(f"{path} must be an integer")
    integer = int(number)
    if integer < 0:
        raise ValueError(f"{path} must be greater than or equal to 0")
    return integer


def _percentage(value: Any, path: str) -> float:
    number = _number(value, path)
    if number < 0 or number > 100:
        raise ValueError(f"{path} must be between 0 and 100")
    return number


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{path} must be a number")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must be a number") from exc


def _port_number(value: Any, path: str) -> int:
    number = _positive_number(value, path)
    if not number.is_integer():
        raise ValueError(f"{path} must be an integer")
    port = int(number)
    if port > 65535:
        raise ValueError(f"{path} must be between 1 and 65535")
    return port


def _rule_kind(value: Any, path: str) -> str:
    kind = str(value)
    if kind not in RULE_KINDS:
        raise ValueError(f"{path} must be 'busy' or 'idle'")
    return kind


def _match_mode(value: Any, path: str) -> str:
    mode = str(value)
    if mode not in MATCH_MODES:
        raise ValueError(f"{path} must be 'any' or 'all'")
    return mode


def _string_list(value: Any, path: str) -> List[str]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return [str(item) for item in value]


def _non_empty_string_list(value: Any, path: str) -> List[str]:
    items = [item.strip() for item in _string_list(value, path)]
    if any(not item for item in items):
        raise ValueError(f"{path} must not contain empty strings")
    return items


def _int_list(value: Any, path: str) -> List[int]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    try:
        return [int(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must contain only integer values") from exc


def _normalize_command(value: Any, path: str) -> Any:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, dict):
        _validate_advanced_command(value, path)
        return _normalize_advanced_command(value)
    raise ValueError(f"{path} must be a string, a list of strings, or an object")


def _normalize_advanced_command(command: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = dict(command)
    for name in ("stdin", "stdout", "stderr", "cwd"):
        value = normalized.get(name)
        if value is not None:
            normalized[name] = _expand_path(value)
    return normalized


def _expand_path(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value))


def _validate_advanced_command(command: Mapping[str, Any], path: str) -> None:
    unknown_keys = sorted(set(command) - COMMAND_KEYS)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise ValueError(f"{path} has unknown fields: {joined}")

    inner_command = _required(command, "command", path)
    if isinstance(inner_command, str):
        pass
    elif isinstance(inner_command, list) and all(isinstance(item, str) for item in inner_command):
        pass
    else:
        raise ValueError(f"{path}.command must be a string or a list of strings")

    if "env" in command:
        env = _require_object(command["env"], f"{path}.env")
        for key, value in env.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"{path}.env keys must be non-empty strings")
            if value is None:
                raise ValueError(f"{path}.env.{key} must not be null")

    if "env_mode" in command:
        env_mode = str(command["env_mode"])
        if env_mode not in COMMAND_ENV_MODES:
            raise ValueError(f"{path}.env_mode must be 'merge' or 'replace'")

    for name in ("stdin", "stdout", "stderr", "cwd"):
        if name in command and command[name] is not None and not isinstance(command[name], str):
            raise ValueError(f"{path}.{name} must be a string")

    if "start_new_session" in command:
        _bool_value(command["start_new_session"], f"{path}.start_new_session")
