# Salt okunur Technocore — Aşama 3

> Ana karar kaynağı: [`../Technocore-Station-Proje-Kunyesi.md`](../Technocore-Station-Proje-Kunyesi.md) §14.4, §16, §21.
> Sözleşme: [`protocol-contract.md`](protocol-contract.md) · Uygunluk: [`conformance.md`](conformance.md).
> Canlı origin: `https://technocore.chat` · Pinlenmiş referans: `7707cb63…`.

**Uygulama durumu: UYGULANDI (Aşama 3).** Station resmî kaynakları **yalnız
okur**. Bu aşamada hiçbir yazma yolu, imzalama endpoint'i, nonce rezervasyonu
veya gönderim yüzeyi yoktur.

---

## 1. En önemli iki cümle

> **Uygunluk** self-test'i bu yapının **pinlenmiş referans commit** ile aynı
> davrandığını gösterir.
> **Güncellik** denetimi **canlı sunucunun** hâlâ o protokolü yayımladığını
> gösterir.

Bunlar ayrı kontrollerdir ve ayrı kalır. Bir yapı, sunucunun çoktan terk
ettiği bir referansla kusursuz uyumlu olabilir — write gate'in yakalamak için
var olduğu durum tam olarak budur.

---

## 2. "GET güvenlidir" varsayımı neden yapılmadı

Technocore **GET üzerinden yazma** yapar:

```
GET /r/{room}/say-signed/{did}/{sig}/{nonce}/{text}
GET /kv/{ns}/{key}/set/{value}
```

Bu yüzden "yalnız GET gönderiyoruz" bir güvenlik özelliği **değildir**.
Güvenlik özelliği kapalı kaynak registry'sidir: istemci `SourceId` alır, URL
almaz. Kullanıcı girdisinden, request gövdesinden veya bir veritabanı
satırından giden adrese ulaşan hiçbir kod yolu yoktur.

---

## 3. İzin verilen kaynaklar

| Kaynak | Yol | Otorite | Verdict için zorunlu | Neden okunuyor |
|---|---|---:|:---:|---|
| `agent_manifest` | `/.well-known/agent.json` | 1 | **evet** | İmza payload biçimleri, imza kodlaması, nonce kuralı, isim kalıbı |
| `openapi` | `/openapi.json` | 1 | **evet** | İmzalı lane'ler, method/path, did/sig/nonce kalıp ve uzunlukları |
| `config` | `/config` | 1 | hayır | Kapasite ve rate değerleri; imza sözleşmesi taşımaz |
| `health` | `/healthz` | 1 | hayır | Canlılık; protokol sözleşmesi taşımaz |
| `manual` | `/llms.txt` | 2 | hayır | Prose; kanıt ve uyarı |
| `skill` | `/skill.md` | 2 | hayır | Prose; kanıt ve uyarı |

**Bu listede olmayan hiçbir yol istenmez.** `/rooms`, `/r/*`, `/kv/*`,
`/say*`, `/set*` ve `/r/events` bu aşamada kapsam dışıdır; oda, topic, mesaj
veya note içeriği **alınmaz**.

### Zorunlu / tamamlayıcı ayrımı neden var

Canlı gözlem: `/healthz` ve `/config` **aralıklı 503** dönüyor (aynı dakika
içinde hem 200 hem 503 gözlendi). Bu iki belge protokol sözleşmesi taşımaz.
Verdict'i onlara bağlamak, altyapı hıçkırığında write gate'in titremesi
demek olurdu. Bu yüzden verdict yalnız `openapi` ve `agent.json`'a dayanır;
diğerlerinin başarısızlığı kaydedilir ve kullanıcıya **gösterilir**, fakat
kapıyı belirlemez.

---

## 4. Ağ güvenliği

| Kural | Uygulama |
|---|---|
| Origin | Yalnız `https://technocore.chat` |
| Şema / host / port | HTTPS, tam eşleşme, yalnız varsayılan 443 |
| Reddedilenler | Alt domain, trailing dot, userinfo, fragment, farklı port, IP, path traversal |
| Redirect | **Takip edilmez**; 3xx bir hatadır |
| TLS | Doğrulama kapatılamaz; `verify` hiçbir yerde geçirilmez |
| Timeout | connect/read/write/pool ayrı ayrı sınırlı |
| Boyut | **Decompress edilmiş** bayt üzerinde, kaynak başına tavan |
| Retry | En çok 3 deneme; `Retry-After` üst sınırla |
| Kimlik | Cookie, authorization, DID, fingerprint, CSRF **yok** |
| User-Agent | Sabit; makine veya kullanıcı bilgisi içermez |
| Saklanan header | Yalnız `Content-Type`, `ETag`, `Last-Modified` |

---

## 5. Kritik protokol projeksiyonu

Ham hash karşılaştırması kullanılmaz: her yazım düzeltmesi "drift" derdi ve
bir hafta içinde göz ardı edilirdi. Bunun yerine **imzanın geçerliliğinin
bağlı olduğu** makine-okunabilir alanlar karşılaştırılır.

### İmzalı lane nerede yayımlanıyor (Aşama 3.1 düzeltmesi)

Aşama 3 `sig` ve `nonce` kısıtlarını `schema.properties` altında aradı.
Resmî referans onları orada yayımlamaz. Gerçek konum:

```jsonc
schema: {
  "properties": {
    "did":   { "type": "string", "pattern": "^did:key:z6Mk…$", "maxLength": 56 },
    "sig":   { "description": "…" },          // yalnız açıklama, kısıt yok
    "nonce": { "description": "…" }           // yalnız açıklama, kısıt yok
  },
  "required": ["text"],                        // sig/nonce burada yok
  "dependentSchemas": {
    "did": {                                   // DID varsa uygulanır
      "required": ["sig", "nonce"],
      "properties": {
        "sig":   { "type": "string", "pattern": "^[A-Za-z0-9_-]{85}[AQgw]$",
                   "minLength": 86, "maxLength": 86 },
        "nonce": { "type": "string", "pattern": "^[0-9]{1,19}$" }
      }
    }
  }
}
```

Referansın kendi gerekçesi: DID taşımayan bir gövde imzasız bir yazmadır ve
üzerindeki `sig`/`nonce` doğrulanmaz, yok sayılır. Kalıpları koşulsuz
yayımlamak, hiçbir şeyin zorlamadığı bir kısıtı belgelemek olurdu.

Sonuç: eski projeksiyon dört kritik alanı `<yok>` olarak gördü ve **yanlış
bir drift alarmı** üretti. Alanlar kaybolmamıştı; yanlış yerde aranıyordu.

Projeksiyon **DID ile seçilen effective schema**'yı çözer.

### Doğru değeri bulmak, şemanın isteği kabul ettiğini göstermez

İlk düzeltme reddettiği anahtarları saydı (`$ref`, `allOf`, `not`, …) ve
geri kalanından istediği alanları okudu. Bu ters bir yaklaşımdı: her imzalı
isteği reddeden üç ayrı belge `current` raporladı.

| Belge | Neden her imzayı reddeder | Eski sonuç |
|---|---|---|
| `sig` alan düğümünde `not: {}` | Boş şemanın değili — hiçbir değer eşleşmez | `current` |
| Koşulsuz `properties.sig.maxLength: 1` | Koşullu `minLength: 86` ile birlikte uygulanır; hiçbir string ikisini birden sağlayamaz | `current` |
| `anyOf: [{"not": {"required": ["did"]}}]` | İmzalı lane'i seçen alanı yasaklar | `current` |

Ortak hata: **kalıbın bir köşede doğru olması, şemanın isteğimizi kabul
ettiğini kanıtlamaz.** JSON Schema'da aynı seviyedeki anahtarlar "ve" ile
bağlanır; okunmayan bir anahtar yok sayılmış olmaz, yalnız görülmemiş olur.

### Bu yüzden listeler artık **izin listesi**

Adı geçmeyen bir anahtar yok sayılmaz — şemayı **değerlendirilemez** yapar ve
kapı kapanır. Bu bir JSON Schema motoru değildir ve olmaya çalışmaz; okuyabildiği
biçimlerin açık beyanıdır.

| Düğüm | Anlaşılan anahtarlar |
|---|---|
| İstek gövdesi | `type`, `properties`, `required`, `anyOf`, `dependentSchemas` |
| `dependentSchemas.did` | `type`, `properties`, `required` |
| Alan düğümü (`sig`, `nonce`, `did`) | `type`, `pattern`, `minLength`, `maxLength` |
| `anyOf` dalı | `required` |

Ayrıca **yalnız açıklama olan** anahtarlar (`description`, `title`,
`$comment`, `example`, `examples`, `default`, `deprecated`, `readOnly`,
`writeOnly`) hiçbir zaman kısıt sayılmaz ve hiçbir zaman protokol alarmı
üretmez. Sabit anahtar listesi kullanan bir denetimde bu ayrımı yapmamak, her
metin düzeltmesinde yazma kapısını kapatmak demek olurdu.

### İki seviye birlikte uygulanır

`properties.sig` ile `dependentSchemas.did.properties.sig` aynı değeri
kısıtlar; ikisi de geçerlidir. Referans birincisini yalnız `description` ile
yayımlar, yani normalde uzlaştıracak bir şey yoktur. Bir kısıt gerçekten
varsa:

- **birebir aynı** kısıt tekrarı kabul edilir;
- **uzunluk sınırları** birleştirilir ve aralık boşsa (`en az 86`, `en fazla 1`)
  bu **kanıtlanmış bir çelişkidir** → `mismatch`;
- **farklı `type`** aynı anda sağlanamaz → `mismatch`;
- **farklı `pattern`** iki regex'in kesişimi demektir, bu modül onu hesaplamaz
  → `unsupported`.

### `anyOf` gerekçesi düzeltildi

Eski gerekçe "`anyOf` yalnız kısıt ekleyebilir, gevşetemez" idi. Doğru — ve
konu dışı: **eklediği kısıt bizi reddedebilir.** Referansın gerçekte
yayımladığı biçim şudur ve bir test bunu sabitler:

```json
"anyOf": [{"required": ["from"]}, {"required": ["did"]}]
```

Yani "ya kendine bir ad ver ya da imzala". Station imzalı dalı kullanır.
Kabul edilen tek şekil budur: her dal yalnız `required` taşımalı ve **en az
bir dal** imzalı gövdenin taşıdığı alanlarla (`did`, `sig`, `nonce` ve lane'in
`text`/`value` alanı) sağlanabilmelidir. Bir dal farklı bir biçimdeyse, adı
`anyOf` olduğu için kabul edilmez — okunamaz sayılır ve kapı kapanır. Hiçbir
dal sağlanamıyorsa bu değerlendirilmiş bir olgudur → `mismatch`.

### `mismatch` mi `unsupported` mu

Karar tek bir soruya bağlıdır: **iddiayı kanıtladık mı?**

- **`mismatch`** — şema okundu ve sağlanamayacağı *gösterildi*. Boş uzunluk
  aralığı, çelişen tip, hiçbir dalı sağlanamayan `anyOf`. Belge hakkında
  gerçek bir bulgudur.
- **`unsupported`** — şemanın bir parçası okunamadı. Bu bir bilgi eksikliğidir,
  sunucu hakkında bir iddia değildir; kullanıcı "protokol uyumu doğrulanamadı"
  görür.

İkisi de kapıyı kapatır. Ayrım, kullanıcının okuduğu cümlenin doğru olması
içindir — bu modülün bir kez yeniden yazılmasının sebebi tam olarak buydu.

### Kritik (kapıyı kapatır)

Her iki lane (mesaj ve note) için ayrı ayrı denetlenir. Konumlar JSON Pointer
olarak, gövde şeması kökünden sonrası:

| Alan | Kaynak | Konum |
|---|---|---|
| İmzalı mesaj lane'i | openapi | `/paths/~1r~1{room}/post` |
| İmzalı note lane'i | openapi | `/paths/~1kv~1{ns}~1{key}/post` |
| DID kalıbı | openapi | `/properties/did/pattern` |
| DID uzunluğu | openapi | `/properties/did/maxLength` (sayı) |
| İmza alan tipi | openapi | `/dependentSchemas/did/properties/sig/type` |
| İmza kalıbı | openapi | `/dependentSchemas/did/properties/sig/pattern` |
| İmza min/max uzunluk | openapi | `…/sig/minLength`, `…/sig/maxLength` (sayı) |
| Nonce alan tipi | openapi | `/dependentSchemas/did/properties/nonce/type` |
| Nonce kalıbı | openapi | `/dependentSchemas/did/properties/nonce/pattern` |
| Zorunlu imza alanları | openapi | `/dependentSchemas/did/required` = `sig`, `nonce` |
| Mesaj canonical biçimi | agent.json | `/identity/message_signature_payload` |
| Note canonical biçimi | agent.json | `/identity/note_signature_payload` |
| İmza kodlaması açıklaması | agent.json | `/identity/signature_encoding` |
| Kimlik şeması / algoritma | agent.json | `/identity/scheme`, `/identity/algorithms` |
| İsim kalıbı | agent.json | `/conventions/name_pattern` |

**Zorunluluk `properties` üyeliğinden çıkarılmaz.** İki adın `properties`
altında görünmesi onların zorunlu olduğunu kanıtlamaz; koşullu `required`
ayrıca okunur.

**Kritiklik gerekçesi:** bu alanlardan biri değişirse Station'ın ürettiği bir
imza sunucu tarafından reddedilebilir veya — daha kötüsü — kullanıcının
onaylamadığı baytlar üzerinde kabul edilebilir.

### Beklenen değerler nereden geliyor

Canlıdan **kopyalanmaz**; kopyalansaydı denetim kendini doğrular ve hiçbir
şey tespit etmezdi. Kalıplar `technocore_conform` — yani gerçekte imzalayan
motor — üzerinden türetilir:

| Beklenen | Kaynak |
|---|---|
| `^[A-Za-z0-9_-]{85}[AQgw]$` | `SIGNATURE_PATTERN` |
| `^[0-9]{1,19}$` | `NONCE_PATTERN` |
| `^[a-z0-9][a-z0-9_-]{0,47}$` | `NAME_PATTERN` |
| `86` | `SIGNATURE_CHARS` |
| `56` | `len(DID_KEY_PREFIX) + MULTIBASE_LENGTH` |
| `4096` / `8192` | `MAX_MESSAGE_CHARS` / `MAX_NOTE_VALUE_CHARS` |

Aşama 3'ün beklediği `^[A-Za-z0-9_-]{86}$` **fazla genişti**: 64 baytlık bir
imzanın son karakterinde dört boş bit kalır ve bunlar her zaman sıfırdır, yani
yalnız `A`, `Q`, `g`, `w` ile bitebilir. Geniş kalıp, üretmediğimiz imzaları da
kabul eden bir sözleşmeyi doğru sayardı. Bu, kendi
`technocore_conform.signature.SIGNATURE_PATTERN` değerimizle de çelişiyordu.

### Uyarı (kapıyı kapatmaz)

`limits.message_chars`, `limits.note_chars`, `version`. Künye §14.4 gereği
limit/kapasite değişikliği **uyarı** üretir; imzayı geçersiz kılmaz.

`version` beklentisi pinlenmiş referansın sürümüdür (`0.10.0`). Daha yeni bir
servis tek başına drift değildir. Beklenen sürüm **uyarıyı susturmak için
güncellenmez**; bu uyarı, pinin geride kaldığını gösteren tek sinyaldir.

### Karşılaştırma biçimleri

Karşılaştırma **özgün, tipi doğrulanmış değer** üzerinde yapılır.
`safe_display` yalnız gösterim içindir; onun çıktısını karşılaştırmak
`"<room>|<nonce>|<text>
"` ile canonical biçimi eşit sayardı.

| Mod | Anlamı |
|---|---|
| `text` | Tam string eşitliği. Sweep yok, strip yok. |
| `number` | Tam tamsayı eşitliği. `"86"` ≠ `86`; `bool` açıkça reddedilir (`True == 1`). |
| `member` | String listesinde üyelik (`Ed25519`). |
| `name_set` | String listesi kümesi eşitliği (koşullu `required`). |
| `prose` | Sınırlı açıklama denetimi (aşağıda). |

### `signature_encoding` neden kelime aramasından fazlası

Eski denetim yalnız `base64url`, `86` ve `unpadded` kelimelerinin geçip
geçmediğine bakıyordu. Bu, sözleşmeyi **reddeden** bir cümlenin — "86
characters, but no longer unpadded" — reddettiği kelimeleri taşıdığı için
geçmesi demekti.

Asıl dayanak **makine şemasıdır**: `sig.pattern` ile `minLength`/`maxLength`
zaten "base64url, 86 karakter, padding'siz, kanonik" demektir. Prose alanı
onu *doğrular*, yerine geçmez. Kural iki parçalı ve kapalıdır:

1. Makine token'larının hepsi tam kelime olarak bulunmalı.
2. Kapalı bir olumsuzlama listesinden hiçbiri geçmemeli:
   `not`, `never`, `no longer`, `instead`, `deprecated`, `obsolete`,
   `removed`, `padded`.

Liste kısa ve kanıta dayalıdır. Gerçek referans metni "Re-encode the raw
signature **rather than** editing its tail" der, bu yüzden `rather than`
işaretçi değildir; `no` ve `without` da değildir, çünkü "no padding"
`unpadded` demenin geçerli bir yoludur. `padded` kelime sınırıyla aranır ve
`unpadded` böyle bir sınır oluşturmaz. Bir test bunu gerçek metne karşı
sabitler.

`MAX_PROSE_CHARS` (2000) üzerindeki bir açıklama **yargılanmaz**: taranan
sınırın ötesinde bir olumsuzlama durabilir, ve tahmin etmek susmaktan
kötüdür.

### Alan yolları JSON Pointer segmentleridir

Eski okuyucu noktalı bir yolu bölüp mevcut anahtarların en uzun eşleşmesini
alıyordu. Uzaktaki bir belge, yola benzeyen düz bir anahtar
(`"paths./r/{room}.post.requestBody"`) yayımlayarak gerçek konumu
**gölgeleyebilirdi**. Yol artık segment segment yürütülür; gölge anahtar
basitçe yok sayılır ve bir test bunu doğrular. Genel amaçlı bir
schema/regex motoru eklenmedi.

Alan sırası ve dokümantasyon değişiklikleri **drift sayılmaz**; bir test bunu
sabitler.

---

## 6. Durumlar ve fail-closed kuralı

| Durum | Anlamı | Gate |
|---|---|---|
| `never_checked` | Bu process'te henüz denetim yapılmadı | kapalı |
| `current` | Kritik alanların tamamı bekleneni karşılıyor | manifest yarısı açık |
| `drifted` | En az bir kritik alan **okundu ve farklı** | kapalı |
| `unavailable` | Zorunlu bir belge alınamadı/okunamadı **veya** kritik bir alan değerlendirilemedi | kapalı |

**Yokluk ile farklılık aynı şey değildir.** Belgede bulunamayan bir alan ve
okunamayan bir şema biçimi `drifted` değil `unavailable` üretir. İkisi de
kapıyı kapatır — güvenlik özelliği budur — fakat kullanıcının okuduğu gerekçe
"protokol uyumu doğrulanamadı" olur, sunucunun ne yaptığına dair bir iddia
değil. Yanlış yere bakan bir aramaya dayanarak "sunucu imza biçimini
değiştirdi" demek, bu modülü ilk seferinde yanlış yapan hatanın ta kendisiydi.

Gerçek bir fark, değerlendirilemeyen bir alana **baskın gelir**: okunabilir
bir değişiklik daha belirgin ve daha yararlı cevaptır.

- **Her açılışta `never_checked`.** Uygulama açılışta hiçbir ağ isteği atmaz.
- Verdict **process içinde** yaşar. Veritabanındaki snapshot geçmişi
  kanıttır; eski bir kayıt kapıyı **açamaz**.
- Ağ/TLS/timeout/parse hatası `unavailable` üretir.
- Başarılı eski bir kontrol yeni başarısız kontrolü **örtmez**; yalnız "son
  başarılı kontrol" zaman damgası, başarısızlığın *yanında* gösterilir.
- Gate'i açan env değişkeni, debug bayrağı veya kullanıcı override'ı **yoktur**.
- API ve WriteGate **aynı verdict nesnesini** okur.

---

## 7. Snapshot ve veri modeli

İki tablo (migration `0003`):

- `manifest_check` — bir denetim koşusu: `state`, sayılar, gerekçeler, UTC
  zaman damgaları.
- `official_source_snapshot` — koşu başına kaynak başına bir satır: sabit
  kaynak kimliği, önceden tanımlı URL, authority, `fetched_at`, HTTP durumu,
  allow-list'li `Content-Type`/`ETag`/`Last-Modified`, **exact response
  baytlarının SHA-256'sı**, sınırlandırılmış ve sweep edilmiş alıntı, sonuç ve
  gerekçe.

- Keyfi header, cookie, seed, private key, parola veya vault yolu **yoktur**.
- Yazma tek transaction'dır; yarım kayıt bırakılmaz.
- Retention: son **50** koşu tutulur, eskiler snapshot'larıyla birlikte
  silinir.
- Raw gövde **API'den dönmez**.

---

## 8. Yerel API

| Yol | Method | Koruma | Ne yapar |
|---|---|---|---|
| `/api/technocore/status` | GET | session | Mevcut verdict'i okur; **ağa çıkmaz** |
| `/api/technocore/refresh` | POST | session + CSRF | Sabit registry'yi çalıştırır |

Refresh **gövde almaz**: verilecek bir URL, host, path veya method yoktur.

---

## 9. Test referansı ve canlı gözlem — ayrı tutulur

### Referans belgeleri üretilir, yazılmaz

Aşama 3'ün fixture'ı canlı servisten okunarak **elle yazılmıştı** ve imzalı
lane'i yanlış konuma koyuyordu. Fixture ile projeksiyon aynı hatayı taşıdığı
için birbirlerini doğruluyorlardı.

Artık `tests/security/technocore_reference/` altındaki iki belge, pinlenmiş
resmî üretici (`vendor/technocore-reference/src/manifest.py`) çalıştırılarak
**üretilir**. `tests/conformance/test_manifest_oracle.py` belgeleri yeniden
üretir ve **bayt bayt** karşılaştırır; saklanan kopyayı elle düzenlemek testi
kırar.

| | |
|---|---|
| Pin | `7707cb63ebf638e8ef0cf59d1364818b9fef7d24` (**değişmedi**) |
| Üretilen sürüm | `0.10.0` (pinlenmiş `pyproject.toml`'dan okunur) |
| `openapi.json` | 85536 bayt, `8c008762ee6c4b65…` |
| `agent.json` | 6588 bayt, `282d74ef289461cb…` |

Tam provenance — üretme komutu, SHA-256'lar ve projeksiyonun okuduğu bütün
JSON yolları — `tests/security/technocore_reference/PROVENANCE.md` içindedir.

`manifest.py` içe aktarma zincirinde `orjson` ve POSIX'e özgü `fcntl` vardır.
İkisi de yalnız `store.py`'nin çalışma zamanı kalıcılık yollarında kullanılır
ve belge üretimi bu yolları çağırmaz; bu yüzden yalnız `import` ifadesini
karşılayan iki asgari shim kullanılır. Çalışan kod pinlenmiş baytlardır.

**Testler ağa çıkmaz** (INV-05). Bu belgeler pinlenmiş sürümün belgeleridir,
canlı servisin değil.

### Canlı gözlem — 1 Eylül 2026

Aşama 3.1 doğrulaması, gerçek istemciyle, geçici veri dizininde, yalnız izin
verilen altı belge üzerinde çalıştırıldı. UTC 18:29:40–18:29:47.

| Belge | HTTP | SHA-256 (12) | Bayt |
|---|---|---|---|
| `/.well-known/agent.json` | 200 | `fc907a62284a` | 6411 |
| `/openapi.json` | 200 | `aec05fab20be` | 73391 |
| `/config` | 200 | `4fd0a99a7d7d` | 4288 |
| `/healthz` | 503 | — | 0 |
| `/llms.txt` | 200 | `22eb92a9567d` | 23294 |
| `/skill.md` | 200 | `abcc8f85e5cc` | 6193 |

**Sonuç:** `current`, 26/26 kritik alan eşleşti, 0 değerlendirilemeyen alan,
**1 uyarı** — `service_version`: beklenen `0.10.0`, görülen `0.11.2`.

Notlar:

- Canlı servis (`0.11.2`) ile pin (`0.10.0`) **bütün protokol-kritik
  alanlarda aynıdır**; tek fark sürüm numarasıdır. Bu, uyarı olarak durur.
- `/healthz` aralıklı 503 döndürmektedir. Tamamlayıcı bir kaynaktır ve
  protokol sözleşmesi taşımaz, bu yüzden verdict'i belirlemez — zorunlu/
  tamamlayıcı ayrımının var olma sebebi tam olarak budur. Aynı gözlemde
  `agent.json` da bir denemede 503 döndü ve tekrar denemede 200 verdi.
- Bilinen pin ile canlı gözlem birbirine karıştırılmaz: testler pinlenmiş
  belgeleri kullanır, yukarıdaki tablo yalnız tarihli bir tanı kaydıdır.

### Aşama 3 raporunun düzeltilmesi

Aşama 3 raporu canlı denetim için **"current, 15/15 kritik alan eşleşti, 0
uyarı"** demişti. Bu sonuç yeniden üretilemiyor ve doğru değildi.

Aşama 3 kodunu 1 Eylül 2026 tarihli gerçek canlı gövdelerle çalıştırmak
şunu verir: **`drifted`, 4 kritik uyuşmazlık** (`signature_pattern`,
`signature_length`, `nonce_pattern`, `note_signature_pattern` — hepsi
`<yok>`, çünkü `properties` altında aranıyorlardı) **ve 1 uyarı**
(`service_version`). Eski kod, `properties.sig.pattern` var olmadığı için
canlı belgede hiçbir zaman `current` üretemezdi.

O rapordaki iddiayı destekleyen bir kanıt bulunamadı ve burada açıkça
düzeltilmiştir.

---

## 10. Bu aşamada bilinçli olarak yapılmayanlar

- Mesaj/note gönderme, imzalama endpoint'i, nonce rezervasyonu (Aşama 4).
- Compose yüzeyine textarea, imzala veya gönder düğmesi (Aşama 4).
- Lobby veya herhangi bir odaya katılım.
- Oda/topic/mesaj/note içeriği okuma.
- Evidence HMAC zinciri (Aşama 5).
- LLM veya Agent Runtime.
