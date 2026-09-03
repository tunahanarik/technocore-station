# Paket C doğrulama raporu — Dashboard kabuğu ve hata sözleşmesi

Tarih: 2026-09-03 · Taban: `277a97c888e5c7b4f923c0062608b7a2a2e2cb14` (Paket B merge'ü)

## Kapsam ve dayanak

ADR-0001 madde 2 üç-sekme sınırını kaldırdı; hedef, kullanıcının HeroUI
referans görselindeki düzene uygun sol navigasyonlu dashboard. Uçtan-uca
promptun §7 tablosu 9 bölümü adlandırır; §7 ayrıca "boş bölümler uygulamaya
hazır olmadan görünmesin" der. Bu ikisi birlikte şöyle uygulandı:

- `src/sections.ts` **9 bölümün tamamını** kayıt altına alır (id, etiket,
  amaç, `ready` bayrağı).
- `Is Tara` (H1), `Gorevler` ve `Aktivite` (H2) `ready: false` — nav'da
  **hiç görünmezler**; paketleri geldiğinde bayrak açılacak.
- Görünen 6 bölüm: **Genel Bakis** (yeni kompozisyon sayfası),
  **Kimlik ve Guvenlik** (mevcut Identity yüzeyi), **Olustur ve Dogrula**
  (mevcut kilitli Compose yüzeyi), **Kaynaklar** (Technocore kaynak paneli
  buraya taşındı), **Kanitlar** (güven seviyeleri + Paket E'yi adlandıran
  boş durum), **Ayarlar ve Yardim** (tema, servis bilgisi, write-gate
  özeti, Paket G/J dürüst notu).

Navigasyon düz `<nav aria-label="Ana bolumler">` + Button ile kuruldu;
**yeni HeroUI bileşeni kullanılmadı** — CSP inline-style hash riski A1-R1
tetiklenmedi. HEAD'de kaynak ağacı **10 ayrı HeroUI bileşeni** import eder:
`Alert`, `Button`, `Card`, `Checkbox`, `Chip`, `Input`, `Label`, `Modal`,
`Separator`, `TextField`. (Rapor önce "9" diyordu; sayı yanlıştı, iddia
değil.) ADR-0001 m.2 ile **`Tabs` düştü** ve geri gelmedi; başka hiçbir
bileşen eklenmedi veya çıkarılmadı. Sayı artık bir allowlist testiyle
sabittir: `src/heroui-surface.test.ts` bütün `@heroui/react` import'larını
tarayıp beklenen 10'luk kümeye eşitler ve `Tabs`'ın yokluğunu ayrıca
doğrular — yani yeni bir bileşen sessizce giremez.

Router/URL senkronu bilinçli yok: yeni bağımlılık yasağı; "derin link yok"
`docs/ui-action-map.md`'de.

## Hata/loading/timeout sözleşmesi

Tam sözleşme [`docs/ui-action-map.md`](../ui-action-map.md) başındadır; özet:

**Backend (additive — hiçbir mevcut `detail` değeri değişmedi):**

- Her yanıt `X-Station-Request-Id` taşır (istek başına `uuid4().hex`).
  Middleware reddi (403/421) dahil; `RequestIdMiddleware`, SecurityHeaders'ın
  hemen içinde.
- İşlenmeyen istisna zırhı: gövde tam olarak `{"detail": "internal_error"}`,
  500, traceback yalnız sunucu loguna request id anahtarıyla. Starlette'te
  `Exception` handler'ı `ServerErrorMiddleware`'de (SecurityHeaders'ın
  DIŞINDA) koştuğu için zırh sertleştirme başlıklarını paylaşılan
  `apply_security_headers` yardımcıyla kendisi uygular (IMP-260) — testle
  kanıtlı.

**Frontend:**

- `request()` `AbortSignal.timeout` taşır (15 sn; Technocore refresh 30 sn;
  recovery export'un elle fetch'i dahil). Yeni bağımlılık yok.
- `ApiError` geriye uyumlu genişledi: `code` (backend makine kodu ya da
  `http_<status>`), `kind` (timeout / **canceled** / network / malformed /
  auth / rate_limited / unavailable / server / request — bozuk yanıt ile
  bağlantı kesilmesi ayrık), `requestId` (32 **küçük harf** hex doğrulanır,
  yoksa null), `userMessage` (güvenli Türkçe), `retryable`.
- Zaman aşımı iddiası artık sinyale bakar: `timeout` yalnız **kendi**
  `AbortSignal.timeout` sinyalimiz tetiklendiğinde verilir; başka bir sebeple
  iptal edilen istek `canceled` olur. Ürünün bugün bir iptal düğmesi yok ve
  bu `ui-action-map.md` §1.5'te açıkça yazılı.
- `ErrorRegion`: kalıcı, `role="alert"` hata alanı (kaybolan toast'a
  güvenilmez); kod + HTTP + requestId satırı; kind'e göre kurtarma eylemi;
  **redakte** "Tani bilgisini kopyala" — yalnız
  {code, status, kind, request_id, timestamp, section}; DID/URL/payload/
  parola/dosya yolu taşımadığı testle kanıtlı. "Yeniden dene" butonu da
  `retryPending` ile disabled + "Yeniden deneniyor..." olur; altı çağıranın
  hepsi kendi loading durumunu geçirir (`SettingsHelpPage`'e bu pakette
  loading durumu eklendi, `AppShell` mevcut `loading`'i bağladı).
- Kimlik dialoglarının beş hata yüzeyi de artık `ErrorRegion` kullanır:
  kimlik oluşturma, recovery export/inspect/adopt, restore-test ve revoke
  hataları `Kod:/HTTP:/Istek:` satırını ve redakte kopyalamayı taşır.
- `catch {}` / yalnız-console hata yutumu kalmadı; ham JS mesajı da
  kullanıcıya sızmaz: `ApiError` olmayan istisna `unexpected_error` /
  `kind=request` olarak sınıflanır. Bütün mutasyon butonlarında pending
  etiketi + çift-tık koruması.
- Daraltılmış sol menü `<nav>` landmark'ını ve bölüm adlarını korur
  (etiket baş harfe iner, erişilebilir ad `sr-only` olarak tam kalır);
  toggle `aria-expanded` yanında `aria-controls` taşır.

## Testler ve kapılar (birleşik ağaç, orkestratör koşusu)

| Kapı | Sonuç |
|---|---|
| pytest | **823 geçti** (804 + hata sözleşmesi 10 + inceleme düzeltmeleri 9) |
| Vitest | **130 geçti** (59 → 115 → 130; PR #12 bulguları için +15: retry çift-tık koruması, abort/timeout ayrımı, request-id büyük harf reddi, dialog korelasyon kimliği, ham mesaj sızıntısı, daraltılmış nav landmark'ı, HeroUI allowlist) |
| ruff (iki koşu) | geçti |
| mypy strict | `mypy src` **51 dosya**, `mypy --config-file` (CI; testleri de kapsar) **53 dosya**; ikisi de 0 hata |
| eslint / build (tsc+vite) | geçti / geçti |
| `git diff --check` | 0 |

mypy'nin iki sayısı iki ayrı çağrıdır ve depoda geçmişte karıştı (Paket A
raporu 53, Paket B raporu 51 diyordu). Buradaki satır çağrıyı adlandırır;
ikisi de bu ağaçta orkestratör tarafından doğrulandı.

`App.test.tsx` içindeki "tabs, sidebar değil" testi ADR-0001 m.2 gereği
**bilinçli** değiştirildi (yeni iddia: nav landmark + 6 görünür bölüm +
hazır-olmayanlar görünmez + aria-current + klavye). Ürün-kuralı testleri
(dış link yok, yasak kanıt ifadeleri, storage yok, port yok) korundu ve
yeni sayfalara da uygulandı. `tests/security/` altında hiçbir test
silinmedi/gevşetilmedi; 10 test eklendi.

## Bilinçli ertelenenler

- Manuel tarayıcı QA / görsel inceleme ADR-0001 m.4 gereği bu döngüde YOK;
  bütün manuel kabul maddeleri Paket J kullanıcı kılavuzuna taşınacak.
  Yeni UI'nin gerçek tarayıcı davranışı **doğrulanmış sayılmaz**.
- `Is Tara`/`Gorevler`/`Aktivite` bölümleri H1/H2'de; Kanitlar kayıtları
  Paket E'de; OpenCode ayarları Paket G'de dolacak.
- Derin link / URL senkronu yok (kayıtlı karar).

## Bağımsız inceleme sonucu

Temiz bağlamlı, yazardan ayrı bir Claude reviewer subagent'ı head `674c960`
diffini inceledi ve karşı-problarını **fiilen çalıştırdı**: 10 ayrı yanıt
sınıfında request-id taraması (deponun kendi testinin kapsamadığı SPA,
derin-link ve statik yollar dahil), düşmanca bir backend `detail`'iyle
(Windows yolu + DID içeren) redaksiyon probu, streaming route probu, yanıt
gövdesini gömen bir `ResponseValidationError`, jsdom'da tık-spam probu.
Kapıları da bağımsız koştu.

**Kıramadığı iddialar** (özet): istemcinin sahte request-id başlığı
yansıtılmıyor ve kimlikler benzersiz; zırh `HTTPException`'ları yutmuyor
(404/401/422 gövdeleri aynen geçiyor); 500 gövdesi tam olarak
`{"detail":"internal_error"}` ve zincirin dışında üretilmesine rağmen tüm
sertleştirmeyi taşıyor; SecurityHeaders en dışta (SI-33); redakte kopyalama
düşmanca `detail` karşısında bile yalnız altı anahtarı veriyor;
`AbortSignal.timeout` dört yolda da var (elle fetch dahil); `auth` retryable
değil; `ready:false` bölümler DOM'a hiç ulaşmıyor; storage/dış link/
`dangerouslySetInnerHTML`/boş `catch` yok; `tests/security` diff'i 190
ekleme **0 silme**; yeni bağımlılık yok; yanıt modellerine alan eklenmedi.

**Bulgular ve merge öncesi yapılanlar:**

| Bulgu | Durum |
|---|---|
| **P1 (bloklayıcı, gerçek değişmez ihlali):** `RedactingFilter` yalnız log MESAJINI temizliyordu; traceback'i `Formatter.formatException()` sonradan `record.exc_info`'dan üretiyor ve filtre ona hiç dokunmuyordu. Paket C, uygulama katmanında bilerek `exc_info` loglayan ilk yer olduğu için bypass'ı bu paket açtı. Prob, mesaja hiçbir dize yerleştirmeden DID'i, canlı `/session/<token>` yolunu ve `register_secret()` ile **kayıtlı** bir değeri ham yazdırdı; `<redacted>` hiç geçmedi. Starlette handler'dan sonra istisnayı her zaman yeniden fırlattığı için uvicorn aynı traceback'i ikinci kez yazıyordu. | `RedactingFilter` artık `exc_text`'i, `exc_info`'dan üretilen traceback'i ve `stack_info`'yu da redakte eder; hazır gelen `exc_text` de temizlenir; `getMessage()` hatası artık filtreyi kısa devre etmez. Filtre root handler'ın yanı sıra `uvicorn`, `uvicorn.error`, `uvicorn.access`, `uvicorn.asgi` logger'larına **doğrudan** bağlandı (logger filtreleri hiyerarşide miras alınmaz). 7 yeni test iddiasını **formatlanmış handler çıktısı** üzerinde kurar — eski test `record.exc_info`'ya baktığı için bunu asla yakalayamazdı. (SI-127) |
| P2-a `ErrorRegion` "Yeniden dene" çift-tık koruması taşımıyor | `retryPending` eklendi; 6 çağıranın hepsi bağlandı; `SettingsHelpPage`'e loading durumu eklendi; `App.load`'un `loading`'i kabuğa bağlandı |
| P2-b Mutasyon hataları korelasyon kimliği taşımıyor | 5 kimlik dialogu `ErrorRegion`'a geçti; `errorMessage()` yardımcı fonksiyonu (ham `error.message` sızıntısıyla birlikte) kaldırıldı, yerini `toApiError` aldı |
| P3-1 `AbortError` ile timeout ayrılamıyor | `canceled` sınıfı eklendi; sınıflandırma artık kendi sinyalimize bakar; §1.5 iptal yolunun bugün olmadığını açıkça yazar |
| P3-2 `REQUEST_ID_RE` büyük/küçük harf duyarsız | `i` bayrağı kaldırıldı, testle sabitlendi |
| P3-3 Daraltılmış nav landmark'ı unmount ediyor | `<nav>` + bölüm butonları daraltılmışken de kalıyor; toggle'a `aria-controls` eklendi |
| P3-4 Bu rapordaki sayım hataları | mypy 51, HeroUI 10 bileşen (`Tabs` düştü); allowlist testi eklendi |
| P3-5 Harita eksikleri | "Son islem basarisiz oldu" satırı ve `SystemStatusBar` satırı `ui-action-map.md`'ye eklendi |
| P3-6 Akış sonrası istisna görünmez | `ui-action-map.md` §10'a "bilinen sınır" olarak yazıldı (backend koduna dokunulmadı) |
| **P3 (backend):** /api dışı bir yolda 500 `no-store` kaybediyordu | `apply_security_headers(..., no_store=True)`; `NO_STORE_PREFIXES` bilinçli genişletilmedi (statik varlıklar önbelleklenebilir kalmalı), karar çağrı yerine taşındı. (SI-128) |

Düzeltmeler sonrası tam suite: **823 pytest** + **130 Vitest**. P0 yok; tek
bloklayıcı bulgu (P1) merge'den önce kapatıldı ve mutasyon denemesiyle
doğrulandı (düzeltme geri alınınca 9 yeni testten 7'si kırmızıya döndü).

Bu bir **insan güvenlik incelemesi değildir**; ADR-0001 §5 kalan risk olarak
durmaya devam eder.

## Sınırlar

Gerçek DID/kasa/recovery okunmadı; Technocore'a istek yok; yeni npm/Python
bağımlılığı yok; uzak font/CDN yok; pin (`7707cb63`) ve beklenen sürüm
değişmedi; tag/release/deploy yok; PR #7'ye dokunulmadı.
