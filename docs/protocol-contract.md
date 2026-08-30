# Technocore protokol sözleşmesi

> Ana karar kaynağı: [`../Technocore-Station-Proje-Kunyesi.md`](../Technocore-Station-Proje-Kunyesi.md) §14.
> Resmî referans: `flop-labs/technocore-chat` @ `7707cb63ebf638e8ef0cf59d1364818b9fef7d24`
> (bkz. [`../vendor/technocore-reference/PROVENANCE.md`](../vendor/technocore-reference/PROVENANCE.md)).

**Uygulama durumu: canonical/sweep/imza yüzeyi UYGULANDI (Aşama 2B); ağ
yolu YOKTUR.** `technocore-conform` paketi sweep, canonical string, `did:key`
ve Ed25519 imzalama/doğrulama sözleşmesini uygular ve pinlenmiş resmî
referansa karşı diferansiyel olarak test edilir. Technocore'a **hiçbir**
network yolu, istemci veya write endpoint'i hâlâ yoktur; dış yazma kapısı
kapalıdır.

Uygulama ayrıntısı, self-test ve CLI için: [`conformance.md`](conformance.md).

---

## 1. Kapsam ayrımı

Technocore, FLOP Network blokzincir protokolünün parçası **değildir**;
buna karşılık kendi belgelenmiş HTTP uygulama protokolüne ve imza uygunluk
sözleşmesine **sahiptir**.

| Technocore neyi doğrular | Neyi doğrulamaz |
|---|---|
| Ed25519 imzasının geçerliliği | Gerçek kişi/kurum kimliği |
| Kullanılan DID'nin ilgili özel anahtara sahip olması | Mesaj içeriğinin doğruluğu |
| — | Dürüstlük, kalıcılık, güvenilir zaman |

---

## 2. Canonical string sözleşmesi

Sunucu **tam olarak sakladığı baytların** üzerindeki imzayı doğrular.

```text
message:  <room>|<nonce>|<swept_text>
note:     <namespace>|<key>|<nonce>|<swept_value>
```

Ayırıcı tek bir `|` (U+007C) karakteridir. Alanlar kaçışlanmaz.

### 2.1 Sweep (tek satır süpürme)

Depolamadan önce her yazma bir sweep'ten geçer. Resmî referans:
`vendor/technocore-reference/src/store.py` → `clean_text`.

Sözleşme:

1. Unicode kategorisi **`Cc`, `Cf`, `Cs`, `Co`, `Zl` veya `Zp`** olan her
   karakter tek bir **boşluk** (U+0020) ile değiştirilir.
2. Sonuç metnin **uçları trim edilir**.

Sweep **normalization yapmaz** ve boşlukları **collapse etmez**: art arda üç
kontrol karakteri üç boşluk olur. Uzunluk sweep sonrasındaki code point
sayısıyla ölçülür (mesaj 4096, note değeri 8192).

Sonuçlar:
- Sweep **idempotent** olmalıdır: `sweep(sweep(x)) == sweep(x)` (AC-03).
- **Ham metin imzalanırsa sunucu 403 döner.** İmza, saklanan swept metni
  kapsamalıdır — bu, kaydın sonradan diskteki baytlara karşı yeniden
  doğrulanabilmesi için bilinçli bir tasarımdır.
- Kullanıcıya **gönderilecek olan** (swept) metin gösterilir ve onaylatılır;
  ham metinle farkı Compose & Verify yüzeyinde diff olarak sunulur.

### 2.2 İmza kodlaması

- Algoritma: **Ed25519**.
- Kodlama: **padding'siz base64url**.
- Uzunluk: **86 karakter** (64 bayt imza) — AC-04.

### 2.3 DID

- Biçim: `did:key`, Ed25519 açık anahtarının **base58btc + multicodec**
  gösterimi.
- Aynı seed için üretilen DID, resmî `scripts/sign.py` çıktısıyla
  **karakter karakter aynı** olmalıdır (AC-01).
- DID bir kimlik sağlayıcı değildir; yalnız **anahtar sahipliği**
  göstergesidir.

### 2.4 İmza kapsamı — dikkat

İmza **canonical string'i** kapsar, **tüm JSON request gövdesini kapsamaz**.
Exact JSON request baytları Evidence için saklanabilir, fakat
*"imza bu JSON'u kapsıyor"* **denmez**.

---

## 3. Seed türetme — Station sapması

Resmî `scripts/sign.py`, 64-hex olmayan bir `--seed` girdisini SHA-256'dan
geçirerek seed üretir (passphrase kolaylığı).

**Station bu yolu uygulamaz.** Künye §8.3 paroladan seed türetmeyi açıkça
yasaklar. Station yalnız:

- `secrets.token_bytes(32)` ile üretilmiş seed, veya
- kullanıcının kendi 64-hex seed'inin yerel import'u

kabul eder. Bu bilinçli ve belgelenmiş bir sapmadır; conformance testleri
yalnız **DID türetme, sweep, canonical ve imza** yüzeylerini karşılaştırır.

---

## 4. Yazma yolları

| Karar | Değer | Gerekçe |
|---|---|---|
| Varsayılan lane | **signed POST** | URL/log/uzunluk risklerini azaltır (ADR-011) |
| GET | **Yalnız conformance testi ve protokol fallback** | Kullanıcıya ikinci ve riskli yazma yolu sunulmaz (ADR-012) |

GET **UI seçeneği değildir**.

---

## 5. Nonce

- Mesajlar için `(did, room)` başına **monoton sayaç**.
- Yeni nonce = `max(yerel_son_deger + 1, milisaniye_saati)`.
- Sayaç **imzadan önce transaction içinde ayrılır**.
- Aynı canonical içerik **tekrar gönderilmez**; kullanıcı yeni içerik/nonce
  ile yeniden onaylar.
- Notlar için namespace/key kuralı **runtime manifest'ten** doğrulanır.

---

## 6. Protocol drift ve write gate

Station üç şeyi birlikte tutar:

1. Pinlenmiş resmî referans commit'i.
2. Canlı manifest/version hash'i.
3. Son conformance test sonucu.

**Fail-closed kuralı:** imza, canonicalization, nonce veya encoding alanı
değişirse **write gate kapanır**. Limit/kapasite değişikliği uyarı üretir.
Kullanıcı farkı ve kaynak URL'yi **görmeden** yazma yeniden açılamaz.

**Kodda sabit protokol limiti kullanılmaz.** Limitler runtime'da okunur;
ölçümler tarihli snapshot olarak tutulur.

---

## 7. Ağ güvenliği kuralları (Aşama 3'te uygulandı)

- Sabit **host allow-list**.
- **Zorunlu TLS doğrulaması** — `verify=False` ve eşdeğerleri yasaktır.
- Rate-limit ve retry davranışı tanımlıdır.
- **Kullanıcı onayı olmadan hiçbir dış yazma yapılmaz.**
- **Yalnız `https://technocore.chat`**; şema, host ve varsayılan port sabit.
- Erişilebilir yollar **kapalı bir registry**'dir. Technocore'da bazı GET
  yolları yazma yaptığı için "GET güvenlidir" varsayımı yapılmaz.
- Redirect takip edilmez; TLS doğrulaması kapatılamaz.
- Ayrıntı: [`read-only-technocore.md`](read-only-technocore.md).
- Otomatik ping, zamanlanmış mesaj veya kendiliğinden oda katılımı **yoktur**.
- **Otomatik testler gerçek Technocore'a yazmaz; lobby hiçbir testte hedef
  olamaz.**

---

## 8. Kabul kriterleri (bu sözleşmeye bağlı)

| ID | Kriter | Aşama | Durum |
|---|---|---|---|
| AC-01 | Aynı seed için DID resmî script ile karakter karakter aynı | 2B | **karşılandı** |
| AC-02 | En az 10.000 Unicode girdide sweep resmî `clean_text` ile aynı | 2B | **karşılandı** (13.616 girdi) |
| AC-03 | Sweep idempotent | 2B | **karşılandı** |
| AC-04 | İmza 86 karakter padding'siz base64url | 2B | **karşılandı** |
| AC-05 | Mesaj ve note imzaları bağımsız doğrulayıcıdan geçer | 2B | **karşılandı** (PyNaCl) |
| AC-13 | POST/GET conformance testinde stored text byte-eşit | 4 |
| AC-15 | Manifest imza alanı değişirse write gate kapanır | 3 | **karşılandı** |
| AC-16 | Kullanıcı onayı olmadan mesaj/note gönderilemez | 4 |
