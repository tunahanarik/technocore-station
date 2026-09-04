# OpenCode Go bağlantısı (Paket G)

> Kapsam kararları: [`decisions/0005-paket-g-kapsam-kararlari-2026-09-04.md`](decisions/0005-paket-g-kapsam-kararlari-2026-09-04.md)
> — **bağlayıcıdır**. Bu belge o kararların **uygulanmış** hâlini tarif eder.

Bu paket uygulamanın **dördüncü giden yüzeyini** açar ve bunu yapan ilk
yüzey, **bir kimlik bilgisi taşıyan** ilk yüzeydir. Üç Technocore istemcisinin
hiçbiri `Authorization` göndermez; bu gönderir. Değişen tek şey bu değildir:
farklı origin, farklı registry, farklı başarısızlık politikası ve —
diğerlerinde hiç olmayan — **ücretlenebilir bir istek** vardır.

Paketin en önemli çıktısı bir özellik değil, bir **dürüstlük hattıdır**:
resmî belgede doğrulanmış olan ile doğrulanmamış olan kodda birbirinden
ayrılır ve ayrım kullanıcıya kadar taşınır.

---

## 1. Doğrulanan ve doğrulanamayan sözleşme

ADR-0005 §1 doğrulamanın kaydıdır. Kod bu ayrımı üç yerde taşır:
`registry.py`'nin modül docstring'i, `MODEL_MAPPINGS` tablosunun
`protocol_verification` alanı ve `client.py`'deki tek `Authorization` satırı.

### Doğrulandı

| Konu | Nerede yaşıyor |
|---|---|
| Üç protokol yolu ve katalog yolu | `registry.ENDPOINTS` (dört sabit adres) |
| Base URL `https://opencode.ai/zen/go/v1` | `registry.OPENCODE_ORIGIN` + `ZEN_GO_BASE_PATH` |
| Katalog **anahtarsız** yanıt veriyor | `ENDPOINTS[MODELS].requires_key = False` |
| Katalog yalnız `{id, object, created, owned_by}` taşıyor | `catalog.CatalogEntry` — dört alan, beşincisi yok |
| `opencode-go/<id>` bir **provider önekidir** | `registry.wire_model_id()`, testle sabit |
| **Model → protokol eşlemesi (27 satır)** | `registry.MODEL_MAPPINGS` — "Endpoints" tablosunun transkripsiyonu, her satır `documented` |
| **Model başına veri saklama koşulu** | `ModelMapping.retention` + `training_use`, yanında `privacy_source` ve `privacy_read_on` |
| Kullanım limitleri (5sa $12 / hafta $30 / ay $60) | `quota.PUBLISHED_LIMITS` |
| "Use balance" tercihi **sağlayıcı konsolunda** | `quota.USE_BALANCE_STATEMENT` |
| `x-opencode-session` gönderilmeli | `client.SESSION_HEADER_NAME` |

### Doğrulanamadı — ve kodda nasıl işaretlendi

Bu paketin ayırt edici kısmı budur. Doğrulanamayan her parça **sessizce
varsayılmadı**; her biri için kodda bir işaret var ve işaretin çoğu
kullanıcıya kadar gidiyor.

| Doğrulanamayan | Koddaki işaret | Kullanıcıya gider mi |
|---|---|---|
| Auth header'ının adı/formatı | `client.AUTH_HEADER_NAME` üzerinde büyük harflerle `NOT VERIFIED IN THE OFFICIAL DOCUMENTATION`; tek yerde tanımlı ve bir test başka hiçbir modülde `Authorization`/`Bearer ` **string sabiti** olmadığını doğrular | **Evet** — `auth_header_caveat` alanı |
| Katalogda olup **tabloda olmayan** modelin protokol ailesi | `MappingVerification.UNVERIFIED`; `ModelMapping.selectable` bundan **türetilir**, ayrı bir bayrak değildir | **Evet** — her modelin `reason` alanı |
| Üç ailenin gövde şekli | `adapters.SHAPE_PROVENANCE`: "üst protokol ailelerinin bilinen non-streaming biçimi, fixture'a karşı doğrulandı" | **Evet** — `protocol_context.shape_provenance` |
| Streaming ve tool-call biçimi | `events.STREAMING_SUPPORTED = False`, `TOOL_CALLS_SUPPORTED = False`, `DEFERRAL_SENTENCE` | **Evet** — `protocol_context` |
| Hata gövdelerinin şekli | `FailureKind.PROVIDER_ERROR` — "görebildiğimiz ama sınıflandırdığımızı iddia etmediğimiz hata" kovası | **Evet** — `failure.detail` |
| **Eşlemesiz** modellerin veri saklama koşulu | `TrainingUse.UNKNOWN`; `requires_training_acknowledgement` `UNKNOWN`'da da `True` | **Evet** — `retention`, `training_use` |

### Düzeltilen bir yanlış iddia

Bu bölümün ilk yazımı şunu söylüyordu:

> "Bu sürümde hiçbir model seçilebilir değildir… belge hangi modelin hangi
> aileye ait olduğunu söylemiyor."

**Yanlıştı.** `opencode.ai/docs/go` sayfasının "Endpoints" tablosunun
sütunları `Model | Model ID | Endpoint | AI SDK Package` ve **27 satırın
hepsinde `Endpoint` yazılı**. Üstelik o hâldeki tabloda `grok-4.6`
`chat/completions` diye kayıtlıydı; belge `responses` diyor — yani eşleme
yalnız "işaretlenmemiş" değil, **yanlış**tı.

Cümle burada kayda geçiyor, sessizce silinmiyor, çünkü asıl ders arızanın
biçiminde: *ihtiyatlı görünen* bir "doğrulayamadık" ifadesi, kaynak
söylüyorken yanlıştır ve bu kez **özelliği kapatmıştı** —
`selectable_model_ids()` boş küme dönüyordu, hiçbir model seçilemiyordu ve
bağlantı, promptun §11'de yasakladığı "göstermelik API kutusu" hâline
düşmüştü. Yanlış yönde başarısız olan bir ihtiyat, ihtiyat değildir.

### Bugünkü hâli

**27 satırın tamamı `documented`** ve seçilebilir:

| Aile | Uç nokta | Model sayısı |
|---|---|---|
| `responses` (`@ai-sdk/openai`) | `…/zen/go/v1/responses` | 4 |
| `messages` (`@ai-sdk/anthropic`) | `…/zen/go/v1/messages` | 8 |
| `chat/completions` (`@ai-sdk/openai-compatible`) | `…/zen/go/v1/chat/completions` | 15 |

Tablo **4 Eylül 2026'da** okundu; kaynak sayfanın o günkü altbilgisi
`Sep 3, 2026` diyordu. O okumada canlı katalog **34** kimlik döndürdü ve
aradaki **7 fazlalık** tabloda yoktu: `unverified` kalır, **listelenir ama
seçilemez**, nedeni kullanıcıya gider ve tahmin edilmez. `selectable_count`,
`model_count`'tan ayrı bir alan olarak döner; "listeleniyor" ile
"adreslenebiliyor" iki ayrı sayıdır.

### Tablonun bayatlaması, ve neden artık görünür

Bağımsız bir inceleme sayfayı **yeniden okudu**: sayfa `omen-alpha →
chat/completions` satırını kazanmıştı ve canlı katalog **35** kimlik
döndürüyordu — fazlalık 7 değil **8**. Bu bir transkripsiyon hatası değil,
**sürüklenme**dir: kod `DOC_LAST_UPDATED = "2026-09-03"` pinliyor, sayfa ise
ilerlemiş. İki sonucu vardı ve ikisi de kapatıldı.

**1. Kullanıcıya kaynak hakkında olgu söyleniyordu.** Eski cümle "Bu model
resmi belgenin uç nokta tablosunda yok" diyordu — süreç o sayfayı derlemeden
beri okumamışken **şimdiki hâli** hakkında bir iddia. Sayfa satır kazanınca
cümle yanlış oldu ve hiçbir şey bunu bilemezdi. Cümleler artık **bu sürüm**
hakkındadır ve okuma tarihini taşır:

> Bu model, bu sürümün pinli uç nokta tablosunda yok (tablo 2026-09-04
> tarihinde okundu). …

**2. Sürüklenmeyi fark eden bir şey yoktu.** `len(MODEL_MAPPINGS) == 27` ve
fazlalık sayısı pinliydi ama karşılaştırılmıyordu. Bugün:

* `TABLE_PROVENANCE` **koşulsuz** gösterilir — tablo kaç satır, ne zaman
  okundu, sayfanın altbilgisi ne diyordu. Yalnız bir sorun çıkınca beliren
  bir künye, kimsenin okumadığı künyedir.
* `EXPECTED_UNMAPPED_COUNT = 7` pinlidir ve **katalogdan türetilmez** — türetilse
  kataloğun her dediğini onaylardı, ki bu tam olarak ADR-0005 §1.2'nin ders
  çıkardığı kendi kendini mühürleyen hata biçimidir.
* Çekilen katalogdaki eşlemesiz model sayısı bu pini aşarsa
  `catalog.drift_notice` dolar ve panelde **uyarı** olarak render edilir:
  "Sağlayıcının kataloğu 35 model listeledi ve bunların 8 tanesi bu sürümün
  pinli tablosunda yok… tablo bayat olabilir."

`omen-alpha` tabloya **eklenmedi**. Eklemek yeni bir transkripsiyon ve
orkestratör doğrulaması gerektirir; bu paketin işi sürüklenmeyi *görünür*
kılmaktı, sessizce yamamak değil.

Uçtan uca kanıt artık enjekte edilmiş bir tabloyla değil, **gerçek tabloyla**
alınıyor: `test_opencode_catalog.py::test_a_documented_model_can_be_chosen…`,
`::test_a_model_on_each_documented_family_can_be_chosen` ve HTTP yüzeyinde
`test_opencode_http.py::test_a_documented_model_can_be_chosen_over_http…`.

**Kapanmayan boşluk:** auth header'ının adı hâlâ doğrulanmadı (ADR-0005 §1.1).
Protokol eşlemesinin doğrulanmış olması bunu değiştirmez — biri isteğin
*nereye* gideceğini söyler, diğeri *neyle imzalanacağını*.

---

## 2. Dördüncü giden istemci

`station_api/opencode/client.py`. Üç Technocore istemcisiyle **aynı** taşıma
kurallarını taşır ve testleri tekrar eder: üç modülde geçerli olup dördüncüde
geçerli olmayan bir kural, hiç yazılmamış bir kuraldan kötüdür — kapsanmış
gibi okunur.

* TLS doğrulaması kapatılamaz. `verify` paket genelinde **hiç yazılmaz**;
  taşıyıcı yalnız `httpx.MockTransport` kabul eder (SI-174 kalıbı).
* Redirect takip edilmez. Bir 3xx, kimlik bilgisi taşıyan bir isteğin
  allow-list dışına çıkma yoludur.
* Dört fazlı timeout; hiçbir faz "sınırsız" miras almaz.
* Boyut sınırı **decompress edilmiş** baytlar üzerinde, akış sırasında.
* Host allow-list zorunlu; `assert_allowed_url` şema, host, port, user-info,
  fragment, traversal **ve query string** reddeder. Query'nin ayrıca
  reddedilmesinin nedeni bu istemciye özgüdür: bir anahtarın "hızlıca"
  `?api_key=` olarak eklendiği yer orasıdır ve URL, header'dan çok daha fazla
  yerde loglanır.

### Ücretin değiştirdiği tek kural: tekrar

| Uç nokta | Deneme | Neden |
|---|---|---|
| `/models` (ücretsiz, anahtarsız) | en çok **2** | Genel bir belgeyi iki kez sormanın bedeli yok |
| Üç protokol yolu (**ücretli**) | tam **1** | Süreçten çıkmış bir istek, yanıtı kaybolsa bile ücretlenmiş olabilir |

Kayıp yanıt `OpenCodeLostResponseError` olur ve cümlesi şudur: *"Istek
surecten cikmis olabilir; otomatik olarak tekrarlanmaz."* `_with_bounded_retry`
ücretli bir uç noktayı **yapısal olarak** reddeder ve `post_completion`
içinde hiçbir döngü olmadığı sözdizim ağacından denetlenir.

### Ağ kesici yutulmuyor

`test_outbound_guard.py`'nin ikizi yazıldı. `OutboundNetworkBlockedError` bir
`AssertionError`'dır ve istemcinin yakaladığı hiçbir tipin alt sınıfı
değildir; ayrıca bir test `client.py`'nin **hiçbir `except` bloğunun**
`Exception`/`BaseException`/`AssertionError` yakalamadığını sözdizim ağacından
doğrular — çünkü mock'u unutulmuş bir test, sessizce geçen bir testtir.

### Allow-list'in bugünkü hâli: tam yol

`OUTBOUND_CLIENT_MODULES` düz bir kümeden önce **dizin → modül** haritasına,
sonra **kaynak köküne göreli tam yol** kümesine dönüştü:

```python
OUTBOUND_CLIENT_MODULES = frozenset({
    "station_api/technocore/client.py",
    "station_api/technocore/write_client.py",
    "station_api/technocore/evidence_client.py",
    "station_api/opencode/client.py",
})
```

**İki adımın gerekçesi, doğru yönüyle.** Bu belge bir süre birinci adımı
tersine anlattı; düzeltilmiş hâli şudur.

Paket G öncesindeki yazım `path.name not in MODULES or path.parent.name !=
"technocore"` idi. `opencode/client.py` httpx import etseydi bu kural onu
**reddederdi** — adı listedeydi ama dizini `technocore/` değildi — ve kural
aynı anda her izinli modülün tek bir dizinde yaşadığını iddia ediyordu; bu
da artık doğru değildi.

İlk düzeltme listeyi **çıplak üst dizin adına** göre anahtarladı ve bir
inceleme onu tek hamlede kırdı: `station_api/plugins/opencode/client.py`
konumuna yerleştirilen, httpx import edip anahtarı rastgele bir host'a
gönderen bir modül **27 testin hepsini sessizce geçti**, çünkü üst dizininin
adı `opencode`'du. Çıplak bir ad konum değildir: ağacın herhangi bir yerinde
`opencode` veya `technocore` adlı yeni bir dizin muafiyeti miras alırdı.

Tam yol bunu kapatır. `station_api/opencode/client.py` tek bir dosyadır, bir
adlandırma kuralı değil. İncelemecinin probu regresyon testi olarak durur
(`test_write_gate.py::test_a_client_planted_where_a_directory_borrows_an_allowed_name_is_refused`)
ve ters yönü kapatan bir ikizi vardır
(`::test_a_client_planted_where_a_directory_borrows_the_technocore_name_is_refused`).

Görev katmanının yasak listesi de genişledi: `station_api.opencode`'un
**tamamı** yasak, yalnız istemci modülü değil. Servis kullanıcı adına ağa
çıkıyor; onu import eden bir görev katmanının giden yüzeyi bir adım ötede
olurdu.

---

## 3. Kimlik bilgisi zarfı — ve audit'ten tek farkı

`station_api/opencode/credential_store.py`. Paket E'nin `audit_envelope.py`
**şeklini** kopyalar, kodunu değil:

* zarf `{format, version, kind, created_at, dpapi_blob}` ve okurken
  `require_exact_keys`'ten geçer;
* yazma atomiktir: `O_CREAT|O_EXCL` ile **boş** oluştur → ACL → yaz → fsync →
  `os.replace` → ACL, ve rename'in **her iki yanında** fail-closed.

> Dosyanın adı ilk yazımda `credentials.py`'ydi ve deponun kendi
> `.gitignore`'undaki `credentials.*` kuralı yüzünden hiç commit edilmemişti;
> yani PR diff'ine hiç girmedi ve modül **incelenmeden** birleşti. Ad
> `credential_store.py` olarak düzeltildi ve `test_tracked_sources.py` aynı
> tuzağı bir daha kurulamaz hâle getirdi. Bu belgedeki eski ad da bu yüzden
> düzeltildi: tuzağa düşüren tam olarak o addı.

### Ayrı denetimin bulduğu dört şey

Modül sonradan tek başına denetlendi. Dördü de düzeltildi, hiçbiri
"belgelendi ve bırakıldı" değil:

| Bulgu | Kanıt | Düzeltme |
|---|---|---|
| Dosya ile DB **ayrışabiliyordu**; `/status` yanlış fingerprint gösteriyordu | DB oturumu bozulduğunda zarfta yeni anahtar, satırda eski fingerprint | `store_credential` satırı **önce düşürür**, dosya yazıldıktan sonra yeniden yazar (SI-263) |
| `os.replace`'ten **sonraki** hata eski anahtarı yok edip yenisini korumasız bırakıyordu | ACL çağrısı patlatıldı; eski anahtar gitti, yeni anahtar canlı kaldı | rename olduysa hedef de silinir — sonuç "zarf yok" (SI-264) |
| Vault hataları OpenCode hiyerarşisinden **kaçıyordu** | DPAPI/ACL arızası route'ta yakalanmayan `VaultError`, opak 500 | zarf sınırında çevrilir: makine arızası 503, zarf arızası 400 (SI-267) |
| SI-239'un `kind`/`format` yarısını **hiçbir test tutmuyordu** | döngü bozuk dosyayı biriktiriyordu; `version=99` ilk turda takılıyordu | döngü her turda taze zarftan başlar; eksik/fazla/yanlış-tipli alan testi eklendi (SI-239) |

Ayrıca: ACL artık **tek bayt yazılmadan** uygulanır (eski sıra yaz → fsync →
ACL idi ve izleme 537 baytın inherited DACL altında var olduğunu gösterdi),
dizinin kendisi de kısıtlanır, ve `store`/`load`/`delete` süreç içi tek bir
kilitle sıralanır — eşzamanlı okuma/yazma `PermissionError` üretiyordu.

`load()` **hiçbir şey kaydetmez** ve docstring'i artık bunu söyler; üretimde
kullanılacak yol `opened()` contextmanager'ıdır, register/forget çifti
çağırandan alınmıştır. Bellek temizliği (`bytearray` + sıfırlama) burada
**yoktur** ve modül docstring'i bunu açıkça yazar: anahtar Pydantic'ten
itibaren `str`'dir ve yalnız bu katmanı `bytes`'a çevirmek üstteki üç
çerçevedeki aynı nesneyi bırakırdı.

**Bilinçli fark — ve bu farkın kendisi test edilmiştir.** Audit zincirinin
materyali **asla üzerine yazılmaz**; provider anahtarı **yazılmalıdır**, çünkü
kullanıcı anahtarını değiştirebilmelidir ve reddetmek onu göremediği bir
dosyayı silmeye mahkûm ederdi. `test_opencode_credentials.py` iki davranışı
**yan yana** sabitler:

| Test | İddia |
|---|---|
| `test_a_credential_is_replaceable_because_a_user_must_be_able_to_rotate_one` | ikinci `store` başarılı, yeni değer okunuyor |
| `test_the_audit_material_still_refuses_to_be_overwritten` | ikinci `create_material` `AuditEnvelopeError` |

Şekli üçüncü kez kopyalayacak kişi, hangi tarafın kasıtlı olduğunu tahmin
etmek zorunda kalmaz.

### Domain separation

`dpapi.protect` entropi parametresi almaz — tek bir uygulama sabiti kullanır
— dolayısıyla kasa blob'u ile bu blob DPAPI açısından birbirinin yerine
geçebilir. Ayrım **in-band**'dir: düz metin `DOMAIN_SEPARATION_LABEL`
(`technocore-station/opencode/v1/credential\0`) ile önekleniyor ve önek
okurken zorunlu. Bu dosyanın yerine kopyalanmış bir audit materyali zarfı
reddedilir — aksi hâlde 32 bayt MAC materyali giden bir `Authorization`
header'ına girerdi. Sabit **gizli değildir**; yalnız alan ayırır.

### Veritabanına ne giriyor

`opencode_credential_metadata` üç şey tutar: **göreli** zarf yolu, iki zaman
damgası ve bir fingerprint (sabit ve genel bir etiketin anahtar altında
HMAC'i). `secret_metadata` deseni. **Saklanan anahtarı geri gösteren,
maskeleyen veya kopyalayan hiçbir endpoint yoktur** — maskeli de dâhil.
Sütun adlarında `key` parçası yasaktır (bu yüzden `envelope_relpath`), ve
yanıt modellerinde `api_key`/`key` adlı alan yoktur.

### Kısa anahtar tuzağı

`logging_setup.register_secret` **16 karakterden kısa değerleri sessizce yok
sayar**. Böyle bir anahtar saklanır ve **hiçbir zaman redakte edilmezdi**.
`MIN_KEY_LENGTH = 20` bu eşiğin üzerindedir ve `assert_storable` kısa değeri
kapıda reddeder; `OpenCodeService._registered` uzunluğu kullanım anında
**yeniden** denetler, çünkü tek giriş yolunun store olduğuna güvenmek bu
sözü bir varsayıma çevirirdi.

---

## 4. Üç protokol adaptörü ve ortak olay modeli

`adapters.py` üç aileyi tek bir `events.CompletionEvent`'e indirger:

```
CompletionEvent(protocol, model, text, finish, usage, failure)
```

| Alan | Anlamı | Neden böyle |
|---|---|---|
| `finish` | `completed` / `length` / `refused` / `provider_error` / `unknown` | `unknown` **`completed` değildir**: modelin neden durduğu hakkındaki sessizlik tamamlanmış bir cevap değildir |
| `usage` | `TokenUsage(input, output)`, `None` olabilir | Sağlayıcı saymadıysa `None`. **Sıfır uydurulmaz**; `total_tokens` yarısı eksikse `None` döner, kısmi toplam vermez |
| `failure` | `FailureKind` + HTTP durumu + cümle | `succeeded` **gövdeden türetilir**, durum satırından değil |

Üç ailenin `text`/`usage`/`finish` anahtarları farklıdır (`output_text` vs
`content[].text` vs `choices[0].message.content`; `input_tokens` vs
`prompt_tokens`) ve normalizasyon yalnız burada olur.

### Adaptörlerin yapmayı reddettiği dört şey

1. **200'ü başarı saymak.** Üç aile de 200 içinde `error` üyesi taşıyabilir.
   `parse_response` metni aramadan **önce** hatayı arar; bulursa olay bir
   başarısızlıktır. (`test_a_two_hundred_carrying_a_provider_error_is_not_a_success`)
2. **Kullanımı uydurmak.** Token sayısı yoksa `UNKNOWN_USAGE`. `bool` bir
   token sayısı olarak kabul edilmez (Python'da `True` bir `int`'tir).
3. **Tanımadığı şekli boş cevap saymak.** Ne hata ne tanınır metin taşıyan
   bir 200 `MALFORMED_BODY`'dir. "Okuyamadık" ile "bir şey söylemedi" farklı
   cümlelerdir.
4. **Model değiştirmek.** Fallback yoktur; istekteki kimlik, çağıranın kapalı
   tablodan çözdüğü kimliktir.

Yanlış aile seçildiğinde gövde **sessizce parse olmaz** — bu, tahmin edilmiş
bir eşlemenin üreteceği hata biçimidir ve ADR-0005 §5'in tahmini
yasaklamasının somut nedenidir.

**Streaming ve tool-call yoktur** (ADR-0005 §2). Sözleşmeleri yayımlanmadığı
için yazmak tahmin olurdu; erteleme H2'ye aittir ve `protocol_context`
üzerinden görünürdür.

---

## 5. Katalog ve eşleme tasarımı

```
GET /zen/go/v1/models  ──►  parse_catalog()  ──►  CatalogEntry(id, owned_by, created)
                                                        │
                          MODEL_MAPPINGS (derleme zamanı)│
                                                        ▼
                                                   ModelView(selectable, protocol, reason, retention, …)
```

* Katalog **yalnız kullanıcı isteğiyle** çekilir (`POST /api/opencode/catalog/refresh`).
  Açılışta, durum okurken veya model seçerken hiçbir istek çıkmaz — ve bu
  iddia **sayılarak** ölçülür, varsayılmaz.
* Katalog **hiçbir şeye karar vermez**. Bir girdi `protocol`, `endpoint` veya
  `selectable` alanı taşısa bile bunlar okunmaz; `ModelView` yalnız kapalı
  tablodan doldurulur. Metadata'nın iddia ettiği bir URL doğrudan fetch
  edilmez.
* **Yarım parse yok.** Okunamayan tek bir satır bütün belgeyi reddettirir:
  kısalmış bir liste, model kaldırılmış gibi görünür.
* Aynı kimliği iki kez listeleyen katalog reddedilir — hangisinin kastedildiği
  bir tahmin olurdu.
* İçe alınan string'ler süpürülür ve sınırlanır; **bidi override dâhil**
  (`Cf` kategorisi), çünkü bir kimliğin göründüğü ad ile olduğu ad farklı
  olabilir.

### Cache: tablo, dosya değil

Cache `opencode_catalog_check` + `opencode_model_snapshot` tablolarındadır
(`official_source_snapshot` deseni). Dosya olmamasının nedeni sadelik değil:
bir cache dosyasının yolu olurdu, yol kaydedilirdi ve kaydedilmiş bir yol
SI-36'nın "API yanıtında dönmez" dediği şeydir. Tabloda tutmak soruyu ortadan
kaldırır. `snapshot_excerpt` insan incelemesi için tutulur ve **HTTP'ye
dönmez**.

**İki ayrı tarih** taşınır ve bu kasıtlıdır:

| Alan | Anlamı |
|---|---|
| `fetched_at` | Son **deneme** |
| `models_fetched_at` | Listelenen modellerin gerçekten okunduğu an |

Başarısız bir yenileme hatayı gösterir, cache'i **silmez** ve cache'e kendi
tarihini **ödünç vermez**. Tek alan olsaydı bu iki yalandan birini seçmek
zorunda kalırdık.

### Eğitim/veri saklama

Koşul **model başınadır**, tek bir battaniye cümle değil — Privacy tablosu
27 satırın beşi için ortak durumdan farklı bir şey yazıyor:

| Model | Model training | Data retention |
|---|---|---|
| `grok-4.6`, `gpt-5.6-luna` | `Not used` | **`30 days`** |
| `muse-spark-1.3-contributor`, `muse-spark-1.2-contributor` | **`Yes`** | **`Not ZDR`** |
| `deepseek-v4-pro`, `deepseek-v4-flash`, `deepseek-v4-flash-vision-exp` | `Not used` | **`0 days*`** |
| kalan 20 satır | `Not used` | `0 days` |

* Gizlilik tablosunun okunduğu **tarih ve kaynak** her modelin yanında taşınır.
* `0 days*` içindeki **yıldız korunur**. İşaret ettiği dipnot okunmadı;
  yıldızı düşürmek koşullu bir ifadeyi koşulsuz hâle getirirdi.
* İki `muse-spark-*` satırı **`documented` olduğu için seçilebilir**, ama
  **varsayılan olarak seçilmez**: onaysız seçim 400 döner ve gerekçe veri
  koşulunu söyler; `training_acknowledged` ile geçer (ADR-0005 §5).
  "Seçilebilir" ile "ek onay ister" iki ayrı özelliktir — birleştirmek ya
  eğitim modelini yanlış gerekçeyle gizlerdi ya da sessizce seçtirirdi.
* Onay **maymuncuk değildir**: `training_acknowledged`, protokol ailesi
  bilinmeyen bir modeli seçilebilir yapmaz
  (`::test_an_acknowledgement_does_not_unlock_an_unaddressable_model`).
* `TrainingUse.UNKNOWN`, `NO` ile aynı şey **değildir**: bilinmeyen koşul da
  ek onay ister. **Bilinmeyen veya süresi geçmiş bilgiye "saklanmıyor"
  denmez** — koddan böyle bir yol yoktur ve bir test bunu tarar. Koşulu
  yayımlanmış bir satır kendi terimini söyleyebilir, ama `privacy_source` ve
  `privacy_read_on` olmadan söyleyemez: iddia sağlayıcınındır ve yanıt
  kimin olduğunu belirtir.
* `TRAINING_FAMILY_PREFIXES` (`muse-spark`) yalnız **çıtayı yükseltmek** için
  kullanılır: eşleşme ek onay getirir, eşleşmemek hiçbir şeyi güvenli ilan
  etmez. Tabloda satırı olmayan bir `muse-spark-*` kimliği bu yüzden hem
  seçilemez hem de onay isteyen tarafta kalır.

---

## 6. "Bağlantıyı denetle" — dürüst çıktı

Üç gözlem çatışıyor (ADR-0005 §4): katalog anahtarsız cevap veriyor, protokol
yolunda `GET` 404 dönüyor, ve gerçek bir çağrı bu turda yasak. Sonuç:

```
VerificationState = not_configured | never_checked | key_saved_unverified
```

**`verified` diye bir değer yoktur.** Enum'da bulunmayan bir değer, yanlış
yerden yazılamaz.

Anahtar kayıtlıyken çıktı şudur:

* `state`: `key_saved_unverified`
* `detail`: *"Anahtar kaydedildi, dogrulanmadi. Bu tek yesil bir rozet degildir."*
* `reasons` (**çoğul, kasıtlı**): katalog anahtarsız yanıt verdiği için
  doğrulamıyor; gerçek istek ücretli olabileceği için yalnız kullanıcının
  açık eylemine bağlıdır ve bu turda uygulanmadı; auth header'ı belgede
  doğrulanmamıştır.

**Biçim kontrolüyle başarı üretilmez.** `assert_storable` yalnız güvenle
tutulabilirliği denetler (uzunluk, kırpılmamışlık); anahtarın "makul
göründüğünü" kontrol eden bir kural, anlamı olmayan yeşil bir sonuç üretirdi.

---

## 7. Kota/maliyet bağlamı

`quota.py` ve `OpenCodeSpendingContext`. `budget_available: Literal[False]`
**değişmedi** (ADR-0005 §9). Taşınan her şey salt-okunur:

* yayımlanmış limitler (5sa $12 / hafta $30 / ay $60) ve limit dolunca ne
  olduğu;
* "Use balance" tercihinin **sağlayıcı konsolunda** olduğu ve API'den
  sorgulanamadığı — Station bu ayarı değiştirmez ve **engellediğini iddia
  etmez**;
* yerel bir sayacın paylaşılan bir abonelikte gerçek kullanımı
  **kanıtlamadığı**;
* token/maliyet sağlayıcıdan gelmediğinde `unknown` yazıldığı, sıfır
  yazılmadığı.

Abonelik **"sınırsız" denmez**: `quota.assert_no_unlimited_claim` ürünün
kendi cümlelerini denetler (`evidence/language.py`'nin charter guard kalıbı) ve
route bunu her yanıtta çalıştırır.

---

## 8. HTTP yüzeyi

    GET  /api/opencode/status             tüm bağlantı, salt okunur
    POST /api/opencode/credential         anahtarı kaydet
    POST /api/opencode/credential/forget  anahtarı sil
    POST /api/opencode/catalog/refresh    katalogu çek (yalnız istek üzerine)
    POST /api/opencode/model              model seç, ya da gerekçeli ret

Beş route; hepsi oturum + CSRF + Host + Origin + Sec-Fetch-Site arkasında
(middleware, dolayısıyla opt-out yok). **Yokluğu kasıtlı olanlar:**

* **anahtarı geri gösteren route** — maskeli, kısmi veya "doğrulama için"
  bile değil;
* **completion route'u** — ücretli istek H2'nindir; buraya bir düğme koymak
  "Station kendiliğinden para harcamaz" cümlesini dipnotlu hâle getirirdi;
* **URL/host/path/protokol parametresi** — `refresh` gövde bile almaz;
* **fallback** — adreslenemeyen model 400'dür, sessiz ikame değil.

---

## 9. Testler

Sayılar `pytest --collect-only -q` çıktısıdır (parametrelenmiş testler ayrı
sayılır) ve **ayrı kimlik-bilgisi denetiminin** düzeltmelerinden sonraki
hâliyle yeniden sayılmıştır.

| Dosya | Test | Kapsam |
|---|---|---|
| `test_opencode_client.py` | 24 | allow-list, TLS, redirect, gövde tavanı, tekrar politikası, header'lar, tek `Authorization` |
| `test_opencode_credentials.py` | 31 | zarf şekli (eksik/fazla/yanlış-tipli alan dahil), üzerine yazma farkı, domain separation, fingerprint, ACL (dosya **ve** dizin, bayttan önce), DB sınırı, **dosya↔satır ayrışmasının iki yolu**, vault hatalarının çevrilmesi, eşzamanlılık, `opened()` |
| `test_opencode_protocols.py` | 62 | üç aile × fixture, 401/403/404/429/5xx, 200-içi hata, bozuk/boş gövde, uydurulmayan usage |
| `test_opencode_catalog.py` | 46 | parse, eşleme, listelenen≠seçilebilir, eğitim onayı, cache tarihi/hatası, **yalnız protokol kapısının ateşlendiği satır**, **sürüklenme uyarısı** |
| `test_opencode_http.py` | 33 | route kümesi, oturum/CSRF, anahtar dönmüyor, sıfır giden istek, **Türkçe "sınırsız" yasağı**, **DPAPI/ACL arızasının 503'ü** |
| `test_opencode_leakage.py` | 17 | canary: gövde+header, OpenAPI, SQLite, zarf, veri dizini, log, bundle, yansıtılan anahtar, **reddedilen gövdenin 422'si** |
| `test_tracked_sources.py` | 3 | kaynak ağacındaki her dosya gerçekten **izleniyor**; `credentials.*` tuzağı bir daha kurulamaz |

Ayrıca genişletilen mevcut testler: `test_write_gate.py` (29 test — tam yol
allow-list'i ve iki "ödünç alınmış dizin adı" probu), `test_outbound_guard.py`
(20 test), `test_module_registry.py` (34 test — migration `0008`, OpenCode
tablolarının sütun denetimi ve **beşinci aşama-numarası yeri**).


Hiçbir test gerçek bir çağrı yapmaz; hepsi `httpx.MockTransport` iledir ve
autouse ağ kesici iki katmanda blokludur.

---

## 10. Ertelenenler ve kalan riskler

| Konu | Nereye |
|---|---|
| Streaming / SSE | H2 — sözleşme yayımlandığında |
| Tool-call | H2 — aynı gerekçe |
| Gerçek probe ("anahtarı doğrula") | Kullanıcının açık eylemine bağlı; ücretli olabileceği için bu turda uygulanmadı |
| Gerçek bütçe sınırı ve eşzamanlılık | H2 |
| Katalogdaki **7 eşlemesiz** model | Belge "Endpoints" tablosuna eklediğinde `MODEL_MAPPINGS`'te satır başına tek satır |

**Kalan riskler:**

* Auth header'ı bir varsayımdır. Yanlışsa her ücretli istek 401 döner —
  gürültülü ve ucuz bir başarısızlık, sessiz bir yanlışlık değil.
* Adaptörlerin gövde şekli fixture'a karşı doğrulanmıştır, **gerçek hesaba
  karşı değil**. Geliştirici kullanıcının gerçek anahtarını okumaz, istemez,
  kullanmaz; gerçek hesap testi hesabın sahibine aittir.
* `TRAINING_FAMILY_PREFIXES` ad öneki eşleşmesidir; wire kimliği farklıysa
  eşleşmez. Bu yön güvenlidir (koşul `unknown` kalır ve yine ek onay ister),
  fakat "eğitim için kullanılıyor" etiketinin eksik kalabileceği anlamına
  gelir.
* İnsan güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5).
