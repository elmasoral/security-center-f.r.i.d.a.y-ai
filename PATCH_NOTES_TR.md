# MEDPOV F.R.I.D.A.Y v2.7.0 — Multi AI Provider Patch

Bu patch v2.6.3 üzerine uygulanır.

## Sürüm Özeti

v2.7.0 ile FRIDAY artık yalnızca Gemini tarafına bağlı kalmaz. Ayarlar paneline AI Provider mimarisi eklendi ve OpenAI, Gemini'nin yanında ikinci sağlayıcı olarak sisteme bağlandı.

## Yeni Özellikler

- AI Provider seçimi eklendi:
  - Gemini
  - OpenAI
  - Auto / Fallback
- OpenAI ayar sekmesi eklendi.
- OpenAI API key, text model, vision model, realtime model ve voice alanları eklendi.
- OpenAI bağlantı test butonu eklendi.
- Kamera / ekran analizinde OpenAI Vision desteği eklendi.
- OpenAI Vision cevapları cevap dili ayarına göre Türkçe / İngilizce zorlanır.
- OpenAI ile yazılı komut routing desteği eklendi.
- OpenAI function calling çıktıları FRIDAY'in mevcut lokal araçlarına bağlandı.
- Security Center, dosya, kamera, browser, reminder ve diğer tool tanımları OpenAI router tarafından görülebilir hale getirildi.
- OpenAI cevapları için Windows local TTS fallback eklendi.
- Gemini Live, OpenAI modunda mikrofon transkripsiyon köprüsü olarak kullanılabilir.
- Dosya analizinde eski `google.generativeai` import uyarısı kaldırıldı; `google-genai` adapter yapısına geçildi.
- `config/friday_settings.example.json` ve `config/api_keys.example.json` OpenAI alanlarıyla güncellendi.
- `requirements.txt` içine `openai` paketi eklendi.
- Footer sürüm etiketi v2.7.0 olarak güncellendi.

## Çalışma Mantığı

### Gemini Modu

Eski davranışı korur. Gemini Live sesli konuşma, tool orchestration ve vision akışı ana sağlayıcı olarak çalışır.

### OpenAI Modu

- Yazılı komutlar OpenAI function calling ile yorumlanır.
- OpenAI uygun lokal FRIDAY aracını seçer.
- Araçlar yine kullanıcının bilgisayarında lokal olarak çalışır.
- Kamera ve ekran görüntüsü OpenAI Vision ile analiz edilir.
- OpenAI REST cevapları Windows local TTS ile okunur.
- Mikrofon tarafında mevcut Gemini Live bağlantısı transkripsiyon köprüsü olarak açık kalır; final komut OpenAI'a yönlendirilir.

### Auto / Fallback Modu

Gemini ana sağlayıcı olarak kalır. Vision/text tarafında OpenAI anahtar bilgisi varsa fallback için hazır tutulur.

## Güncellenen Dosyalar

```txt
main.py
ui.py
actions/screen_processor.py
actions/file_processor.py
tools/friday_settings_store.py
tools/friday_settings_dialog.py
tools/friday_local_tts.py
providers/__init__.py
providers/openai_provider.py
config/friday_settings.example.json
config/api_keys.example.json
requirements.txt
PATCH_NOTES_TR.md
```

## Kurulum

1. Patch içindeki dosyaları proje köküne aynı klasör yapısıyla kopyala.
2. Bağımlılıkları güncelle:

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. FRIDAY'i aç.
4. Sağ panelden **Ayarları Aç** butonuna bas.
5. **AI Provider** sekmesinden provider seç.
6. **OpenAI** sekmesine API key gir ve bağlantıyı test et.
7. Kaydet ve FRIDAY'i yeniden başlat.

## Test Komutları

```txt
Friday selam.
Kamerayı açıp bakar mısın?
Şu an elimde ne tutuyorum?
Security Center bağlantısı nasıl?
Son tehditleri özetle.
Bu dosyayı analiz et.
```

## Notlar

- OpenAI modunda kamera/görüntü analizi REST vision mantığıyla çalışır; sürekli kamera stream'i gönderilmez. Bu daha stabil ve maliyet açısından daha kontrollüdür.
- Gemini Live bağlantısı tamamen kaldırılmadı; mevcut ses, transkripsiyon ve stabil tool altyapısı korunur.
- OpenAI key girilmeden OpenAI modu çalışmaz; ayarlar panelindeki test butonu ile kontrol edilebilir.


# MEDPOV F.R.I.D.A.Y v2.6.3 — Hızlı Log + Vision Stabilite Patch

Bu patch v2.6.2 üzerine uygulanır.

## Düzeltilenler

- Sağdaki FRIDAY Command Log artık harf harf yazmak yerine satırı anlık basar.
- Uzun kamera/voice konuşmalarında log kuyruğunun geriden gelmesi azaltıldı.
- Aynı anda gelen tekrar `CAMERA VISION online/offline` logları temizlendi.
- Kamera ilk açılışında snapshot bekleme süresi güvenli şekilde artırıldı.
- Vision WebSocket `1011 keepalive ping timeout` sonrası kırık session içinde kalmıyor; bağlantı zorla yenileniyor.
- Send timeout eklendi; görsel analiz takılı kalırsa kullanıcıya kısa hata logu basılıyor.
- Eski vision cevabının yeni kamera komutundan sonra konuşma/loglama ihtimali azaltıldı.
- Footer sürüm etiketi v2.6.3 olarak güncellendi.

## Değişen dosyalar

- `ui.py`
- `actions/screen_processor.py`
- `PATCH_NOTES_TR.md`

## Kurulum

Zip içindeki dosyaları proje köküne aynı klasör yapısıyla kopyalayın ve FRIDAY'i yeniden başlatın.


# MEDPOV F.R.I.D.A.Y v2.6.2 — Kamera Snapshot + Live Reconnect Stabilite Patch

Bu patch v2.6.1 üzerine uygulanır.

## Düzeltilenler

- İlk kamera komutunda görülen `Kamera frame hazır değil` hatası için kısa retry penceresi eklendi.
- Kamera açma sinyali Qt tarafında asenkron çalıştığı için snapshot artık ilk frame hazır olana kadar güvenli biçimde bekliyor.
- `screen_process` ve doğrudan kamera yakalayıcı aynı komutta iki kez `start_camera_mode` çağırmıyor.
- Sağ log panelinde aynı komut zincirinde tekrar eden `CAMERA VISION online` kayıtları azaltıldı.
- Worker thread içinden doğrudan OpenCV/QImage prime işlemi kaldırıldı; frame üretimi UI thread akışında bırakıldı.
- Google Live session 1011/1008 hatalarında konsolu dev trace ile doldurmadan daha temiz reconnect yapıyor.
- Native audio preview modelinde reconnect sonrası 1008 riskini azaltmak için `session_resumption` kaldırıldı.
- Live reconnect sırasında eski audio queue, eski cevap ve eski vision request temizleniyor.
- Vision thread geçici hata sonrası ölürse bir sonraki kamera isteğinde yeniden başlatılabiliyor.

## Değişen dosyalar

- `main.py`
- `ui.py`
- `actions/screen_processor.py`

## Test komutları

```txt
Kamerayı açar mısın?
Şu an elimde ne tutuyorum?
Tekrar kameraya bak.
Kamerayı kapatır mısın?
```

Beklenen sonuç: İlk komutta frame hazır değil hatası vermeden 1-2 saniye içinde cevap üretmesi, yeni komutta eski analizi susturması ve kamera kapatma komutunda eski vision cevabının devam etmemesi.


# MEDPOV FRIDAY v2.6.1 Camera + Language Patch

Bu patch v2.6.0 üzerine eklenir.

## Değişen dosyalar

- `actions/screen_processor.py`
- `main.py`
- `ui.py`
- `tools/friday_settings_store.py`
- `tools/friday_settings_dialog.py`
- `config/friday_settings.example.json`
- `config/api_keys.example.json`

## Eklenenler

### 1. Kamera analizi hızlandırıldı

- UI kamera snapshot bekleme süresi 3.0 saniyeden 0.75 saniyeye indirildi.
- Kamera snapshot görüntüsü Vision API'ye gitmeden önce 640x360 JPEG olarak sıkıştırılıyor.
- HUD kamera çözünürlüğü 1280x720 yerine 960x540 kullanıyor.
- Snapshot cache daha sık güncelleniyor.
- İlk frame prime bekleme aralığı kısaltıldı.

### 2. Yeni komut eski kamera analizini iptal eder

- Vision isteklerinde `latest-wins` mantığı eklendi.
- Yeni kamera analizi geldiğinde eski kuyruk, eski frame ve eski ses kuyruğu temizlenir.
- Kamera kapat komutu aktif vision cevabını da iptal eder.
- Aynı cümlenin çok hızlı tekrar eden partial voice transcriptleri engellenir; fakat yeni komutlar artık 3.5 saniye boyunca bloklanmaz.

### 3. Cevap dili ayarı eklendi

Settings > Ses sekmesine `Cevap dili` alanı eklendi:

- Türkçe cevap ver
- Answer in English

Bu ayar `config/friday_settings.json` içinde şu şekilde tutulur:

```json
"assistant": {
  "response_language": "tr"
}
```

Ayar `config/api_keys.json` içine de geriye uyumlu olarak yazılır:

```json
"friday_response_language": "tr"
```

## Kurulum

Zip içindeki dosyaları mevcut proje köküne aynı klasör yapısı ile kopyala ve değiştir.
Sonra FRIDAY'i kapatıp tekrar aç.

## Test komutları

- `Kamerayı açar mısın?`
- `Şu an elimde ne tutuyorum?`
- Eski cevap bitmeden: `Tekrar bak, şimdi elimde ne var?`
- `Kamerayı kapatır mısın?`
- Settings > Ses > Cevap dili: English seçip yeniden başlat, sonra aynı komutları test et.
