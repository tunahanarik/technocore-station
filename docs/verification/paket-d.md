# Paket D doğrulama raporu — Composer & Participation

Tarih: 2026-09-03 · Taban: `0bed0fcc2bf5ae5e18b5939fab9f366210d65431` (Paket C merge'ü)

Kapsam kararları: [`ADR-0002`](../decisions/0002-paket-d-kapsam-kararlari-2026-09-03.md).
Bu paket **AC-13** ve **AC-16**'yı karşılar; AC-14 Paket E'dedir (ADR-0002 §4.3).

## Kapsam kararı: yalnız mesaj lane'i

Keşif, künye ile pinli protokol arasında gerçek bir çelişki buldu. Pinli
`openapi.json` note lane'inin `sig` açıklaması birebir:

> "Only the `room-owners` and `room-allow` namespaces take a signed write;
> every other one is world-writable and refuses it."

Künyenin istediği DID profile note'u ise imzasız lane'de yayımlanıyor.
İmzasız bir yazma **imza kanıtı üretemez**; onu "gönderildi" rozetiyle
sunmak künyenin ve `evidence-model.md`'nin yasakladığı kanıt-seviyesi
karıştırması olurdu. Bu yüzden Paket D yalnız `POST /r/{room}` mesaj
lane'ini uygular; note gönderimi kapsam dışıdır ve UI bunu dürüstçe yazar.
`canonical_note`/`sweep_note_value` conformance testleriyle korunmaya
devam eder.

## Onay zinciri

Üç adım, üç ayrı istek — canonical string nonce'u içerdiği için nonce
canonical'dan önce ayrılmak zorunda:

| Adım | Ne olur |
|---|---|
| `POST /api/compose/draft` | Sweep; swept metin, görünmez-karakter farkı, etkin limitler, `draft_digest`. **Nonce yok, imza yok.** |
| `POST /api/compose/sign` | Gate yeniden koşar; nonce transaction içinde ayrılır; canonical kurulur; seed kısa süre açılıp imzalanır, imza **kendi kendine doğrulanır**, seed sıfırlanır; tek kullanımlık `send_token`. |
| `POST /api/compose/send` | Gate yeniden koşar; token atomik olarak harcanır; gövde yeniden kurulup yeniden doğrulanır; **tek** POST. |

`send_token` şunlara bağlıdır: canonical bayt digest'i, oda, ayrılan nonce,
DID, imza anındaki **manifest verdict kimliği** ve oturum. TTL 180 sn.
Yeni bir manifest denetimi yeni bir verdict kimliği üretir, dolayısıyla
bekleyen bir onayı geçersiz kılar — fail-closed okuma. Gate'in üç adımda da
koşulduğu, çağrı sayılarak iddia edilir (yalnız UI disable'a güvenilmez).

Metin veya oda değişince onay düşer: UI'da `send_token` yalnız bileşen
state'inde yaşadığı için düzenlemeden sonra eski baytları yayımlayabilecek
hiçbir şey kalmaz.

## Nonce

Rezervasyon tablosunun **kendisi** sayaçtır; kayabilecek ayrı bir "son
değer" satırı yoktur. Sonraki değer = `max(çift için MAX(nonce)+1,
ms_saati)`, `with Session(engine) as session, session.begin():` içinde
hesaplanıp yazılır — imzadan önce. `str(int)` ile yazıldığı için başında
sıfır olan nonce temsil edilemez (ADR-0002 §4.2: `"007"` ile `"7"` sunucuda
aynı sayı ama farklı imzadır). Tavan `min(10^19-1, 2^63-1)`; tükenme
istisna fırlatır ve satır yazmaz.

İki ayrı soruya iki ayrı koruma: process kilidi (tek Station'da iki tık) ve
`UNIQUE(did, room, nonce_value)` (aynı dosyada ikinci process). Constraint
reddi sınırlı bir yeniden okumayı tetikler — bu **yerel** bir yazma
çakışmasıdır, giden bir tekrar değildir. Gerçek thread'lerle kanıtlandı:
tek sayaç üzerinde 16×12 rezervasyon, ve engine'i paylaşan iki bağımsız
reserver ile 25+25.

## Üç sonuç durumu

| Sonuç | Koşul |
|---|---|
| `accepted` | 2xx |
| `refused` | 400, 403, 413, 422 — yazmadığı kanıtlanan |
| `outcome_unknown` | timeout, taşıma hatası, bozuk yanıt, 3xx, 429, 5xx |

Tekrar döngüsü, backoff, `Retry-After` **yok**; hem davranışsal (tek
deneme) hem yapısal olarak (AST taraması) iddia edilir. Nonce istekten
**önce** harcanmış işaretlenir; üç sonuçta da yanmış kalır. UI
`outcome_unknown`'ı "gönderildi" veya "başarısız" diye sunmaz ve **retry
kontrolü göstermez**; uzlaştırmanın bu sürümde açık olmadığını yazar.

## Vacuous test bulgusu (bu paketin yan ürünü)

`test_no_outbound_write_route_exists_even_when_every_check_passes` **hiçbir
şey denetlemiyordu**: FastAPI'nin bu sürümü dahil edilen router'ları `path`
taşımayan `_IncludedRouter` nesnelerine sarıyor, dolayısıyla
`{getattr(route,"path","")}` boş string'leri kıyaslıyordu — üç güvenlik
testi boşa koşuyordu. Artık `collect_route_paths()` özyinelemeli topluyor ve
her çağıran ayrıca **bilinen** bir yolun listede olduğunu iddia ediyor;
test bir daha sessizce körleşemez. Yeni iddia yazma taşıyıcısını doğrudan
izliyor: kapılar açık, manifest güncel, her okuma yüzeyi yoklanmış — sıfır
giden yazma.

## Test emniyet ağı

Bugüne kadar hiçbir mekanizma, `MockTransport` enjekte etmeyi unutan bir
testin `technocore.chat`'e çıkmasını engellemiyordu. Artık autouse bir
fixture gerçek giden taşıyıcıyı (sync ve async) devre dışı bırakıyor;
loopback açık kalıyor ki `tests/integration` çalışsın. Fırlatılan istisna
bilinçli olarak httpx hiyerarşisinin **dışında** bir `AssertionError`
alt sınıfı — aksi halde okuma istemcisi onu `unavailable`, yazma istemcisi
`outcome_unknown` diye yutardı. Guard-the-guard testleri yamanın kurulu
olduğunu ve mock'suz her iki istemcinin de gürültüyle kırıldığını doğrular.

## Testler ve kapılar (birleşik ağaç, orkestratör koşusu)

| Kapı | Sonuç |
|---|---|
| pytest | **1009 geçti** (823 → 1009) |
| Vitest | **155 geçti** (130 → 155) |
| ruff (iki koşu) | geçti |
| mypy strict | `mypy src` **61 dosya** / `mypy --config-file` (CI) **63 dosya** — ikisi de 0 hata |
| eslint / build (tsc+vite) | geçti / geçti |
| `git diff --check` | 0 |

Backend tarafında 176, frontend tarafında 25 yeni test. Promptun zorunlu
listesi eksiksiz karşılandı: onaysız / süresi geçmiş / yeniden kullanılmış /
başka taslağa ait / başka oturuma ait onay, çift tıklama (gerçek thread
yarışı, tam olarak bir gönderim), nonce yarışları, stale verdict, swept
metin değişimi, sınır ve aşırı payload, yanlış imza (86 karakterlik
canonical sahtecilik + yanlış anahtar), kayıp yanıt, kabul-ama-geri-okuma-
başarısız, oturum sonu, ağ istisnası. İmza doğrulaması ayrıca vendor
oracle'ına karşı diferansiyel olarak koşuluyor.

Mevcut testler **silinmedi, güçlendirildi**: httpx import allow-list'i iki
incelenmiş istemciye genişletildi (okuma yolu yazma istemcisini import
edemez), yazma registry'si aynalandı, `test_no_code_path_can_reach_a_technocore_write_endpoint`
**değişmeden** yeşil kaldı (POST lane'i GET markerlarını taşımıyor) ve
bunun nedeni docstring'e yazıldı.

## Bilinçli ertelenenler ve kalan riskler

1. **Gerçek servise hiç yazma yapılmadı.** Bütün sonuçlar mock'a karşı
   üretildi. İlk gerçek gönderim hâlâ incelenmemiş bir adımdır; insan
   güvenlik incelemesi zorunludur (ADR-0001 §5).
2. **`outcome_unknown`'ın çıkışı yok.** Uzlaştırma oda okumayı gerektirir;
   bu paket o yolu bilinçli olarak açmaz. Durum olduğu gibi gösterilir.
3. **Ne gönderildiğinin kaydı yok.** Sonuç alanı yeniden yüklemede kaybolur;
   kanıt defteri (AC-14) Paket E'dedir ve tarayıcı depolaması yasaktır.
4. **Nonce tabanı saatin kabaca doğru olmasını varsayar.** Çok ileri
   kurulmuş bir saat o `(did, room)` için geniş bir aralığı kalıcı yakar;
   monotonluk bozulmaz, aralık geri alınamaz.
5. **Seed sıfırlama best-effort** (CPython kopyalamış olabilir) —
   `identity-lifecycle.md` §6'daki dürüst sınır aynen geçerli.
6. **Process'ler arası nonce güvenliği `UNIQUE` kısıtına dayanır**,
   `BEGIN IMMEDIATE`'e değil; iki gerçek OS process'i test edilmedi.
7. **Tarayıcı QA yok** (ADR-0001 m.4): geri sayım, `aria-describedby`
   bağlantısı ve `TextField`+`TextArea` bileşimi yalnız jsdom'da kanıtlı.
8. `meta` odasının `lobby` ile birlikte reddi Station'ın kendi
   sıkılaştırmasıdır, protokol zorunluluğu değildir (ADR-0002 §4.1).

## Bağımsız inceleme sonucu

(PR üzerinde doldurulacak — temiz bağlamlı reviewer subagent koşulacak; bu
insan güvenlik incelemesi değildir, ADR-0001 §5 kalan risk.)

## Sınırlar

Gerçek DID/kasa/recovery okunmadı; Technocore'a hiçbir istek gönderilmedi
(testler mock taşıyıcı ile, autouse ağ kesici altında koştu); lobby hiçbir
testte hedef olmadı; yeni npm/Python bağımlılığı yok; pin (`7707cb63`) ve
beklenen sürüm değişmedi; tag/release/deploy yok; PR #7'ye dokunulmadı.
