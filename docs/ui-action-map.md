# UI eylem haritası

> Paket C çıktısı. Sol menülü dashboard kabuğundaki **her** etkileşimin
> sözleşmesi: önkoşul, çağrılan işlev, loading/success/error/timeout/iptal
> davranışı ve otomatik test kimliği.
>
> Kapsam notları:
> - **Derin link yok.** Bölüm seçimi yalnız React state'tir; URL/router
>   senkronu yoktur ve yeni bağımlılık eklenmemiştir. Yenilenen sayfa ilk
>   bölüme (Genel Bakış) döner.
> - **Tarayıcı QA bu döngüde yapılmaz** (ADR-0001 madde 4). Görsel/manuel
>   doğrulama, Paket J kullanıcı kılavuzundaki manuel kabul listesine
>   ertelenmiştir.
> - UI metinleri mevcut konvansiyona uygun olarak diyakritiksiz Türkçe
>   yazılır ("Ana bolumler", "Kopyalandi").

## 1. Hata / loading / timeout sözleşmesi

Tüm backend trafiği `apps/station-web/src/api/client.ts` üzerinden geçer.

### 1.1 Zaman aşımı

Her istek `AbortSignal.timeout(ms)` ile sınırlıdır:

| Yol | Süre | Gerekçe |
|---|---|---|
| Tüm istekler (varsayılan) | 15 000 ms | Yerel loopback servisi; daha uzunu donma demektir |
| `refreshTechnocore` (`POST /api/technocore/refresh`) | 30 000 ms | Sunucu tarafı birden çok resmî belgeye çıkar |
| `exportRecovery` (elle `fetch`) | 15 000 ms | Aynı varsayılan; bu yol da kapsanır |

### 1.2 `ApiError` sınıflandırması (`kind`)

| `kind` | Tetikleyici | `retryable` | Kurtarma eylemi |
|---|---|---|---|
| `timeout` | **Bizim** `AbortSignal.timeout` sinyalimiz doldu | evet | "Yeniden dene" |
| `canceled` | İstek iptal edildi ama bunu bizim zaman aşımımız yapmadı | evet | "Yeniden dene" |
| `network` | `fetch` `TypeError` ile reddetti (bağlantı yok) | evet | "Yeniden dene" |
| `malformed` | Yanıt geldi ama JSON/gövde çözülemedi | hayır | Kod + istek kimliği ile bildirim |
| `auth` | HTTP 401 / 403 veya oturum hiç başlatılamadı | hayır | Launcher ile yeniden açma açıklaması |
| `rate_limited` | HTTP 429 | evet | Bekleyip "Yeniden dene" |
| `unavailable` | HTTP 503 | evet | Servis kontrol önerisi + "Yeniden dene" |
| `server` | Diğer 5xx | evet | "Yeniden dene" |
| `request` | Diğer 4xx | hayır | Mesajı gösterme; eylem yok |

Ek alanlar:

- `status`: HTTP durumu; yanıt hiç gelmediyse `0`.
- `code`: backend `detail` değeri `^[a-z0-9_]+$` kalıbındaysa o; değilse
  `http_<status>`. HTTP dışı sınıflar için sabit kodlar: `timeout`,
  `request_canceled`, `network_error`, `malformed_response`,
  `session_not_bootstrapped`, `unexpected_error`.
- `requestId`: `X-Station-Request-Id` başlığından; **32 küçük harf hex**
  (`/^[0-9a-f]{32}$/`, `i` bayrağı yok) doğrulanır. Sunucu `uuid4().hex`
  üretir; büyük harfli bir değer bizim ürettiğimiz kimlik değildir ve
  `null` sayılır. Başlık yoksa veya bozuksa `null`; backend bu başlığı
  koymuyorsa da kod çalışır (test:
  `client.test.ts::refuses an upper-case request id: the server writes
  lower-case hex`).
- `userMessage`: backend Türkçe cümle döndüyse o; makine koduysa veya boşsa
  `kind` kataloğundan güvenli Türkçe cümle. Kullanıcıya asla çıplak makine
  kodu tek başına gösterilmez. **Ham JS hata mesajı da gösterilmez:**
  `ApiError` olmayan bir istisna (`TypeError` gibi) `toApiError` ile
  `unexpected_error` / `kind=request` sınıfına çevrilir, `error.message`
  kullanıcıya çıkmaz (test: `pages.test.tsx::never shows a raw JavaScript
  message when a non-ApiError escapes`).

Bozuk yanıt (`malformed`) ile bağlantı kesilmesi (`network`) bilinçli olarak
ayrı sınıflardır: biri "servis konuşuyor ama anlaşılmıyor", öteki "bayt hiç
gelmedi" bulgusudur.

`timeout` ile `canceled` de aynı nedenle ayrıdır. `timeout` servis hakkında
bir **iddiadır** ("bizim süremiz içinde yanıt vermedi") ve yalnız kendi
`AbortSignal.timeout` sinyalimiz tetiklendiğinde doğrudur. Sınıflandırma
rejection'ın adına değil, **bizim geçirdiğimiz sinyale** bakar: `TimeoutError`
yalnız bir zaman aşımı sinyalinden çıkabildiği için kesindir; çıplak bir
`AbortError` ise ancak kendi sinyalimiz `aborted` ve `reason.name ===
"TimeoutError"` ise zaman aşımı sayılır, aksi halde `canceled` olur.
Bugün ürünün kendi başlattığı tek iptal zaman aşımıdır (bkz. §1.5), bu yüzden
`canceled` pratikte yalnız tarayıcı isteği kendisi düşürdüğünde (sayfa
kapanması gibi) görülür; sınıf, ileride bir iptal düğmesi eklenirse yalanı
baştan engellemek için vardır. Testler: `client.test.ts::calls an abort a
timeout only when our own deadline fired`, `::classifies an abort our deadline
did not cause as canceled, not a timeout`.

### 1.3 `ErrorRegion` (kalıcı hata alanı)

`src/components/ErrorRegion.tsx`. Kaybolan toast değildir; `role="alert"`
taşır ve kullanıcı eyleme geçene kadar ekranda kalır. İçerik:

- `userMessage` + sınıfa uygun kurtarma metni (auth → launcher açıklaması,
  unavailable → servis kontrolü önerisi),
- kararlı satır: `Kod: <code> · HTTP: <status|-> · Istek: <requestId|->`,
- `retryable` ve callback verilmişse **"Yeniden dene"** butonu,
- **"Tani bilgisini kopyala"** butonu.

"Yeniden dene" de async bir eylemdir ve §1.4'e tabidir: çağıran `retryPending`
verdiğinde buton `isDisabled` olur ve **"Yeniden deneniyor..."** yazar; ikinci
aktivasyon callback'i hiç çağırmaz (test: `ErrorRegion.test.tsx::disables the
retry and says so while the retried request is in flight`, `::starts no second
request when the retry is clicked repeatedly`).

**Redaksiyon kuralı:** kopyalanan tanı yükü YALNIZ
`{code, status, kind, request_id, timestamp, section}` alanlarını içerir.
URL, istek gövdesi, DID, dosya yolu, parola, cookie ve `userMessage` metni
**asla** kopyalanmaz (test: `ErrorRegion.test.tsx::copies only redacted
diagnostics`). Kopyalama başarısızsa buton "Kopyalanamadi" der; başarı
taklidi yapılmaz.

Kabuktaki bağlantı hatası ve her sayfanın veri çekme hatası bu bileşenle
gösterilir.

### 1.4 Çift tıklama koruması

Async eylem taşıyan her buton, istek uçuştayken `isDisabled` + pending
etiketi alır ("Denetleniyor...", "Olusturuluyor...", "Hazirlaniyor...",
"Dogrulaniyor...", "Aciliyor...", "Kuruluyor...", "Siliniyor...",
**"Yeniden deneniyor..."**). İkinci aktivasyon istek başlatmaz.

Bu kural `ErrorRegion`'ın "Yeniden dene" butonunu da kapsar; her çağıran
kendi loading durumunu `retryPending` ile geçirir:

| Çağıran | Pending kaynağı |
|---|---|
| `AppShell` (kabuk hatası) | `App.load`'un `loading` durumu |
| `OverviewPage` (3 kart) | tek `refreshing` bayrağı — üç retry de aynı `load`'u tekrarlar |
| `IdentityPage` (kimlik + "Son islem basarisiz oldu") | `loading` |
| `IdentityPage` / uygunluk paneli | ayrı `conformanceLoading` (kimlik yüzeyi uygunluk okumasını beklemez) |
| `ComposeVerifyPage` | `loading` |
| `SettingsHelpPage` | `gateLoading` (bu pakette eklendi; daha önce hiç loading durumu yoktu) |
| `TechnocoreSourcesPanel` | hata "check"ten geldiyse `busy`, "load"tan geldiyse `loadBusy` |

Testler: `pages.test.tsx::disables the check button while a check is in
flight`, `pages.test.tsx::disables the gate retry while the retry is in
flight`, `App.test.tsx::disables the shell retry while the retry is in
flight`, `ErrorRegion.test.tsx::starts no second request when the retry is
clicked repeatedly`.

### 1.5 İptal

**Ürünün kullanıcıya sunduğu bir "isteği iptal et" düğmesi yoktur.** Dialoglardaki
"Vazgec" bir istek iptali değildir: dialog kapanır ve parola alanları silinir,
uçuştaki istek sürer; sonucu geldiğinde dialog kapalıysa yalnız durum
güncellenir. Sayfa gezinmesi (bölüm değişimi) seçili olmayan bölümü unmount
eder; unmount edilen bileşenin isteği sonucu geldiğinde React 19'da no-op'tur —
istek yine de tamamlanır. Uygulamanın kendi başlattığı tek iptal
`AbortSignal.timeout` zaman aşımıdır.

Bu yüzden `kind=canceled` bugün yalnız isteği tarayıcı/çalışma ortamı
düşürdüğünde (sayfa kapanması gibi) ortaya çıkar. Sınıfın var olma sebebi
§1.2'de: iptali `timeout` diye raporlamak, gözlenmemiş bir servis yavaşlığı
iddiası olurdu. Bir iptal düğmesi eklenirse bu tabloya ayrı bir satır olarak
girer; sınıflandırmanın değişmesi gerekmez.

## 2. Kabuk (AppShell)

| Ekran / yol | Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|---|
| Kabuk (açılış) | otomatik oturum başlatma | launcher cookie'si | `bootstrapSession()` + `fetchAppStatus()` | durum kartları "Kontrol ediliyor" | bölümler veriyle dolar | `ErrorRegion` "Yerel cekirdege baglanilamadi"; auth→launcher açıklaması, network→"Yeniden dene" | `kind=timeout`, "Yeniden dene" | yok | `App.test.tsx::surfaces an auth failure with the launcher guidance and no retry`, `::offers a retry when the local core is unreachable, and retries` |
| Sol menü | 6 bölüm butonu (`nav aria-label="Ana bolumler"`) | bölüm `ready: true` | yok (React state) | anında | seçili bölüm mount edilir, `aria-current="page"` taşınır; hazır olmayan bölüm hiç görünmez | — | — | — | `App.test.tsx::renders a left navigation with exactly the ready sections (ADR-0001)`, `::never shows a section that is not ready`, `::mounts only the selected section and moves aria-current on click`, `::is operable with the keyboard: tab to a section, Enter selects it` |
| Sol menü | "Menuyu daralt" / "Menuyu ac" (`aria-expanded` + `aria-controls`) | — | yok (React state; kalıcı depolama yok) | anında | menü daralır/genişler, seçim korunur. **Landmark unmount edilmez:** `<nav aria-label="Ana bolumler">` ve bütün bölüm butonları daraltılmış durumda da DOM'da kalır; görünen etiket baş harfe iner (`aria-hidden`), erişilebilir ad tam etiket olarak `sr-only` kalır | — | — | — | `App.test.tsx::collapses the navigation without losing the selection`, `::keeps the navigation landmark and every section name while collapsed`, `::points the collapse toggle at the region it controls`, `::selects a section from the collapsed menu` |
| Üst başlık | (kontrol yok; sade başlık) | — | — | — | — | — | — | — | — |

## 3. Genel Bakış

| Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|
| `SystemStatusBar` (bölümün en üstünde, dört durum kartı; etkileşimli kontrol yok) | kabuk `status`/`loading` prop'u | prop (kendi isteği YOK) | dördü de "Kontrol ediliyor" | yerel servis / veritabani / oturum guvenligi / Technocore kartları | `status === null` ise dört kart "Ulasilamiyor/Bilinmiyor" der; kabuk hatası ayrıca `AppShell`'in `ErrorRegion`'ında | — (kendi isteği yok) | — | `pages.test.tsx::composes identity, Technocore, conformance and service health` (Yerel servis + Oturum guvenligi kartları), `App.test.tsx::reports Technocore as not yet checked on a fresh launch` |
| otomatik özet yükleme | bölüm seçili | `fetchIdentity()`, `fetchTechnocore()`, `fetchConformance()` (bağımsız) | kart başına "Durum okunuyor..." | kimlik özeti + sonraki güvenli adım; drift durumu + son kontrol zamanı; uygunluk özeti; servis sağlığı kartları. Hash listesi YOK | kart başına ayrı `ErrorRegion` + "Yeniden dene" | `kind=timeout` aynı bölge | bölüm değişince unmount | `pages.test.tsx::composes identity, Technocore, conformance and service health`, `::shows summaries only: no hash runs and no source detail`, `::designs the first-use state instead of faking data`, `::shows each failed summary as its own persistent error with retry` |
| "Kimlik ve Guvenlik bolumune git" (2 kart) | — | `onNavigate("identity")` | — | bölüm değişir | — | — | — | `pages.test.tsx::offers a go-to-section action on every summary card` |
| "Kaynaklar bolumune git" | — | `onNavigate("sources")` | — | bölüm değişir | — | — | — | aynı test |

## 4. Kimlik ve Güvenlik

| Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|
| otomatik yükleme | bölüm seçili | `fetchIdentity()` + `fetchConformance()` (bağımsız) | "Durum okunuyor..." kartı | durum + kapı + uygunluk paneli | kimlik okunamazsa `ErrorRegion` "Kimlik durumu okunamadi" + "Yeniden dene"; uygunluk okunamazsa panelde ayrı `ErrorRegion` "Uygunluk durumu okunamadi" | `kind=timeout` aynı bölgeler | bölüm değişince unmount | `pages.test.tsx::shows an honest empty state instead of a placeholder identity`, `::shows an error region, not a fake verdict, when conformance cannot be read` |
| son işlem hatası (kimlik yüklü ekranda `ErrorRegion` "Son islem basarisiz oldu") | `status` var **ve** son `load()` hata verdi | `fetchIdentity()` (retry aynı `load`) | — | bölge kaybolur | `ErrorRegion` + "Yeniden dene" (uçuşta "Yeniden deneniyor...") | `kind=timeout` aynı bölge | bölüm değişince unmount | `pages.test.tsx::shows an honest empty state instead of a placeholder identity` (yol), `ErrorRegion.test.tsx` (bölgenin kendi sözleşmesi) |
| "Kopyala" (Public DID / fingerprint) | kimlik var | `navigator.clipboard.writeText` | — | "Kopyalandi" (2 sn) | "Kopyalanamadi" | — | — | `pages.test.tsx::shows the public DID with a copy action` |
| "Yeni kimlik olustur" | `no_identity`/`revoked`, kasa `usable` | dialog açar | — | Create dialog | kasa yoksa `isDisabled` | — | — | `pages.test.tsx::surfaces a capability error and blocks creation` |
| "Recovery dosyasindan kur" | `no_identity`, kasa `usable` | dialog açar | — | Adopt dialog | disabled | — | — | `pages.test.tsx::offers the next safe action rather than every action at once` (görünürlük) |
| "Recovery dosyasi olustur" | `recovery_pending`/`ready` | dialog açar | — | Export dialog | — | — | — | görünürlük: aynı test |
| "Restore-test yap" | `recovery_pending`/`ready` | dialog açar | — | Restore dialog | — | — | — | `pages.test.tsx::Restore-test file picker` bloğu |
| "Revoke et" | `recovery_pending`/`ready` | dialog açar | — | Revoke dialog | — | — | — | görünürlük testleri |

### 4.1 Kimlik dialogları (5)

Ortak davranış: "Vazgec" dialogu kapatır ve tüm parola/onay alanlarını
siler (test: `pages.test.tsx::clears passphrase state when the dialog
closes`). Her dialogun sağ üstündeki `Modal.CloseTrigger` (X) ve Esc/backdrop
aynı `onClose` yolundan geçer, yani aynı temizliği yapar; timeout/network aynı yoldan sınıflanır; busy sırasında gönderim
butonu disabled'dır.

**Hata yüzeyi:** dialog içindeki hata da sayfalarla aynı `ErrorRegion`'dır —
`userMessage` + `Kod: … · HTTP: … · Istek: …` satırı + redakte "Tani
bilgisini kopyala". Kullanıcının desteğe en çok ihtiyaç duyduğu yer burasıdır
ve `Ayarlar ve Yardim` kullanıcıya tam olarak bu çıktıyı iletmesini söyler.
`onRetry` bilinçli olarak **verilmez**: yarım kalmış bir mutasyonu bir uyarı
kutusundan yeniden ateşlemek güvenli bir kurtarma değildir; kullanıcı formu
yeniden gönderir veya dialogu kapatır. Testler: `pages.test.tsx::carries the
code, HTTP status and request id when creation fails`, `::never shows a raw
JavaScript message when a non-ApiError escapes`.

| Dialog | Kontroller | Önkoşul (buton aktifleşme) | API | Busy etiketi | Test |
|---|---|---|---|---|---|
| Yeni kimlik olustur | koruma radyoları (DPAPI+parola / yalnız DPAPI), 2 parola alanı, risk onay kutusu (parolasızda), onay metni alanı, "Vazgec", "Kimligi olustur" | onay metni birebir + (parola ≥ min & eşleşiyor) veya risk kabul | `POST /api/identity` (`createIdentity`) | "Olusturuluyor..." | `pages.test.tsx::requires the exact confirmation text before enabling creation`, `::states plainly that a DID is not a wallet or a claim` |
| Recovery dosyasi olustur | recovery parolası ×2, (gerekirse) kasa parolası, "Vazgec/Kapat", "Recovery dosyasini indir" | parola ≥ min & eşleşiyor | `POST /api/identity/recovery/export` (`exportRecovery`, elle fetch + 15 sn timeout) | "Hazirlaniyor..." | dialog görünürlük + client testleri (`client.test.ts` sınıflandırma) |
| Restore-test | dosya seçici (".tcrec", "Dosya sec"/"Baska dosya sec"), recovery parolası, "Vazgec", "Restore-test yap" | dosya seçili | `POST /api/identity/recovery/verify` (`verifyRecovery`) | "Dogrulaniyor..." | `pages.test.tsx::Restore-test file picker` (5 test) |
| Recovery dosyasindan kur | dosya seçici, recovery parolası, "Dosyayi kontrol et" → DID önizleme + koruma radyoları + yeni kasa parolası, "Bu kimligi kur", "Vazgec" | 1. adım: dosya; 2. adım: inspect başarılı | `POST /api/identity/recovery/inspect` sonra `/adopt` | "Aciliyor..." / "Kuruluyor..." | dialog state testleri (görünürlük) |
| Kimligi revoke et | DID onay alanı, "Vazgec", "Kimligi revoke et" | yazılan DID birebir eşleşir | `POST /api/identity/revoke` (`revokeIdentity`) | "Siliniyor..." | görünürlük testleri |

## 5. Oluştur ve Doğrula

| Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|
| otomatik kapı okuma | bölüm seçili | `fetchIdentity()` | "Kapi durumu okunuyor..." | önkoşul listesi (kilitli yüzey; giriş alanı ve gönder kontrolü yok) | `ErrorRegion` "Kapi durumu okunamadi" + "Yeniden dene" | `kind=timeout` aynı bölge | bölüm değişince unmount | `pages.test.tsx::stays locked and reflects the real write gate`, `::offers no compose field and no send control while locked`, `::shows a persistent error region when the gate cannot be read` |

## 6. Kaynaklar

| Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|
| otomatik durum okuma (dışarı istek YAPMAZ) | bölüm seçili | `fetchTechnocore()` | "Durum okunuyor..." | son denetim durumu; hiç yapılmadıysa dürüst boş durum | `ErrorRegion` "Durum okunamadi" + "Yeniden dene" (yalnız okumayı tekrarlar) | `kind=timeout` | bölüm değişince unmount | `pages.test.tsx::starts as not yet checked and offers an explicit user action` |
| "Resmi kaynaklari denetle" | oturum + CSRF | `POST /api/technocore/refresh` (`refreshTechnocore`, 30 sn timeout) | buton "Denetleniyor..." + disabled | belge erişimi ve protokol değerlendirmesi ayrı raporlanır | `ErrorRegion` "Denetim yapilamadi"; retry aynı açık eylemi tekrarlar | `kind=timeout`, retry sunulur | yok (sonuç beklenir) | `pages.test.tsx::disables the check button while a check is in flight`, `::shows official source metadata after a check`, `client.test.ts::gives the official-source check a longer 30 second deadline` |
| URL "Kopyala" | kaynak listelendi | `navigator.clipboard.writeText` | — | "Kopyalandi" (2 sn) | "Kopyalanamadi" | — | — | `pages.test.tsx::never turns a remote URL into a clickable link` (URL asla anchor değildir, SI-54/AC-17) |

## 7. Kanıtlar

Etkileşimli kontrol yoktur. Boş durum, kayıt görünümünün Paket E ile
geleceğini açıkça söyler; dört güven seviyesi sınırlarıyla listelenir.
Testler: `pages.test.tsx::shows an empty state that names the package that
will fill it`, `::declares level 4 as absent rather than implying it
exists`, `::carries the trust levels but not the official-source panel`.

## 8. Ayarlar ve Yardım

| Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|
| "Koyu tema / Acik tema" | — | `applyTheme()` (yalnız DOM; kalıcı depolama YOK) | — | tema değişir; yeniden açılışta sistem teması | — | — | — | `pages.test.tsx::hosts the theme control and says the choice is not persisted` |
| otomatik kapı okuma | bölüm seçili | `GET /api/write-gate` (`fetchWriteGate`) | "Kapi durumu okunuyor..." | kapı özeti + kontrol listesi | `ErrorRegion` "Kapi durumu okunamadi" + "Yeniden dene" | `kind=timeout` | bölüm değişince unmount | `pages.test.tsx::renders the real write gate from /api/write-gate`, `::shows a persistent error with retry when the gate cannot be read` |
| uygulama/servis bilgisi | kabuk `status` yüklü | prop (yeni istek yok) | — | aşama/mod/veritabanı/oturum taşıma | durum yoksa dürüst açıklama metni | — | — | `pages.test.tsx::shows the application and service facts from the backend status` |
| yardım notu | — | — | — | "OpenCode Go baglantisi Paket G'de, kullanim kilavuzu Paket J'de eklenecek" | — | — | — | `pages.test.tsx::is honest about what arrives in later packages` |

## 9. Bölüm kayıt defteri

`src/sections.ts` dokuz bölümü kaydeder; `ready: false` olanlar nav'da HİÇ
görünmez:

| Bölüm | `ready` | Açılacağı paket |
|---|---|---|
| Genel Bakis | evet | — |
| Is Tara | hayır | H1 |
| Gorevler | hayır | F / H2 |
| Aktivite | hayır | H2 |
| Kimlik ve Guvenlik | evet | — |
| Olustur ve Dogrula | evet | — |
| Kaynaklar | evet | — |
| Kanitlar | evet | — (kayıt görünümü E ile dolar) |
| Ayarlar ve Yardim | evet | — |

Test: `App.test.tsx::never shows a section that is not ready`.

## 10. Bilinen sınırlar

Bu sözleşmenin kapsamadığı, bilinen ve bilinçli boşluklar:

1. **Akış başladıktan sonra oluşan sunucu istisnası kullanıcıya hata olarak
   görünmez.** Starlette'in istisna zırhı yalnız yanıt henüz başlamamışsa
   (`if not response_started`) devreye girer; baytlar gitmeye başladıktan
   sonra patlayan bir handler, istemciye yalnız yarım bir gövde ve kapanan
   bir bağlantı bırakır. Bu durumda `ApiError` sınıfı `malformed` (gövde
   çözülemedi) veya `network` (bağlantı düştü) olur; **`server` olmaz** ve
   `X-Station-Request-Id` başlığı zaten gönderildiği için korelasyon kimliği
   yine de kullanıcıya görünür.
   Bugün bu sınır **tetiklenemez**: streaming yanıt döndüren hiçbir route
   yoktur; recovery export dahil (`POST /api/identity/recovery/export`)
   tamponlanmış bir `Response` döner. Not, ileride bir streaming route
   eklenirse bunun bir sözleşme boşluğu olduğunu hatırlatmak için buradadır.
   (Backend davranışıdır; bu paket backend kodunu değiştirmez.)
2. **Derin link / URL senkronu yok** (§ kapsam notları) — yenilenen sayfa
   Genel Bakis'e döner.
3. **İstek iptali yok** (§1.5) — zaman aşımı dışında uçuştaki bir istek
   durdurulamaz.
4. **Tarayıcı QA yok** (ADR-0001 m.4) — bu haritadaki davranışlar Vitest +
   jsdom ile kanıtlıdır; gerçek tarayıcı doğrulaması Paket J'dedir.

## 11. HeroUI bileşen kümesi

Kullanılan HeroUI v3 bileşenleri **10 tanedir** ve kilitlidir: `Alert`,
`Button`, `Card`, `Checkbox`, `Chip`, `Input`, `Label`, `Modal`, `Separator`,
`TextField`. ADR-0001 m.2 ile `Tabs` düşmüştür ve geri gelmez. Küme bir
allowlist testiyle sabitlenir: kaynak ağacındaki bütün `@heroui/react`
import'ları taranır ve beklenen kümeye eşit olmalıdır (test:
`heroui-surface.test.ts::imports exactly the reviewed component set and
nothing new`, `::no longer imports the retired Tabs component`). Yeni bir
bileşen eklemek, import satırının yan etkisi değil, bu listeyi bilerek
genişletmek demektir.
