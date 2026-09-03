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
**yeni HeroUI bileşeni kullanılmadı** (kanıtlı 9 bileşen korundu — CSP
inline-style hash riski A1-R1 tetiklenmedi). Router/URL senkronu bilinçli
yok: yeni bağımlılık yasağı; "derin link yok" `docs/ui-action-map.md`'de.

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
  `http_<status>`), `kind` (timeout / network / malformed / auth /
  rate_limited / unavailable / server / request — bozuk yanıt ile bağlantı
  kesilmesi ayrık), `requestId` (32-hex doğrulanır, yoksa null),
  `userMessage` (güvenli Türkçe), `retryable`.
- `ErrorRegion`: kalıcı, `role="alert"` hata alanı (kaybolan toast'a
  güvenilmez); kod + HTTP + requestId satırı; kind'e göre kurtarma eylemi;
  **redakte** "Tani bilgisini kopyala" — yalnız
  {code, status, kind, request_id, timestamp, section}; DID/URL/payload/
  parola/dosya yolu taşımadığı testle kanıtlı.
- `catch {}` / yalnız-console hata yutumu kalmadı; bütün mutasyon
  butonlarında pending etiketi + çift-tık koruması.

## Testler ve kapılar (birleşik ağaç, orkestratör koşusu)

| Kapı | Sonuç |
|---|---|
| pytest | **814 geçti** (804 + yeni `tests/security/test_error_contract.py` 10) |
| Vitest | **115 geçti** (59 → 115; ErrorRegion 15, nav/aria/klavye, timeout sınıflandırma, redaksiyon, Genel Bakis kompozisyonu, çift-tık, boş durumlar) |
| ruff (iki koşu) / mypy strict | geçti / 53 dosya 0 hata |
| eslint / build (tsc+vite) | geçti / geçti |
| `git diff --check` | 0 |

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

(PR üzerinde doldurulacak — temiz bağlamlı reviewer subagent koşulacak; bu
insan güvenlik incelemesi değildir, ADR-0001 §5 kalan risk.)

## Sınırlar

Gerçek DID/kasa/recovery okunmadı; Technocore'a istek yok; yeni npm/Python
bağımlılığı yok; uzak font/CDN yok; pin (`7707cb63`) ve beklenen sürüm
değişmedi; tag/release/deploy yok; PR #7'ye dokunulmadı.
