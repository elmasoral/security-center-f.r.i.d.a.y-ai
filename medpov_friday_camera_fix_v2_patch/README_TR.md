# MEDPOV FRIDAY Camera / Vision Fix v2

Bu patch, kamera modunun doğru çalışıp yanlış cevap vermesini engeller ve kamera analizini hızlandırır.

## Düzeltilenler

- `kamera aç` / `kamera kapat` komutlarında FRIDAY kamerayı doğru açıp kapatırken artık “açamam / kapatamam” gibi yanlış sesli cevapları bastırır.
- `şu an elimde ne tutuyorum`, `buna bak`, `kameraya bak`, `ne görüyorsun` gibi gerçek dünya/görsel sorularında otomatik kamera moduna geçer.
- Görsel analiz başlamadan önce kamera HUD hemen açılır.
- Vision Live session uygulama açılır açılmaz arkada warmup edilir, ilk analiz daha hızlı başlar.
- Kamera snapshot boyutu ve JPEG kalitesi optimize edildi.
- Aynı kamera analizinin Gemini tarafından ikinci kez tetiklenmesi engellendi.

## Kurulum

Patch klasörünü repo köküne kopyala ve PowerShell ile çalıştır:

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
powershell -ExecutionPolicy Bypass -File .\medpov_friday_camera_fix_v2_patch\apply_patch.ps1
```

Sonra:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install opencv-python
python main.py
```

## Test komutları

```txt
kamera aç
kamera kapat
şu an elimde ne tutuyorum
buna bak
kameraya bak ve ne gördüğünü söyle
```
