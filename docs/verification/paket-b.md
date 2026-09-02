# Paket B doğrulama raporu — Aşama 3.1 son kapanış

Tarih: 2026-09-02 · Taban: `65cfc7bf9a64a390849e59c561a066fc3b61831c` (Paket A merge'ü)

## Yeniden üretim (önce-durumu)

12 mutasyon türü × 2 lane = **24 senaryo**, bağımsız bir agent tarafından
mevcut kodda, pinli üretilmiş belgelerin kopyaları üzerinde koşuldu (canlı
sunucunun bu şemaları yayımladığı iddia edilmiyor). **24/24 yanlışlıkla
`current` üretiyordu; hiçbir alan ateşlenmiyordu.** Ortak kök nedenler:

1. `.get(...) is None` kalıpları şema ÜYELERİNDE JSON null'u yoklukla
   eşitliyordu (#1–4) — modülün kendi `_Absent` ilkesine aykırı.
2. `_judge_constraint` yalnız "tümü dışlandı mı / aralık boş mu" soruyordu;
   "meşru değerlerin BİR KISMI dışlandı mı" hiç sorulmuyordu (#11–12) ve
   payload sınırları hiç yorumlanmıyordu (#9–10).
3. Pattern değerleri hiçbir yerde derlenmiyordu (#7–8).
4. Ad listelerinde teklik denetlenmiyordu (#5–6; JSON Schema metaşeması
   şart koşar).

## Sınıflandırma kararları ve önce/sonra matrisi

| # | Mutasyon | Önce | Sonra | Karar gerekçesi |
|---|---|---|---|---|
| 1 | `P[payload] = null` | current | **unavailable** | null geçersiz şema üyesidir, yokluk değil |
| 2 | `P.sig = null` | current | **unavailable** | aynı |
| 3 | `C.properties.did = null` | current | **unavailable** | aynı |
| 4 | tetiklenen bağımlılıkta null üye | current | **unavailable** | tetiklenen subschema bütünüyle okunabilir olmalı |
| 5 | `required` tekrarlı ad | current | **unavailable** | metaşema ihlali ("geçersiz şema" — prompt tablosu) |
| 6 | `anyOf` dalında tekrarlı ad | current | **unavailable** | aynı kural iç dalda da uygulanır |
| 7 | payload `pattern="(?!)"` | current | **unavailable** | payload'daki herhangi bir kalıbın kabul kümesi değerlendirilemez |
| 8 | payload `pattern="["` | current | **unavailable** | derlenemeyen kalıp uygulanamaz şemadır |
| 9 | payload `maxLength=5` | current (sessiz) | **current + UYARI + etkin limit (1,5)** | künye §14.4: kapasite uyarıdır; limit runtime'dan okunur |
| 10 | payload `minLength=100` | current (sessiz) | **current + UYARI + etkin limit (100,MAX)** | aynı |
| 9+10 | birlikte | drifted | **drifted** | boş aralık dejenere yayındır |
| 11 | nonce `maxLength=5` | current | **drifted** | (1,19) kapsanmalı; ms-saat nonce'u ~13 hane — pratikte her taze yazım reddedilirdi |
| 12 | nonce `minLength=5` | current | **drifted** | sayaç tabanlı 1–4 haneli nonce meşru gönderimdir |

Not: #5/#6'da yeniden üretim ajanının "current kalabilir" önerisinden bilinçli
sapıldı — kullanıcı promptunun tablosu "geçersiz şema" der ve JSON Schema
metaşeması `required` tekliğini şart koşar (IMP-258).

## Yapısal çözüm (yalnız yeni `if` değil)

- **Değer + tip + uygulanma kapsamı birlikte:** `_read_name_list` teklik
  denetler; `_check_field_node` pattern'i derler (`MAX_PATTERN_CHARS=512`
  üstü değerlendirilmez; uzak girdiyle asla ÇALIŞTIRILMAZ); null üye her
  seviyede "gecersiz sema uyesi" mesajıyla `unavailable`.
- **SOME-exclusion:** `STATION_FIELD_LENGTHS`'i olan alanlarda yayımlanan
  aralık gönderim aralığını **kapsamak** zorunda (`low > sent.minimum` veya
  `high < sent.maximum` → conflict). did/sig tek uzunluk olduğundan eski
  tam-dışlama davranışı korunur.
- **Payload = uyarı + etkin limit:** 4 yeni WARNING alanı
  (`payload_min/max_length`, `note_payload_min/max_length`);
  `SignedBodyView.payload_low/high` birleşik yayını taşır;
  `ProjectionResult.effective_payload_limits` tavanla (4096/8192) kırpılmış
  `SentLength` döndürür — composer'ın (Paket D) gerçek istekte uygulayacağı
  değer. Yayın yoksa beklenti gözlemlenir → uyarı yok.
- Genel amaçlı JSON Schema motoru YOK; `$ref`/ağ/sınırsız derinlik yok.

## Testler

Aşama B bölümü: **20 test fonksiyonu / 56 parametrik senaryo**, iki lane'de
(bağımsız inceleme sayımıyla düzeltildi; ilk kayıt 17/50 diyordu).
Nonce sınır matrisi (min 1/2/19/20, max 19/18/6/1/0) kapsama kuralını sabitler;
null-vs-silinmiş ayrımı iki farklı mesajla ("null - gecersiz sema uyesi" /
"yok") ayrıca test edilir; tavan üstü yayının kırpılması dahil. Hiçbir mevcut
test silinmedi/gevşetilmedi.

| Kapı | Sonuç |
|---|---|
| pytest | **804 geçti** (739 + Aşama B 56 + inceleme regresyonları 9) |
| ruff (üç ağaç) / mypy strict | geçti / 51 dosya 0 hata |
| Vitest | 59 geçti |
| `git diff --check` | 0 |

(CI sonuçları PR üzerinde; merge önü şartıdır.)

## Bilinçli ertelenenler

- **Composer'ın TAM isteğinin doğrulanması** (prompt §6.1 madde 5) Paket D'ye
  bağlıdır: composer henüz yok. B'nin ihracı (`effective_payload_limits`) tam
  bu entegrasyon için tasarlandı; D kabulünde "onaylanan swept payload +
  ayrılmış nonce ile tam istek doğrulaması" zorunlu madde olarak duruyor.
- Alan sayısındaki artış "bütün protokol doğrulandı" iddiası DEĞİLDİR (D-R5
  aynen geçerli).

## Bağımsız inceleme sonucu

Temiz bağlamlı, yazardan ayrı bir Claude reviewer subagent'ı head `2ed92c9`
diffini inceledi ve **21 karşı-probu fiilen çalıştırdı** (null varyantları,
tekrarlı `dependentSchemas.did.required`, 512/513 sınırındaki pattern'ler,
nonce kapsama matrisi geniş/dar/negatif, koşullu-tek `maxLength:7` birleşimi,
main'in eski değerlendiricisine karşı önce-durumu doğrulaması dahil).

Bulgular ve merge öncesi yapılanlar:

| Bulgu | Düzeltme |
|---|---|
| **P2-1:** `re.compile("a{4294967296}")` `re.error` değil `OverflowError` fırlatır — 13 karakterlik uzak pattern `project()`'i patlatıyordu (servis geniş `except` ile fail-closed kalıyordu ama gözlemsiz) | Guard `(re.error, OverflowError)` yakalar; regresyon testi eklendi |
| **P2-2:** tetiklenen non-did bağımlılığında `properties: null` yokluk gibi okunup `current` sızdırıyordu | `_check_object_node` null'u "gecersiz sema uyesi" olarak ayırır; regresyon testi eklendi |
| **P3-1:** `dependentSchemas`/`dependentSchemas.did` null iken "yok/eksik" mesajı veriliyordu | null/absent mesaj disiplini bu iki noktada da uygulanır; parametrik test eklendi |
| **P3-2:** bu raporun ilk sürümündeki sayımlar (17/50, mypy 53) hatalıydı | 20/56 ve 51 olarak düzeltildi; düzeltme notu bırakıldı |
| **P3-3:** `unavailable()` verdict'inde `effective_payload_limits` `{}` dönüyordu → gelecekteki D tüketicisinde KeyError | Her iki anahtar pinli güvenli varsayılanla daima döner; testi eklendi |

Düzeltmeler sonrası tam suite: **804 pytest** + 59 Vitest. P0/P1 yok. Bu
inceleme bir **insan güvenlik incelemesi değildir** (ADR-0001 §5 kalan risk).

## Sınırlar

Gerçek DID/kasa/recovery okunmadı; ağa çıkılmadı; pin (`7707cb63`) ve beklenen
sürüm değişmedi; tag/release/deploy yok; PR #7'ye dokunulmadı.
