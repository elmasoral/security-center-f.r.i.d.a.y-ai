from __future__ import annotations

import ipaddress
import json
import re
from typing import Any, Dict, Optional

try:
    from .security_center_client import SecurityCenterClient
except Exception:
    from security_center_client import SecurityCenterClient  # type: ignore

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _norm(text: str) -> str:
    text = (text or "").lower().strip()
    return text.translate(str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}))


def _valid_ip(ip: str) -> str:
    try:
        return str(ipaddress.ip_address((ip or "").strip()))
    except Exception:
        return ""


def _first_ip(text: str) -> str:
    for m in IP_RE.finditer(text or ""):
        ip = _valid_ip(m.group(0))
        if ip:
            return ip
    return ""


def _safe_int(v: Any, default: int, minimum: int = 1, maximum: int = 500) -> int:
    try:
        return max(minimum, min(maximum, int(v)))
    except Exception:
        return default


def _pick(d: Dict[str, Any], *keys: str, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _listish(v: Any) -> list[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, tuple):
        return list(v)
    return [v]


def _event_line(ev: Dict[str, Any]) -> str:
    return (
        f"#{_pick(ev, 'id', 'event_id', default='?')} | "
        f"{str(_pick(ev, 'risk', 'risk_level', default='?')).upper()} | "
        f"score {_pick(ev, 'score', 'risk_score', default='-')} | "
        f"{_pick(ev, 'actor_ip', 'ip', 'client_ip', default='-')} | "
        f"{_pick(ev, 'category', 'type', default='-')} | "
        f"{_pick(ev, 'uri', 'path', default='-')} | "
        f"{_pick(ev, 'last_seen_at', 'created_at', default='-')}"
    )


def _format_overview(data: Dict[str, Any]) -> str:
    if not data.get("ok"):
        return f"Security Center bağlantı hatası: {data.get('message', 'unknown error')}"
    s = data.get("stats") or {}
    lines = [
        "MEDPOV Security Center canlı bağlantı aktif.",
        f"Erişim: {data.get('access', '-')} | Asistan: {data.get('assistant', '-')} | Sürüm: {data.get('version', '-')}",
        f"Toplam event: {s.get('total_events', 0)} | Açık event: {s.get('open_events', 0)} | Son 24 saat: {s.get('events_24h', 0)} | Son 7 gün: {s.get('events_7d', 0)}",
        f"Açık HIGH: {s.get('high_open', 0)} | Açık CRITICAL: {s.get('critical_open', 0)} | Aktif block rule: {s.get('active_block_rules', 0)} | Canlı oturum: {s.get('live_sessions_active', 0)}",
    ]
    top = _listish(data.get("top_ips_24h"))[:5]
    if top:
        lines.append("Son 24 saatin baskı yapan IP’leri:")
        for r in top:
            if isinstance(r, dict):
                lines.append(f"- {r.get('ip', '-')} | {r.get('top_risk', '-')} | event {r.get('events', 0)} | attempts {r.get('attempts', 0)} | {r.get('sample_category', '-')}")
    latest = _listish(data.get("latest_high_risk_events"))[:5]
    if latest:
        lines.append("Son yüksek riskli olaylar:")
        lines += ["- " + _event_line(x) for x in latest if isinstance(x, dict)]
    recs = _listish(data.get("recommendations_tr"))
    if recs:
        lines.append("Öneri: " + " ".join(map(str, recs[:3])))
    return "\n".join(lines)


def _format_threats(data: Dict[str, Any]) -> str:
    if not data.get("ok"):
        return f"Tehdit akışı alınamadı: {data.get('message', 'unknown error')}"
    events = _listish(data.get("events") or data.get("threats") or data.get("latest_high_risk_events"))
    if not events:
        return "Son filtrede HIGH/CRITICAL tehdit bulunmadı."
    return "\n".join(["Son Security Center tehditleri:"] + ["- " + _event_line(x) for x in events[:12] if isinstance(x, dict)])


def _format_ip_profile(data: Dict[str, Any], ip: str) -> str:
    if not data.get("ok"):
        return f"IP profili alınamadı ({ip}): {data.get('message', 'unknown error')}"
    profile = data.get("ip_profile") or data.get("profile") or data
    lookup = (data.get("lookup") or (profile.get("lookup") if isinstance(profile, dict) else {})) or {}
    analysis = (data.get("analysis") or (profile.get("analysis") if isinstance(profile, dict) else {})) or {}
    events = _listish(data.get("events") or (profile.get("events") if isinstance(profile, dict) else []))
    rules = _listish(data.get("rules") or (profile.get("rules") if isinstance(profile, dict) else []))
    queries = _listish(data.get("research_queries") or (profile.get("research_queries") if isinstance(profile, dict) else []))
    lines = [f"IP profil raporu: {ip}"]
    if isinstance(lookup, dict) and lookup:
        bits = [f"{k}: {lookup.get(k)}" for k in ["country", "city", "org", "isp", "asn", "hostname", "reverse_dns"] if lookup.get(k)]
        if bits:
            lines.append("Lookup: " + " | ".join(bits[:8]))
    if isinstance(analysis, dict) and analysis:
        summary = analysis.get("summary") or analysis.get("recommendation") or analysis.get("verdict")
        risk = analysis.get("risk") or analysis.get("risk_level")
        if risk or summary:
            lines.append(f"Analiz: {risk or '-'} — {summary or '-'}")
    if events:
        lines.append(f"Event geçmişi: {len(events)} kayıt gösteriliyor")
        lines += ["- " + _event_line(x) for x in events[:8] if isinstance(x, dict)]
    if rules:
        lines.append("Aktif/ilgili IP kuralları: " + str(len(rules)))
    if queries:
        lines.append("İnternet araştırma sorguları: " + " | ".join(map(str, queries[:4])))
    return "\n".join(lines)


def _format_generic(data: Dict[str, Any], title: str) -> str:
    if not data.get("ok"):
        return f"{title} başarısız: {data.get('message', 'unknown error')}"
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return f"{title}:\n" + (text[:5000] + "\n... çıktı kısaltıldı ..." if len(text) > 5000 else text)


def _map_counts(data: Dict[str, Any]) -> tuple[int, int]:
    counts = data.get("counts") or {}
    threats = counts.get("threats")
    users = counts.get("live_users")
    if threats is None:
        threats = len(_listish(data.get("threat_events") or data.get("events")))
    if users is None:
        users = len(_listish(data.get("live_users")))
    try:
        threats = int(threats or 0)
    except Exception:
        threats = 0
    try:
        users = int(users or 0)
    except Exception:
        users = 0
    return threats, users


def _push_map_to_ui(player: Any, data: Optional[Dict[str, Any]] = None, mode: str = "world", focus: str = "") -> bool:
    if player is None:
        return False
    try:
        if hasattr(player, "open_security_map"):
            return bool(player.open_security_map(mode=mode, data=data or {}, focus=focus))
        if hasattr(player, "start_security_map"):
            return bool(player.start_security_map(mode=mode, data=data or {}, focus=focus))
    except Exception:
        return False
    return False


def _focus_map(player: Any, place: str) -> bool:
    if player is None:
        return False
    try:
        if hasattr(player, "focus_security_map"):
            return bool(player.focus_security_map(place))
    except Exception:
        return False
    return False


def _close_map(player: Any) -> bool:
    if player is None:
        return False
    try:
        if hasattr(player, "stop_security_map"):
            player.stop_security_map()
            return True
        if hasattr(player, "close_security_map"):
            player.close_security_map()
            return True
    except Exception:
        return False
    return False


def _format_map(data: Dict[str, Any], mode: str) -> str:
    if not data.get("ok"):
        return f"Security map alınamadı: {data.get('message', 'unknown error')}"
    threats, users = _map_counts(data)
    target = data.get("target") or {}
    target_label = target.get("url") or target.get("label") or "Protected website"
    updated = data.get("updated_at") or data.get("server_time") or "-"
    if mode == "threat":
        return f"Threat Map açıldı. Hedef: {target_label}. Son 24 saat tehdit noktası: {threats}. Güncelleme: {updated}."
    if mode == "live":
        return f"Live Map açıldı. Hedef: {target_label}. Canlı/geçmiş ziyaretçi noktası: {users}. Güncelleme: {updated}."
    return f"Both Map açıldı. Hedef: {target_label}. Tehdit: {threats}, kullanıcı: {users}. Güncelleme: {updated}."


def security_center_action(parameters: Optional[Dict[str, Any]] = None, player: Any = None, speak: Any = None) -> str:
    p = parameters or {}
    raw = str(p.get("action") or p.get("command") or "overview").strip().lower()
    text = str(p.get("text") or p.get("query") or "")
    ip = _valid_ip(str(p.get("ip") or "")) or _first_ip(text)
    event_id = p.get("event_id") or p.get("id")
    limit = _safe_int(p.get("limit"), 20, 1, 100)
    hours = _safe_int(p.get("hours") or p.get("since_hours"), 24, 1, 720)
    minutes = _safe_int(p.get("minutes"), 1440, 1, 525600)
    reason = str(p.get("reason") or "MEDPOV Friday action").strip()
    risk = str(p.get("risk") or "").strip().upper()
    mode = str(p.get("mode") or "").strip().lower()
    live_range = str(p.get("live_range") or "live").strip().lower()
    threat_range = str(p.get("threat_range") or p.get("range") or "24h").strip().lower()
    focus = str(p.get("focus") or p.get("place") or p.get("city") or "").strip()
    include_curve_points = bool(p.get("include_curve_points", True))

    c = SecurityCenterClient()
    action = raw.replace("-", "_").replace(" ", "_")
    aliases = {
        "status": "overview", "durum": "overview", "ozet": "overview", "özet": "overview", "dashboard": "overview", "genel": "overview",
        "son_tehditler": "threats", "threat": "threats", "tehdit": "threats", "tehditler": "threats", "high": "threats", "critical": "threats",
        "ip": "ip_profile", "ip_profil": "ip_profile", "lookup": "ip_profile",
        "analiz": "analyze", "analyze_ip": "analyze", "ip_analyze": "analyze", "ip_analiz": "analyze",
        "blokla": "block_ip", "block": "block_ip", "izin_ver": "allow_ip", "allow": "allow_ip", "ignore": "ignore_ip", "yoksay": "ignore_ip",
        "saglik": "health", "sağlık": "health", "health_check": "health", "canli": "live", "canlı": "live", "live_sessions": "live",
        "map": "map_open", "harita": "map_open", "world_map": "map_open", "global_map": "map_open", "harita_ac": "map_open", "map_open": "map_open",
        "map_close": "map_close", "harita_kapat": "map_close", "close_map": "map_close",
        "map_zoom": "map_zoom", "zoom": "map_zoom", "focus_map": "map_zoom", "city": "map_zoom",
        "threat_map": "map_threat", "map_threat": "map_threat", "tehdit_haritasi": "map_threat", "tehdit_haritası": "map_threat",
        "live_map": "map_live", "map_live": "map_live", "canli_harita": "map_live", "canlı_harita": "map_live",
        "global_activity": "map_live", "global_activities": "map_live", "global_aktivite": "map_live", "global_aktiviteler": "map_live", "son_global_aktiviteler": "map_live", "activity_map": "map_live", "latest_activity": "map_live",
        "both_map": "map_both", "map_both": "map_both", "hepsi_harita": "map_both", "combined_map": "map_both",
    }
    action = aliases.get(action, action)

    # Visual map actions. These update the large FRIDAY HUD map when a UI player is available.
    if action == "map_open":
        # Open a clean world map first. Threat/live layers must be requested explicitly.
        _push_map_to_ui(player, None, mode="world", focus=focus)
        return "Security global world map açıldı. Katmanlar kapalı; tehditleri veya son global aktiviteleri istediğinde çizgiler gösterilir."
    if action == "map_close":
        _close_map(player)
        return "Security map kapatıldı."
    if action == "map_zoom":
        if not focus:
            focus = text.strip()
        if not focus:
            return "Zoom için şehir/ülke adı gerekli. Örnek: Londra aç, Tokyo'ya zoom yap."
        ok = _focus_map(player, focus)
        return f"Harita {focus} konumuna odaklandı." if ok else f"Harita odağı uygulanamadı: {focus}."
    if action == "map_threat":
        data = c.threat_map(threat_range=threat_range, include_curve_points=include_curve_points)
        _push_map_to_ui(player, data, mode="threat", focus=focus)
        return _format_map(data, "threat")
    if action == "map_live":
        data = c.live_map(live_range=live_range, include_curve_points=include_curve_points)
        _push_map_to_ui(player, data, mode="live", focus=focus)
        return _format_map(data, "live")
    if action == "map_both":
        data = c.both_map(threat_range=threat_range, live_range=live_range, include_curve_points=include_curve_points)
        _push_map_to_ui(player, data, mode="both", focus=focus)
        return _format_map(data, "both")
    if action in {"map_data", "map_intelligence"}:
        data = c.map(mode=mode or "both", threat_range=threat_range, live_range=live_range, include_curve_points=include_curve_points)
        _push_map_to_ui(player, data, mode=(mode or str(data.get("mode") or "both")), focus=focus)
        return _format_map(data, str(data.get("mode") or mode or "both"))

    # Read/query API actions.
    if action == "overview":
        return _format_overview(c.overview())
    if action == "threats":
        return _format_threats(c.threats(limit=limit, hours=hours))
    if action == "events":
        return _format_threats(c.events(risk=risk, ip=ip, limit=limit))
    if action == "event":
        return "Event detayı için event_id gerekli. Örnek: /sc event 124" if not event_id else _format_generic(c.event(int(event_id)), f"Security event #{event_id}")
    if action == "ip_profile":
        return "IP profili için IP gerekli. Örnek: /sc ip 65.55.210.207" if not ip else _format_ip_profile(c.ip_profile(ip, refresh=True, limit=limit), ip)
    if action == "analyze":
        if event_id:
            return _format_generic(c.analyze(event_id=int(event_id)), f"Event analiz #{event_id}")
        return "Analiz için IP veya event_id gerekli. Örnek: /sc analyze 65.55.210.207" if not ip else _format_generic(c.analyze(ip=ip), f"IP analiz {ip}")
    if action == "traffic":
        return _format_generic(c.traffic(ip=ip, limit=limit, since_hours=hours), "Security Center trafik")
    if action == "live":
        return _format_generic(c.live(limit=limit), "Security Center canlı oturumlar")
    if action == "bots":
        return _format_generic(c.bots(limit=limit), "Bot kayıtları")
    if action == "login":
        return _format_generic(c.login(limit=limit), "Login baskısı")
    if action == "health":
        return _format_generic(c.health(), "Security Center sağlık raporu")
    if action == "settings":
        return _format_generic(c.settings(), "Security Center ayar özeti")
    if action == "capabilities":
        return _format_generic(c.capabilities(), "Security Center yetenekleri")

    # Authorized write actions.
    if action == "block_ip":
        return "IP bloklamak için IP gerekli. Örnek: /sc block 1.2.3.4" if not ip else _format_generic(c.block_ip(ip, minutes=minutes, reason=reason), f"IP block işlemi {ip}")
    if action == "allow_ip":
        return "IP allow için IP gerekli. Örnek: /sc allow 1.2.3.4" if not ip else _format_generic(c.allow_ip(ip, reason=reason), f"IP allow işlemi {ip}")
    if action == "ignore_ip":
        return "IP ignore için IP gerekli. Örnek: /sc ignore 1.2.3.4" if not ip else _format_generic(c.ignore_ip(ip, reason=reason), f"IP ignore işlemi {ip}")
    if action == "expire_ip_rules":
        return "IP rule kaldırma için IP gerekli. Örnek: /sc expire-ip-rules 1.2.3.4" if not ip else _format_generic(c.expire_ip_rules(ip, str(p.get("rule_type") or "")), f"IP rule expire {ip}")
    if action == "resolve_event":
        return "Event resolve için event_id gerekli. Örnek: /sc resolve-event 124" if not event_id else _format_generic(c.resolve_event(int(event_id)), f"Event resolve #{event_id}")
    if action == "resolve_ip_events":
        return "IP event resolve için IP gerekli. Örnek: /sc resolve-ip 1.2.3.4" if not ip else _format_generic(c.resolve_ip_events(ip), f"IP event resolve {ip}")
    if action == "ai_recheck":
        return _format_generic(c.ai_recheck(limit=limit), "Local AI re-check")

    # Full capacity fallback: pass through any future Security Center API read action safely.
    passthrough_params = dict(p.get("params") or {}) if isinstance(p.get("params"), dict) else {}
    for k in ("q", "risk", "status", "resolved", "since_hours", "limit", "offset", "ip", "id", "event_id"):
        if p.get(k) not in (None, ""):
            passthrough_params[k] = p.get(k)
    if action:
        return _format_generic(c.raw_action(action.replace("_", "-"), method=str(p.get("method") or "GET"), **passthrough_params), f"Security Center API action {action}")

    return f"Bilinmeyen Security Center komutu: {raw}. Kullanım: overview, threats, ip_profile, analyze, block_ip, health, map, threat_map, live_map, both_map."


def parse_slash_command(text: str) -> Optional[Dict[str, Any]]:
    raw = (text or "").strip()
    low = raw.lower()
    if not low.startswith(("/sc", "sc ", "security-center ", "security center ", "/map", "map ", "harita ")):
        return None
    cleaned = re.sub(r"^/(sc|security-center|map)\s*", "", raw, flags=re.I).strip()
    cleaned = re.sub(r"^(sc|security-center|security center|map|harita)\s+", "", cleaned, flags=re.I).strip()
    if not cleaned:
        return {"action": "map_open" if low.startswith(("/map", "map ", "harita ")) else "overview"}
    parts = cleaned.split()
    cmd = parts[0].lower()
    rest = " ".join(parts[1:])
    ip = _first_ip(cleaned)
    event_id = None
    for token in parts[1:]:
        if token.isdigit():
            event_id = int(token)
            break
    aliases = {
        "overview": "overview", "status": "overview", "durum": "overview", "özet": "overview", "ozet": "overview",
        "threats": "threats", "tehditler": "threats", "tehdit": "threats", "ip": "ip_profile", "lookup": "ip_profile", "profile": "ip_profile", "profil": "ip_profile",
        "analyze": "analyze", "analiz": "analyze", "event": "event", "olay": "event", "events": "events", "olaylar": "events",
        "traffic": "traffic", "trafik": "traffic", "live": "live", "canlı": "live", "canli": "live", "bots": "bots", "bot": "bots", "login": "login",
        "health": "health", "sağlık": "health", "saglik": "health", "block": "block_ip", "blokla": "block_ip", "allow": "allow_ip", "izin": "allow_ip",
        "ignore": "ignore_ip", "yoksay": "ignore_ip", "resolve-event": "resolve_event", "resolve": "resolve_event", "resolve-ip": "resolve_ip_events", "ai-recheck": "ai_recheck", "recheck": "ai_recheck",
        "map": "map_open", "open": "map_open", "aç": "map_open", "ac": "map_open", "close": "map_close", "kapat": "map_close",
        "zoom": "map_zoom", "focus": "map_zoom", "city": "map_zoom", "threat-map": "map_threat", "threat": "map_threat", "tehdit-map": "map_threat", "tehdit": "map_threat",
        "live-map": "map_live", "canli-map": "map_live", "canlı-map": "map_live", "global-activity": "map_live", "global-activities": "map_live", "global-aktivite": "map_live", "global-aktiviteler": "map_live", "activity": "map_live", "aktivite": "map_live", "both-map": "map_both", "both": "map_both", "hepsi": "map_both",
    }
    action = aliases.get(cmd, cmd)
    if action == "map_zoom" and not rest:
        rest = " ".join(parts[1:])
    return {"action": action, "ip": ip, "event_id": event_id, "text": rest, "focus": rest if action == "map_zoom" else ""}
