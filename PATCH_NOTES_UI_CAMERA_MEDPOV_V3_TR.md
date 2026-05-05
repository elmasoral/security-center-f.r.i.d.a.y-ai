# MEDPOV F.R.I.D.A.Y v2.8.6 — UI Language + Camera Privacy + MEDPOV Knowledge Patch

Bu patch şunları ekler:

## 1. English-first UI
- FRIDAY Settings ve PC Settings pencerelerindeki Türkçe görünen ana metinler İngilizceye çevrildi.
- Sağ paneldeki split settings kartları İngilizce hale getirildi.
- Security Center quick link etiketleri İngilizce hale getirildi.

## 2. Turkish UI language support
- FRIDAY Settings > AI Provider sekmesine `Interface language` seçimi eklendi.
- `English interface` ve `Türkçe arayüz` seçenekleri `config/friday_settings.json` içinde `assistant.ui_language` olarak saklanır.
- Dil değişikliği için FRIDAY yeniden başlatılması önerilir.

## 3. Camera hard-disable privacy gate
- FRIDAY Settings > Privacy / Camera sekmesine `Camera Access` eklendi.
- Sağ panelde yeni `[F6] Camera` kısayolu ve butonu eklendi.
- Kamera disable iken kullanıcı kamerayı aç dese bile FRIDAY kamera açmaz ve kısa cevap verir:
  `Camera access is currently disabled in FRIDAY settings. I cannot open the camera until Camera Access is enabled.`
- Kamera disable iken `screen_process(angle="camera")`, `friday_camera_mode(open)` ve lokal kamera komutları engellenir.

## 4. MEDPOV permanent knowledge
- `knowledge/medpov_profile.txt` eklendi.
- FRIDAY artık MEDPOV’un ne olduğunu, resmi site bağlamını ve kurucu bilgisini kalıcı sistem promptuna ekler.
- MEDPOV artık medikal/hastane sitesi olarak tanıtılmaz.

## 5. Config additions
`config/friday_settings.example.json` içine eklendi:

```json
"assistant": {
  "ui_language": "en"
},
"privacy": {
  "camera_enabled": true
}
```
