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

**Bu listede olmayan hiçbir yol bu registry'den istenmez.** `/kv/*`,
`/say*`, `/set*` ve `/r/events` kapsam dışıdır. `/rooms` **bu**
registry'nin dışındadır ve Paket H1'de ayrı bir registry'de açılmıştır; bkz.
aşağıdaki tablo.

### `/r/*` cümlesi ne zaman ve neden değişti

Aşama 3'te bu paragraf şöyleydi: *"`/rooms`, `/r/*`, `/kv/*`, `/say*`,
`/set*` ve `/r/events` bu aşamada kapsam dışıdır."* Cümle **sessizce
silinmedi**; iki aşamada iki kez daraltıldı ve ikisi de burada yazılıdır.

| Aşama | Ne değişti | Nerede karar verildi |
|---|---|---|
| Paket D | `POST /r/{room}` **yazma** lane'i açıldı; ayrı bir kapalı registry (`write_targets.py`) ve ayrı bir istemci ile | ADR-0002 §1, §3 |
| Paket E | `GET /r/{room}/export` **kanıt okuma** lane'i açıldı; üçüncü bir kapalı registry (`evidence_targets.py`) ve üçüncü bir istemci ile | ADR-0003 §1 |
| Paket H1 | `GET /rooms` ve `GET /r/{room}` **tarama okuma** lane'leri açıldı; dördüncü bir kapalı registry (`workscan/targets.py`) ve beşinci bir istemci ile. `/r/events` **hâlâ kapsam dışıdır**: openapi girdisi `parameters: null` ve sözleşmesi yalnız düzyazıda | ADR-0007 §3 |

Değişmeyen şey, cümlenin gerçekte koruduğu özelliktir: **bu registry** hâlâ
altı sabit belgedir, hiçbir girdisi oda parametresi taşımaz ve bir test hem
küme eşitliğini hem de `"/r/" not in source.path` iddiasını sabitler. Yani
"salt-okuma izleme yolu bir odayı adresleyemez" hâlâ yapısal bir olgudur;
değişen, o yolun *tek* yol olmaktan çıkmasıdır.

Oda içeriği hâlâ **serbestçe okunmaz**, fakat Paket H1'den sonra bu cümlenin
kapsamı daraldı ve daraldığı yer burada yazılıdır. Kanıt okuması yalnız
kullanıcı isteğiyle, yalnız kendi gönderdiğimiz bir kaydın odası için çalışır,
aynı `DENIED_ROOMS` politikasına tabidir (lobby dâhil) ve akış üstünde 12 MiB
tavanla taranır. Ayrıntı: [`evidence-model.md`](evidence-model.md) §3.

Paket H1'in tarama okuması **hiç yazmadığımız** odaları da okuyabilir, ve bu
yüzden kendi sınırlarını taşır: kapsam **kullanıcının o istekte seçtiği oda
kümesidir** (bütün oda evreni taranmaz, en çok on oda), yalnız açık bir
kullanıcı eylemiyle çalışır (zamanlayıcı, arka plan görevi ve `wait` yoktur),
ve oda adı yine **aynı** `DENIED_ROOMS` politikasından geçer — Station lobby'yi
okumaz da. Okunan içerik seviye 1 değil **seviye 3**'tür (`community`).
Ayrıntı: [`work-scan.md`](work-scan.md).

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

### Anahtar adı yetmez: değeri de okunur

İzin listesi **hangi** anahtarın görünebileceğini düzeltti; ne dediğini
okumadı. Tek anahtarlık on bir mutasyon — her biri Station'ın göndereceği
isteği reddeden bir şema — iki lane'de de `current` raporladı:

- gövde ve koşullu düğümde `type` ile `required` hiç okunmuyordu;
- yalnız `dependentSchemas.did` bakılıyordu, oysa imzalı gövde `sig`, `nonce`
  ve payload alanını da taşır — bunlardan birine bağlı bir koşul da bize
  uygulanır;
- koşullu `properties` içinde yalnız `sig`/`nonce` okunuyordu, orada duran bir
  `did` incelenmiyordu;
- bozuk bir sınır (`"1"`, `null`) **hiç sınır yokmuş gibi** okunuyordu — tahmin
  edilecek en tehlikeli yön.

Kural: izin listesindeki bir anahtarın **değeri denetlenir ve planlanan imzalı
gövde üzerindeki etkisi değerlendirilir.**

| Anahtar | Nerede | Beklenen değer tipi | Nasıl değerlendirilir |
|---|---|---|---|
| `type` | gövde, koşullu düğüm | string | `"object"` olmalı; değilse bizim JSON nesnemiz reddedilir |
| `type` | alan düğümü | string | `"string"` olmalı; Station bu alanları string gönderir |
| `required` | gövde, koşullu düğüm | string listesi | Adların tamamı planlanan gövdede bulunmalı |
| `required` | `anyOf` dalı | string listesi | En az bir dal planlanan gövdeyle sağlanabilmeli |
| `pattern` | alan düğümü | string | Tek kalıp; iki farklı kalıp kesişimi hesaplanmaz → okunamaz |
| `minLength` / `maxLength` | alan düğümü | negatif olmayan tamsayı | Tüm seviyeler birleştirilir; aralık boşsa veya Station'ın gönderdiği uzunluğu dışlıyorsa kapı kapanır |

`bool` uzunluk sayılmaz (Python'da `int` alt sınıfıdır ve `True == 1`).
`null`, `false` ve `0` eksik anahtardan **ayrılır**; JSON'da her biri belirli
bir şey söyler ve hiçbiri "bu anahtar yok" demek değildir.

### Planlanan imzalı gövde

Değerlendirmenin ölçütü belge değil, **bizim göndereceğimiz gövdedir**:

| Lane | Alanlar |
|---|---|
| Mesaj | `did`, `sig`, `nonce`, `text` |
| Note | `did`, `sig`, `nonce`, `value` |

`from` bilinçli olarak yoktur: referans onu imzalı lane'de yok sayar, bu yüzden
Station göndermez ve ona bağlı bir dala güvenemez.

Uzunluklar da kendi sözleşmemizden gelir — `did` tam 56, `sig` tam 86, `nonce`
1–19 basamak. Bir sınır **alışılmadık olduğu için** değil, **bizim
göndereceğimiz her değeri dışladığı için** yanlıştır; bu karşılaştırma
protokolün bizim tarafımızdan bir sayı gerektirir.

### Uygulanan bütün koşullar sayılır

`dependentSchemas` alt şemasını **gövdenin tamamına** uygular. İmzalı gövde üç
kimlik alanını da taşıdığı için bunlardan herhangi birine anahtarlanmış bir
koşul devreye girer. Göndermediğimiz bir ada (`from`) anahtarlanmış koşul ise
bize hiç uygulanmaz ve kapıyı kapatmaz — bunu da bir test sabitler.

### Aşama B kapanışı: değer okumanın son boşlukları

12 yeni sınır türü × 2 lane (24 senaryo) daha önce `current` sızdırıyordu;
hepsi kapatıldı. Kurallar:

- **null ≠ yokluk, şema üyelerinde de.** `properties.text = null`,
  `properties.sig = null`, koşullu `properties.did = null` veya tetiklenen bir
  bağımlılığın içindeki null üye **geçersiz şema üyesidir** → `unavailable`.
  Üyenin tamamen silinmesi ayrı bir durumdur: koşulsuz payload/sig düğümünün
  yokluğu kısıt yayımlamamaktır (zorunlu üyeler ayrıca korunur) ve mesajları
  farklıdır ("null - gecersiz sema uyesi" ile "yok").
- **`required`/`anyOf.required` ad listeleri tekrarsız olmalı.** JSON Schema
  metaşeması tekliği şart koşar; kendi metaşemasını kıran belge "doğru
  okundu" diye sunulmaz → `unavailable`.
- **Pattern değerleri artık derlenir** (`re.compile`, asla uzak girdiyle
  ÇALIŞTIRILMAZ; `MAX_PATTERN_CHARS` üstü değerlendirilmez). Derlenemeyen
  kalıp → `unavailable`. **Payload alanında yayımlanan herhangi bir kalıp**
  da `unavailable`: keyfî bir regex'in keyfî kullanıcı metninden neyi kabul
  ettiğine karar vermiyoruz ve pinli sözleşme orada kalıp yayımlamaz.
- **Kimlik alanlarında SOME-exclusion.** Station'ın meşru gönderdiği
  değerlerin *bir kısmını* dışlamak da reddedilen istektir: nonce 1-19
  basamağın her uzunluğunda gerçekten üretilir (sayaç küçük başlar; ms-saati
  ~13 hane), bu yüzden yayımlanan aralık (1,19)'u **kapsamak** zorundadır —
  kesişmek yetmez. `minLength=5` veya `maxLength=5` → `drifted`. did/sig tek
  uzunluk olduğu için bu kural eski tam-dışlama denetimine indirgenir.
- **Payload sınırları künye §14.4'e göre uyarıdır, kapanma değildir.**
  Yayımlanan `text`/`value` uzunluk sınırı pinli beklentiden farklıysa
  `payload_*_length` UYARI alanları ateşlenir, durum `current` kalır ve
  **etkin limitler** (`ProjectionResult.effective_payload_limits`, kendi
  tavanımızla kırpılmış) composer'ın gerçek istekte uygulayacağı değer olarak
  dışa verilir — "kodda sabit limit yok" ilkesinin makine karşılığı. Dejenere
  yayın (boş aralık) yine `drifted`.

### Bozuk şema neden `unavailable`

Önceki sürümde koşullu `sig.maxLength = "86"` **`drifted`** sayılıyordu. Artık
`unavailable`. Gerekçe: bir string, uzunluk sınırı değildir. Bu **okunabilir
bir sözleşme farkı değil, bozuk bir şemadır**; "sunucu uzunluğu string-86
yaptı" demek, elimizde olmayan bir kanıtı iddia etmek olur. Kapı her iki
sınıflandırmada da kapalıdır; değişen yalnız kullanıcının okuduğu cümledir.

Ayrım kısaca: **`drifted`** = şema iyi biçimli, okunabilir ve bizi reddediyor;
**`unavailable`** = şema bozuk veya desteklenen biçimin dışında, yani
değerlendirilemedi.

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

> **26 sayısı neyi kanıtlar?** Yalnız şunu: bu projeksiyonun okuduğu 26 kritik
> alanın tamamı beklenen değeriyle eşleşti ve gövde şemasının desteklenen
> biçimi içinde bizi reddeden bir kural bulunmadı. **JSON Schema
> sözleşmesinin tamamının doğrulandığı anlamına gelmez.** Değerlendirici
> bilinçli olarak dardır: regex kesişimi, sayısal aralık dışındaki genel
> çelişkiler ve desteklenen biçimin dışındaki bileşik şemalar hesaplanmaz —
> okunamaz sayılıp kapı kapatılır. Canlı `current` tek başına
> değerlendiricinin sağlamlığının kanıtı değildir.

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

Bu liste **Aşama 3'ün** kararlarıdır ve tarihî kayıt olarak durur. Sonraki
paketler ilk iki maddeyi (Paket D), beşinci maddeyi (Paket E, ayrıca
`/r/{room}/export` kanıt okuması) ve **dördüncü maddeyi** (Paket H1: oda,
topic ve mesaj içeriği okuma) bilinçli olarak açtı; §3'teki tabloya bakınız.
Dördüncü maddenin açılması **serbest** oda okuması değildir: kapsam
kullanıcının seçtiği oda kümesidir, `DENIED_ROOMS` geçerlidir ve polling
yoktur (ADR-0007 §3, §4). Lobby'ye katılım, note lane'i, LLM ve Agent Runtime
hâlâ kapsam dışıdır.
