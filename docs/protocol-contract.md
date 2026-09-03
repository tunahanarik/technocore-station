# Technocore protokol sözleşmesi

> Ana karar kaynağı: [`../Technocore-Station-Proje-Kunyesi.md`](../Technocore-Station-Proje-Kunyesi.md) §14.
> Resmî referans: `flop-labs/technocore-chat` @ `7707cb63ebf638e8ef0cf59d1364818b9fef7d24`
> (bkz. [`../vendor/technocore-reference/PROVENANCE.md`](../vendor/technocore-reference/PROVENANCE.md)).

**Uygulama durumu: canonical/sweep/imza yüzeyi UYGULANDI (Aşama 2B); salt
okunur ağ yolu UYGULANDI (Aşama 3); imzalı **mesaj** yazma lane'i UYGULANDI
(Paket D). Note yazma yolu YOKTUR ve kapsam dışıdır (ADR-0002 §1).**

`technocore-conform` paketi sweep, canonical string, `did:key` ve Ed25519
imzalama/doğrulama sözleşmesini uygular ve pinlenmiş resmî referansa karşı
diferansiyel olarak test edilir. Paket D bu yüzeyin üzerine tek bir yazma
lane'i ekler: `POST /r/{room}`, yalnız kullanıcının ayrı ayrı onayladığı bir
imza ve gönderim ile, her adımda yeniden koşan bir write gate'in arkasında.
Ayrıntı §4'te.

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

### 4.1 Uygulanan mesaj lane'i (Paket D)

| Alan | Değer |
|---|---|
| Method / yol | `POST https://technocore.chat/r/{room}` |
| Gövde alanları | `{did, sig, nonce, text}` — **`from` yoktur** |
| Alan kümesinin kaynağı | `projection.PLANNED_BODY_FIELDS[Lane.MESSAGE_BODY]` |
| Etkin uzunluk sınırı | `projection.effective_payload_limits["text"]` (canlı manifest ∩ künye tavanı) |
| Registry | `technocore/write_targets.py` — salt-okuma kaynak registry'sinden **ayrı** ve kapalı |
| Reddedilen odalar | `lobby`, `meta` (buluşma noktaları; INV-05, ADR-0002 §4.1) |

`from` bilinçli olarak yoktur: referans imzalı lane'de onu yok sayar, yani
imzanın kapsamadığı ve hiçbir şeyin doğrulamadığı bir alan olurdu.

Oda adı çalışma anında doğrulanır: ad resmî `name_pattern`'a uymalı,
buluşma odalarından biri olmamalı ve taşıdığı `<sınıf>-` işaretçilerinin
hepsi bu sürümün tanıdığı sınıflardan olmalıdır. İşaretçiler **canlı
manifest'in** `conventions.room_classes` alanından okunur (tahmin edilmez);
ayrıştırma kuralı referansın kendi algoritmasıdır. Denetim koşmamışsa
işaretçi kümesi boştur ve hiçbir oda çözülmez — kapı zaten kapalıdır.

**Onay zinciri — üç istek, üç ayrı karar (ADR-0002 §2):**

| Adım | İstek | Sunucu ne yapar |
|---|---|---|
| 1 | `POST /api/compose/draft` `{room, text}` | Sweep eder; swept metni, görünmez-karakter farkını, etkin limitleri ve `draft_digest`'i döner. **Nonce ayırmaz, imzalamaz.** |
| 2 | `POST /api/compose/sign` `{draft_id, draft_digest, vault_passphrase?}` | Gate'i yeniden koşar; nonce'u transaction içinde ayırır; canonical'ı kurar; seed'i kısa süre açıp imzalar ve sıfırlar; ürettiği imzayı kendi canonical'ına karşı **gerçekten doğrular**; tek kullanımlık `send_token` üretir |
| 3 | `POST /api/compose/send` `{send_token}` | Gate'i yeniden koşar; token'ı harcar; gövdeyi yeniden doğrular; **bir kez** POST eder |

`send_token` beş şeye bağlıdır — canonical bayt digest'i, oda, ayrılan nonce,
imzalayan DID ve imza anındaki manifest verdict kimliği (ayrıca oturum) —
tek kullanımlıktır ve **180 saniyede** dolar. Write gate üç adımın
**hepsinde** yeniden koşar; UI'nın düğmeyi devre dışı bırakması bir kontrol
değildir.

Sabit imza uzunluğu ön kontrolü gerçek doğrulamanın yerine geçmez: 86
karakterlik, kanonik biçimli fakat geçersiz bir imza ancak Ed25519
doğrulamasıyla yakalanır ve gönderim yolu bu doğrulamayı yapar.

### 4.2 Gönderim sonucu üç durumludur (ADR-0002 §3)

| Sonuç | Koşul |
|---|---|
| `accepted` | 2xx |
| `refused` | **yazmadığı kanıtlanan** yanıtlar: 400, 403, 413, 422 |
| `outcome_unknown` | timeout, bağlantı hatası, bozuk yanıt, 3xx, 429, 5xx |

**Hiçbir durumda otomatik tekrar yoktur.** Salt-okuma istemcisinin üç
denemeli politikası bu yola taşınmaz: tekrarlanan bir yazma, tek onaylı
mesajı birden çok yayımlanmış mesaja çevirir. Ayrılan nonce her üç durumda da
harcanmış sayılır; `outcome_unknown` sonrası yeni gönderim yeni nonce ve
**yeni onay** ister. `outcome_unknown`'dan çıkış odayı okuyarak uzlaştırmayı
gerektirir ve oda okuma yolu bu pakette açılmaz, bu yüzden durum kullanıcıya
olduğu gibi gösterilir; "gönderildi" veya "başarısız" diye sunulamaz.

422 (tekrar filtresi) kullanıcıya "aynı metin yakın zamanda yazılmış" olarak
açıklanır ve **retryable değildir**: aynı baytları yeniden yollamak yine
reddedilir.

### 4.3 Note lane'i kapsam dışıdır

Pinli protokol imzalı note yazmayı yalnız `room-owners` ve `room-allow`
namespace'lerinde kabul eder; künyenin istediği DID profil notu ise
`/kv/did-<xx>/<...>` konvansiyonunda, yani **imzasız** lane'de yayımlanır ve
imza kanıtı üretmez. İmzasız bir yazmayı "gönderildi" rozetiyle sunmak kanıt
seviyelerini karıştırmak olurdu. Gerekçenin tamamı ADR-0002 §1'dedir.

`canonical_note` / `sweep_note_value` kodu conformance testleriyle korunmaya
devam eder; ölü kod değildir, yalnız gönderim yolu yoktur. Bu yokluk
`/api/compose/capability` yanıtında `note_lane_available: false` ve bir
gerekçe cümlesiyle **açıkça** bildirilir.

---

## 5. Nonce

- Mesajlar için `(did, room)` başına **monoton sayaç**.
- Yeni nonce = `max(yerel_son_deger + 1, milisaniye_saati)`.
- Sayaç **imzadan önce transaction içinde ayrılır**.
- Aynı canonical içerik **tekrar gönderilmez**; kullanıcı yeni içerik/nonce
  ile yeniden onaylar.
- Notlar için namespace/key kuralı **runtime manifest'ten** doğrulanır.

### 5.1 Uygulama (Paket D)

Sayaç ayrı bir "son değer" satırı değil, `message_nonce_reservation`
tablosunun kendisidir: sıradaki değer, o `(did, room)` çiftine ait **bütün**
satırların — durumu ne olursa olsun — `MAX(nonce_value)`'ından türetilir.
Rezervasyon ile gönderim arasında ölen bir süreç sayıyı harcanmış bırakır.

- **Başında sıfır olan nonce asla üretilmez.** Değer `int`'ten `str` ile
  üretilir, bu yüzden temsil edilemez. Sunucu nonce'u sayı olarak
  karşılaştırır, imza ise metni kapsar: `"007"` ile `"7"` aynı sayı, farklı
  imzadır (ADR-0002 §4.2).
- **Tavan** `min(10^19 - 1, 2^63 - 1)`'dir — protokolün 19 hanesi ile
  SQLite'ın 64 işaretli biti; düşük olan geçerlidir. Tavana ulaşıldığında
  taşma değil **ret** olur ve satır yazılmaz.
- **Eşzamanlılık** iki katmanla korunur: process kilidi (aynı Station'da iki
  tıklama) ve `UNIQUE(did, room, nonce_value)` (aynı dosyayı açan ikinci bir
  process). Kısıt reddettiğinde sınırlı bir yeniden okuma yapılır; bu
  **yerel** bir çakışma çözümüdür, giden isteğin tekrarı değildir.
- **İptal dolaşıma dönüş değildir.** Verilip bırakılan sayı harcanmıştır;
  yeniden vermek tek nonce altında iki farklı payload imzalamak olurdu.
- Nonce, istek gitmeden **önce** `spent` işaretlenir; crash, öldürülen süreç
  veya kaybolan yanıt sayıyı yeniden kullanılabilir bırakmaz.

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
  olamaz.** Paket D bunu artık mekanik olarak da zorlar: test oturumu boyunca
  gerçek giden HTTP taşıyıcısı devre dışıdır ve mock enjekte etmeyi unutan
  bir test sessizce ağa çıkmak yerine kırılır (ADR-0002 §4.4).

### 7.1 İki istemci, iki politika (Paket D)

Station tam olarak **iki** giden istemci taşır ve ikisi de tek modüldedir:

| Modül | Yön | Politika |
|---|---|---|
| `technocore/client.py` | salt okuma, kapalı belge registry'si | 3 denemeye kadar retry (transport, 5xx, 429), `Retry-After` üst sınırlı |
| `technocore/write_client.py` | imzalı mesaj yazma, kapalı write registry'si | **tek deneme, retry yok, backoff yok, `Retry-After` okunmaz** |

Ayrı modül olmaları kozmetik değildir: hata politikaları zıttır ve
birleştirmek yanlış olanı miras almak demektir. Bir testle hem bu iki
modülün dışında hiçbir yerde HTTP istemcisi import edilmediği, hem de okuma
yolunun yazma istemcisini import edemediği doğrulanır.

---

## 8. Kabul kriterleri (bu sözleşmeye bağlı)

| ID | Kriter | Aşama | Durum |
|---|---|---|---|
| AC-01 | Aynı seed için DID resmî script ile karakter karakter aynı | 2B | **karşılandı** |
| AC-02 | En az 10.000 Unicode girdide sweep resmî `clean_text` ile aynı | 2B | **karşılandı** (13.616 girdi) |
| AC-03 | Sweep idempotent | 2B | **karşılandı** |
| AC-04 | İmza 86 karakter padding'siz base64url | 2B | **karşılandı** |
| AC-05 | Mesaj ve note imzaları bağımsız doğrulayıcıdan geçer | 2B | **karşılandı** (PyNaCl) |
| AC-13 | POST/GET conformance testinde stored text byte-eşit | 4 | **karşılandı** (mesaj lane'i; `test_message_lane_differential.py` — composer'ın ürettiği imza ve gönderdiği gövde pinlenmiş resmî imzalayıcıyla karakter karakter aynı) |
| AC-15 | Manifest imza alanı değişirse write gate kapanır | 3 | **karşılandı** |
| AC-16 | Kullanıcı onayı olmadan mesaj/note gönderilemez | 4 | **karşılandı** (üç adımlı onay zinciri; tüm kapılar açıkken bile onaysız hiçbir yazma süreçten çıkmaz — SI-129) |

AC-14 (gönderim sonrası exact export satırı ve generation) bu pakette
**değildir**; `docs/evidence-model.md` onu Aşama 5'e koyar ve Paket E
karşılar (ADR-0002 §4.3).
