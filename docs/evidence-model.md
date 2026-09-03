# Kanıt (Evidence) güven modeli

> Ana karar kaynağı: [`../Technocore-Station-Proje-Kunyesi.md`](../Technocore-Station-Proje-Kunyesi.md) §15.
> Kapsam kararları: [`decisions/0003-paket-e-kapsam-kararlari-2026-09-04.md`](decisions/0003-paket-e-kapsam-kararlari-2026-09-04.md).

**Uygulama durumu: UYGULANDI (Paket E).** Evidence kaydı, export yakalama,
audit zinciri, secret-şekil taraması ve dışa aktarım vardır. Bu belge artık
bir sözleşme *taahhüdü* değil, **çalışan sistemin tarifi**dir; dil kuralları
(§2) aynen ve bu kez **backend testleriyle de** bağlayıcıdır.

Bu modelin amacı tek bir şeydir: **fazla iddia etmemek.** Ürün, imza
kanıtını sunucu gözlemiyle, sunucu gözlemini de güvenilir zamanla aynı
şeymiş gibi göstermez.

---

## 1. Dört seviye

| Seviye | Ad | Kanıtlanan | Kanıtlanmayan |
|---:|---|---|---|
| 1 | **İmza kanıtı** (cryptographic authorship) | DID özel anahtarına sahip tarafın belirli canonical string'i imzaladığı | Gerçek kimlik, içeriğin doğruluğu, zaman, anahtarın çalınmadığı |
| 2 | **Sunucu gözlemi** (server observation) | Station'ın belirli exact sunucu yanıtını / generation bilgisini gördüğü | Sunucunun dürüstlüğü, bağımsız üçüncü taraf gözlemi |
| 3 | **Yerel kayıt zamanı** (local receipt time) | Yerel makinenin o anda gösterdiği saat | Güvenilir zaman damgası |
| 4 | **Haricî anchor** (external anchoring) | Haricî bir tarafın hash'i belirli tarihten önce gördüğü | **MVP'de yoktur** — açıkça `null` |

Seviye 4 MVP'de **boştur**. Veritabanında `evidence_record.external_anchor`
sütunu vardır ve her zaman `NULL` yazılır; dışa aktarımda anahtar
**atlanmaz**, `null` olarak yazılır. Atlanan bir anahtar "kimse bakmadı" gibi
okunur; `null` alınmış bir kararı gösterir.

Her kayıt hangi seviyenin dolu hangisinin boş olduğunu **kendi taşır**
(`EvidenceView.levels`); seviyeler tek bir yeşil rozete toplanmaz.

---

## 2. Yasak ifadeler

Aşağıdaki ifadeler UI, **API**, **log**, belge ve **dışa aktarım**
çıktılarında kullanılamaz:

- "sunucu kanıtı"
- "değişmez kayıt"
- "güvenilir zaman kanıtı"
- "airdrop uygunluk kanıtı"

Doğru karşılıkları sırasıyla: *sunucu gözlemi* / *yakalanan kayıt*,
*yerel arşiv kaydı*, *yerel kayıt zamanı*, (karşılığı yoktur — üretilmez).

Audit zinciri için kullanılacak tek ifade: **"çevrimdışı değişikliğe karşı
tespit edici"**.

**Paket E iki ifade daha ekledi** — ikisi de truncation hakkındaki aşırı
iddiadır: "değiştirilemez kayıt" ve "kurcalanamaz kayıt". Gerekçe §4'tedir.

### Nasıl zorlanıyor

Paket E'ye kadar bu kural **yalnız frontend testiyle** korunuyordu, yani bir
kullanıcının okuduğu ekranı kapsıyor, aynı kullanıcının *dışa aktardığı*,
grep'lediği veya hata raporuna yapıştırdığı metni kapsamıyordu. Artık
`station_api.evidence.language` bir registry taşır; karşılaştırma
**katlanmış** biçimde yapılır (küçük harf, aksan ayrıştırma, `ı` → `i`), yani
"Sunucu Kanıtı" ile ASCII yazılmış "sunucu kaniti" aynı iddiadır ve ikisi de
yakalanır. Export yazıcıları ve audit satırları yazılmadan önce
`assert_no_forbidden_claim` çağırır: bir ihlal **yazmayı reddeder**.

---

## 3. Export yakalama (uygulandı)

Resmî `GET /r/{room}/export` yüzeyi okunur. Bu yol `SOURCES`'a **eklenmedi**;
üçüncü bir kapalı registry açıldı (`technocore/evidence_targets.py`) ve
istemcisi `technocore/evidence_client.py`'dir — `httpx` import edebilen üçüncü
ve son modül (ADR-0003 §1).

Yakalama **yalnız kullanıcı isteğiyle** çalışır. Otomatik değildir, zamanlı
değildir ve hiçbir koşulda bir yeniden gönderimin ön adımı değildir.

Tek istek, **akış üstünde satır satır** taranır ve yalnız şunlar saklanır:

1. Kendi kaydımızın **ham baytları** (satır sonlandırıcısı hariç), byte
   offset ve uzunluk ile.
2. **Room generation** (`X-Room-Generation`), yalnız rakamsa; değilse
   düşürülür — okunamayan generation, eksik generation'dır.
3. Bütün akışın **yürüyen SHA-256'sı** — eşleşmeden *sonraki* baytlar dahil.
4. Sınırlı bir çevre penceresi: en çok 2 satır önce, 2 satır sonra ve satır
   başına en çok 4 KiB. İki sınır birden gerekir; üç kısa satır ile üç
   10 MiB'lık satır ikisi de "üç satır"dır.

Tam ring **saklanmaz**. Tarama tavanı **12 MiB**'dır: 10 MiB ring
(`limits.room_ring_bytes`) artı başlık payı. Mevcut `_read_capped`
kullanılamazdı — chunk'ları `b"".join` ile birleştirir, yani bir tavan değil
bir tampondur (aynı hata IMP-289'da düzeltilmişti).

**Satırı bulmak için satır bazında minimal parse yapılır, kanıt olarak ham
baytlar saklanır.** Pinli belge export'u tam olarak bunun için yayımlar:
"bytes exactly as written, never re-serialized — so a signed record
re-verifies from its exported line alone". Parse'tan yeniden üretilmiş bir
satır yalnız kendini doğrular.

Nonce **big-integer-safe** okunur. Pinli açıklama uyarır: 19 hane 2^53'ü
aşar ve float'a yuvarlanmış bir nonce iyi imzaları bozar. Satırlar
`loads_strict` ile okunur (Python `int`'i keyfi hassasiyettedir), JSON float
olarak gelen bir nonce eşleşmeye **yuvarlanmaz**, ve yinelenen anahtar taşıyan
bir satır okunamaz sayılır.

### Altı yakalama durumu

Sonuç tek bir yeşil rozete indirgenmez (ADR-0003 §3):

| Durum | Anlamı |
|---|---|
| `line_captured` | Kendi satırımız bulundu; ham baytları ve offset'i saklandı. **Seviye 2 sunucu gözlemidir**, "gönderildi kanıtı" değildir. |
| `line_not_found` | Taranan kısımda yoktu. **Hiçbir şey kanıtlamaz** — ring unutur, `e-` odası daha hızlı unutur. |
| `generation_changed` | Oda dönemi öncekinden farklı; kayıtlar **karşılaştırılamaz**. Bulunmuş bir satıra bile baskındır. |
| `stream_truncated` | Tarama tavana dayandı. Eksik taramada yokluk, yokluğun kanıtı değildir. |
| `parse_problem` | Satırlar okunamadı. Okunamayan ≠ değişmiş (IMP-238 emsali). |
| `fetch_failed` | Okuma tamamlanmadı. |

Son beşi **"doğrulandı" değildir**. `line_not_found` bir `outcome_unknown`
gönderimi **asla** `not_sent`'e çevirmez: modelin var olma sebebi tam olarak
bu çıkarımı reddetmektir.

**Okuma yeniden denenebilir, yazma asla.** `CaptureState.may_retry_write`
her durum için `False` döner ve bir test bunu sabitler; kanıt yüzeyinde
yeniden gönderim yapan hiçbir route, parametre veya bayrak yoktur.

Oda adı **yazma yolunun aynı politikasından** geçer — ad kalıbı, tanınan
sınıf işaretçileri ve `DENIED_ROOMS` dahil. Lobby'nin export'u da okunmaz.

---

## 4. Audit zinciri (uygulandı)

- Audit satırları **HMAC-SHA256** zinciriyle bağlanır (`prev_mac` → `mac`).
  Canonical satır `strict_json.canonical_json_bytes` ile üretilir — kasa
  zarfının kullandığı, bayt bayt pinlenmiş kodlama.
- Satır numarası 1'den başlar, boşluksuz artar ve `UNIQUE` kısıtıyla
  korunur. Satırın sakladığı **her alan** MAC'in içindedir.
- HMAC materyali **ayrı bir DPAPI zarfında** tutulur
  (`<data_dir>/audit/v1/chain-material.json`). `DpapiVault` yeniden
  kullanılamazdı: kimliğe bağlıdır, dosya adı kimlik id'sidir, iç AAD kimliği
  taşır ve `store()` asla üzerine yazmaz — oysa zincir başı her append'te
  yeniden yazılır (ADR-0003 §6). Materyal **hiçbir tabloya girmez**;
  `audit_chain_metadata` yalnız göreli yol, oluşturma zamanı ve bir
  fingerprint (sabit public etiketin materyalle HMAC'i) tutar.
- Zincir **başı** (son MAC + satır sayısı) **ikinci bir DPAPI zarfındadır**
  ve append ile **aynı transaction sınırında** güncellenir.
- Audit zinciri ve Evidence kayıtları **asla budanmaz** (ADR-0003 §7).
  Ortadan satır silmek zincirin göstermek için var olduğu şeydir; bunu
  zamanlanmış bir politika hâline getirmek kendi kanıtımızı programlı olarak
  bozmak olurdu.

### Sağladığı ve sağlamadığı güvence — dürüst hâli

**Tespit edilenler:** ortadan satır silme, herhangi bir alanın değiştirilmesi,
satırların yeniden sıralanması. Bunlar için bir test her birini gerçekten
yapar ve raporun *doğru* cümleyi kurduğunu doğrular.

**Sonun kesilmesi:** zincirin içinde uzunluğunu söyleyen bir şey yoktur. Bunu
sağlayan tek şey **ayrı zarftaki baştır**, ve o da yalnız **bu Windows
kullanıcısı olarak çalışmayan** bir saldırgana karşı işe yarar.

**Bu bir garanti değildir.** Aynı Windows kullanıcısı olarak çalışan bir
saldırgan aynı zarfı açar, bütün MAC'leri yeniden hesaplar ve başı yeniden
yazar. Bir test bu saldırıyı **gerçekten uygular** ve zincirin `intact`
raporladığını gösterir. İzin verilen tek ifade bu yüzden "çevrimdışı
değişikliğe karşı tespit edici"dir; "değiştirilemez kayıt" ve "kurcalanamaz
kayıt" yasak listesindedir.

**Yarım kalan yazma ≠ saldırı.** Bir dosya ile bir SQLite transaction'ı atomik
olarak commit edemez. Aradaki pencerede bir çökme başı bir satır ileride veya
bir satır geride bırakır; `verify()` bunu `head_mismatch` olarak ve
"yarıda kalan bir yazma bu sayıları üretir" cümlesiyle raporlar. Buna
"kurcalama" demek, kapatılan bir kontrolün en kısa yoludur.

**Materyal açılamıyorsa** sonuç `unavailable`'dır — hiçbir zaman "geçti"
değil.

---

## 5. Secret ayrımı

- Evidence kayıtlarında seed, private key, parola veya oturum bilgisi
  **bulunamaz**. Hiçbir sütun adı `seed`/`private`/`secret`/`mnemonic`/
  `passphrase`/`password` parçası taşımaz.
- Evidence yazılmadan önce **secret-şekil taraması** uygulanır
  (`evidence/secret_scan.py`).
- **Fail-closed: yazmayı reddeder, sessizce redakte etmez.** Kanıt olan şey
  ham baytlardır; redakte edilmiş bir bayt değiştirilmiş bir bayttır ve
  hiçbir şeyi doğrulamayan, ama kanıta benzeyen bir kayıt üretir.
- **Sıra kritiktir: önce allow-list, sonra red kuralları.** İmzalı bir gövde
  yüksek entropili public değerlerden *yapılmıştır*; 86 karakterlik bir
  base64url imza 43 karakterlik koşular içerir. Red-önce bir tarayıcı bu
  ürünün ürettiği her kaydı reddeder, ve bunun "düzeltmesi" kuralları gerçek
  trafik geçene kadar gevşetmektir — yani hiçbir şey tespit etmemek.
  - **Allow-list:** 86 karakterlik kanonik imza, `did:key:z` önekli DID,
    1–19 haneli nonce. Kalıplar `technocore_conform`'dan alınır ve burada
    çapalanır.
  - **Red:** `logging_setup` registry'sindeki kayıtlı değerler, 64-hex
    koşular, 43 karakterlik base64url koşular.
  - SHA-256 digest'i de 64 hex'tir ve public'tir; yine de **reddedilir**.
    Taranan alanların (canonical metin, request/response baytları) çıplak bir
    digest taşıması için bir sebep yoktur, ve bir istisna açmak gerçek bir
    seed'in o kılığa girebileceği yer olurdu.
- **False positive → reddet ve bildir.** Ret mesajı hangi kuralın ateşlendiğini
  söyler ve **tetikleyen değeri asla yankılamaz**.
- Exact JSON request baytları saklanabilir; ancak *"imza bu JSON'u kapsıyor"*
  **denmez** (bkz. [`protocol-contract.md`](protocol-contract.md) §2.4). İmza
  canonical *string*'i kapsar.

---

## 6. Dışa aktarım

- Biçimler: **JSON** ve **Markdown**.
- **Açık kullanıcı onayı zorunludur ve yapısaldır.** Servis bir
  `ExportConsent` alır; bu nesne yalnız `Literal[True]` alan bir classmethod
  ile kurulabilir, istek modelinin `acknowledged` alanının varsayılanı yoktur
  (eksikse 422) ve route ayrıca yeniden kontrol eder. "Yine de dışa aktar"ın
  hem tip denetiminden geçen hem çalışan bir yazımı yoktur.
- **Deterministiktir:** aynı girdi → aynı bayt. JSON `canonical_json_bytes`
  ile üretilir; Markdown sabit sırada sabit bölümler ve `\n` satır sonu
  kullanır. İki kez dışa aktarıp diff alan bir kullanıcı hiçbir şey görmemeli
  ki bir fark **bir şey ifade etsin**.
- **İçe alınan metin etkisizleştirilir.** `safe_display` kontrol, format ve
  bidi karakterlerini süpürür — ve başka hiçbir şey yapmaz: `<`, `[`, `](`,
  backtick ve `|` escape **edilmez**. Mesaj gövdesi kullanıcı ve ağ metnidir;
  bir Markdown dosyasında link, ham HTML, tablo satırı veya fence açabilir.
  Bu yüzden Markdown yazıcısının kendi escaper'ı vardır ve her enterpole
  değere uygulanır. JSON yazıcısının escaper'a ihtiyacı yoktur — JSON'da
  markup yoktur.
- **Sunucu hiçbir yola dosya yazmaz.** Recovery ile aynı kalıp: HTTP yanıtı +
  `Content-Disposition` + tarayıcı indirmesi (ADR-0003 §9). Path traversal,
  symlink, reparse point ve overwrite soruları bu özellikte **doğmaz**.
- **Dosya adı allow-list'ten yeniden kurulur** (`station_api/downloads.py`):
  `[A-Za-z0-9._-]` dışındaki her şey tire olur, koşular birleşir, baştaki
  nokta/tire kırpılır, uzunluk sınırlanır ve boşa düşen ad bir yedeğe
  dönüşür. Tırnak, CRLF, `;`, `../`, RTL override ve non-ASCII bu kuralla
  birlikte kaybolur. Aynı yardımcı recovery indirmesine de uygulandı: orası
  ham bir f-string'di ve bugün güvenliydi, çünkü tek değişkeni base58 bir DID
  kuyruğuydu — yani tam olarak, kimse yeniden bakmadığında doğru olmayı
  bırakan türden bir güvenlik.
- Her kayıt hangi seviyenin dolu hangisinin boş olduğunu **açıkça** taşır.
  Seviye 4 `null` yazılır; boş bırakılmaz veya uydurulmaz.
- Dışa aktarım **kendisi bir audit olayıdır**.

---

## 7. Uzlaştırma (`outcome_unknown`)

Export okuması açıldığı için uzlaştırma teknik olarak mümkün hâle geldi.
Anlamı **daralmıştır**: `reconciliation_required` "kanıt yakalama
denenebilir" demektir, "yeniden gönder" değil.

- Satırın bulunması **Seviye 2 sunucu gözlemidir**.
- Satırın bulunmaması **hiçbir şey kanıtlamaz**.
- Hiçbir koşulda yazma tekrarı önerilmez veya mümkün kılınmaz.

---

## 8. Kabul kriterleri

| ID | Kriter | Aşama | Durum |
|---|---|---|---|
| AC-14 | Gönderim sonrası exact export satırı ve generation kaydedilir | 5 / Paket E | uygulandı |
| AC-17 | Technocore içeriğindeki HTML/URL aktif içerik olmaz | 3 | uygulandı |
| AC-18 | Airdrop garantisi veya claim iddiası UI'da bulunmaz | tüm aşamalar | uygulandı |
