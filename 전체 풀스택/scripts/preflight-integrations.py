from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Check:
    name: str
    status: str
    detail: str


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or any(token in lowered for token in ("replace-me", "change-me", "your-", "example"))


def require(values: dict[str, str], checks: list[Check], names: list[str], *, template: bool) -> None:
    for name in names:
        if name not in values:
            checks.append(Check(name, "fail", "variable is not declared"))
        elif not template and is_placeholder(values[name]):
            checks.append(Check(name, "fail", "value is empty or still a placeholder"))
        else:
            checks.append(Check(name, "pass", "declared" if template else "configured"))


def json_get(url: str, headers: dict[str, str] | None = None, timeout: float = 15.0):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_socket(checks: list[Check], name: str, host: str, port: str) -> None:
    try:
        with socket.create_connection((host, int(port)), timeout=5):
            checks.append(Check(name, "pass", "TCP endpoint reachable"))
    except Exception as exc:
        checks.append(Check(name, "fail", f"TCP endpoint unavailable ({type(exc).__name__})"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate integration configuration without exposing secrets.")
    parser.add_argument("--env", type=Path, default=ROOT / ".env")
    parser.add_argument("--template", action="store_true", help="Validate declarations but allow blank placeholders")
    parser.add_argument("--live", action="store_true", help="Probe configured external endpoints")
    parser.add_argument("--confirm-external", action="store_true", help="Required with --live")
    args = parser.parse_args()
    if args.live and not args.confirm_external:
        parser.error("--live requires --confirm-external")
    if not args.env.is_file():
        print(json.dumps({"status": "fail", "error": f"env file not found: {args.env}"}, indent=2))
        return 2

    values = load_env(args.env)
    checks: list[Check] = []
    require(values, checks, ["DJANGO_SECRET_KEY", "INTERNAL_API_TOKEN"], template=args.template)
    require(
        values,
        checks,
        ["DB_ENGINE", "MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"],
        template=args.template,
    )

    image_mode = values.get("OPENAI_IMAGE_MODE", "comfyui").lower()
    if image_mode == "comfyui":
        require(
            values,
            checks,
            ["COMFYUI_BASE_URL", "COMFYUI_UNET_MODEL", "COMFYUI_CLIP_MODEL", "COMFYUI_VAE_MODEL"],
            template=args.template,
        )
    elif image_mode == "openai":
        require(
            values,
            checks,
            [
                "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_IMAGE_MODEL", "OPENAI_IMAGE_SIZE",
                "OPENAI_IMAGE_QUALITY", "OPENAI_IMAGE_MAX_REQUESTS_PER_DAY",
                "OPENAI_IMAGE_ESTIMATED_COST_USD", "OPENAI_IMAGE_MAX_ESTIMATED_COST_USD_PER_DAY",
            ],
            template=args.template,
        )
        if not args.template and values.get("OPENAI_IMAGE_MAX_REQUESTS_PER_DAY", "0") == "0":
            checks.append(Check("OPENAI_IMAGE_MAX_REQUESTS_PER_DAY", "fail", "paid API request ceiling must be greater than zero"))
    else:
        checks.append(Check("OPENAI_IMAGE_MODE", "fail", f"unsupported mode: {image_mode}"))

    auth_mode = values.get("AUTH_MODE", "disabled").lower()
    if auth_mode == "internal_db":
        require(
            values,
            checks,
            [
                "INTERNAL_AUTH_BOOTSTRAP_ENABLED", "INTERNAL_AUTH_USERNAME",
                "INTERNAL_AUTH_PASSWORD", "INTERNAL_AUTH_DISPLAY_NAME", "INTERNAL_AUTH_EMAIL",
            ],
            template=args.template,
        )
    elif auth_mode == "corporate_db":
        require(
            values,
            checks,
            [
                "AUTH_DB_ENGINE", "AUTH_DB_HOST", "AUTH_DB_PORT", "AUTH_DB_NAME", "AUTH_DB_USER",
                "AUTH_DB_PASSWORD", "AUTH_DB_TABLE", "AUTH_DB_USERNAME_COLUMN", "AUTH_DB_PASSWORD_COLUMN",
                "AUTH_DB_ACTIVE_COLUMN", "AUTH_DB_PASSWORD_SCHEME",
            ],
            template=args.template,
        )
        if values.get("AUTH_DB_ENGINE", "").lower() != "mysql":
            checks.append(Check("AUTH_DB_ENGINE", "fail", "corporate authentication requires external MySQL"))
    elif auth_mode != "disabled":
        checks.append(Check("AUTH_MODE", "fail", f"unsupported mode: {auth_mode}"))

    if args.live:
        if values.get("DB_ENGINE", "mysql") != "sqlite":
            check_socket(checks, "application_database_tcp", values["MYSQL_HOST"], values["MYSQL_PORT"])
        if auth_mode == "corporate_db":
            check_socket(checks, "corporate_auth_database_tcp", values["AUTH_DB_HOST"], values["AUTH_DB_PORT"])
        if image_mode == "comfyui":
            headers = {"Authorization": f"Bearer {values['COMFYUI_API_KEY']}"} if values.get("COMFYUI_API_KEY") else {}
            try:
                json_get(f"{values['COMFYUI_BASE_URL'].rstrip('/')}/system_stats", headers)
                object_info = json_get(f"{values['COMFYUI_BASE_URL'].rstrip('/')}/object_info", headers, 30.0)
                required_nodes = {"UNETLoader", "CLIPLoader", "VAELoader", "EmptyFlux2LatentImage", "Flux2Scheduler"}
                missing = sorted(required_nodes - set(object_info))
                checks.append(Check("comfyui_runtime", "fail" if missing else "pass", f"missing nodes: {missing}" if missing else "runtime and Flux nodes available"))
            except Exception as exc:
                checks.append(Check("comfyui_runtime", "fail", f"probe failed ({type(exc).__name__})"))
        elif image_mode == "openai":
            headers = {"Authorization": f"Bearer {values['OPENAI_API_KEY']}"}
            if values.get("OPENAI_ORGANIZATION"):
                headers["OpenAI-Organization"] = values["OPENAI_ORGANIZATION"]
            if values.get("OPENAI_PROJECT"):
                headers["OpenAI-Project"] = values["OPENAI_PROJECT"]
            try:
                json_get(f"{values['OPENAI_BASE_URL'].rstrip('/')}/models/{values['OPENAI_IMAGE_MODEL']}", headers)
                checks.append(Check("openai_credentials", "pass", "model metadata endpoint authorized; no image generated"))
            except urllib.error.HTTPError as exc:
                checks.append(Check("openai_credentials", "fail", f"HTTP {exc.code}; no image generated"))
            except Exception as exc:
                checks.append(Check("openai_credentials", "fail", f"probe failed ({type(exc).__name__})"))

    failed = [check for check in checks if check.status == "fail"]
    payload = {
        "status": "fail" if failed else "pass",
        "mode": "live" if args.live else "template" if args.template else "offline",
        "env_file": str(args.env),
        "checks": [asdict(check) for check in checks],
        "secrets_printed": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
