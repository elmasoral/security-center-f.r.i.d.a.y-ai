# MEDPOV FRIDAY Modern UI v2 Patch

Bu patch, önceki modern UI düzenlemesinin üstüne gelen ince ayar paketidir.

## Düzeltilenler

- Üst header içinde F.R.I.D.A.Y başlığı gerçek merkeze alındı.
- Sol üst MEDPOV marka alanına özel çizimli shield logo eklendi.
- Intelligent File Input içindeki karışık upload ikonu sadeleştirildi.
- Sol paneldeki System Activity bar yazısı yerine gerçek çizimli line telemetry widget eklendi.
- Security Center Quick Links kartına sağ tarafta büyük güvenlik badge eklendi.
- Sağ panel spacing ve kart oranları örnek tasarıma yaklaştırıldı.

## Kurulum

```powershell
cd C:\wamp64\www\med\medpov-friday-git
powershell -ExecutionPolicy Bypass -File .\medpov_friday_modern_ui_v2_patch\apply_patch.ps1
```

## Test

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

## Push

```powershell
git status
git add ui.py
git commit -m "Refine FRIDAY modern command center UI"
git push origin main
```
