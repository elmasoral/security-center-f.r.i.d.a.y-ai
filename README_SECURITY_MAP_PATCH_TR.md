# MEDPOV FRIDAY — Security Center Global Map HUD Patch

Bu patch, FRIDAY Command Center içine Security Center dashboard mantığına yakın çalışan büyük bir dünya haritası modu ekler.

## Yeni sesli/yazılı komutlar

- `harita aç`
- `dünya haritası aç`
- `map open`
- `Londra aç`
- `Tokyo’ya zoom yap`
- `Istanbul’a git`
- `son tehditleri haritada göster`
- `canlı bağlantıları göster`
- `tehditleri ve canlı bağlantıları birlikte göster`
- `haritayı kapat`

## Desteklenen Security Center API map action’ları

- `GET action=map&mode=both&include_curve_points=1`
- `GET action=threat-map&threat_range=24h`
- `GET action=live-map&live_range=live`
- `GET action=both-map&live_range=live&include_curve_points=1`

## Değişen dosyalar

- `main.py`
- `ui.py`
- `core/prompt.txt`
- `tools/security_center_client.py`
- `tools/medpov_security_center_commands.py`
- `config/security_center.example.json`
- `PATCH_NOTES_TR.md`

## Kurulum

Patch içindeki dosyaları mevcut FRIDAY proje klasörüne aynı yollarla kopyala. Sonra uygulamayı yeniden başlat.

Önerilen Security Center ayarı:

```json
{
  "api_url": "https://medpov.com/main/security-center/admin/api/remote-access.php",
  "api_key": "mpsec_YOUR_API_KEY",
  "timeout": 25,
  "map_defaults": {
    "mode": "both",
    "threat_range": "24h",
    "live_range": "live",
    "include_curve_points": true
  }
}
```

API key’i FRIDAY Settings panelinden girmen daha güvenli olur. Public JavaScript içine API key koyma.
