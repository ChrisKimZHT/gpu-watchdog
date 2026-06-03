from __future__ import annotations

from typing import Any, Dict, List, Mapping, MutableMapping


RULE_TYPES = {"cpu", "memory", "disk", "gpu", "process"}
RULE_KINDS = {"busy", "idle"}
MATCH_MODES = {"any", "all"}
EVENT_KINDS = {"alert", "reminder"}
BARK_KEYS = {"enabled", "server", "device_key", "timeout_seconds", "level", "passthrough"}

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_BARK_SERVER = "https://api.day.app"
DEFAULT_BARK_TIMEOUT_SECONDS = 10.0
DEFAULT_BARK_LEVEL = "active"


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
        _validate_command(rule["command"], f"{path}.command")

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


def _int_list(value: Any, path: str) -> List[int]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    try:
        return [int(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} must contain only integer values") from exc


def _validate_command(value: Any, path: str) -> None:
    if isinstance(value, str):
        return
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return
    raise ValueError(f"{path} must be a string or a list of strings")
