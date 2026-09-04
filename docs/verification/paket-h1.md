# Paket H1 doğrulama raporu — Work Scan

Tarih: 2026-09-04 · Taban: `9773a54f16b294cd25a1ff53d714f2ab46f03584` (Paket G merge'ü)

Kapsam kararları: [`ADR-0007`](../decisions/0007-paket-h1-kapsam-kararlari-2026-09-04.md).

## Bildirilen kısıt ihlali

Keşif sırasında bir alt-agent `technocore.chat`'e **canlı GET istekleri**
attı (`/rooms`, `/kv/topic/kibble`, `/humans`, `/llms.txt`); görev talimatı
"hiçbir istek atma" diyordu. Yazma yok, kimlik/DID/cookie yok, ücretli çağrı
yok — INV-05 ve CLAUDE.md kural 5 çiğnenmedi. Agent ihlali kendisi bildirdi;
o kaynaktan gelen iki bulgu ayrıca etiketlendi ve **bu paketin hiçbir kararı
onlara dayanmıyor**. Uygulama boyunca hiçbir dış servise istek gönderilmedi.

## İki büyük karar

**Kibble'a hiçbir istek atılmadı ve istemci yazılmadı** (ADR-0007 §1).
Servis var ve okuma endpoint'leri belgelenmiş; ama `job` nesnesinin alan
adları, sayfalama, rate limit, kullanım koşulları ve işletmeci
**doğrulanamadı**, ve `/api/board` sayfalamasız ~77 bin kayıtla **60
saniyede timeout** oldu. Şema bilinmeden adapter yazmak alan adı
uydurmaktır. Registry'de `support_unverified` kaydı açıldı; `adapter_written`
ve `contacted` **türetilmiş özellik** ve daima `False`, ve bir test kayıtlı
origin'in beş giden modülün hiçbirinde geçmediğini doğruluyor.

Servisin kendi iki cümlesi birebir taşınıyor: *"Kibble is not FLOP Network
and not Technocore. It settles nothing."* ve *"Advisory IOU from the public
tape. Nothing is paid."* — yani "resmî FLOP kaynağı varsayma" kuralını
kaynağın kendisi doğruluyor. `authority = 3` (community) zorunlu ve bir test
yanıt gövdesinin tamamını gezip hiçbir yerde `score`/`rank`/`reputation`/
`eligibility` **anahtarı** olmadığını iddia ediyor.

**Aday üretimi deterministik** (ADR-0007 §2). Model çağrısı yok. Gerekçe
yalnız "harcama yasak" değil: deterministik çıkarımda uydurulacak alan
yoktur — her alan ya ham kaynaktan (`room`, `seq`, `ts`, `from`, `text`) ya
sabit şablondan gelir, dolayısıyla promptun istediği çıktı-şeması denetimi
*ek* güvenlik olur, *tek* güvenlik değil. Bedeli kullanıcıya **gösteriliyor**:
"bu sürüm adayları kalıp eşleşmesiyle çıkarır; anlamsal çıkarım yoktur, bu
yüzden bir odadaki her fırsat görülmez."

## Sekiz öğe yapısal olarak zorunlu

`SourceQuote`, `EffortEstimate` ve `WorkCandidate`'in `__post_init__`'leri
kurulumu reddediyor (`EvidenceRef` kalıbı), yani **eksik bir aday hiç var
olamıyor**. `EffortEstimate.label` sabit `"tahmin"` — çağıranın
düşürebileceği bir parametre değil. `budget_state` `NOT_IMPLEMENTED`'dan
başka bir şey olamıyor. Sekizinci öğe `OpenStateNote` ve **hiçbir yerinde
boolean yok**; yalnız "şu ana kadar okunanda kapanış işareti görülmedi
(snapshot …)" cümlesi var. UI'da da "açık/kapalı" rozeti yok ve bir test
bunu tarıyor.

Altı yasak biçim (wallet/ödeme, puan kasma, spam ping, boş "done", kendini
onaylama, duplicate teslimat) **sinyallerden önce** eşleşiyor, yani ikisini
birden taşıyan bir satır reddediliyor; duplicate ayrıca `candidate_id =
domain_digest(domain, room, seq)` ile yapısal.

**İncelikli dedup kararı:** aday içeriğine sekizinci öğenin **şablonu**
giriyor, işlenmiş cümlesi değil. Okuma zamanını dahil etmek aynı satıra her
bakışta yeni bir `source_version_id` verir ve "içerik değişince kanıt
eşleşmez" kuralını "saat ilerleyince eşleşmez"e çevirirdi (IMP-397).

## Okuma yüzeyi

Dördüncü kapalı registry: yalnız `GET /rooms` ve `GET /r/{room}`.
**`/r/events` kapsam dışı** — openapi `parameters: null` diyor, sözleşme
yalnız düzyazıda; bir test yokluğunu iddia ediyor. `SOURCES` **değişmedi**
ve bu paketten yeniden pinlendi (`len(SOURCES) == 6`, `set(SourceId)`).
Belgeye şu da kaydedildi: yanındaki `"/r/" not in source.path` iddiası
`/rooms`'u **yakalamazdı** — korumayı gerçekten sağlayan satır küme
eşitliğidir.

Beşinci istemci kendi imzasını taşıyor (`fetch_room_index`,
`fetch_room_messages`); bir test `ReadOnlyTechnocoreClient.fetch(self,
source)` imzasının değişmediğini ve yeni istemcinin `fetch`'i **hiç**
olmadığını pinliyor. İki yenilik var:

- **İlk kez sorgu dizesi gönderiliyor**, bu yüzden `assert_allowed_url`
  artık **zaten sorgu taşıyan** bir URL'i reddediyor — hazır bir sorgu,
  birisinin adres birleştirdiği anlamına gelir.
- **Başarı ölçütü status değil `Content-Type`**: `format=json` tavsiyedir,
  yok sayılan bir değer 200 döndürüp `text/plain` bırakır ve bu kendi
  hatasını alır.

`limit` gönderilmeden önce 1..200'e clamp ediliyor (asla reddedilmiyor);
negatif `since` sunucunun "geçersiz = en yeniler" davranışına
bırakılmıyor, reddediliyor; `wait` ve `n` **hiç gönderilmeyenler**
listesinde ve paketin string literal'lerinde de yok (AST ile denetleniyor).
Oda adı yazma yolunun aynı politikasından geçiyor — `DENIED_ROOMS` (lobby,
meta) **okumada da** geçerli.

## Polling yok, bayatlık uydurulmuyor

Zamanlayıcı, arka plan görevi ve `wait` yok; yenileme yalnız açık kullanıcı
eylemiyle. UI'da tek bir istek tıklamasız atılıyor (durum okuması) ve bir
test hiçbir zamanlayıcı kurulmadığını hem çalışma anında hem kaynak
taramasıyla doğruluyor. Kapsam **kullanıcının işaretlediği odalar**; bir
test tam olarak onların tarandığını iddia ediyor.

Bayatlık için **eşik uydurulmadı** ve `is_stale` diye bir alan yok. Etiket
her snapshot'ta ölçülen okuma anını **ve** sunucunun kendi
`ROOMS_CACHE_SECONDS = 3` beyanını taşıyor. Tarama yanıtının kendi
beyanlanmış sınırı olmadığı ayrıca yazılıyor — oda listesinin sayısı ona
**ödünç verilmiyor**. Bir test hiçbir yerde "bayatlamış/taze/güncel değil"
hükmü olmadığını doğruluyor.

## Otorite seviyesi ve uzak içerik

Üçüncü seviye (`community`) tanımlandı: yollar seviye 1, **içerikleri
seviye 3**. `from` `did:key` değilse "kendi beyan ettiği takma ad" diye
gösteriliyor. `topic`'in dünyaya yazılabilir bir not olduğu ve **onay
olmadığı** yazılı. Alıntılar `<pre>` içinde tıklanamaz düz metin — HTML veya
link olarak render edilmiyor (SI-54).

## Durum makinesi

`SUGGESTED` `PRODUCIBLE_STATES`'e eklendi; `RUNNING`/`PAUSED` üretilemez
kaldı. **`INITIAL_STATE` `AWAITING_APPROVAL` kaldı** ve
`test_the_initial_state_is_not_suggested` korunup güçlendirildi. İki üretici
var: `open_task` tarama kaynağını reddediyor, `suggest_task` tarama-dışı
kaynağı reddediyor; ikisi de başlangıç durumunun seçildiği **tek** özel
yardımcıya devrediyor. `TaskSourceId.PUBLIC_ROOM_SCAN` eklendi, yani
kullanıcının kendi görevi ile taranmış aday **hem kaynak kimliğiyle hem
başlangıç durumuyla** ayrışıyor.

Paket F'nin elle yazılmış oracle'ları gerekçesiyle birlikte güncellendi;
davranışsal yürüyüş yeni oracle'a inanmadan önce `suggested`'a **gerçek
servis üzerinden ulaşmak** zorunda.

## Mutasyon kontrolü

| Mutasyon | Sonuç |
|---|---|
| `assert_no_forbidden_claim` gövdesi `return None` | **2 kırmızı** |
| `WORK_SCAN_FORBIDDEN_PHRASES` → `()` | **6 kırmızı** |
| `targets.py` literal'ine yasak ifade yerleştirildi | **1 kırmızı**, dosya ve satır adıyla |

Yasak-ifade registry'si Paket E'nin altı ifadesini miras alıp yedi tane
ekliyor; katlama `evidence/language.py`'den yeniden kullanılıyor ve testler
yazımları **bağımsız** üretiyor.

## Testler ve kapılar (birleşik ağaç, orkestratör koşusu)

| Kapı | Sonuç |
|---|---|
| pytest | **1769 geçti** (1555 → 1692 → inceleme düzeltmeleriyle 1769) |
| Vitest | **256 geçti** (233 → 256) |
| Playwright (e2e) | **58 geçti** (53 → 58) |
| ruff (iki koşu) / mypy strict | geçti / 114 dosya 0 hata (incelemeci kendi ağacında 112 ölçtü; fark çağrı kökünden gelir) |
| eslint / build | geçti / geçti |
| `git diff --check` | 0 |

Yeni HeroUI bileşeni **yok** — küme 11'de kaldı, A1-R1 yeniden açılmadı.
`App.test.tsx`'in `never shows a section that is not ready` testi **bayt
bayt aynı**; yalnız verisi güncellendi. Klavye sırası testine bir `Tab`
adımı eklendi, çünkü yeni bölüm araya giriyor — orada eksik bir durak
yalnız-fareyle-erişilen bir bölüm demek olurdu.

## Kalan riskler

1. **Ring düşüşü telde yok.** `WorkScanRingDrop` şemada var ama hiçbir
   route onu yaymıyor ve servis imleçli okuma yapmıyor, yani sunucu sinyali
   hiç üretmiyor. Alan **uydurulmadı**; ayrı uyarı neden yok olduğunu
   söylüyor. İmleçli okuma açılırsa alan ve sunumu **birlikte** gelmeli.
2. **Kibble'ın iki İngilizce cümlesi frontend'de ikinci bir kopya** — tel
   yalnız Türkçe açıklamayı taşıyor, dolayısıyla `kibble.py`'den sapabilir.
3. **Tarama süresi 10 oda için ~6,8 dakikaya çıkabilir** ve iptal kontrolü
   yok (uygulama genelinde mevcut bir boşluk). Kısa bir deadline alternatifi
   `timeout` deyip sunucunun oda-başına hata listesini **atardı**, ki bu
   daha kötü.
4. **Sinyal tablosu dört tanıyıcı** ve elle yazılmış Türkçe/İngilizce
   işaretlerden ibaret. Bilinçli olarak kaba; dürüstlük cümlesi bunu
   kullanıcıya söylüyor — ama gerçek recall düşük ve **hiçbir test bunu
   ölçemez**.
5. `MAX_ROOMS_PER_SCAN = 10` seçilmiş bir sayıdır, yayımlanmış bir limitten
   türetilmedi; okuma kotası (120/dk/IP) belgeli ama istemci tarafında
   zorlanmıyor.
6. e2e spec'i `/api/workscan/*`'ı tamamen mock'luyor, yani yalnız render ve
   etkileşimi kanıtlıyor.
7. İnsan güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5).

## Bağımsız inceleme sonucu

Temiz bağlamlı, yazardan ayrı bir Claude reviewer subagent'ı head `d97ca0b`
diffini inceledi, kapıları kendi koştu ve probları **fiilen çalıştırdı** —
kendi sayaçlarını hem httpx taşıyıcısına hem `socket.connect`'e takıp sıfır
kaçış ölçtü, yani bu incelemede de hiçbir istek makineyi terk etmedi.

### P1 — yanıt, taramanın kapsamını yeniden adlandırabiliyordu

Aday üzerindeki `room` **sunucunun yanıtından** okunuyor ve istenen odayla
hiç karşılaştırılmıyordu. İncelemeci `demo-room` isteyip her yanıtta
`{"room": "lobby"}` döndürdü:

```
URL actually requested   : .../r/demo-room?limit=50&format=json
response last_scan.rooms : ['lobby']
candidate.source.room    : lobby
candidate.source.reference: lobby#7@2026-01-01T00:00:00Z
```

Yani projenin hiçbir kabiliyette adını anmayacağına söz verdiği oda, uzak
bir belgenin iddiasıyla ekrana gelebiliyordu. Dahası **kimlik de sunucu
kontrollüydü**: iki farklı oda aynı `room`+`seq` iddia ettiğinde **aynı
`candidate_id`** çıkıyor ve gerçekten farklı iki satır tek adaya çöküyordu —
"duplicate yapısal olarak engellenir" iddiası, anonim belgenin dürüstlüğü
kadar güvenilirdi. Bunu tutması gereken test yalnız **istek sayısını**
ölçüyordu, kapsam iddiasını değil.

Düzeltme: `parse_room_messages` çözümlenmiş odayı **zorunlu anahtar
argüman** olarak alıyor (varsayılan yok — varsayılan, unutmanın bir yoludur)
ve uyuşmayan belgeyi **reddediyor**. Yeniden etiketlemek yerine reddetmek
seçildi: başka bir odayı adlandıran içerik gerçekten *o odanın* olabilir,
onu istenen ad altına dosyalamak iki yalandan kötüsü olurdu. Ret mesajı
iddia edilen adı **yankılamıyor** — `lobby`'yi ekrandan uzak tutan kontrol
onu basmamalı.

### Diğer bulgular

| Bulgu | Düzeltme |
|---|---|
| **P2:** `adapter_written`/`contacted` mutasyonları **0 test** kırmızıya döndürüyordu; guard sanılan test aslında bir **şema sabitini** yeniden iddia ediyordu ve asla kırılamazdı | Route artık kaydın özelliklerini `Literal[False]` döndüren, doğru olanı serialize etmek yerine **fırlatan** bir yardımcıdan okuyor; ayrıca kaydın kendisi doğrudan iddia ediliyor. Mutasyonlar artık **23'er test** öldürüyor |
| **P2:** altı yasak iş biçimi "yapısal" değil, kaba alt dize işaretiydi — **27 kaçıştan 19'u** kapıyı atlatıp gerçek aday üretti (araya boşluk, zero-width, Kiril harfi, tire, eş anlamlılar) | İki yarım birden: `fold()` artık Unicode `Cf` karakterlerini siliyor ve Kiril/Yunan benzerlerini Latin karşılıklarına eşliyor; **ek olarak** kelime-içi ayırıcıları da kaldıran bir `tighten()` yalnız **yasak kapısında** eşleştiriliyor. Ayırıcı silme bilinçle `fold()`'un içine konmadı: `tighten` kelime sınırlarını kaybeder ve bu, yanlış pozitifin bedeli "bir satır gerekçesiyle reddedilir" olan yerde doğru, kullanıcının **kendi sözlerinden metin çıkaran** nötrleme yolunda yanlış takas olurdu. Ve iddia gerçeğe indirildi: ADR ve belge artık "kalıp eşleşmesi" diyor, **kullanıcıya gösterilen ayrı bir dürüstlük cümlesiyle** birlikte |
| **P2:** `RoomScanTarget` doğrulanmamış kurulabiliyordu ve `DENIED_ROOMS` giden yolda yeniden kontrol edilmiyordu — elle kurulmuş bir hedefle `lobby`/`meta` isteği transport'a ulaşıyordu | `__post_init__` ad kalıbını, `DENIED_ROOMS`'u ve anlaşılan sınıfları yeniden uyguluyor; `assert_allowed_url` de oda politikasını kontrol ediyor. `assert_allowed_query` artık katlanmış eşleşiyor (`{"WAIT": "30"}` geçiyordu) |
| **P2:** `ts` alanı olmayan **tek bir mesaj** on odalık taramayı **HTTP 500** yapıp okunmuş her odayı çöpe atıyordu | Doğru katmanda düzeltildi — **satır başına**: `CandidateError` görünür bir `unusable_source` reddine dönüşüyor, diğer dokuz oda hayatta kalıyor. Servis ve route yedekleri de eklendi ve bugün erişilemez oldukları için **açık hata enjeksiyonuyla** sürülüyorlar |
| **P3:** `WorkCandidate.__post_init__`'in beş cümlelik `missing` döngüsü ve `if not self.id` kontrolü **hiçbir şeyle** kapsanmıyordu (mutasyonda yalnız 3 kırmızı) | Kapsandı; mutasyonlar artık **15** ve **1** test öldürüyor |
| **P3:** tekrarlanan `seq` bir satırı **sessizce** düşürüyordu | Görünür `duplicate_sequence` reddi |
| **P3:** zamanlayıcı/long-poll taraması route katmanını kaçırıyordu | Kapsama alındı |
| **P3:** "servisin kendi iki cümlesi birebir taşınıyor" **yanlıştı** — tel yalnız Türkçe açıklamayı taşıyordu, iki İngilizce cümle yalnız frontend sabitlerinden geliyordu | Cümleyi indirmek yerine **tel genişletildi**: iki alıntı da yanıtta; frontend'in elle yazılmış kopyaları silindi. İki yerde tutulan bir alıntı, kimsenin diff'lemediği kopyada sapar |

### Mutasyon kontrolü: 13 mutasyon, **13'ü de öldürüldü**

Oda uyuşmazlığı kontrolü (4), `adapter_written` (23), `contacted` (23),
`tighten()` (10), `fold()` sertleştirmesi (8), `RoomScanTarget.__post_init__`
(2), URL oda kontrolü (1), `assert_allowed_query` (1), satır başına
`except` (2), oda başına `except` (1), route `except` (1), `missing`
döngüsü (15), `if not self.id` (1), sessiz duplicate (2).

### Kararsız test (ayrı bulgu)

`d97ca0b`'de determinizm testi iki `now()` çağrısının **farklı** olmasını
iddia ediyordu; incelemeci ardışık iki türetimin **%78,3** oranında aynı
`read_at`'e düştüğünü ölçtü ve testi iki tam koşuda kırık gördü. Yani
"1692 geçti" iddiası bir koşu için doğruydu ama tekrarlanabilir değildi.
`c62d73c` bunu düzeltti: saat **oynatılıyor**, yarıştırılmıyor.

### Kıramadıkları

Açılışta **sıfır** giden istek (kendi sayaçlarıyla, `create_app` ve lifespan
dahil); kapsam gövdedir (25 oda → 10 istek, 30 tekrar → 3, işaretsiz → 0);
oda adı enjeksiyonunun **17 denemesi** kapalı; `limit` clamp'i; TLS/redirect/
boyut/`Retry-After`; `Content-Type` kapısının 11 varyantı; `wait`/`n`'in hiç
tele çıkmaması; durum makinesi (`INITIAL_STATE` değişmemiş, `running`/
`paused` üretilemez, davranışsal yürüyüş yeni üreticiyi kapsıyor); sekizinci
öğede hiçbir boolean olmaması (`object.__new__` ile sahtelenmiş bir aday bile
`Literal`'ları değiştiremiyor); bayatlıkta hiçbir hüküm bulunmaması; yasak
ifade denetiminin uzak metni nötrlemesi; ve `tests/` altında **yalnız
ekleme** olması.

Düzeltmeler sonrası tam suite: **1769 pytest** + **256 Vitest** +
**58 Playwright**.

Bu inceleme bir **insan güvenlik incelemesi değildir** (ADR-0001 §5).

## Sınırlar

Uygulama boyunca Technocore'a, Kibble'a veya başka bir servise **hiçbir
istek gönderilmedi**; her test `MockTransport` ile iki katmanlı ağ kesici
altında koştu. Gerçek DID/kasa/recovery/API anahtarı okunmadı; lobby hiçbir
testte hedef olmadı; yeni bağımlılık yok; pin (`7707cb63`) ve beklenen
sürüm değişmedi; tag/release/deploy yok.
