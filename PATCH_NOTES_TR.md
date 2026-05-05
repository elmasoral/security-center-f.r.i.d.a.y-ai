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
