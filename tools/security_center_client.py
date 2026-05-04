from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_API_KEY = ""
DEFAULT_API_URL = "https://siteadi.com/security-center/admin/api/remote-access.php"

try:
    from .friday_settings_store import get_security_center_config
except Exception:
    try:
        from friday_settings_store import get_security_center_config  # type: ignore
    except Exception:
        get_security_center_config = None  # type: ignore


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _load_local_config() -> Dict[str, Any]:
    root = _project_root()
    cfg = _load_json(root / "config" / "security_center.json")
    if get_security_center_config is not None:
        try:
            modern = get_security_center_config()
            if isinstance(modern, dict):
                cfg.update(modern)
        except Exception:
            pass
    return cfg


class SecurityCenterClient:
    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None, timeout: int = 25) -> None:
        cfg = _load_local_config()
        self.api_url = (api_url or os.getenv("MPSEC_API_URL") or cfg.get("api_url") or DEFAULT_API_URL).strip()
        self.api_key = (api_key or os.getenv("MPSEC_API_KEY") or cfg.get("api_key") or DEFAULT_API_KEY).strip()
        self.timeout = int(cfg.get("timeout", timeout) or timeout)

    def request(self, action: str = "overview", method: str = "GET", **params: Any) -> Dict[str, Any]:
        action = (action or "overview").strip()
        method = (method or "GET").upper().strip()
        payload = {"action": action, **{k: v for k, v in params.items() if v is not None and v != ""}}
        headers = {"Accept": "application/json", "X-MEDPOV-API-Key": self.api_key, "User-Agent": "MEDPOV-Friday/SecurityCenterClient"}
        if method == "POST":
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
            req = urllib.request.Request(self.api_url, data=body, headers=headers, method="POST")
        else:
            query = urllib.parse.urlencode(payload, doseq=True)
            sep = "&" if "?" in self.api_url else "?"
            req = urllib.request.Request(self.api_url + sep + query, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"ok": False, "message": raw or str(exc)}
            data.setdefault("ok", False)
            data.setdefault("http_status", exc.code)
            return data
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def ping(self) -> Dict[str, Any]: return self.request("ping")
    def capabilities(self) -> Dict[str, Any]: return self.request("capabilities")
    def overview(self) -> Dict[str, Any]: return self.request("overview")
    def threats(self, limit: int = 20, hours: int = 24) -> Dict[str, Any]: return self.request("threats", limit=limit, hours=hours)
    def events(self, risk: str = "", ip: str = "", limit: int = 25, resolved: Optional[bool] = None) -> Dict[str, Any]:
        resolved_value = None if resolved is None else ("1" if resolved else "0")
        return self.request("events", risk=risk, ip=ip, limit=limit, resolved=resolved_value)
    def event(self, event_id: int) -> Dict[str, Any]: return self.request("event", id=event_id)
    def ip_profile(self, ip: str, refresh: bool = True, limit: int = 20) -> Dict[str, Any]: return self.request("ip-profile", ip=ip, refresh="1" if refresh else "0", limit=limit)
    def analyze(self, ip: str = "", event_id: Optional[int] = None) -> Dict[str, Any]: return self.request("analyze", ip=ip, event_id=event_id)
    def traffic(self, ip: str = "", limit: int = 50, since_hours: int = 24) -> Dict[str, Any]: return self.request("traffic", ip=ip, limit=limit, since_hours=since_hours)
    def live(self, limit: int = 60) -> Dict[str, Any]: return self.request("live", limit=limit)
    def bots(self, limit: int = 25) -> Dict[str, Any]: return self.request("bots", limit=limit)
    def login(self, limit: int = 25) -> Dict[str, Any]: return self.request("login", limit=limit)
    def health(self) -> Dict[str, Any]: return self.request("health")
    def settings(self) -> Dict[str, Any]: return self.request("settings")
    def block_ip(self, ip: str, minutes: int = 1440, reason: str = "MEDPOV Friday remote block") -> Dict[str, Any]: return self.request("block-ip", method="POST", ip=ip, minutes=minutes, reason=reason)
    def allow_ip(self, ip: str, reason: str = "MEDPOV Friday remote allow") -> Dict[str, Any]: return self.request("allow-ip", method="POST", ip=ip, minutes=0, reason=reason)
    def ignore_ip(self, ip: str, reason: str = "MEDPOV Friday remote ignore") -> Dict[str, Any]: return self.request("ignore-ip", method="POST", ip=ip, minutes=0, reason=reason)
    def expire_ip_rules(self, ip: str, rule_type: str = "") -> Dict[str, Any]: return self.request("expire-ip-rules", method="POST", ip=ip, rule_type=rule_type)
    def resolve_event(self, event_id: int, status: str = "remote_resolved") -> Dict[str, Any]: return self.request("resolve-event", method="POST", id=event_id, status=status)
    def resolve_ip_events(self, ip: str, status: str = "remote_ip_resolved") -> Dict[str, Any]: return self.request("resolve-ip-events", method="POST", ip=ip, status=status)
    def ai_recheck(self, limit: int = 50) -> Dict[str, Any]: return self.request("ai-recheck", method="POST", limit=limit)


def _print_json(data: Dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str]) -> int:
    c = SecurityCenterClient()
    cmd = (argv[1] if len(argv) > 1 else "overview").strip().lower()
    if cmd == "ping": _print_json(c.ping())
    elif cmd in {"overview", "status"}: _print_json(c.overview())
    elif cmd == "threats": _print_json(c.threats())
    elif cmd in {"ip", "ip-profile"} and len(argv) > 2: _print_json(c.ip_profile(argv[2], refresh=True))
    elif cmd in {"analyze", "analyze-ip"} and len(argv) > 2: _print_json(c.analyze(ip=argv[2]))
    elif cmd == "event" and len(argv) > 2: _print_json(c.event(int(argv[2])))
    elif cmd == "block" and len(argv) > 2: _print_json(c.block_ip(argv[2], reason="Friday CLI requested block"))
    elif cmd == "health": _print_json(c.health())
    elif cmd == "live": _print_json(c.live())
    else:
        print("Usage: python security_center_client.py [ping|overview|threats|ip <IP>|analyze <IP>|event <ID>|block <IP>|health|live]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))


