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
| `timeout` | `AbortSignal.timeout` doldu (`TimeoutError`/`AbortError`) | evet | "Yeniden dene" |
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
  `network_error`, `malformed_response`, `session_not_bootstrapped`,
  `unexpected_error`.
- `requestId`: `X-Station-Request-Id` başlığından (32 hex doğrulanır);
  başlık yoksa veya bozuksa `null`. Backend bu başlığı henüz koymuyorsa da
  kod çalışır.
- `userMessage`: backend Türkçe cümle döndüyse o; makine koduysa veya boşsa
  `kind` kataloğundan güvenli Türkçe cümle. Kullanıcıya asla çıplak makine
  kodu tek başına gösterilmez.

Bozuk yanıt (`malformed`) ile bağlantı kesilmesi (`network`) bilinçli olarak
ayrı sınıflardır: biri "servis konuşuyor ama anlaşılmıyor", öteki "bayt hiç
gelmedi" bulgusudur.

### 1.3 `ErrorRegion` (kalıcı hata alanı)

`src/components/ErrorRegion.tsx`. Kaybolan toast değildir; `role="alert"`
taşır ve kullanıcı eyleme geçene kadar ekranda kalır. İçerik:

- `userMessage` + sınıfa uygun kurtarma metni (auth → launcher açıklaması,
  unavailable → servis kontrolü önerisi),
- kararlı satır: `Kod: <code> · HTTP: <status|-> · Istek: <requestId|->`,
- `retryable` ve callback verilmişse **"Yeniden dene"** butonu,
- **"Tani bilgisini kopyala"** butonu.

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
"Dogrulaniyor...", "Aciliyor...", "Kuruluyor...", "Siliniyor..."). İkinci
aktivasyon istek başlatmaz (test: `pages.test.tsx::disables the check button
while a check is in flight`).

### 1.5 İptal

Kullanıcıya açık bir iptal düğmesi yalnız dialoglarda vardır ("Vazgec"):
dialog kapanır, parola alanları silinir; uçuştaki istek sonucu geldiğinde
dialog kapalıysa yalnız durum güncellenir. Sayfa gezinmesi (bölüm değişimi)
seçili olmayan bölümü unmount eder; unmount edilen bileşenin isteği sonucu
geldiğinde React 19'da no-op'tur. Bunun dışında istek iptali yoktur; zaman
aşımı `AbortSignal.timeout` ile otomatiktir.

## 2. Kabuk (AppShell)

| Ekran / yol | Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|---|
| Kabuk (açılış) | otomatik oturum başlatma | launcher cookie'si | `bootstrapSession()` + `fetchAppStatus()` | durum kartları "Kontrol ediliyor" | bölümler veriyle dolar | `ErrorRegion` "Yerel cekirdege baglanilamadi"; auth→launcher açıklaması, network→"Yeniden dene" | `kind=timeout`, "Yeniden dene" | yok | `App.test.tsx::surfaces an auth failure with the launcher guidance and no retry`, `::offers a retry when the local core is unreachable, and retries` |
| Sol menü | 6 bölüm butonu (`nav aria-label="Ana bolumler"`) | bölüm `ready: true` | yok (React state) | anında | seçili bölüm mount edilir, `aria-current="page"` taşınır; hazır olmayan bölüm hiç görünmez | — | — | — | `App.test.tsx::renders a left navigation with exactly the ready sections (ADR-0001)`, `::never shows a section that is not ready`, `::mounts only the selected section and moves aria-current on click`, `::is operable with the keyboard: tab to a section, Enter selects it` |
| Sol menü | "Menuyu daralt" / "Menuyu ac" (`aria-expanded`) | — | yok (React state; kalıcı depolama yok) | anında | menü gizlenir/gelir, seçim korunur | — | — | — | `App.test.tsx::collapses the navigation without losing the selection` |
| Üst başlık | (kontrol yok; sade başlık) | — | — | — | — | — | — | — | — |

## 3. Genel Bakış

| Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|
| otomatik özet yükleme | bölüm seçili | `fetchIdentity()`, `fetchTechnocore()`, `fetchConformance()` (bağımsız) | kart başına "Durum okunuyor..." | kimlik özeti + sonraki güvenli adım; drift durumu + son kontrol zamanı; uygunluk özeti; servis sağlığı kartları. Hash listesi YOK | kart başına ayrı `ErrorRegion` + "Yeniden dene" | `kind=timeout` aynı bölge | bölüm değişince unmount | `pages.test.tsx::composes identity, Technocore, conformance and service health`, `::shows summaries only: no hash runs and no source detail`, `::designs the first-use state instead of faking data`, `::shows each failed summary as its own persistent error with retry` |
| "Kimlik ve Guvenlik bolumune git" (2 kart) | — | `onNavigate("identity")` | — | bölüm değişir | — | — | — | `pages.test.tsx::offers a go-to-section action on every summary card` |
| "Kaynaklar bolumune git" | — | `onNavigate("sources")` | — | bölüm değişir | — | — | — | aynı test |

## 4. Kimlik ve Güvenlik

| Kontrol | Önkoşul | API / işlev | Loading | Success | Error | Timeout | İptal | Test |
|---|---|---|---|---|---|---|---|---|
| otomatik yükleme | bölüm seçili | `fetchIdentity()` + `fetchConformance()` (bağımsız) | "Durum okunuyor..." kartı | durum + kapı + uygunluk paneli | kimlik okunamazsa `ErrorRegion` "Kimlik durumu okunamadi" + "Yeniden dene"; uygunluk okunamazsa panelde ayrı `ErrorRegion` "Uygunluk durumu okunamadi" | `kind=timeout` aynı bölgeler | bölüm değişince unmount | `pages.test.tsx::shows an honest empty state instead of a placeholder identity`, `::shows an error region, not a fake verdict, when conformance cannot be read` |
| "Kopyala" (Public DID / fingerprint) | kimlik var | `navigator.clipboard.writeText` | — | "Kopyalandi" (2 sn) | "Kopyalanamadi" | — | — | `pages.test.tsx::shows the public DID with a copy action` |
| "Yeni kimlik olustur" | `no_identity`/`revoked`, kasa `usable` | dialog açar | — | Create dialog | kasa yoksa `isDisabled` | — | — | `pages.test.tsx::surfaces a capability error and blocks creation` |
| "Recovery dosyasindan kur" | `no_identity`, kasa `usable` | dialog açar | — | Adopt dialog | disabled | — | — | `pages.test.tsx::offers the next safe action rather than every action at once` (görünürlük) |
| "Recovery dosyasi olustur" | `recovery_pending`/`ready` | dialog açar | — | Export dialog | — | — | — | görünürlük: aynı test |
| "Restore-test yap" | `recovery_pending`/`ready` | dialog açar | — | Restore dialog | — | — | — | `pages.test.tsx::Restore-test file picker` bloğu |
| "Revoke et" | `recovery_pending`/`ready` | dialog açar | — | Revoke dialog | — | — | — | görünürlük testleri |

### 4.1 Kimlik dialogları (5)

Ortak davranış: "Vazgec" dialogu kapatır ve tüm parola/onay alanlarını
siler (test: `pages.test.tsx::clears passphrase state when the dialog
closes`); hata dialog içi kalıcı uyarıda `ApiError.userMessage` ile
gösterilir; timeout/network aynı yoldan sınıflanır; busy sırasında gönderim
butonu disabled'dır.

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
