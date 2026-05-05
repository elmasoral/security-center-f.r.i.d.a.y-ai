# MEDPOV FRIDAY Camera Vision Fix v3

Bu patch, kamera modunda "Şu an elimde ne tutuyorum?" gibi komutlarda yaşanan kapanma sorununu düzeltir.

## Düzeltilenler

- Kamera açılır açılmaz ilk frame senkron olarak hazırlanır.
- Vision analiz thread'i aynı kamerayı ikinci kez açmaya çalışmaz.
- UI snapshot hazır değilse OpenCV fallback ile kamerayı tekrar açıp crash riski oluşturmaz.
- Gemini duplicate camera tool çağrısı geldiğinde sesli/yanlış cevap vermemesi için bastırılır.

## Kurulum

Patch klasörünü repo köküne çıkar:

```powershell
cd C:\wamp64\www\med\medpov-friday-git
powershell -ExecutionPolicy Bypass -File .\medpov_friday_camera_fix_v3_patch\apply_patch.ps1
```

Test:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

Komutlar:

```txt
kamera aç
kamera kapat
şu an elimde ne tutuyorum
kameraya bak ve ne gördüğünü söyle
```

Sorun yoksa push:

```powershell
git status
git add main.py ui.py actions/screen_processor.py
git commit -m "Fix FRIDAY camera vision snapshot crash"
git push origin main
```

Canlı klasör güncelleme:

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
git fetch origin
git reset --hard origin/main
git clean -fd
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```
