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
