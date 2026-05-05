# MEDPOV F.R.I.D.A.Y v2.8.6 — Split Settings + PC Workspace Patch

Bu patch, sağ paneldeki FRIDAY Settings alanını ikiye böler:

- **FRIDAY**: AI provider, ses, Gemini/OpenAI, Security Center ayarları.
- **PC Settings**: Güvenilir klasörler, backup, zip, screenshot, not ve Word/Notepad kontrol ayarları.

## Yeni PC Workspace Yetenekleri

FRIDAY artık PC Settings panelinden eklenen güvenilir klasörlerde şu işlemleri yapabilir:

- Klasör/dosya listeleme
- Klasör ağacı çıkarma
- Dosya/klasör kopyalama
- ZIP oluşturma
- Proje yedeği alma
- Hızlı not oluşturma
- Ekran görüntüsü alma
- Güvenilir dosya/klasör açma
- Word açıp verilen metni yazma/yapıştırma
- Notepad açıp verilen metni yazma/yapıştırma
- Disk kullanım kontrolü

## Güvenlik Mantığı

Dosya işlemleri sadece **PC Settings > Güvenilir klasörler** içine eklenen yollarda çalışır. Örneğin:

```text
C:\wamp64\www
C:\MEDPOV
C:\wamp64\www\security-center
```

FRIDAY bu klasörler dışındaki kritik sistem yollarına otomatik dosya işlemi yapmaz. Bir klasör reddedilirse PC Settings panelinden güvenilir klasör olarak eklenmelidir.

## Örnek Komutlar

```text
C:\wamp64\www klasörünü güvenilir klasörlere ekle.
Security Center projemi zip yedekle.
C:\wamp64\www\security-center klasörünün ağacını çıkar.
Ekran görüntüsü al.
Not al: Bugün Friday PC Workspace eklendi.
Word aç ve şunu yaz: MEDPOV Friday test notu.
```
