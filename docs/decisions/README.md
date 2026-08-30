# Mimari kararlar (ADR indeksi)

> Kararların **tam metni ve gerekçesi**
> [`../../Technocore-Station-Proje-Kunyesi.md`](../../Technocore-Station-Proje-Kunyesi.md) §9
> tablosundadır. Bu dizin o kararların indeksidir ve künyeden **sonra**
> alınan kararları ayrı dosyalar hâlinde tutar.

## 1. Kilitli kararlar (künye §9)

Bunlar **kilitlidir**. Değiştirmek için önce künyenin güncellenmesi gerekir.

| ID | Karar | Etkilediği yer |
|---|---|---|
| ADR-001 | Ürün adı Technocore Station | tüm belgeler |
| ADR-002 | Dashboard korunur, MVP üç ana yüzeyle başlar | `station-web` |
| ADR-003 | DID generator ürünün özelliğidir, ürünün kendisi değildir | kapsam |
| ADR-004 | Ana değer conformance + Evidence + provenance | kapsam |
| ADR-005 | React 19 + Vite + TypeScript + HeroUI v3 | `station-web` |
| ADR-006 | Python 3.12 + FastAPI yerel çekirdek | `station-api` |
| ADR-007 | SQLite/WAL yerel veri tabanı | `station-api/db` |
| ADR-008 | Windows-only MVP | tüm ürün |
| ADR-009 | Küçük vault arayüz sınırı; yalnız DPAPI uygulanır | Aşama 2 |
| ADR-010 | DID note Proje 0 MVP'ye dahildir | Aşama 4 |
| ADR-011 | POST tüm yazmaların varsayılanıdır | Aşama 4 |
| ADR-012 | GET yalnız conformance ve protokol fallback içindir | Aşama 4 |
| ADR-013 | Frontend ve backend aynı origin'den çalışır | Aşama 1 |
| ADR-014 | Recovery ilk gerçek yazmadan önce zorunludur | Aşama 2 |
| ADR-015 | Parola katmanı opsiyonel, önerilen ve setup'ta seçili | Aşama 2 |
| ADR-016 | Parola açılışta değil, secret kullanan işlemlerde istenir | Aşama 2 |
| ADR-017 | Dinamik plugin yok; compile-time registry | Aşama 6 |
| ADR-018 | Uygunluk paketi ilk etapta monorepo içindedir | `packages/` |
| ADR-019 | Tauri paketleme daha sonra kararlaştırılır | Aşama 7 |
| ADR-020 | Gerçek DID yalnız kullanıcının bilgisayarında oluşturulur | operasyon |

## 2. Aşama 1 uygulama kararları

Bunlar künyedeki kilitli kararların **uygulama detaylarıdır**; yeni ürün
kararı değildir. Ayrı ADR dosyası açmayı gerektirecek kadar büyümedikleri
sürece burada tutulurlar.

| ID | Karar | Gerekçe |
|---|---|---|
| IMP-101 | Monorepo kökü bu depo kökünün kendisidir (ayrı `technocore-station/` alt dizini açılmadı) | Künye zaten proje klasörüne konmuştur; iç içe ikinci bir kök göreli referansları bozar |
| IMP-102 | Alembic kullanılır ve version tablosu `schema_migrations` olarak adlandırılır | Künyedeki tablo adı korunur; sıra `down_revision` zinciriyle deterministik, `upgrade head` idempotent olur |
| IMP-103 | Oturum cookie'sine `Secure` bayrağı konmaz | Loopback HTTP; uygulanamayacak bir güvenlik iddiası üretilmez (bkz. `security-invariants.md` §2) |
| IMP-104 | `Sec-Fetch-Site: none` yalnız güvenli (GET/HEAD) navigasyonda kabul edilir | Launcher'ın açtığı `/session/<token>` sekmesi `none` üretir; state-changing istekte `same-origin` zorunludur |
| IMP-105 | CSRF değeri oturum oluşturulurken üretilir; `/api/session/bootstrap` salt okunur GET'tir | Bootstrap'ı CSRF muafiyetiyle özel-durum yapma ihtiyacı ortadan kalkar |
| IMP-106 | CSP: `style-src-attr 'unsafe-inline'` | React Aria / HeroUI konumlandırma için inline `style` **attribute** üretir; inline `<style>` elemanı ve tüm script'ler yine yasaktır |
| IMP-107 | Vite `modulePreload.polyfill: false` | Polyfill inline `<script>` enjekte eder ve `script-src 'self'` ile çakışır |
| IMP-108 | CSRF middleware doğrulaması için **üretim rotası eklenmedi**; probe app testlerde kurulur | Test amaçlı endpoint production yüzeyine sızmaz |
| IMP-109 | Development'ta backend sabit `STATION_DEV_PORT` (varsayılan 8787) kullanır | Vite proxy hedefinin bilinmesi gerekir; production yolu efemer kalır |
| IMP-110 | `technocore-conform` Aşama 1'de yalnız paket sınırı + placeholder | Prompt gereği; sweep/DID/imza kodu Aşama 2B'de yazılır |

## 3. Yeni ADR nasıl eklenir

Yeni ve **kalıcı** bir mimari karar alındığında bu dizine
`NNNN-kisa-baslik.md` adıyla dosya eklenir ve yukarıdaki tabloya satır
girilir. Şablon:

```markdown
# ADR-NNNN — <başlık>

- Durum: önerildi | kabul edildi | reddedildi | değiştirildi (ADR-XXXX ile)
- Tarih: YYYY-AA-GG
- Aşama: <ilgili aşama>

## Bağlam
<Hangi kısıt veya çelişki bu kararı gerektirdi?>

## Karar
<Ne yapılacak?>

## Sonuçlar
<Neyi kolaylaştırır, neyi zorlaştırır, hangi riski kabul ediyoruz?>

## Alternatifler
<Değerlendirilip elenen seçenekler ve eleme gerekçesi.>
```

Künyeyle çelişen bir ADR yazılmaz; önce künye güncellenir.
