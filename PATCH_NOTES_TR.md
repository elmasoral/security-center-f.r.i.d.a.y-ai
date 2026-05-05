# MEDPOV F.R.I.D.A.Y v2.8.2 — OpenAI Realtime GA Ses Şeması Düzeltmesi

Bu patch v2.8.1 üzerinde OpenAI Realtime bağlantısında görülen iki kritik problemi düzeltir:

- `Unknown parameter: session.output_modalities` hatası
- OpenAI Realtime tarafında kullanıcının söylediklerinin Command Log'a düşmemesi ve ses çıkışının stabil başlamaması

## Ana Neden

v2.8.1 içinde OpenAI Realtime bağlantısı hâlâ eski `OpenAI-Beta: realtime=v1` header'ı ile açılıyordu; fakat session payload tarafında yeni GA alanları (`session.type`, `output_modalities`, `audio.input`, `audio.output`) gönderiliyordu. Bu karışık şema bazı endpointlerde session ayarını reddediyor ve ses/araç bağlamını eksik bırakıyordu.

## Yapılan Düzeltmeler

- OpenAI Realtime varsayılan bağlantısı GA moda alındı.
- Varsayılan OpenAI Realtime bağlantısından `OpenAI-Beta: realtime=v1` header'ı kaldırıldı.
- GA session payload tekrar doğru hale getirildi:
  - `session.type = realtime`
  - `session.model = gpt-realtime`
  - `session.output_modalities = ["audio"]`
  - `session.audio.input.format = audio/pcm @ 24000`
  - `session.audio.output.voice = seçili OpenAI sesi`
- Eski endpoint uyumluluğu için beta fallback eklendi:
  - GA alanları reddedilirse legacy payload `modalities`, `input_audio_format`, `output_audio_format` alanlarıyla tekrar denenir.
- OpenAI Realtime response create event'i schema moduna göre ayrıldı:
  - GA: `output_modalities`
  - Beta fallback: `modalities`
- Kullanıcı konuşması transcript event'leri için ek event adı desteği eklendi.
- Kullanıcı konuşmaya başladığında kuyrukta kalan FRIDAY ses parçaları temizlenir; barge-in davranışı iyileştirildi.
- Ayarlar > OpenAI sekmesinde OpenAI Realtime sesleri kadın/erkek etiketleriyle düzenlendi.
- OpenAI Realtime için desteklenen ses listesi sadeleştirildi:
  - Kadın tonları: `marin`, `coral`, `shimmer`, `sage`
  - Erkek tonları: `cedar`, `alloy`, `ash`, `ballad`, `echo`, `verse`
- Footer sürümü `v2.8.2` olarak güncellendi.

## Değişen Dosyalar

```txt
main.py
ui.py
tools/friday_settings_store.py
tools/friday_settings_dialog.py
README.md
PATCH_NOTES_TR.md
```

## Kurulum

Patch içindeki dosyaları proje köküne aynı klasör yapısıyla kopyalayın.

Sonra:

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

FRIDAY'i tamamen kapatıp tekrar başlatın.

## Önerilen Ayar

```txt
AI Provider: OpenAI Realtime · bağımsız canlı ses + tool orchestration
Fallback: OpenAI
OpenAI Realtime model: gpt-realtime
OpenAI Realtime sesi: marin veya cedar
```

## Test

```txt
Friday beni duyuyor musun?
Kamerayı açıp bakar mısın?
Şu an elimde ne tutuyorum?
Kamerayı kapat.
```

Beklenen log:

```txt
SYS: OpenAI Realtime provider online.
SYS: OpenAI Realtime audio session ready.
You: Friday beni duyuyor musun?
FRIDAY: ...
```

Artık şu hata gelmemelidir:

```txt
ERR: OpenAI Realtime — Unknown parameter: 'session.output_modalities'.
```


# MEDPOV F.R.I.D.A.Y v2.8.0 — Full OpenAI Realtime Provider Patch

Bu sürüm, OpenAI modunu v2.7.x hibrit köprü yapısından çıkarıp Gemini'den bağımsız bir canlı OpenAI Realtime provider haline getirir.

## Ana Değişiklik

v2.7.x OpenAI modu şu şekilde çalışıyordu:

```txt
Mikrofon / canlı transcript: Gemini Live
Komut beyni: OpenAI
Kamera analizi: OpenAI Vision
Ses çıkışı: OpenAI TTS
```

v2.8.0 OpenAI modu artık şu şekilde çalışır:

```txt
Mikrofon girişi: OpenAI Realtime
Canlı konuşma / düşünme: OpenAI Realtime
Tool/function calling: OpenAI Realtime
Ses çıkışı: OpenAI Realtime streamed audio
Kamera/görüntü analizi: OpenAI Vision tool sonucu olarak OpenAI Realtime'a döner
```

## Neler Eklendi?

- OpenAI provider seçiliyken Gemini Live oturumu artık başlatılmaz.
- OpenAI Realtime WebSocket bağlantısı eklendi.
- Mikrofon PCM16 ses akışı doğrudan OpenAI Realtime'a gönderilir.
- OpenAI Realtime streamed audio cevabı doğrudan FRIDAY ses çıkışına basılır.
- OpenAI Realtime tool/function calling desteği eklendi.
- `screen_process` kamera/görüntü analizleri tool sonucu olarak OpenAI Realtime'a döner.
- OpenAI Realtime üzerinden doğal tek oturumlu cevap akışı sağlandı.
- v2.7.x'teki Gemini transcript → OpenAI command → OpenAI TTS gecikmesi kaldırıldı.
- Hoparlör → mikrofon → kendi cevabına cevap verme riski azaltıldı.
- OpenAI provider modunda Gemini Vision warmup devre dışı bırakıldı.
- OpenAI ayar açıklamaları güncellendi.
- Footer sürümü `v2.8.0` olarak güncellendi.

## Güncellenen Dosyalar

```txt
main.py
actions/screen_processor.py
tools/friday_settings_dialog.py
requirements.txt
README.md
PATCH_NOTES_TR.md
```

## Kurulum

Patch içindeki dosyaları proje köküne aynı klasör yapısıyla kopyalayın.

Sonra:

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

FRIDAY'i tamamen kapatıp yeniden açın.

## Önerilen Ayar

```txt
AI Provider: OpenAI Realtime · bağımsız canlı ses + tool orchestration
Fallback: OpenAI
OpenAI Realtime model: gpt-realtime
OpenAI voice: marin veya cedar
```

## Test Komutları

```txt
Friday selam.
Şu an elimde ne tutuyorum?
Kamerayı kapat.
Güvenlik merkezi ile bağlantı nasıl?
```

## Not

OpenAI Realtime provider artık Gemini'den bağımsızdır. Gemini sadece AI Provider olarak Gemini seçildiğinde çalışır.


# MEDPOV F.R.I.D.A.Y v2.7.1 — OpenAI Natural Voice Patch

Bu patch v2.7.0 üzerine uygulanır.

## Neden gerekliydi?

v2.7.0'da OpenAI provider komut ve kamera analizini OpenAI ile yapıyordu; fakat ses okuma tarafında Windows lokal TTS/SAPI kullanılıyordu. Bu yüzden ses robotik, kopuk ve bazı Windows sistemlerinde COM hatası nedeniyle tamamen başarısız olabiliyordu.

## Düzeltilenler

- OpenAI provider cevaplarında Windows lokal TTS yerine OpenAI cloud TTS eklendi.
- Varsayılan TTS model: `gpt-4o-mini-tts`.
- Varsayılan OpenAI voice: `marin`.
- OpenAI ayar paneline `TTS model` alanı eklendi.
- OpenAI voice alanı combobox yapıldı.
- Yeni cevap geldiğinde önceki TTS sesini kesen latest-wins kontrolü eklendi.
- Windows SAPI sadece yedek fallback olarak bırakıldı.
- SAPI fallback için thread içi COM initialize koruması eklendi.
- OpenAI provider açıklaması “lokal TTS” yerine “doğal OpenAI TTS” olarak güncellendi.
- Footer sürümü `v2.7.1` olarak güncellendi.

## Önemli not

Bu patch OpenAI ses çıkışını akıcı hale getirir. Mikrofon dinleme/transkripsiyon tarafı hâlâ Gemini Live köprüsü üzerinden çalışır. Eğer ChatGPT mobil uygulamasındaki gibi tam çift yönlü, akıcı speech-to-speech isteniyorsa sonraki büyük adım OpenAI Realtime provider entegrasyonudur.

## Güncellenen dosyalar

- `tools/friday_local_tts.py`
- `tools/friday_settings_store.py`
- `tools/friday_settings_dialog.py`
- `config/friday_settings.example.json`
- `config/api_keys.example.json`
- `ui.py`
- `README.md`

## Kurulum

Patch içindeki dosyaları proje köküne aynı klasör yapısıyla kopyala. Sonra:

```powershell
cd C:\MEDPOV\security-center-f.r.i.d.a.y-ai
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Ardından FRIDAY'i kapatıp yeniden aç.

## Ayar önerisi

Ayarlar > AI Provider:

- AI Provider: `OpenAI`
- Fallback: `OpenAI` veya `Gemini`

Ayarlar > OpenAI:

- TTS model: `gpt-4o-mini-tts`
- OpenAI voice: `marin` veya `cedar`


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
