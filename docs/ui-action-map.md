# UI eylem haritası

> Paket C çıktısı; Paket D ile "Oluştur ve Doğrula" bölümü (§5) dolduruldu.
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
"Imzalaniyor...", "Gonderiliyor...", **"Yeniden deneniyor..."**). İkinci
aktivasyon istek başlatmaz.

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

Testler: `pages.test.tsx::disables the check button while a check is in
flight`, `pages.test.tsx::disables the gate retry while the retry is in
flight`, `App.test.tsx::disables the shell retry while the retry is in
flight`, `ErrorRegion.test.tsx::starts no second request when the retry is
clicked repeatedly`, `ComposerPanel.test.tsx::starts no second send when the
send button is clicked twice`.

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
5. **`outcome_unknown` için uzlaştırma yok** (ADR-0002 §3) — çıkış yolu odayı
   okumayı gerektirir ve oda okuma yolu bu pakette açılmadı. Durum kullanıcıya
   olduğu gibi gösterilir; UI tahmin yürütmez ve "Yeniden dene" sunmaz.
6. **Gönderilmiş bir mesajın kaydı yoktur.** Sonuç bölgesi sayfa yenilenince
   kaybolur; kalıcı kanıt defteri (AC-14 dâhil) Paket E'dedir. Tarayıcı
   depolaması yasak olduğu için (SI-24) ara bir çözüm de eklenmedi.
7. **Üst karakter sınırı aşımı butonu kilitlemez.** Süpürme metni kısaltabilir
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

Küme bir
allowlist testiyle sabitlenir: kaynak ağacındaki bütün `@heroui/react`
import'ları taranır ve beklenen kümeye eşit olmalıdır (test:
`heroui-surface.test.ts::imports exactly the reviewed component set and
nothing new`, `::no longer imports the retired Tabs component`). Yeni bir
bileşen eklemek, import satırının yan etkisi değil, bu listeyi bilerek
genişletmek demektir.
