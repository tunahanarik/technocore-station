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
| pytest | **1692 geçti** (1555 → 1692; +138) |
| Vitest | **255 geçti** (233 → 255) |
| Playwright (e2e) | **58 geçti** (53 → 58) |
| ruff (iki koşu) / mypy strict | geçti / 114 dosya 0 hata |
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

(PR üzerinde doldurulacak — temiz bağlamlı reviewer subagent koşulacak; bu
insan güvenlik incelemesi değildir, ADR-0001 §5 kalan risk.)

## Sınırlar

Uygulama boyunca Technocore'a, Kibble'a veya başka bir servise **hiçbir
istek gönderilmedi**; her test `MockTransport` ile iki katmanlı ağ kesici
altında koştu. Gerçek DID/kasa/recovery/API anahtarı okunmadı; lobby hiçbir
testte hedef olmadı; yeni bağımlılık yok; pin (`7707cb63`) ve beklenen
sürüm değişmedi; tag/release/deploy yok.
