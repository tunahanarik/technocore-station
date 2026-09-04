# ADR-0005 — Paket G kapsam kararları (4 Eylül 2026)

Durum: **kabul edildi** · Bağlam: uçtan uca prompt §11 (OpenCode Go bağlantısı)

Prompt §11.1 sözleşmenin resmî belgeden **doğrulanmasını** şart koşuyor ve
tahmin etmeyi yasaklıyor. Doğrulama yapıldı ve sonuç kapsamı belirledi.

## 1. Belgeden doğrulananlar ve doğrulanamayanlar

Okunan sayfalar (4 Eylül 2026; `docs/go` altbilgisi **"Last updated: Sep 3,
2026"**): `opencode.ai/docs/go/`, `/docs/zen/`, `/docs/providers/`,
`/docs/config/`, ve **kimliksiz** `GET /zen/go/v1/models`. Hiçbir API
anahtarı kullanılmadı, ücretli çağrı yapılmadı.

**Doğrulandı:**

| Konu | Bulgu |
|---|---|
| Üç protokol yolu | `…/zen/go/v1/responses`, `…/messages`, `…/chat/completions` — "Endpoints" tablosunda birebir |
| **Model → protokol eşlemesi** | Aynı "Endpoints" tablosu; sütunları `Model \| Model ID \| Endpoint \| AI SDK Package` ve **27 satırın her birinde `Endpoint` değeri yazılı**. Eşleme okunmuştur, çıkarılmamıştır |
| Base URL | `https://opencode.ai/zen/go/v1`; `api.opencode.ai` hiçbir sayfada geçmiyor |
| Model kataloğu | `…/zen/go/v1/models` yanıt veriyor |
| Kullanım limitleri | 5 saat $12 / hafta $30 / ay $60; limit dolunca ücretsiz modeller |
| "Use balance" | Limit dolunca Zen bakiyesine düşer; kontrol **konsolda** (`opencode.ai/auth`), API'den sorgulanamıyor |
| Veri saklama/eğitim | Privacy tablosu; çoğu model "Not used / 0-30 gün", Muse Spark modelleri **eğitim için kullanılıyor** |
| İstemci tanımlama | Belge açıkça istiyor: geniş user-agent kullanma, **`x-opencode-session` header'ı gönder** |
| `opencode-go/<id>` | **Provider öneki**, wire id değil. Katalog çıplak id döndürüyor (`glm-5.3`, `grok-4.6`) |

**Belgede BULUNAMADI** (uydurulmayacak):

1. **Auth header'ının adı ve formatı.** Dört sayfanın hiçbirinde
   `Authorization`, `Bearer` veya `x-api-key` geçmiyor. Web'de dolaşan
   iddiaların kaynağı **üçüncü taraf proxy repoları** — sözleşme sayılamaz.
2. **Üç protokol ailesinin request/response şekli**, streaming/SSE event
   formatı, tool-call formatı, usage/finish/error semantiği. Tablo hangi
   modelin hangi **uç noktaya** gittiğini söylüyor; o uç noktaya **ne
   gönderileceğini** söylemiyor.

   > **Düzeltme (4 Eylül 2026).** Bu maddenin ilk yazımı "üçü birbirinden
   > yalnız 'AI SDK Package' sütunuyla ayrılıyor" diyordu ve bundan, hangi
   > modelin hangi aileye ait olduğunun yayımlanmadığı sonucu çıkarılmıştı.
   > **Bu yanlıştı.** "Endpoints" tablosunun ayrı bir `Endpoint` sütunu var
   > ve 27 satırın hepsinde dolu. Madde silinmedi, çünkü hata öğretici:
   > ihtiyatlı görünen bir "doğrulayamadık" cümlesi, kaynak söylüyorken
   > **yanlış** bir cümledir — ve bu kez özelliğin kendisini kapatmıştı
   > (`selectable_model_ids()` boş dönüyordu, hiçbir model seçilemiyordu).
   > Kapsamı daralan hâli yukarıda; eşleme artık §5'te doğrulanmış sayılıyor.
3. **Hata kodları ve gövde şekilleri** (401/403/404/429/5xx).

**Katalogun kendisi de fakir:** yanıt yalnız `{id, object, created,
owned_by}` taşıyor — 34 model. **Protokol eşlemesi, context/output limiti,
tool desteği, display name ve veri saklama koşulu katalogda YOK**; bunlar
yalnız `docs/go` sayfasının HTML tablolarında.

**Ve en önemlisi: katalog anahtarsız yanıt verdi.** Model listesini
çekebilmek, anahtarın geçerli olduğunu **kanıtlamaz**.

## 2. Streaming ve tool-call bu pakette YOK

Streaming/SSE ve tool-call formatı belgede tanımlı değil; yazmak tahmin
etmek olurdu ve prompt bunu yasaklıyor. Ayrıca H2 (yürütücü) olmadan bir
"run" yok — `running` durumu Paket F'de bilinçli olarak üretilemez ve
SI-216 bunu sabitliyor.

**Karar:** G streaming ve tool-call **uygulamaz**. Adapter'lar
non-streaming şekli fixture'a karşı kanıtlar. Streaming, sözleşmesi
doğrulandığında H2'nin işidir. Bu erteleme kullanıcıya görünür yazılır.

## 3. Auth header'ı: beyan edilmiş, doğrulanmamış varsayım

Ürün çalışır olmak zorunda ama sözleşme yayımlanmamış. Sessizce varsaymak
prompt §11.1'i ihlal eder; hiç yazmamak özelliği göstermelik bırakır.

**Karar:** Header **tek bir yerde**, açıkça "resmî belgede doğrulanmamış"
etiketiyle tanımlanır. `Authorization: Bearer <key>` kullanılır **ve** bu
seçimin belgeden değil yaygın uygulamadan geldiği hem ADR'de hem UI'da
yazılır. Değişmesi gerektiğinde tek satır değişir. `x-opencode-session`
**belgede zorunlu tutulduğu için** gönderilir; değeri oturum başına
rastgele üretilir, kullanıcıya veya kimliğe bağlanmaz (SI-71'in ruhu) ve
kalıcı değildir.

## 4. "Bağlantıyı denetle" bir rozet üretmez

Üç gözlem çatışıyor: katalog anahtarsız cevap veriyor (anahtarı
doğrulamaz), `GET /chat/completions` **404** dönüyor (probe değil), ve
gerçek bir çağrı bu döngüde yasak.

**Karar:** Denetim, Technocore'un `never_checked` / `unavailable(reasons)`
kalıbını izler. Sonuç en fazla **"anahtar kaydedildi, doğrulanmadı"**
olabilir ve bu tek yeşil rozete indirgenmez. Anahtar **biçim kontrolüyle
başarı üretilmez**. Gerçek bir küçük probe'un maliyetli olabileceği yazılır
ve **yalnız kullanıcının açık eylemine** bağlanır — bu turda uygulanmaz.

## 5. Protokol eşlemesi kapalı registry'den gelir

Katalog protokol eşlemesi taşımıyor. Metadata'nın iddia ettiği bir URL'yi
doğrudan fetch etmek de yasak (prompt §11.3).

**Karar:** Model → protokol eşlemesi **derleme zamanı kapalı bir tablodur**
(Technocore `SOURCES` kalıbı). Katalog kullanıcı isteğiyle çekilir; **eşlemesi
olmayan bir model listelenir ama seçilemez** ve nedeni görünür olur.
Uydurma, "yaklaşık" veya sabit model adıyla dropdown doldurulmaz. Cache
tarihi ve erişim hatası gösterilir. Cache `official_source_snapshot`
desenine benzer bir tabloda tutulur; **dosya yolu API yanıtında dönmez**
(SI-36).

"Listeleniyor" ile "bu hesap çağırabiliyor" **farklıdır** ve UI bunu
karıştırmaz. Eğitim için kullanılan modeller (Privacy tablosundaki "Yes"
satırları) **varsayılan seçilmez** ve seçilirken ek onay ister.

**Tablonun bugünkü içeriği (4 Eylül 2026'da okundu):** "Endpoints"
tablosunun **27 satırının tamamı** `MODEL_MAPPINGS`'e `documented` olarak
geçti — `responses` 4, `messages` 8, `chat/completions` 15 model. Canlı
katalog **34** kimlik döndürmüştü; aradaki **7 fazlalık** tabloda yok,
`unverified` kalır, **listelenir ama seçilemez** ve nedeni kullanıcıya
gider. Privacy tablosu satır satır taşınır: `grok-4.6` ve `gpt-5.6-luna`
için `30 days`, iki `muse-spark-*` satırı için `Yes / Not ZDR` (ek onay
ister), üç `deepseek-*` satırı için **yıldızıyla birlikte** `0 days*`,
kalanlar `Not used / 0 days`.

Bunların hiçbiri §1'deki **auth header** boşluğunu kapatmaz: protokol
eşlemesinin doğrulanmış olması, isteğin hangi header'la imzalanacağının
bilindiği anlamına gelmez. O madde yerinde duruyor.

## 6. Dördüncü giden istemci — gerekçeli ve görünür

`OUTBOUND_CLIENT_MODULES` bugün üç modülde kilitli ve yorumu diyor ki
"dördüncü bir giriş, dördüncü bir giden yüzey demektir; bunu bir gözden
geçiren görmeli."

**Karar:** Dördüncü istemci açılır. ADR-0003 §1'in ölçütü karşılanıyor
(farklı kabiliyet, farklı registry, farklı başarısızlık politikası) ve
üstüne iki tane daha var: **farklı origin** ve **farklı kimlik doğrulama
modeli** — OpenCode `Authorization` taşır, Technocore istemcilerinin hiçbiri
taşımaz.

Allowlist tek düz kümeden `{dizin: {modül}}` haritasına dönüşür; bugünkü
`path.parent.name != "technocore"` koşulu OpenCode modülü `technocore/`
dışında olduğu için yanlış sonuç verirdi. Bu daha dürüst: her giden yüzey
kendi dizininde adlandırılır.

**SI-71 daraltılır, gevşetilmez:** "giden istekte cookie/auth/DID/CSRF yok"
kuralı Technocore istemcilerine ait kalır; OpenCode için ayrı bir değişmez
yazılır — *giden istekte yalnız provider anahtarı; DID, CSRF, oturum
kimliği ve kullanıcı dosya yolu asla*. TLS doğrulaması kapatılamaz, redirect
kapalı, taşıyıcı yalnız `MockTransport` (SI-174 kalıbı), host allow-list
zorunlu.

## 7. Credential: audit zarfı **şablon** olarak, bir farkla

`DpapiVault` kimliğe bağlıdır (32-hex identity id, iç AAD, "asla üzerine
yazma") — kullanılamaz. Paket E'nin `audit_envelope.py` şekli uygundur ve
E'de olduğu gibi **kod değil şekil** paylaşılır: `{format, version, kind,
created_at, dpapi_blob}` + `require_exact_keys` + atomik yazma (mkstemp →
fsync → ACL → `os.replace` → ACL).

**Bilinçli fark:** audit materyali asla üzerine yazılmaz; **API anahtarı
yazılmalıdır** — kullanıcı anahtarını değiştirebilmelidir. E'nin kalıbını
kopyalayan biri yanlış tarafı miras almasın diye bu ADR'ye yazılır.
Domain-separation sabiti OpenCode'a özgü olur.

Veritabanına **yalnız** göreli yol, zaman ve fingerprint girer
(`secret_metadata` deseni). Saklanan anahtarı geri gösteren/kopyalayan
endpoint **yoktur**; API yalnız `configured` ve güvenli durum metadata'sı
döndürür.

## 8. Redaksiyon ve canary

Anahtar DPAPI'den açılır açılmaz `register_secret`, iş bitince
`forget_secret`. **Tuzak:** `register_secret` 16 karakterden kısa değerleri
sessizce yok sayar — uzunluk ayrıca denetlenir.

TEST-ONLY bir anahtar canary'si eklenir (`TEST_ONLY_SEED_HEX` kalıbı) ve
`test_seed_leakage.py`'nin ikizi yazılır: HTTP gövdeleri **ve header'ları**,
OpenAPI, SQLite, zarf dosyası, veri dizini, log ve exception, **frontend
bundle**. Canary'nin depoda başka yerde bulunmadığı da doğrulanır, arama
anlamlı kalsın diye. Upstream anahtarı bir hata metninde geri yansıtsa bile
frontend ve log bunu göstermez.

## 9. Bütçe G'de açılmaz

Depo iki farklı şey söylüyordu: Paket F'nin `BUDGET_DETAIL` metni "G ve H2"
diyor, yürütme planı G için "gerçek harcama yok" diyor.

**Karar:** `budget_available: Literal[False]` **değişmez**. G yalnız
**salt-okunur harcama bağlamı** taşır: belgelenmiş limitler, modelin veri
saklama/eğitim koşulu, ve "Use balance" tercihinin **sağlayıcı konsolunda**
kontrol edildiği bilgisi. Station otomatik billing ayarı değiştirmez ve
"Use balance"ı engellediğini **iddia etmez**. Gerçek bütçe sınırı ve
eşzamanlılık H2'nindir. Abonelik "sınırsız" diye sunulmaz; token/maliyet
sağlayıcıdan gelmiyorsa `unknown` yazılır, sıfır uydurulmaz.

## 10. Frontend: yeni bileşen yok, verilmiş söz bilinçli revize edilir

Maskeli anahtar girişi için yeni HeroUI bileşeni **gerekmiyor** — mevcut
`TextField + Label + Input type="password"` kalıbı (`PassphraseField`)
yeterli. Model seçici için `Select`/`Autocomplete` allowlist dışında;
**native `<select>` veya mevcut radio-fieldset kalıbı** kullanılır, allowlist
11'de kalır.

`SettingsHelpPage` bugün kullanıcıya söz veriyor: *"bu ekranda bilerek
hicbir secret giris veya gosterim alani yoktur"* ve
`pages.test.tsx::offers no secret input anywhere` bunu sabitliyor. Bu söz
**bilinçli olarak** revize edilir — sessizce değil: yeni metin istisnanın
yalnız provider anahtarı için olduğunu, DID seed/private key/recovery için
hiçbir istisna bulunmadığını söyler. **SI-48 daraltılır** (seed/private
key/recovery parolası), gevşetilmez. ADR-0001 §6 bu dar istisnayı zaten
yetkilendirmiş durumda.

Seçilen model tarayıcı deposuna yazılamaz (SI-24) — backend'de yaşar.
Anahtar kaydedildikten sonra input ve state temizlenir; clipboard, toast,
analytics ve error telemetry'ye yazılmaz.

## 11. Kapsam dışı ve değişmeyenler

Model worker'ına anahtar, DID seed'i, vault parolası, recovery veya backend
process environment'ı **verilmez** — bu pakette worker zaten yok.
Kullanıcının seçtiği model sessizce başka modele/provider'a **çevrilmez**;
fallback yoktur. Ağ tekrarı sınırlıdır ve kayıp yanıtın ek ücret
doğurabileceği dikkate alınır. Uygulama kendi User-Agent'ını kullanır,
başka istemciyi **taklit etmez**.

Aşama numarası dört yerde `6` → `7` (SI-232). Modül registry'sine
dokunulmaz — OpenCode bir modül değil, altyapıdır. Yeni bağımlılık yok.
Gerçek servise ücretli çağrı yok; her şey `MockTransport` ile. Geliştirici
kullanıcının gerçek anahtarını **okumaz, istemez, kullanmaz**; "sahte
transport ile doğrulandı, gerçek hesap testi kullanıcıya aittir" denir.
İnsan güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5).
