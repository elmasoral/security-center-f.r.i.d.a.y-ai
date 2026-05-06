from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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


def _shorten(text: str, limit: int = 700) -> str:
    text = (text or "").replace("\x00", "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ..."


def _looks_like_json(text: str) -> bool:
    s = (text or "").lstrip("\ufeff\n\r\t ")
    return s.startswith("{") or s.startswith("[")


class SecurityCenterClient:
    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None, timeout: int = 25) -> None:
        cfg = _load_local_config()
        self.api_url = (api_url or os.getenv("MPSEC_API_URL") or cfg.get("api_url") or DEFAULT_API_URL).strip()
        self.api_key = (api_key or os.getenv("MPSEC_API_KEY") or cfg.get("api_key") or DEFAULT_API_KEY).strip()
        self.timeout = int(cfg.get("timeout", timeout) or timeout)
        self.last_debug: Dict[str, Any] = {}

    def _headers(self, json_body: bool = False) -> Dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.5",
            "X-MEDPOV-API-Key": self.api_key,
            "User-Agent": "MEDPOV-Friday/SecurityCenterClient/2.8.10",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        if json_body:
            headers["Content-Type"] = "application/json; charset=utf-8"
        return headers

    def _build_request(self, action: str, method: str, payload: Dict[str, Any]) -> Tuple[urllib.request.Request, str]:
        method = (method or "GET").upper().strip()
        clean_payload = {k: v for k, v in payload.items() if v is not None and v != ""}
        clean_payload.setdefault("action", action)
        clean_payload.setdefault("_", int(time.time() * 1000))

        if method == "POST":
            body = json.dumps(clean_payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                self.api_url,
                data=body,
                headers=self._headers(json_body=True),
                method="POST",
            )
            return req, self.api_url

        query = urllib.parse.urlencode(clean_payload, doseq=True)
        sep = "&" if "?" in self.api_url else "?"
        url = self.api_url + sep + query
        req = urllib.request.Request(url, headers=self._headers(json_body=False), method="GET")
        return req, url

    def _parse_response(
        self,
        raw: str,
        status: int,
        content_type: str,
        action: str,
        method: str,
        url: str,
    ) -> Dict[str, Any]:
        text = raw or ""
        stripped = text.strip()
        self.last_debug = {
            "action": action,
            "method": method,
            "http_status": status,
            "content_type": content_type,
            "url": url,
            "raw_preview": _shorten(stripped, 500),
        }

        if not stripped:
            # Many admin-side write endpoints legitimately return an empty 200/204
            # after completing the operation. Treat those as success so Friday
            # does not report a JSON parser error for resolve/block actions.
            write_actions = {
                "block-ip", "allow-ip", "ignore-ip", "expire-ip-rules",
                "resolve-event", "resolve-ip-events", "ai-recheck",
            }
            if 200 <= int(status or 0) < 300 and method.upper() == "POST" and action in write_actions:
                return {
                    "ok": True,
                    "message": "Security Center returned an empty success response.",
                    "action": action,
                    "http_status": status,
                }
            return {
                "ok": False,
                "message": "Security Center API returned an empty response. Check the remote-access.php endpoint, API key, PHP errors, or web server logs.",
                "action": action,
                "http_status": status,
                "content_type": content_type,
            }

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            kind = "HTML/non-JSON" if not _looks_like_json(stripped) else "invalid JSON"
            return {
                "ok": False,
                "message": (
                    f"Security Center API returned {kind} instead of JSON. "
                    f"Parser: {exc.msg} at line {exc.lineno} column {exc.colno}."
                ),
                "action": action,
                "http_status": status,
                "content_type": content_type,
                "raw_preview": _shorten(stripped, 700),
            }

        if isinstance(parsed, dict):
            parsed.setdefault("ok", True)
            parsed.setdefault("http_status", status)
            return parsed

        if isinstance(parsed, list):
            return {"ok": True, "items": parsed, "http_status": status}

        return {"ok": True, "value": parsed, "http_status": status}

    def _do_request(self, action: str, method: str, **params: Any) -> Dict[str, Any]:
        payload = {"action": action, **{k: v for k, v in params.items() if v is not None and v != ""}}
        req, url = self._build_request(action, method, payload)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = int(getattr(response, "status", 200) or 200)
                content_type = str(response.headers.get("Content-Type", "") or "")
                return self._parse_response(raw, status, content_type, action, method.upper(), url)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            content_type = str(exc.headers.get("Content-Type", "") if exc.headers else "")
            data = self._parse_response(raw, int(exc.code), content_type, action, method.upper(), url)
            data.setdefault("ok", False)
            data.setdefault("http_status", exc.code)
            return data
        except urllib.error.URLError as exc:
            return {
                "ok": False,
                "message": f"Security Center API connection failed: {exc.reason if hasattr(exc, 'reason') else exc}",
                "action": action,
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc), "action": action}

    def request(self, action: str = "overview", method: str = "GET", **params: Any) -> Dict[str, Any]:
        action = (action or "overview").replace("_", "-").strip()
        method = (method or "GET").upper().strip()

        data = self._do_request(action, method, **params)
        if data.get("ok"):
            return data

        # Some shared hosts/security layers occasionally answer empty/non-JSON to
        # GET requests while the same action works with POST JSON. Retry read
        # actions once with POST before giving a user-facing failure.
        retryable_markers = ("empty response", "instead of JSON", "invalid JSON", "HTML/non-JSON")
        msg = str(data.get("message") or "")
        read_actions = {
            "ping", "capabilities", "overview", "status", "threats", "events", "event",
            "ip-profile", "analyze", "traffic", "live", "bots", "login", "health",
            "settings", "map", "threat-map", "live-map", "both-map",
        }
        if method == "GET" and action in read_actions and any(m.lower() in msg.lower() for m in retryable_markers):
            retry = self._do_request(action, "POST", **params)
            if retry.get("ok"):
                retry.setdefault("retried_with", "POST")
                return retry
            retry.setdefault("first_error", data)
            return retry

        return data

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
    def map(self, mode: str = "both", threat_range: str = "24h", live_range: str = "live", include_curve_points: bool = True) -> Dict[str, Any]:
        return self.request(
            "map",
            mode=mode,
            threat_range=threat_range,
            live_range=live_range,
            include_curve_points="1" if include_curve_points else "0",
        )

    def threat_map(self, threat_range: str = "24h", include_curve_points: bool = True) -> Dict[str, Any]:
        return self.request("threat-map", threat_range=threat_range, include_curve_points="1" if include_curve_points else "0")

    def live_map(self, live_range: str = "live", include_curve_points: bool = True) -> Dict[str, Any]:
        return self.request("live-map", live_range=live_range, include_curve_points="1" if include_curve_points else "0")

    def both_map(self, threat_range: str = "24h", live_range: str = "live", include_curve_points: bool = True) -> Dict[str, Any]:
        return self.request(
            "both-map",
            threat_range=threat_range,
            live_range=live_range,
            include_curve_points="1" if include_curve_points else "0",
        )

    def raw_action(self, action: str, method: str = "GET", **params: Any) -> Dict[str, Any]:
        return self.request(action, method=method, **params)
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
    elif cmd == "map": _print_json(c.map(mode=(argv[2] if len(argv) > 2 else 'both')))
    elif cmd == "threat-map": _print_json(c.threat_map())
    elif cmd == "live-map": _print_json(c.live_map())
    elif cmd == "both-map": _print_json(c.both_map())
    else:
        print("Usage: python security_center_client.py [ping|overview|threats|ip <IP>|analyze <IP>|event <ID>|block <IP>|health|live|map|threat-map|live-map|both-map]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
