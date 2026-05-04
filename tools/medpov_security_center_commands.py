from __future__ import annotations
import ipaddress, json, re
from typing import Any, Dict, Optional
try:
    from .security_center_client import SecurityCenterClient
except Exception:
    from security_center_client import SecurityCenterClient  # type: ignore
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
def _valid_ip(ip: str) -> str:
    try: return str(ipaddress.ip_address((ip or "").strip()))
    except Exception: return ""
def _first_ip(text: str) -> str:
    for m in IP_RE.finditer(text or ""):
        ip = _valid_ip(m.group(0))
        if ip: return ip
    return ""
def _safe_int(v: Any, default: int, minimum: int=1, maximum: int=500) -> int:
    try: return max(minimum, min(maximum, int(v)))
    except Exception: return default
def _pick(d: Dict[str, Any], *keys: str, default=None):
    for k in keys:
        if k in d and d[k] not in (None, ""): return d[k]
    return default
def _listish(v: Any) -> list[Any]:
    if v is None: return []
    if isinstance(v, list): return v
    if isinstance(v, tuple): return list(v)
    return [v]
def _event_line(ev: Dict[str, Any]) -> str:
    return f"#{_pick(ev,'id','event_id',default='?')} | {str(_pick(ev,'risk','risk_level',default='?')).upper()} | score {_pick(ev,'score','risk_score',default='-')} | {_pick(ev,'actor_ip','ip','client_ip',default='-')} | {_pick(ev,'category','type',default='-')} | {_pick(ev,'uri','path',default='-')} | {_pick(ev,'last_seen_at','created_at',default='-')}"
def _format_overview(data: Dict[str, Any]) -> str:
    if not data.get('ok'): return f"Security Center bağlantı hatası: {data.get('message','unknown error')}"
    s=data.get('stats') or {}; lines=["MEDPOV Security Center canlı bağlantı aktif.", f"Erişim: {data.get('access','-')}; Asistan: {data.get('assistant','-')}; Sürüm: {data.get('version','-')}", f"Toplam event: {s.get('total_events',0)} | Açık event: {s.get('open_events',0)} | Son 24 saat: {s.get('events_24h',0)} | Son 7 gün: {s.get('events_7d',0)}", f"Açık HIGH: {s.get('high_open',0)} | Açık CRITICAL: {s.get('critical_open',0)} | Aktif block rule: {s.get('active_block_rules',0)} | Canlı oturum: {s.get('live_sessions_active',0)}"]
    top=_listish(data.get('top_ips_24h'))[:5]
    if top:
        lines.append('Son 24 saatin baskı yapan IP’leri:')
        for r in top:
            if isinstance(r, dict): lines.append(f"- {r.get('ip','-')} | {r.get('top_risk','-')} | event {r.get('events',0)} | attempts {r.get('attempts',0)} | {r.get('sample_category','-')}")
    latest=_listish(data.get('latest_high_risk_events'))[:5]
    if latest:
        lines.append('Son yüksek riskli olaylar:'); lines += ['- '+_event_line(x) for x in latest if isinstance(x,dict)]
    recs=_listish(data.get('recommendations_tr'))
    if recs: lines.append('Öneri: ' + ' '.join(map(str,recs[:3])))
    return '\n'.join(lines)
def _format_threats(data: Dict[str, Any]) -> str:
    if not data.get('ok'): return f"Tehdit akışı alınamadı: {data.get('message','unknown error')}"
    events=_listish(data.get('events') or data.get('threats') or data.get('latest_high_risk_events'))
    if not events: return 'Son filtrede HIGH/CRITICAL tehdit bulunmadı.'
    return '\n'.join(['Son Security Center tehditleri:'] + ['- '+_event_line(x) for x in events[:12] if isinstance(x,dict)])
def _format_ip_profile(data: Dict[str, Any], ip: str) -> str:
    if not data.get('ok'): return f"IP profili alınamadı ({ip}): {data.get('message','unknown error')}"
    profile=data.get('ip_profile') or data.get('profile') or data
    lookup=(data.get('lookup') or (profile.get('lookup') if isinstance(profile,dict) else {})) or {}
    analysis=(data.get('analysis') or (profile.get('analysis') if isinstance(profile,dict) else {})) or {}
    events=_listish(data.get('events') or (profile.get('events') if isinstance(profile,dict) else []))
    rules=_listish(data.get('rules') or (profile.get('rules') if isinstance(profile,dict) else []))
    queries=_listish(data.get('research_queries') or (profile.get('research_queries') if isinstance(profile,dict) else []))
    lines=[f"IP profil raporu: {ip}"]
    if isinstance(lookup,dict) and lookup:
        bits=[f"{k}: {lookup.get(k)}" for k in ['country','city','org','isp','asn','hostname','reverse_dns'] if lookup.get(k)]
        if bits: lines.append('Lookup: '+' | '.join(bits[:8]))
    if isinstance(analysis,dict) and analysis:
        summary=analysis.get('summary') or analysis.get('recommendation') or analysis.get('verdict'); risk=analysis.get('risk') or analysis.get('risk_level')
        if risk or summary: lines.append(f"Analiz: {risk or '-'} — {summary or '-'}")
    if events:
        lines.append(f"Event geçmişi: {len(events)} kayıt gösteriliyor"); lines += ['- '+_event_line(x) for x in events[:8] if isinstance(x,dict)]
    if rules: lines.append('Aktif/ilgili IP kuralları: '+str(len(rules)))
    if queries: lines.append('İnternet araştırma sorguları: '+' | '.join(map(str,queries[:4])))
    return '\n'.join(lines)
def _format_generic(data: Dict[str, Any], title: str) -> str:
    if not data.get('ok'): return f"{title} başarısız: {data.get('message','unknown error')}"
    text=json.dumps(data, ensure_ascii=False, indent=2)
    return f"{title}:\n" + (text[:5000] + '\n... çıktı kısaltıldı ...' if len(text)>5000 else text)
def security_center_action(parameters: Optional[Dict[str, Any]]=None, player: Any=None, speak: Any=None) -> str:
    p=parameters or {}; raw=str(p.get('action') or p.get('command') or 'overview').strip().lower(); text=str(p.get('text') or p.get('query') or '')
    ip=_valid_ip(str(p.get('ip') or '')) or _first_ip(text); event_id=p.get('event_id') or p.get('id')
    limit=_safe_int(p.get('limit'),20,1,100); hours=_safe_int(p.get('hours') or p.get('since_hours'),24,1,720); minutes=_safe_int(p.get('minutes'),1440,1,525600); reason=str(p.get('reason') or 'MEDPOV Friday action').strip(); risk=str(p.get('risk') or '').strip().upper()
    c=SecurityCenterClient(); action=raw.replace('-', '_').replace(' ','_')
    aliases={'status':'overview','durum':'overview','ozet':'overview','özet':'overview','dashboard':'overview','genel':'overview','son_tehditler':'threats','threat':'threats','tehdit':'threats','tehditler':'threats','high':'threats','critical':'threats','ip':'ip_profile','ip_profil':'ip_profile','lookup':'ip_profile','analiz':'analyze','analyze_ip':'analyze','ip_analyze':'analyze','ip_analiz':'analyze','blokla':'block_ip','block':'block_ip','izin_ver':'allow_ip','allow':'allow_ip','ignore':'ignore_ip','yoksay':'ignore_ip','saglik':'health','sağlık':'health','health_check':'health','canli':'live','canlı':'live','live_sessions':'live'}
    action=aliases.get(action, action)
    if action=='overview': return _format_overview(c.overview())
    if action=='threats': return _format_threats(c.threats(limit=limit, hours=hours))
    if action=='events': return _format_threats(c.events(risk=risk, ip=ip, limit=limit))
    if action=='event': return 'Event detayı için event_id gerekli. Örnek: /sc event 124' if not event_id else _format_generic(c.event(int(event_id)), f"Security event #{event_id}")
    if action=='ip_profile': return 'IP profili için IP gerekli. Örnek: /sc ip 65.55.210.207' if not ip else _format_ip_profile(c.ip_profile(ip, refresh=True, limit=limit), ip)
    if action=='analyze':
        if event_id: return _format_generic(c.analyze(event_id=int(event_id)), f"Event analiz #{event_id}")
        return 'Analiz için IP veya event_id gerekli. Örnek: /sc analyze 65.55.210.207' if not ip else _format_generic(c.analyze(ip=ip), f"IP analiz {ip}")
    if action=='traffic': return _format_generic(c.traffic(ip=ip, limit=limit, since_hours=hours), 'Security Center trafik')
    if action=='live': return _format_generic(c.live(limit=limit), 'Security Center canlı oturumlar')
    if action=='bots': return _format_generic(c.bots(limit=limit), 'Bot kayıtları')
    if action=='login': return _format_generic(c.login(limit=limit), 'Login baskısı')
    if action=='health': return _format_generic(c.health(), 'Security Center sağlık raporu')
    if action=='settings': return _format_generic(c.settings(), 'Security Center ayar özeti')
    if action=='capabilities': return _format_generic(c.capabilities(), 'Security Center yetenekleri')
    if action=='block_ip': return 'IP bloklamak için IP gerekli. Örnek: /sc block 1.2.3.4' if not ip else _format_generic(c.block_ip(ip, minutes=minutes, reason=reason), f"IP block işlemi {ip}")
    if action=='allow_ip': return 'IP allow için IP gerekli. Örnek: /sc allow 1.2.3.4' if not ip else _format_generic(c.allow_ip(ip, reason=reason), f"IP allow işlemi {ip}")
    if action=='ignore_ip': return 'IP ignore için IP gerekli. Örnek: /sc ignore 1.2.3.4' if not ip else _format_generic(c.ignore_ip(ip, reason=reason), f"IP ignore işlemi {ip}")
    if action=='resolve_event': return 'Event resolve için event_id gerekli. Örnek: /sc resolve-event 124' if not event_id else _format_generic(c.resolve_event(int(event_id)), f"Event resolve #{event_id}")
    if action=='resolve_ip_events': return 'IP event resolve için IP gerekli. Örnek: /sc resolve-ip 1.2.3.4' if not ip else _format_generic(c.resolve_ip_events(ip), f"IP event resolve {ip}")
    if action=='ai_recheck': return _format_generic(c.ai_recheck(limit=limit), 'Local AI re-check')
    return f"Bilinmeyen Security Center komutu: {raw}. Kullanım: overview, threats, ip_profile, analyze, block_ip, health."
def parse_slash_command(text: str) -> Optional[Dict[str, Any]]:
    raw=(text or '').strip()
    if not raw.lower().startswith(('/sc','sc ','security-center ','security center ')): return None
    cleaned=re.sub(r'^/(sc|security-center)\s*','',raw,flags=re.I).strip(); cleaned=re.sub(r'^(sc|security-center|security center)\s+','',cleaned,flags=re.I).strip()
    if not cleaned: return {'action':'overview'}
    parts=cleaned.split(); cmd=parts[0].lower(); rest=' '.join(parts[1:]); ip=_first_ip(cleaned); event_id=None
    for token in parts[1:]:
        if token.isdigit(): event_id=int(token); break
    aliases={'overview':'overview','status':'overview','durum':'overview','özet':'overview','ozet':'overview','threats':'threats','tehditler':'threats','tehdit':'threats','ip':'ip_profile','lookup':'ip_profile','profile':'ip_profile','profil':'ip_profile','analyze':'analyze','analiz':'analyze','event':'event','olay':'event','events':'events','olaylar':'events','traffic':'traffic','trafik':'traffic','live':'live','canlı':'live','canli':'live','bots':'bots','bot':'bots','login':'login','health':'health','sağlık':'health','saglik':'health','block':'block_ip','blokla':'block_ip','allow':'allow_ip','izin':'allow_ip','ignore':'ignore_ip','yoksay':'ignore_ip','resolve-event':'resolve_event','resolve':'resolve_event','resolve-ip':'resolve_ip_events','ai-recheck':'ai_recheck','recheck':'ai_recheck'}
    return {'action': aliases.get(cmd,cmd), 'ip': ip, 'event_id': event_id, 'text': rest}
