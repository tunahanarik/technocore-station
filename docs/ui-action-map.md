# UI eylem haritası

> Paket C çıktısı; Paket D ile "Oluştur ve Doğrula" bölümü (§5), Paket E ile
> "Kanıtlar" bölümü (§7), Paket G ile "Ayarlar ve Yardım" bölümü (§8), Paket
> H1 ile "Is Tara" bölümü (§12) dolduruldu.
> Sol menülü dashboard kabuğundaki **her** etkileşimin sözleşmesi: önkoşul,
> çağrılan işlev, loading/success/error/timeout/iptal davranışı ve otomatik
> test kimliği.
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
| `signComposeDraft` (`POST /api/compose/sign`) | 30 000 ms | İmzalamadan önce kasa açılır; parolalı kasa bir Argon2id türetmesi demektir ve yerel okuma süresi buna göre ölçülmemiştir |
| `sendComposeMessage` (`POST /api/compose/send`) | 45 000 ms | Backend'in kendi yazma bütçesi connect 5 sn + write 10 sn + read 15 sn'dir; **daha kısa bir istemci süresi, sunucu hâlâ yazarken isteği bırakıp sonucu `timeout` (yerel servis hakkında bir iddia) diye gösterirdi.** Fazladan pay, cevabın sunucunun üç değerli verdict'i olarak kalmasını sağlar |
| `captureEvidenceLine` (`POST /api/evidence/capture`) | 90 000 ms | Yakalama yerel bir okuma değildir: backend odanın resmî export'unu açar ve **12 MiB tavanına kadar** satır satır tarar. Backend'in kendi bütçesi connect 5 sn + read 30 sn'dir, ama o read süresi **chunk başınadır**, tarama tamamına değil — yavaş bir bağlantı otuz saniyede bir kez bile takılmadan route'u dakikalarca meşgul edebilir. Daha kısa bir istemci süresi, ilerleyen bir taramayı bırakıp sonucu `timeout` diye gösterir ve backend'in **altı yakalama durumundan hangisine** vardığını hiç öğrenemezdik; oysa "okuyamadım" ile "satır orada değil" ayrı bulgulardır ve bir istemci kronometresi ikisini birleştiremez |
| `exportEvidence` (`POST /api/evidence/export`, elle `fetch`) | 15 000 ms | Varsayılan; dışa aktarım yerel veritabanından üretilir, dışarı çıkmaz |
| `storeOpenCodeCredential` (`POST /api/opencode/credential`) | 20 000 ms | **Dışarı hiç çıkmaz**: route bir DPAPI zarfını yerel diske yazar (mkstemp → fsync → ACL → atomik replace → ACL) ve sonra yerel durumu okur. Varsayılan 15 sn yerel bir *okuma* için ölçülmüştür; burada bloklayan route sunucu threadpool'unda kuyruğa girer, iki Windows ACL çağrısı ve bir fsync bekler. Asıl gerekçe kısa sürenin maliyeti: replace ortasında bırakılan bir yazma `timeout` (yerel servis hakkında bir iddia) diye raporlanır, oysa zarf pekâlâ yerine oturmuş olabilir — ve kullanıcının bunu öğrenmesinin tek yolu **anahtarı yeniden yazmaktır**. Uygulamadaki diğer her istek bedelsiz tekrarlanır; bu tekrarlanmaz |
| `refreshOpenCodeCatalog` (`POST /api/opencode/catalog/refresh`) | 90 000 ms | Sunucunun kendi bütçesi **iki sınırlı deneme**, her biri connect 5 sn + read 30 sn, aralarında en fazla 5 sn backoff: `fetch_error` diyebilmesi için yaklaşık 75 saniye. Daha kısa bir istemci süresi ilerleyen bir yenilemeyi bırakıp `timeout` derdi ve kullanıcının asıl sorduğu şeyi — katalog durumunu — atardı. Bu istek **hiçbir kimlik bilgisi taşımaz**; katalogun anahtarsız yanıt vermesi zaten §8'deki "denetim rozet üretmez" kararının gerekçesidir |

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
"Imzalaniyor...", "Gonderiliyor...", **"Yakalaniyor..."**,
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
| `ComposerPanel` (yetki okuma hatası) | `capabilityLoading` — yalnız okuma tekrarlanır; taslak/imza/gönderim hatalarında `onRetry` **verilmez** |
| `SettingsHelpPage` | `gateLoading` (bu pakette eklendi; daha önce hiç loading durumu yoktu) |
| `TechnocoreSourcesPanel` | hata "check"ten geldiyse `busy`, "load"tan geldiyse `loadBusy` |
| `EvidenceLedgerPanel` / kayıt listesi | `ledgerLoading` |
| `EvidenceLedgerPanel` / audit zinciri | `auditLoading` (ayrı: zincir okunamazsa kayıtlar yine görünür) |
| `EvidenceLedgerPanel` / yakalama ve dışa aktarım hataları | `onRetry` **verilmez** — kullanıcı aynı açık eylemi kendi kontrolünden tekrarlar |

Yakalama butonu kendi kuralını taşır: uçuşta **"Yakalaniyor..."** yazar ve
`capturingId !== null` olduğu sürece **listedeki bütün** yakalama butonları
disabled olur. Aynı anda tek yakalama; ikinci aktivasyon istek başlatmaz.

Testler: `pages.test.tsx::disables the check button while a check is in
flight`, `pages.test.tsx::disables the gate retry while the retry is in
flight`, `App.test.tsx::disables the shell retry while the retry is in
flight`, `ErrorRegion.test.tsx::starts no second request when the retry is
clicked repeatedly`, `ComposerPanel.test.tsx::starts no second send when the
send button is clicked twice`, `EvidenceLedgerPanel.test.tsx::starts no second
capture while one is in flight`.

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
| Sol menü | 7 bölüm butonu (`nav aria-label="Ana bolumler"`; H1 ile "Is Tara" eklendi) | bölüm `ready: true` | yok (React state) | anında | seçili bölüm mount edilir, `aria-current="page"` taşınır; hazır olmayan bölüm hiç görünmez | — | — | — | `App.test.tsx::renders a left navigation with exactly the ready sections (ADR-0001)`, `::never shows a section that is not ready`, `::mounts only the selected section and moves aria-current on click`, `::is operable with the keyboard: tab to a section, Enter selects it` |
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

Paket D ile bu bölüm etkileşimli hâle geldi: **taslak → imza onayı → ayrı ve
tek kullanımlık gönderim onayı** (künye §7.4, ADR-0002 §2). Üç adım üç ayrı
istektir ve üçü de yazma kapısını sunucu tarafında yeniden koşar; ekrandaki
disabled bir buton hiçbir zaman kapıyı tutan şey değildir.

Bileşenler: `pages/ComposeVerifyPage.tsx` (ön koşul listesi + kabuk) ve
`components/compose/ComposerPanel.tsx` (akışın tamamı).

| Kontrol | Ekran yolu | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|---|
| otomatik kapı okuma | Olustur ve Dogrula → "On kosullar" | bölüm seçili | `fetchIdentity()` | "Kapi durumu okunuyor..." | ön koşul listesi (kapı kontrolleri + durum rozetleri) | `ErrorRegion` "Kapi durumu okunamadi" + "Yeniden dene" | `kind=timeout` aynı bölge | bölüm değişince unmount | `pages.test.tsx::stays locked and reflects the real write gate`, `::shows a persistent error region when the gate cannot be read` |
| otomatik yetki okuma | → "Gonderim akisi" | kapı okuması bitti | `GET /api/compose/capability` (`fetchComposeCapability`, 15 sn) | "Gonderim yetkisi okunuyor..." | yol (`POST /r/{room}`), reddedilen odalar, etkin `min_chars`/`max_chars` | `ErrorRegion` "Gonderim yetkisi okunamadi" + "Yeniden dene" (okuma tekrarı zararsızdır) | `kind=timeout` aynı bölge | bölüm değişince unmount | `ComposerPanel.test.tsx::shows a retryable read failure with a retry, and a write failure without one` |
| kapalı kapı açıklaması | → "Gonderim kapali" | `can_compose === false` | yok | — | `blocking_reasons` okunabilir cümlelere çevrilir; **metin alanı ve gönderim kontrolü hiç render edilmez** (göstermelik disabled form yok) | — | — | — | `ComposerPanel.test.tsx::explains a closed gate from the blocking reasons and offers no form`, `pages.test.tsx::offers no compose field and no send control while locked`, `::names the blocking preconditions instead of showing an inert form` |
| "Hedef oda" (`TextField`+`Input`) | Adım 1 | `can_compose` | React state | — | oda adı; değişimi **önceki taslağı ve onayı düşürür** | — | — | — | `ComposerPanel.test.tsx::drops the approval when the target room changes` |
| "Mesaj metni" (`TextField`+`TextArea`, `rows=6`) | Adım 1 | `can_compose` | React state + sayaç | — | `N / max_chars karakter (en az min_chars)` — sınırlar **capability'den**, hardcode yok. Üst sınır aşımında `aria-invalid="true"` ve açıklama `aria-describedby` ile alana bağlanır | — | — | — | `ComposerPanel.test.tsx::reads the character limits from the capability instead of hardcoding them`, `::links the over-limit explanation to the field it describes` |
| "Taslagi hazirla" | Adım 1 | oda dolu **ve** ham metin `min_chars`'tan kısa değil | `POST /api/compose/draft` (`createComposeDraft`, 15 sn) | "Hazirlaniyor..." + disabled | Adım 2 açılır: sweep farkı, hedef notları | `ErrorRegion` "Taslak hazirlanamadi" (retry **yok**; kullanıcı yeniden gönderir) | `kind=timeout` aynı bölge | yok | `ComposerPanel.test.tsx::reveals the three steps in order and offers no send control before a signature` |
| sweep farkı onay kutusu (`Checkbox`) | Adım 2 | `changed_by_sweep === true` | React state | — | ham ve süpürülmüş metin iki ayrı `<pre>`'de; "Gorunmez karakterler silindi" + karakter sayıları. **İşaretlenmeden "Imzala" disabled kalır** | — | — | — | `ComposerPanel.test.tsx::refuses to sign until the swept difference has been seen`, `::does not ask for an acknowledgement when the sweep changed nothing` |
| "Kasa parolasi" (`PassphraseField`) | Adım 2 | kasa `dpapi+passphrase` | yalnız local state | — | imzalama isteğine geçer; **imza başarılı olur olmaz state'ten silinir** ve alan kaybolur | — | — | — | `ComposerPanel.test.tsx::asks for the passphrase at signing time and keeps none of it afterwards` |
| "Imzala" | Adım 2 | taslak var, sweep farkı görüldü, imza henüz yok | `POST /api/compose/sign` (`signComposeDraft`, 30 sn) | "Imzalaniyor..." + disabled | Adım 3 açılır: canonical `<pre>` içinde birebir, oda/nonce/kısa özet, geri sayım | `ErrorRegion` "Imzalanamadi" (retry yok) | `kind=timeout` aynı bölge | yok | `ComposerPanel.test.tsx::reveals the three steps in order...`, `::shows the canonical string verbatim, because displayed is what is signed` |
| "Onayla ve gonder" (`variant="danger"`) | Adım 3 | imza var **ve** onay süresi dolmadı | `POST /api/compose/send` (`sendComposeMessage`, 45 sn) | "Gonderiliyor..." + disabled; ikinci tık istek başlatmaz | "Gonderim sonucu" bölgesi (üç durum, aşağıda) | `ErrorRegion` "Gonderim tamamlanamadi"; `timeout`/`network`/`canceled` ise ek olarak **"Bu sonuc bilinmiyor"** uyarısı | `kind=timeout` — ayrıca "sunucu yazmış olabilir" uyarısı | yok | `ComposerPanel.test.tsx::starts no second send when the send button is clicked twice`, `::calls a lost send response unknown rather than failed` |
| geri sayım rozeti | Adım 3 | imza var | `window.setInterval` (1 sn) | — | kalan saniye; **0'a inince buton disabled** ve "Onay suresi doldu" açıklaması | — | — | — | `ComposerPanel.test.tsx::locks the send control once the approval has expired, and says why` |
| "Gonderim sonucu" | sonuç bölgesi | bir gönderim denendi | yok | — | üç durum ayrı ayrı sunulur | — | — | — | `ComposerPanel.test.tsx::Composer send outcomes` bloğu (6 test) |
| not gönderimi açıklaması | bölümün sonu | yetki okundu | yok (backend `note_lane_detail`) | — | not lane'inin **neden** olmadığı yazılır | — | — | — | `ComposerPanel.test.tsx::says why there is no note send path` |

### 5.1 Onayın düşürülmesi

Metin veya hedef oda değiştiği anda taslak, imza ve `send_token`'ın üçü de
düşürülür; "Onceki onay dusuruldu" uyarısı **neden** düştüğünü yazar. Bu bir
hatırlatma değil, mekanizmanın kendisidir: `send_token` yalnız bu bileşenin
state'inde tutulur ve tek kopyadır, dolayısıyla düzenlemeden sonra eski
baytları yayımlayabilecek hiçbir şey kalmaz. Aynı temizlik parolayı da kapsar.
Testler: `ComposerPanel.test.tsx::drops the draft and the send approval when
the text changes`, `::drops the approval when the target room changes`.

Bir gönderim denemesinden sonra — **sonuç ne olursa olsun, hata dâhil** —
taslak ve imza yine düşürülür: onay tek kullanımlıktır ve nonce harcanmıştır.
Bu yüzden ikinci bir gönderim, yeni bir taslak ve yeni bir imza onayı ister;
tek tıkla tekrar yoktur (test: `::requires a fresh draft and a fresh signature
for any further send`).

#### Kasa parolası imza hatasında neden state'te kalıyor (bilinçli karar)

`ComposerPanel.tsx` parolayı **başarılı** imzadan hemen sonra siler
(`setPassphrase("")`), gönderim adımının `finally`'sinde tekrar siler ve metin
veya oda düzenlendiğinde `dropApprovals()` içinde bir kez daha siler. Ama
imza **başarısız** olduğunda parola alanda kalır.

Bu bir unutma değil, seçilmiş davranış: yanlış parola bu adımın en sık hata
sebebidir ve kullanıcıya uzun bir parolayı yeniden yazdırmak, onu daha kısa
bir parola veya panoya kopyalama alışkanlığı seçmeye iter — ikisi de bu
alandan daha kötüdür. Değeri temizleyen dört yol zaten var:

1. başarılı imza (`sign()` içinde, istek döner dönmez);
2. metin veya hedef oda düzenlemesi (`dropApprovals()`);
3. gönderim denemesinin `finally`'si, sonuç ne olursa olsun;
4. bileşenin unmount olması — bölüm değişince state yok olur; hiçbir yerde
   `localStorage`/`sessionStorage` yok (SI-24), yani parola sayfa yenilenmesini
   de geçemez.

Sunucu tarafında aynı değer imzalama çağrısı boyunca redaksiyon registry'sine
kayıtlıdır ve çağrı biter bitmez düşürülür (SI-162), dolayısıyla bir hata
yolunda log'a düşmesi de mümkün değildir. **Kod değiştirilmedi.**

### 5.2 Üç sonuç durumu (ADR-0002 §3)

| `outcome` | Nasıl sunulur | Retry butonu |
|---|---|---|
| `accepted` | "Kabul edildi" (success) + `Sonuc/HTTP/Oda/Nonce/Ozet` satırı | yok (gerek yok) |
| `refused` | "Reddedildi" (danger) + backend'in gerekçesi. **HTTP 422** için ayrıca "aynı metin yakın zamanda yazılmış; aynı baytları yeniden yollamak tekrar reddedilir" | yok — aynı baytlar tekrar reddedilir |
| `outcome_unknown` | "Sonuc bilinmiyor: sunucu yazmis olabilir" (warning). Bunu "gönderildi" veya "başarısız" diye sunmak **yasaktır**; `reconciliation_required` iken uzlaştırmanın (oda okuma) bu sürümde açık olmadığı dürüstçe yazılır | **yok** — kör tekrar mesajı ikinci kez yayımlayabilir ve bu sürümde odayı okuyup hangisinin olduğunu anlama yolu yok |

Yerel servise hiç ulaşılamayan bir gönderim de aynı dürüstlüğe tabidir:
`timeout`/`network`/`canceled` sınıflarında `ErrorRegion`'ın yanında "Bu sonuc
bilinmiyor" uyarısı çıkar, çünkü isteğin yanıtını alamamak sunucunun yazmadığı
anlamına gelmez (pinli `llms.txt`: bir fetch hatası, yazmanın başarısız olduğu
kanıtı değildir).

`response_excerpt` uzak içeriktir: `<pre>` içinde **düz metin** olarak, anchor
üretmeden ve markup olarak yorumlanmadan gösterilir (SI-54/AC-17; test:
`::renders the server excerpt as inert plain text`).

Redakte tanı kopyalama yükü değişmedi: yalnız
`{code, status, kind, request_id, timestamp, section}`. Canonical metin, DID,
imza, oda, nonce ve `send_token` bu yüke **girmez** (test: `::keeps the
canonical text, DID, signature and nonce out of the copied diagnostics`).

### 5.3 Neden not gönderimi yok?

ADR-0002 §1: pinlenmiş protokol imzalı note yazmasını yalnız `room-owners` ve
`room-allow` namespace'lerinde kabul ediyor; künyenin istediği DID profil notu
ise **imzasız** lane'de yayımlanır ve imza kanıtı üretemez. İmzasız bir yazmayı
"gönderildi" rozetiyle sunmak kanıt seviyelerini karıştırmak olurdu. UI bu
gerekçeyi backend'in kendi cümlesiyle (`note_lane_detail`) gösterir; eksik bir
buton olarak bırakmaz.

## 6. Kaynaklar

| Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|
| otomatik durum okuma (dışarı istek YAPMAZ) | bölüm seçili | `fetchTechnocore()` | "Durum okunuyor..." | son denetim durumu; hiç yapılmadıysa dürüst boş durum | `ErrorRegion` "Durum okunamadi" + "Yeniden dene" (yalnız okumayı tekrarlar) | `kind=timeout` | bölüm değişince unmount | `pages.test.tsx::starts as not yet checked and offers an explicit user action` |
| "Resmi kaynaklari denetle" | oturum + CSRF | `POST /api/technocore/refresh` (`refreshTechnocore`, 30 sn timeout) | buton "Denetleniyor..." + disabled | belge erişimi ve protokol değerlendirmesi ayrı raporlanır | `ErrorRegion` "Denetim yapilamadi"; retry aynı açık eylemi tekrarlar | `kind=timeout`, retry sunulur | yok (sonuç beklenir) | `pages.test.tsx::disables the check button while a check is in flight`, `::shows official source metadata after a check`, `client.test.ts::gives the official-source check a longer 30 second deadline` |
| URL "Kopyala" | kaynak listelendi | `navigator.clipboard.writeText` | — | "Kopyalandi" (2 sn) | "Kopyalanamadi" | — | — | `pages.test.tsx::never turns a remote URL into a clickable link` (URL asla anchor değildir, SI-54/AC-17) |

## 7. Kanıtlar

Paket E ile bu bölüm kanıt defterine dönüştü. Bileşenler:
`pages/EvidencePage.tsx` (kabuk + güven seviyesi **tanım** listesi + kaynak
sınıflandırma uyarısı) ve `components/evidence/EvidenceLedgerPanel.tsx`
(zincir, kayıtlar, yakalama ve dışa aktarım).

Bölümün taşıdığı beş kural: **(1)** dört güven seviyesi kayıt başına ayrı ayrı
raporlanır, hiçbir zaman toplanmaz; **(2)** yakalama yalnız kullanıcı isteğiyle
çalışır — mount'ta, zamanlayıcıda veya bir gönderimin adımı olarak değil;
**(3)** altı yakalama durumu altı ayrı bulgudur ve beşi "doğrulandı" değildir;
**(4)** hiçbir yerde yazma tekrarı sunulmaz; **(5)** hiçbir uzak değer aktif
içerik olmaz (SI-54).

| Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|
| otomatik kayıt okuma | bölüm seçili | `GET /api/evidence/records` (`fetchEvidenceRecords`, 15 sn) | "Kanit kayitlari okunuyor..." | kayıt listesi + `N kayit` rozeti; kayıt yoksa dürüst boş durum ("Henuz kanit kaydi yok") | `ErrorRegion` "Kanit kayitlari okunamadi" + "Yeniden dene" (yalnız okumayı tekrarlar) | `kind=timeout` aynı bölge | bölüm değişince unmount | `EvidenceLedgerPanel.test.tsx::lists an archived record with its room, nonce and outcome`, `::shows an honest empty state when nothing has been archived`, `::shows a persistent error with a retry when the ledger cannot be read` |
| otomatik zincir okuma | bölüm seçili | `GET /api/evidence/audit` (`fetchAuditChain`, 15 sn) | "Zincir durumu okunuyor..." | beş durumdan biri + `claim` **birebir** + sayaçlar | `ErrorRegion` "Audit zinciri okunamadi" + "Yeniden dene"; **kayıt listesi etkilenmez** | `kind=timeout` aynı bölge | bölüm değişince unmount | `EvidenceLedgerPanel.test.tsx::names the %s verdict distinctly` (5), `::keeps the ledger readable when only the chain read fails` |
| kayıt başına dört güven seviyesi | kayıt listelendi | yok (`record.levels`) | — | `Seviye 1..4` ayrı satırlar, her biri `Var`/`Yok` rozeti + kendi cümlesi; Seviye 4 `external_anchor === null` iken açıkça "yoktur, null olarak tutulur" der | — | — | — | `EvidenceLedgerPanel.test.tsx::reports all four levels separately instead of summing them`, `::states that level 4 is absent rather than leaving it blank` |
| "Kanit satirini yakala (yalniz okur)" / yakalanmışsa "Yakalamayi yeniden dene (yalniz okur)" | kayıt var, oturum + CSRF, başka yakalama uçuşta değil | `POST /api/evidence/capture` (`captureEvidenceLine`, **90 sn**) | buton "Yakalaniyor..." + **listedeki bütün** yakalama butonları disabled | altı durumdan biri ayrı ayrı sunulur (§7.1); ardından kayıt listesi yeniden okunur ki satır ile sonuç bölgesi çelişmesin | `ErrorRegion` "Yakalama tamamlanamadi" (`onRetry` **yok**; kullanıcı butona kendi basar) | `kind=timeout` aynı bölge — "okuyamadım", "satır orada değil" DEĞİLDİR | yok (sonuç beklenir) | `EvidenceLedgerPanel.test.tsx::presents %s as a finding of its own` (6), `::starts no second capture while one is in flight`, `::keeps the redacted diagnostics payload unchanged when a capture fails` |
| dışa aktarım onay kutusu (`Checkbox`) | — | yalnız React state | — | işaretlenmeden **her iki** dışa aktarım butonu `isDisabled`; ikinci aktivasyon istek başlatmaz | — | — | — | `EvidenceLedgerPanel.test.tsx::sends no request until consent has been given` |
| "JSON olarak disa aktar" | onay kutusu işaretli, başka dışa aktarım uçuşta değil | `POST /api/evidence/export` `{format:"json", acknowledged:true}` (`exportEvidence`, 15 sn) | buton "Hazirlaniyor..." + ikisi de disabled | blob + geçici object URL + anchor tıklaması; ad **istemci sabiti** `technocore-station-kanit.json`; URL hemen revoke edilir | `ErrorRegion` "Disa aktarim tamamlanamadi" (`onRetry` **yok**); başarı taklidi yapılmaz | `kind=timeout` aynı bölge | yok | `EvidenceLedgerPanel.test.tsx::exports JSON once the consent box is ticked`, `::reports a refused export instead of pretending a file was produced` |
| "Markdown olarak disa aktar" | aynı | `POST /api/evidence/export` `{format:"markdown", acknowledged:true}` | aynı | ad `technocore-station-kanit.md` | aynı | aynı | yok | `EvidenceLedgerPanel.test.tsx::exports Markdown under the same single consent step` |
| güven seviyesi tanım listesi | — | yok (statik) | — | dört seviyenin **tanımı**; bir kaydın durumu olmadığı açıkça yazılır | — | — | — | `pages.test.tsx::presents the level list as a definition, not as a verdict` |

### 7.1 Altı yakalama durumu (ADR-0003 §3)

Tek bir yeşil rozete indirgenmez; her durum kendi başlığını, kendi tonunu ve
kendi paragrafını taşır. Backend'in cümlesi (`capture_detail`) bizimkinin
**yanında** gösterilir, yerine değil.

| Durum | Başlık | Ton | UI'ın söylediği |
|---|---|---|---|
| `line_captured` | "Satir yakalandi" | ok | **Yalnızca Seviye 2 sunucu gözlemidir.** Mesajın yayımlandığının bağımsız bir ispatı değildir; tek bir sunucunun kendi durumu hakkındaki cevabıdır |
| `line_not_found` | "Satir bulunamadi" | pending | **Hiçbir şey kanıtlamaz.** Oda halkası unutur; unutulmuş bir kayıt ile hiç yazılmamış bir kayıt taramada birebir aynı görünür |
| `generation_changed` | "Oda donemi degisti" | pending | Kayıtlar **karşılaştırılamaz**: uyuşmazlık değil, farklı bir dönem. Bulunmuş bir satır bile bu durumda karşılaştırmaya girmez |
| `stream_truncated` | "Tarama tamamlanamadi" | pending | **Okunamama durumu.** Eksik taramada satırın görünmemesi, yokluğun kanıtı değildir |
| `parse_problem` | "Satirlar okunamadi" | pending | **Okunamama durumu.** Okunamayan bir satır değiştirilmiş bir satır demek değildir (IMP-238 emsali) |
| `fetch_failed` | "Okuma tamamlanamadi" | problem | **Okunamama durumu.** Gönderimin akıbeti hakkında hiçbir şey söylemez |

Her durumun altında istisnasız aynı cümle çıkar: *"Yakalama yalniz okur. Okuma
dilediginiz kadar yeniden denenebilir; gonderim hicbir durumda ve hicbir yolla
yeniden denenmez."* Buton etiketi de bunu taşır — "(yalniz okur)" — çünkü
burada sadece "Yeniden dene" yazan bir buton "tekrar gönder" diye okunurdu.
Test: `EvidenceLedgerPanel.test.tsx::offers no write retry after %s` (altı
durum için de bütün buton etiketlerini tarar).

**`line_not_found` neden retry taşımaz?** Taşır — ama yalnız **okuma**
retry'ı. Ayrım şudur: yakalama bir okumadır ve sunucuda hiçbir şeyi
değiştirmez, bu yüzden istenildiği kadar tekrarlanabilir. Değiştirilemeyen şey
gönderimdir: nonce harcanmıştır (SI-149/150) ve bulunamayan bir satır bunu
telafi etmez. Bu yüzden bu yüzeyde bir *gönderim* retry'ı ne vardır ne de
eklenebilir — `client.ts`'deki yakalama işlevi bir kayıt kimliğinden başka bir
şey almaz, route da odayı satırdan okur.

**`outcome_unknown` + `line_not_found`:** `write_outcome === "outcome_unknown"`
olan her kayıt "Bu gonderimin sonucu hala bilinmiyor" uyarısı taşır; yakalama
`line_not_found` döndüyse uyarıya ikinci bir cümle eklenir ve bu birleşimin
**"gönderim yapılmadı" anlamına gelmediği** yazılır. Test:
`::never turns an unknown outcome plus a missing line into a send that did not
happen` (DOM metninde "gonderilmedi"/"gonderilmemis" aranır).

### 7.2 Audit zinciri: beş durum ve dürüst sunum

| Durum | Başlık | Ton |
|---|---|---|
| `intact` | "Zincir tutarli" | ok |
| `empty` | "Zincir bos" | inactive |
| `broken_link` | "Zincir halkasi kirilmis" | problem |
| `head_mismatch` | "Zincir basi uyusmuyor" | problem |
| `unavailable` | "Zincir dogrulanamadi" | pending — asla "geçti" değil |

`claim` alanı **backend'in ürettiği hâliyle** basılır; UI kendi iddiasını
kurmaz, çünkü aynı cümleyi iki yüzeyin bağımsız yazması tam olarak ikisinin
zamanla ayrışma biçimidir. Yanına üç sınır cümlesi konur:

1. Zincirin içinde kendi uzunluğunu söyleyen bir şey yoktur; **sonun kesilmesi,
   ayrı bir zarfta tutulan zincir başı olmadan tespit edilemez.**
2. Bu bir garanti değildir: **aynı Windows kullanıcısı olarak çalışan** bir
   saldırgan zarfı açar, bütün MAC'leri yeniden hesaplar ve başı yeniden yazar.
3. Yarım kalan bir yazma bir saldırı değildir; dosya ile veritabanı işlemi
   atomik olarak birlikte işlenemez.

İzin verilen tek ifade **"çevrimdışı değişikliğe karşı tespit edici"**dir.
"Değişmez kayıt", "sunucu kanıtı", "güvenilir zaman kanıtı", "airdrop uygunluk
kanıtı", "değiştirilemez kayıt" ve "kurcalanamaz kayıt" yasaktır
(`docs/evidence-model.md` §2). Frontend testi bu altı ifadeyi **katlanmış**
karşılaştırmayla arar (küçük harf, aksan ayrıştırma, `ı` → `i`), yani ASCII'ye
düşürülmüş yazımlar da yakalanır. Testler:
`pages.test.tsx::uses no forbidden over-claiming evidence language`,
`EvidenceLedgerPanel.test.tsx::uses none of the forbidden claims after %s`
(altı yakalama durumunun her biri için ayrı ayrı).

### 7.3 Dışa aktarım: onay, kimlik bağlantısı ve tanı raporundan ayrılığı

- **Açık onay olmadan istek gönderilmez.** Onay kutusu işaretlenmeden her iki
  buton `isDisabled`'dır ve bir aktivasyon `fetch`'e hiç ulaşmaz. Bu tek engel
  değildir, **ilk** engeldir: `EvidenceExportRequest.acknowledged`'ın
  varsayılanı yoktur (eksikse 422), route ayrıca yeniden kontrol eder ve servis
  yalnız `Literal[True]` ile kurulabilen bir `ExportConsent` alır. UI'daki kutu
  göstermelik olsaydı, kullanıcıya onay adımının da göstermelik olduğu
  öğretilirdi.
- **Kimlik bağlantısı uyarısı.** Dosya public DID'i, imzaları ve gönderim
  kayıtlarını taşır. Bunlar gizli değerler değildir; ama paylaşıldıklarında bu
  makinedeki kimlik ile paylaşılan yer arasında **kalıcı bir kimlik bağlantısı**
  kurulur. Uyarı bunu açıkça söyler (test: `::warns that sharing the file
  creates an identity link`).
- **Redakte tanı raporundan ayrı bir yüzeydir.** `ErrorRegion`'ın "Tani
  bilgisini kopyala" çıktısı yalnız
  `{code, status, kind, request_id, section, timestamp}` taşır ve **hiçbir
  kanıt alanı oraya girmez** — Paket E bu yükü değiştirmedi (test:
  `EvidenceLedgerPanel.test.tsx::keeps the redacted diagnostics payload
  unchanged when a capture fails`, anahtar listesini sıralı olarak pinler ve
  oda/nonce/DID/digest'in yükte olmadığını ayrıca doğrular). Dışa aktarım ise
  kayıtların kendisidir; biri diğerinin yerine kullanılmaz ve UI bunu yazar.
- **Teslim yolu recovery ile aynıdır** (ADR-0003 §9): HTTP yanıtı +
  `Content-Disposition` + blob → geçici object URL → anchor tıklaması → hemen
  `revokeObjectURL`. Sunucu hiçbir yola dosya yazmaz.
- **İndirme adı istemci sabitidir** (`technocore-station-kanit.json` /
  `.md`). Sunucunun `Content-Disposition` adı bilinçli olarak **okunmaz**:
  sunucu zaten adı bir allow-list'ten yeniden kuruyor, ad bir istemci
  meselesidir ve kendimizin söyleyebildiği bir değeri geri kazanmak için bir
  başlık parser'ı eklemek yalnızca yanılabilecek bir parser daha demektir.

### 7.4 Ham bayt yoktur

`GET /api/evidence/records` istek/yanıt **baytlarını döndürmez**; yalnız
hash'ler döner ve UI onları da tam basmaz — `shortDigest` ile ilk 12 karakteri
gösterilir (`src/lib/digest.ts`). Gerekçe: SHA-256 de bir seed de 64 hex
karakterdir ve uygulamanın "DOM'a hiçbir 64-hex koşusu çıkmaz" kuralı ancak tek
bir ortak yardımcı varken zorlanabilir. Kanıt test fixture'ı **tam boy**
digest'ler taşır, böylece iddia fixture'ı değil bileşeni sınar (test:
`EvidenceLedgerPanel.test.tsx::never renders a 64-hex run, the same shape as a
seed`).

## 8. Ayarlar ve Yardım

Paket G bu bölüme OpenCode Go bağlantısını ekledi:
`pages/SettingsHelpPage.tsx` (tema, servis bilgisi, yazma kapısı, yardım) +
`components/opencode/OpenCodeConnectionPanel.tsx` (credential, denetim,
sözleşme notları, model kataloğu, kota bağlamı).

### 8.1 Verilmiş sözün bilinçli revizyonu

Bu sayfa şunu söylüyordu: *"bu ekranda bilerek hicbir secret giris veya
gosterim alani yoktur"*, ve `pages.test.tsx::offers no secret input anywhere`
bunu `input[type="password"] === null` ile sabitliyordu. Paket G ile söz artık
doğru değil: sağlayıcı API anahtarı burada giriliyor.

Söz **sessizce silinmedi, daraltılarak yeniden yazıldı** (ADR-0005 §10,
ADR-0001 §6). Yeni metin üç şeyi ayrı ayrı söylüyor: (1) DID seed'i, private
key ve recovery parolası için **frontend'de hiçbir istisna yoktur** ve bunları
kabul eden ya da gösteren bir alan uygulamanın hiçbir yerinde bulunmaz;
(2) tek istisna sağlayıcı API anahtarıdır; (3) anahtar maskeli alana bir kez
yazılır, aynı-origin yerel servise bir kez iletilir, **kaydedildikten sonra
alandan ve bellekten silinir** ve hiçbir yoldan geri gösterilemez.

Test **gevşetilmedi, güçlendirildi**. Eski iddia "hiç password alanı yok"tu;
yenisi "**tam olarak bir** password alanı olabilir, o da OpenCode anahtarıdır,
`autocomplete="off"` taşır, seed/private key/recovery/kasa parolası etiketli
hiçbir alan yoktur ve `textarea` hâlâ sıfırdır". Eski iddianın "en az bir
password alanı var" gibi zayıf bir biçime çevrilmesi ikinci bir alanın kimse
fark etmeden eklenmesine izin verirdi.

### 8.2 Kontrol tablosu

| Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|
| "Koyu tema / Acik tema" | — | `applyTheme()` (yalnız DOM; kalıcı depolama YOK) | — | tema değişir; yeniden açılışta sistem teması | — | — | — | `pages.test.tsx::hosts the theme control and says the choice is not persisted` |
| otomatik kapı okuma | bölüm seçili | `GET /api/write-gate` (`fetchWriteGate`) | "Kapi durumu okunuyor..." | kapı özeti + kontrol listesi | `ErrorRegion` "Kapi durumu okunamadi" + "Yeniden dene" | `kind=timeout` | bölüm değişince unmount | `pages.test.tsx::renders the real write gate from /api/write-gate`, `::shows a persistent error with retry when the gate cannot be read` |
| uygulama/servis bilgisi | kabuk `status` yüklü | prop (yeni istek yok) | — | aşama/mod/veritabanı/oturum taşıma | durum yoksa dürüst açıklama metni | — | — | `pages.test.tsx::shows the application and service facts from the backend status` |
| yardım notu | — | — | — | "OpenCode Go baglantisi bu pakette acildi... kullanim kilavuzu Paket J'de"; tanı çıktısının redakte olduğu ve anahtarın oraya girmediği yazılır | — | — | — | `pages.test.tsx::is honest about what arrives in later packages` |
| otomatik bağlantı okuma | bölüm seçili | `GET /api/opencode/status` (`fetchOpenCodeStatus`, 15 sn) | "Baglanti durumu okunuyor..." | `configured` + parmak izi + iki zaman damgası; **anahtar yok** | `ErrorRegion` "Baglanti durumu okunamadi" + "Yeniden dene" (yalnız okumayı tekrarlar) | `kind=timeout` aynı bölge | bölüm değişince unmount | `pages.test.tsx::never shows a stored key back, only a fingerprint` |
| API anahtarı alanı (`PassphraseField`, `type=password`, `autoComplete="off"`) | anahtar kayıtlı değil **veya** "Anahtari degistir" basıldı | yalnız yerel React state | — | değer yalnız bileşen state'inde; panoya, bildirime, ölçüme, tanı çıktısına yazılmaz; tarayıcı tarafında hiçbir yere kaydedilmez | — | — | "Vazgec" alanı ve state'i siler | `pages.test.tsx::permits exactly one masked field, and it is the OpenCode provider key`, `OpenCodeConnectionPanel.test.tsx::uses no browser-side persistence for the key or the selection` |
| "Anahtari kaydet" | alan boş değil, başka işlem uçuşta değil | `POST /api/opencode/credential` `{api_key}` (`storeOpenCodeCredential`, **20 sn**) | buton "Kaydediliyor..." + panelin bütün butonları disabled | anahtar **bir kez** gider; dönen durum "kaydedildi, doğrulanmadı"dır; input ve state anında temizlenir, alan ekrandan kalkar | `ErrorRegion` "Anahtar kaydedilemedi" — **sunucu düzyazısı düşürülür**, yerine `ApiError`'ın güvenli sınıf cümlesi konur (yansıtılan anahtar render edilmez); `onRetry` yok, kullanıcı butona kendi basar | `kind=timeout` aynı bölge; anahtar **hata durumunda** alanda kalır ki kullanıcı yeniden yazmak zorunda kalmasın | yok (sonuç beklenir) | `OpenCodeConnectionPanel.test.tsx::wipes the key from the field and from the document once it is stored`, `::keeps the redacted diagnostics payload free of the key when a store fails`, `::starts no second store while one is in flight` |
| "Anahtari degistir" / "Vazgec" | anahtar kayıtlı | yalnız React state | — | maskeli alanı açar / kapatır ve state'i siler | — | — | — | `OpenCodeConnectionPanel.test.tsx::offers no control that reads a stored key back` |
| "Baglantiyi denetle" | başka işlem uçuşta değil | `GET /api/opencode/status` (aynı okuma) | buton "Denetleniyor..." + hepsi disabled | **rozet üretmez.** En güçlü sonuç "Anahtar kaydedildi, dogrulanmadi" + gerekçelerin **tamamı** (çoğul liste). Yanına "yeni bir dogrulama uretmez" ve "Anahtarin bicimi dogru diye gecerli sayilmaz" yazılır | `ErrorRegion` "Baglanti durumu okunamadi" | `kind=timeout` aynı bölge | yok | `OpenCodeConnectionPanel.test.tsx::produces no verified verdict and no green badge from a check` |
| "Baglantiyi kaldir" | anahtar kayıtlı | `POST /api/opencode/credential/forget` (boş gövde, 15 sn) | buton "Kaldiriliyor..." + hepsi disabled | `configured=false`; parmak izi ve zaman damgaları düşer | `ErrorRegion` "Anahtar kaldirilamadi" (düzyazı yine düşürülür); `onRetry` yok | `kind=timeout` aynı bölge | yok | `OpenCodeConnectionPanel.test.tsx::offers no control that reads a stored key back` |
| "Modelleri yenile" | başka işlem uçuşta değil | `POST /api/opencode/catalog/refresh` (boş gövde, **90 sn**) | buton "Yenileniyor..." + hepsi disabled | katalog durumu + **listenin okunduğu an** + **son deneme** ayrı ayrı; `listing_caveat` birebir; `N listelendi · M secilebilir` | başarısızlık bir *durum*tur: "Listeye erisilemedi" + `detail (HTTP nnn)`; **eski liste ve tarihi silinmez**. Route hatası olursa `ErrorRegion` "Model listesi yenilenemedi" | `kind=timeout` aynı bölge | yok | `OpenCodeConnectionPanel.test.tsx::shows the cache date and the listing caveat`, `::reports a failed refresh without deleting the cache or its date`, `::starts no second refresh while one is in flight` |
| model radyo grubu (`fieldset` + native `<input type="radio">`) | liste dolu | yalnız React state | — | model başına kimlik, sahip, protokol + eşleme doğrulaması, veri saklama + kaynak + **okunduğu tarih**, eğitim rozeti. **Eşlemesi olmayan model listelenir ama `disabled`'dır** ve "Secilemez: `<reason>`" görünür. Mount'ta **hiçbir model seçili değildir** | — | — | seçim değişince ek onay düşer | `OpenCodeConnectionPanel.test.tsx::lists an unmapped model but refuses to let it be selected, and says why`, `::preselects nothing, so a training model is never the default`, `::says an unknown retention is unknown rather than reassuring`, `::shows the data policy with its source and the date it was read`, `::does not invent a display name, a limit or tool support` |
| eğitim onay kutusu (`Checkbox`) | seçilen model `requires_training_acknowledgement` | yalnız React state | — | işaretlenmeden "Modeli sec" `isDisabled`; kutunun yanında modelin yayımlanmış veri işleme koşulu + kaynak + tarih yazar | — | — | seçim değişince otomatik düşer | `OpenCodeConnectionPanel.test.tsx::requires an extra sharing consent before a training model can be chosen`, `::drops the consent when the pick changes` |
| "Modeli sec" | seçili model `selectable`, gerekiyorsa onay işaretli, başka işlem uçuşta değil | `POST /api/opencode/model` `{model_id, training_acknowledged}` (`selectOpenCodeModel`, 15 sn) | buton "Seciliyor..." + hepsi disabled | "Secili model" satırı güncellenir; seçim **backend'de** yaşar, tarayıcıda değil | `ErrorRegion` "Model secilemedi" + **sunucunun gerekçesi birebir** (bu yol anahtar taşımaz, düzyazı korunur); sessiz ikame **yoktur** | `kind=timeout` aynı bölge | yok | `OpenCodeConnectionPanel.test.tsx::keeps a refusal to select as a refusal, with the server's reason`, `::says the selection is permanent but proves nothing about access` |
| sözleşme notları (statik + backend metni) | bağlantı okundu | yok | — | `auth_header_caveat`, `deferral`, `shape_provenance` **birebir**; "akis: yok · arac cagrisi: yok"; "anahtarin bagli olmasi dosya paylasimi demek degildir" | — | — | — | `OpenCodeConnectionPanel.test.tsx::states that the auth header is an unverified assumption`, `::says streaming and tool calls are absent and why`, `::says a connected key is not permission to share files` |
| kota ve maliyet bağlamı | bağlantı okundu | yok (`spending`) | — | yayımlanmış limitler olduğu gibi; `limit_behaviour`, `use_balance`, `local_counter_caveat`, `unknown_cost_sentence` birebir; "Butce bu surumde yok" | — | — | — | `OpenCodeConnectionPanel.test.tsx::never calls the subscription unlimited and never turns an unknown cost into zero` |

### 8.3 Dürüstlük kuralları ve nasıl zorlandıkları

Beşi de bir gözden geçirme alışkanlığı değil, koddaki bir yapı:

1. **Yeşil rozet üretilemez.** `CHECK_TONE` tablosunda `ok` tonu **yoktur** ve
   `check.state` tipinde `verified` **yoktur**. Rozet, tonun eksikliği
   yüzünden basılamaz.
2. **Bütçe açılamaz.** `budget_available` TS tarafında `false` *tipidir*;
   panelde dallanma yoktur, çünkü bu yapının açık olabildiği bir durum yoktur.
   `streaming_supported` ve `tool_calls_supported` de aynı biçimdedir, bu
   yüzden "yok" kelimeleri kayamaz.
3. **"Sınırsız" yazılamaz.** Cümleler backend'den birebir gelir ve backend
   kendi cümlesini `assert_no_unlimited_claim` ile reddeder; frontend testi
   ayrıca bütün belgede `sinirsiz`/`unlimited` aramaz olduğunu doğrular.
4. **Bilinmeyen maliyet sıfır olmaz.** `unknown_cost_sentence` her zaman
   görünür; panel hiçbir yerde aritmetik yapmaz.
5. **Yansıtılan anahtar render edilmez.** Credential yolundaki hatalar
   `withoutServerProse` ile yeniden kurulur: düzyazı yerine kararlı makine
   kodu konur, `ApiError` kendi güvenli sınıf cümlesine düşer. `code`,
   `status`, `kind` ve `request_id` korunur — yani **redakte tanı payload'ı
   `{code,status,kind,request_id,section,timestamp}` olarak değişmez**; düşen
   tek şey anahtarı taşıyabilecek alandır. Katalog ve model yolları düzyazıyı
   korur, çünkü o iki istek kimlik bilgisi taşımaz ve "bu modelin protokol
   eşlemesi yok" cümlesi reddin ta kendisidir.

### 8.4 Bu bölümde bilerek olmayanlar

- **Kaydedilmiş anahtarı gösteren, maskeleyen, kısmen açan veya kopyalayan
  hiçbir kontrol yok** — çünkü onu döndürecek bir uç nokta da yok. Kullanıcı
  parmak izini ve iki zaman damgasını görür.
- **Ücretli bir probe butonu yok.** Gerçek küçük bir çağrının maliyetli
  olabileceği yazılır, ama bu turda uygulanmaz (ADR-0005 §4).
- **Tamamlama (completion) çağrısı yok.** O yürütücü paketinin işidir; buraya
  bir buton koymak "Station kendiliğinden para harcamaz" iddiasına dipnot
  eklerdi.
- **Fallback yok.** Adreslenemeyen model bir reddir, sessiz bir ikame değil.
- **Tarayıcı deposu yok** (SI-24): ne anahtar, ne seçilen model, ne "beni
  hatırla". Seçim kalıcı bir ayardır ama kalıcılığı backend'dedir.

## 9. Bölüm kayıt defteri

`src/sections.ts` dokuz bölümü kaydeder; `ready: false` olanlar nav'da HİÇ
görünmez:

| Bölüm | `ready` | Açılacağı paket |
|---|---|---|
| Genel Bakis | evet | — |
| Is Tara | evet | — (H1 ile açıldı, ADR-0007 §9; sözleşmesi §12) |
| Gorevler | hayır | F / H2 |
| Aktivite | hayır | H2 |
| Kimlik ve Guvenlik | evet | — |
| Olustur ve Dogrula | evet | — |
| Kaynaklar | evet | — |
| Kanitlar | evet | — (kayıt defteri E ile doldu) |
| Ayarlar ve Yardim | evet | — |

Test: `App.test.tsx::never shows a section that is not ready`. Bu testin
**kendisi** H1'de değişmedi; yalnız beslediği iki veri sabiti güncellendi
(`VISIBLE_SECTIONS` sıralı `toEqual` ile, `HIDDEN_SECTIONS` artık
`["Gorevler", "Aktivite"]`). E2E tarafında aynı liste `e2e/fixtures.ts`
içindeki `SECTION_LABELS`'tır ve erişilebilirlik, CSP ve klavye geçişleri bu
liste üzerinden döndüğü için yeni bölüm otomatik olarak üçünün de kapsamına
girdi.

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
4. **Tarayıcı QA artık var, ama bu haritanın tamamını kapsamıyor.**
   *Değişiklik (4 Eylül 2026, ADR-0006):* bu madde daha önce "Tarayıcı QA yok
   (ADR-0001 m.4) — gerçek tarayıcı doğrulaması Paket J'dedir" diyordu. O
   cümle yazıldığı tarihte doğruydu; ADR-0001 §4 tarayıcı QA'sını bu döngüde
   yasaklıyordu. Kullanıcı 4 Eylül 2026'da bunu **açıkça tersine çevirdi** ve
   ADR-0006 kararı kayda geçti.
   Bugünkü durum: `apps/station-web/e2e/` altında Playwright + Chromium ile
   koşan bir tarayıcı paketi vardır ve **gerçek backend'e**, gerçek
   production build'ine ve gerçek güvenlik başlıklarına karşı çalışır.
   Kapsadıkları dardır ve bilinçlidir: gerçek CSP altında React Aria
   inline-style hash'i (A1-R1), gerçek odak sırası ve focus trap, gerçek
   klavye gezinmesi, `URL.createObjectURL` indirme yolu ve
   `Content-Disposition` gidiş-dönüşü, composer'ın üç onayı, OpenCode anahtar
   maskeleme, erişilebilirlik dumanı ve dış ağa **ölçülmüş** sıfır istek.
   **Kapsamayanlar** aynı ölçüde önemlidir: bu haritadaki hata/loading/timeout
   sözleşmesinin çoğu hâlâ yalnız Vitest + jsdom ile kanıtlıdır; tarayıcı
   testleri onların yerine geçmez (ADR-0006 m.1). Gerçek kimlik oluşturma,
   gerçek `.tcrec` üretimi, gerçek Technocore yazması ve canlı OpenCode
   çağrısı tarayıcı QA'sında **yasaktır** ve edilmez. Bir tarayıcı testinin
   geçmesi kullanıcı kabulü değildir; kabul hâlâ Paket J'dedir.
   Ayrıntı: [`browser-qa.md`](browser-qa.md).
5. **`outcome_unknown` uzlaştırması dar anlamlıdır** (ADR-0003 §4). Paket E
   kanıt okumasını açtı, ama `reconciliation_required` "kanıt yakalama
   denenebilir" demektir, "yeniden gönder" değil. `ComposerPanel`'in gönderim
   sonucu bölgesinde hâlâ retry yoktur ve orada gösterilen cümle
   değişmemiştir; Kanıtlar bölümü aynı kayda **salt okunur** bir yakalama
   eylemi ekler ve altı sonucun beşi hiçbir şeyi çözmez (§7.1).
6. **`ComposerPanel`'in sonuç bölgesi hâlâ kalıcı değildir.** Sayfa
   yenilendiğinde o bölge kaybolur; kalıcı kayıt artık Kanıtlar bölümündedir
   (AC-14). İki yüzey aynı gönderimi farklı ömürlerle gösterir ve bu bilinçli
   bir ayrımdır: biri az önce ne olduğunu, diğeri ne arşivlendiğini söyler.
   Tarayıcı depolaması yasak olduğu için (SI-24) arada bir önbellek yoktur.
7. **Halka (ring) düşüşü sinyali tarama yanıtında taşınmıyor.** Backend
   `RingDropNotice`'ı üretebiliyor ve `WorkScanRingDrop` şeması tanımlı, ama
   tarama imleçsiz okuduğu için (`since` gönderilmiyor) sinyal hiç üretilmiyor
   ve `WorkScanRoomResult` yanıtında böyle bir alan yok. UI bu boşluğu bir
   alan uydurarak doldurmuyor: "Halka dususu ayri bir sinyaldir" uyarısı
   sinyalin neden bu yanıtta olmadığını yazıyor. İmleçli okuma açılırsa alan
   ve gösterim birlikte gelmelidir (§12.3).
8. **Kibble'ın iki İngilizce cümlesi frontend'de sabit.** Tel üzerinde yalnız
   Türkçe karşılığı (`self_description`) geliyor; servisin kendi sözlerini
   birebir göstermek ADR-0007 §1'in isteği olduğu için iki cümle
   `WorkScanPanel.tsx`'te alıntı olarak duruyor. Bu bir **ikinci kopyadır**
   ve backend'deki `SELF_DESCRIPTION`/`SCORE_SELF_DESCRIPTION` ile
   sürüklenebilir; tel bu iki alanı taşımaya başlarsa sabitler düşürülmelidir.
9. **Üst karakter sınırı aşımı butonu kilitlemez.** Süpürme metni kısaltabilir
   ve etkin sınır sunucuda **süpürülmüş** metne uygulanır; UI uyarır ve alanı
   `aria-invalid` yapar ama son kararı sunucuya bırakır. Alt sınırın altı ise
   engellenir: süpürme metni yalnız kısaltabildiği için kısa bir ham metin
   sınırı hiçbir zaman geçemez.

## 11. HeroUI bileşen kümesi

Kullanılan HeroUI v3 bileşenleri **11 tanedir** ve kilitlidir: `Alert`,
`Button`, `Card`, `Checkbox`, `Chip`, `Input`, `Label`, `Modal`, `Separator`,
`TextArea`, `TextField`. ADR-0001 m.2 ile `Tabs` düşmüştür ve geri gelmez.

`TextArea` Paket D ile bilinçli olarak eklendi ve küme 10'dan 11'e çıktı:
composer çok satırlı bir alan istiyor, alternatifler daha kötüydü (çıplak bir
`<textarea>` incelenmiş yüzeyin dışında kalır ve alan/odak davranışını
kaybeder; `Input` bir mesajı taşıyamaz). Bileşen koda dokunulmadan önce
`heroui-react` MCP üzerinden v3 dokümantasyonuyla doğrulandı: ücretsiz bileşen,
standart `<textarea>` attribute'ları, `rows` prop'u ve `TextField` içinde
çocuk olarak kullanılan belgelenmiş kompozisyon (etiket ve doğrulama durumu
alanla birlikte kalsın diye). Yanında başka hiçbir bileşen eklenmedi.

**Paket G de hiçbir bileşen eklemedi; küme 11'de kaldı.** Maskeli anahtar
girişi için yeni bir bileşen gerekmedi: mevcut `PassphraseField` kalıbı
(`TextField` + `Label` + `Input type="password"`) zaten tam olarak bu iş için
incelenmişti; tek değişiklik `autoComplete` union'ının `"off"` ile
genişletilmesidir. Bir sağlayıcı API anahtarı tarayıcının bildiği anlamda bir
parola değildir; `"new-password"` bir parola yöneticisini bu değeri üretmeye
ve saklamaya davet ederdi ve anahtar bu uygulamanın göremediği bir yere
düşerdi. Union `string`'e açılmadı, üç değere genişletildi ki izin verilen
değerler çağrı yerinde sayılı kalsın.

Model seçici için `Select`/`Autocomplete` **kullanılmadı**: ikisi de
allowlist'in dışında ve kümeyi 12-13'e çıkarırdı. Onların yerine
`IdentityDialogs.tsx`'teki mevcut radio-fieldset kalıbı kullanıldı — üstelik
bu kalıp burada daha doğru: her satır modelin protokolünü, eşleme
doğrulamasını, veri saklama koşulunu ve seçilemiyorsa **nedenini** taşımak
zorunda ve bunlar bir `<option>` etiketine sığmaz. Seçilemeyen model
`disabled` bir radyo olarak listelenir, nedeni yanında görünür.

**Paket H1 hiçbir bileşen eklemedi; küme 11'de kaldı.** "Is Tara" yüzeyi
`Card` + `Alert` + `Separator` + `Button` + `Checkbox` ve `StatusPill`
üzerinden `Chip` ile kuruldu. Oda seçimi için `Table` veya `Listbox`
istenmedi: her satır bir oda adı ve **dünyaya yazılabilir** bir başlık taşır,
başlık düz metin olarak (`<pre>`) gösterilmek zorundadır ve bu bir hücreye
sığmaz. Aday listesi için de `Accordion`/`Disclosure` **kullanılmadı** —
sekiz öğenin hepsi görünür olmak zorunda (ADR-0007 §8) ve katlanabilir bir
bileşen tam da gizlenmemesi gereken alanları (riskler, izinler, tahminin
dayanağı) gizlemenin en kolay yolu olurdu. Böylece CSP inline-style hash
riski (A1-R1) yeniden değerlendirilmedi ve tarayıcı QA borcu artmadı.

**Paket E hiçbir bileşen eklemedi; küme 11'de kaldı.** Kanıt defteri
`Card` + `Alert` + `Separator` + `Button` + `Checkbox` ve `StatusPill`
üzerinden `Chip` ile kuruldu; kayıt listesi bir `Table` istemedi, çünkü her
kaydın altında dört güven seviyesi, bir yakalama sonucu paragrafı ve koşullu
bir uyarı vardır — bunlar bir hücreye sığmaz ve satır başına kart kalıbı hem
mevcut kümeyle çözülür hem dar ekranda okunur kalır. Böylece CSP inline-style
hash riski (A1-R1) yeniden değerlendirilmedi ve tarayıcı QA borcu artmadı.

Küme bir
allowlist testiyle sabitlenir: kaynak ağacındaki bütün `@heroui/react`
import'ları taranır ve beklenen kümeye eşit olmalıdır (test:
`heroui-surface.test.ts::imports exactly the reviewed component set and
nothing new`, `::no longer imports the retired Tabs component`). Yeni bir
bileşen eklemek, import satırının yan etkisi değil, bu listeyi bilerek
genişletmek demektir.

## 12. Is Tara (Paket H1)

Bölüm `src/pages/WorkScanPage.tsx` → `components/workscan/WorkScanPanel.tsx`.
Akış tek yönlüdür ve her adımı kullanıcı başlatır:

> kaynakları seç → "iş tara" → sınırlı okuma → adaylar → birini seç → plan ve
> izinler → yerel `suggested` görev

### 12.1 Kontrol tablosu

| Kontrol | Çağrı | Zaman aşımı | Pending etiketi | Hata |
|---|---|---|---|---|
| (mount) | `fetchWorkScanStatus` `GET /api/workscan/status` | 15 sn (varsayılan) | "Tarama yuzeyi okunuyor..." | `ErrorRegion` + "Yeniden dene" |
| Oda listesini oku | `refreshWorkScanRooms` `POST /rooms/refresh` | 45 sn | "Oda listesi okunuyor..." | `ErrorRegion`, retry yok |
| Secili odalari tara | `scanWorkRooms` `POST /scan` | 10 sn + oda başına 40 sn | "Taraniyor..." | `ErrorRegion`, retry yok |
| Secili adayi yerel gorev olarak ac | `suggestWorkScanCandidate` `POST /suggest` | 15 sn | "Aciliyor..." | `ErrorRegion`, retry yok |

Tarama zaman aşımı **hesaplanır**, sabit değil. Sunucu odaları sırayla okur ve
oda başına bütçesi iki denemedir (bağlan 5 sn + oku 10 sn), aralarında en çok
5 sn'ye kadar onurlandırılan bir bekleme vardır: oda başına ~35 sn. İstemci
tarafı bunu okunacak oda sayısıyla çarpar, çünkü kısa bir süre dolduğunda
istek yarıda bırakılır ve sonuç `timeout` — yani **yerel servis hakkında** bir
iddia — olarak raporlanır; oysa sunucunun okuduğu odalar ve **okuyamadığı**
odalar o yanıtın içindedir ve asıl cevap odur.

Çift tıklama koruması dört çağrının dördünde de aynı: tek bir `busy` durumu
tutulur, `busy !== null` iken hiçbir eylem başlamaz ve düğmeler `isDisabled`
olur (§1.4).

### 12.2 Kapsam kullanıcınındır

`/rooms` listesi seçim yapılabilsin diye okunur; bir kuyruk değildir. Tarama
yalnız işaretlenen odalarda çalışır, en çok 10 oda (`WORK_SCAN_MAX_ROOMS`,
sunucunun `max_length` sınırının kopyası — UI 422 alacak bir istek kuramasın
diye). Bütün oda evrenini tarayan bir yol ne burada ne arkadaki route'ta
vardır.

**Polling yoktur.** Zamanlayıcı, arka plan görevi, otomatik yenileme ve
`wait` parametresi yoktur; yenileme yalnız açık bir düğmeyledir. İki testle
sabitlenmiştir: çalışma anında hiçbir `setInterval` kurulmaz, ve bölümün
kendi kaynak dosyaları taranıp `setInterval`/`setTimeout`/
`requestAnimationFrame` ile depolama API'lerinin **hiç geçmediği** doğrulanır
(`WorkScanPanel.test.tsx::installs no timer...`, `::carries no timer or
storage primitive in its own source`).

### 12.3 Dürüstlük yüzeyi

| Ne | Nerede | Test |
|---|---|---|
| Deterministik çıkarımın bedeli (kalıp eşleşmesi, anlamsal çıkarım yok) | "Bu taramanin siniri" bölümü, **her** okumada, sonuç olmadan da | `workscan-honesty` |
| Yasak iş biçimlerinin **kalıp eşleşmesiyle** reddedildiği (yani listede olmayan bir sözcük aday üretebilir) | aynı bölüm, dürüstlük cümlesinin yanında, koşulsuz | `workscan-prohibition` |
| Polling yokluğu ve hiç gönderilmeyen parametreler (`n`, `wait`) | aynı bölüm | `workscan-polling` |
| Oda listesi bayatlığı: ölçülen okuma anı + sunucunun kendi 3 sn beyanı + beyanın kaynağı | oda seçimi bloğu, koşulsuz | `workscan-staleness-rooms` |
| Tarama anlık görüntüsü: ölçülen başlangıç/bitiş ve "bu yanıt mesaj okumaları için ayrı bir bayatlık beyanı taşımıyor" | tarama sonucu bloğu | `workscan-staleness-scan` |
| Halka (ring) düşüşü — **ayrı** bir uyarı | kendi `Alert`'i | `workscan-ring-drop` |
| Okunamayan odalar, ad ad | kendi `Alert`'i | `workscan-failures` |

Bir **eşik uydurulmaz**. Ekranda "bayat"/"taze" diye bir hüküm yoktur; iki
ölçülen değer ve servisin kendi beyanı vardır. Halka düşüşü bayatlıkla aynı
kutuya konmaz: "liste birkaç saniye eski olabilir" ile "hiç okumadığınız
mesajlar artık sunucuda yok" iki ayrı bulgudur ve ikincisini birincinin içine
katmak somut bir kaybı genel bir çekinceye çevirirdi.

Bugünkü sürümde tarama **imleçsizdir** (`since` gönderilmez), bu yüzden
sunucu `first_seq > since + 1` sinyalini üretmez ve yanıt bir halka düşüşü
alanı taşımaz. Uyarı bunu açıkça yazar; bir alan uydurulmadı.

### 12.4 "Açık" demek yasak

İşin durumu yalnız backend'in izin verdiği tek cümleyle sunulur: *"Su ana
kadar okunanda kapanis isareti gorulmedi (anlik goruntu: …)"*. Hiçbir yerde
boolean bir "açık/kapalı" rozeti yoktur ve şemada ondan üretilecek bir alan da
yoktur. Test bütün belgeyi tarar: metni sadece `acik`/`kapali`/`open`/`closed`
olan tek bir öğe bile bulunmamalıdır.

### 12.5 Topluluk otoritesi ve uzak içerik

- Oda içeriği **seviye 3**'tür (`authority: 3`) ve her aday kartında rozetle
  yazar. Yol resmîdir, içerik değildir; ikisi tek bir rozete indirgenmez.
- `from` `did:key` değilse "kendi beyan ettiği takma ad" olarak gösterilir ve
  backend'in izin verdiği tek cümle yanında durur.
- `topic` dünyaya yazılabilir bir KV notudur; ekranda "bir onay değildir"
  yazar.
- Alıntı `<pre>` içinde, düz metin olarak, **tıklanamaz** biçimde gösterilir:
  HTML olarak render edilmez, otomatik bağlantıya çevrilmez ve aday kartında
  hiç `<a>` yoktur (SI-54, AC-17). Vitest ve Playwright ayrı ayrı ölçer.

### 12.6 Sekiz öğe

Aday kartı sekiz başlığın hepsini numaralı olarak gösterir ve hiçbirini
katlamaz: (1) birebir alıntı + `room`/`seq`/`ts` referansı, (2) kime faydası,
(3) teslimat, (4) başarı koşulu ve testi, (5) modül/yazma kapısı yetkinliği,
(6) **"tahmin"** etiketli çalışma tahmini + `not_implemented` bütçe ve nedeni
(H2), (7) izinler ve riskler, (8) açıklık notu. Backend eksik aday
üretemiyor; UI de eksik alan gizlemiyor.

### 12.7 Dış servis kaydı (Kibble)

Bir kayıttır, bir entegrasyon değil. Ekranda: `support_unverified` →
"Destek dogrulanamadi", "Adapter yazilmadi", "Hicbir istek gonderilmedi",
doğrulanan (5) ile doğrulanamayan (5) ayrı ayrı sayılarıyla, kaydın yazıldığı
tarih satırı, servisin kendi iki cümlesi **kendi dilinde birebir** ve yanında
backend'in gönderdiği Türkçe karşılığı.

`score`/`rank` hiçbir yerde bir ölçüt olarak sunulmaz. Bir test, backend'in
yasak-ifade listesini (folded karşılaştırmayla) **render edilmiş belgenin
tamamına** uygular: "dogrulanmis itibar", "itibar puani", "uygunluk puani",
"airdrop uygunlugu", "dogrulanmis talep sahibi", "resmi oda", "hala acik".

### 12.8 Bu bölümde bilerek olmayanlar

- Otomatik yenileme, zamanlayıcı, imleç (`since`) ve `wait`.
- "Tümünü tara" düğmesi ve bir oda şablonu/URL alanı.
- Bir onay adımı: `suggest` görevi `suggested` durumunda açar; onaya geçirmek
  görev yüzeyinin ayrı bir işlemidir.
- Üçüncü taraf bir skor, sıralama veya uygunluk göstergesi.
- Tarayıcı depolaması: seçilen odalar, seçilen aday ve tarama sonucu yalnız
  React state'tedir (SI-24).
