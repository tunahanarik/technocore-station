# SECURITY.md — Technocore Station

Technocore Station **local-first** bir Windows uygulamasıdır. Tehdit modeli,
güvenlik değişmezleri ve kalan riskler burada özetlenir.

Ayrıntılı ve test edilebilir liste:
[`docs/security-invariants.md`](docs/security-invariants.md).
Tehdit modeli: [`docs/threat-model.md`](docs/threat-model.md).
Kimlik yaşam döngüsü: [`docs/identity-lifecycle.md`](docs/identity-lifecycle.md).
Recovery biçimi: [`docs/recovery-format-v1.md`](docs/recovery-format-v1.md).
Ana karar kaynağı: [`Technocore-Station-Proje-Kunyesi.md`](Technocore-Station-Proje-Kunyesi.md) §17.

---

## 1. Güvenlik duruşu

| İlke | Anlamı |
|---|---|
| Local-first | Secret ve asıl kanıt arşivi kullanıcının cihazındadır. |
| No secret in frontend | Frontend hiçbir zaman seed/private key almaz. |
| Human-in-the-loop | Her dış yazma işlemi ayrı kullanıcı onayı ister. |
| Untrusted-by-default | Technocore'dan okunan her içerik veridir, talimat değil. |
| Fail closed | Şüpheli durumda yol kapanır; sessiz fallback yoktur. |
| No hidden network | Telemetri, bulut sync veya tanımsız dış endpoint yoktur. |

---

## 2. Ağ yüzeyi

- Uygulama **yalnız `127.0.0.1`** üzerinde, işletim sisteminden alınan
  **efemer** bir portta dinler.
- `0.0.0.0` / `::` / LAN bind **yasaktır**.
- **CORS middleware yoktur.** Frontend ve backend aynı origin'dedir.
- `Host` başlığı tam olarak `127.0.0.1:<port>` olmalıdır; `localhost` dâhil
  diğer tüm değerler **421 Misdirected Request** ile reddedilir
  (DNS rebinding savunması).
- `Origin` varsa yalnız mevcut origin kabul edilir.
- `Sec-Fetch-Site` varsa `same-origin` olmalıdır; `none` yalnız güvenli
  (GET/HEAD) navigasyonda kabul edilir.

## 3. Oturum modeli

1. Launcher `127.0.0.1:0` adresine bind eder ve efemer portu alır.
2. Bellekte kriptografik rastgele **256-bit tek kullanımlık** açılış token'ı
   üretilir; ömrü **30 saniye**dir.
3. Tarayıcı `/session/<token>` adresinde açılır. **Token loglanmaz.**
4. Backend token'ı **ilk kullanımda iptal eder**, `HttpOnly` +
   `SameSite=Strict` + `Path=/` oturum cookie'si üretir ve temiz `/`
   adresine yönlendirir.
5. Session ve token **tamamen process memory**'de tutulur; diske yazılmaz.

### `Secure` cookie notu
Oturum loopback **HTTP** üzerinde çalıştığı için cookie'ye `Secure`
bayrağı **konmaz**. Tarayıcılar `Secure` cookie'leri düz HTTP'de tutarlı
biçimde kabul etmez; uygulanamayacak bir güvenlik iddiası yaratmamak için
bu bayrak bilinçli olarak dışarıda bırakılmıştır. Koruma `HttpOnly`,
`SameSite=Strict`, exact-`Host` kontrolü ve CSRF katmanından gelir.

## 4. CSRF

- Oturum oluşturulurken session'a özel bir CSRF değeri üretilir.
- SPA bunu aynı-origin `GET /api/session/bootstrap` çağrısıyla alır ve
  **yalnız process memory**'de tutar.
- `localStorage`, `sessionStorage` ve `IndexedDB` **kullanılmaz**.
- Durum değiştiren tüm istekler `X-Station-CSRF` başlığını taşır;
  eksik veya yanlış değer **403** döner.
- CSRF değeri **loglanmaz**.

## 5. Güvenlik başlıkları

Katı `Content-Security-Policy`, `Referrer-Policy: no-referrer`,
`X-Content-Type-Options: nosniff`, `frame-ancestors 'none'` +
`X-Frame-Options: DENY`, kısıtlayıcı `Permissions-Policy`,
oturum/bootstrap yanıtlarında `Cache-Control: no-store`.

**Google Fonts, CDN script veya uzaktan yüklenen UI varlığı kullanılmaz.**

## 6. Secret yönetimi

- Seed hiçbir veritabanı tablosunda bulunmaz.
- Seed ayrı bir Windows **DPAPI** zarfında, **current-user** kapsamında
  saklanır. `CRYPTPROTECT_LOCAL_MACHINE` hiçbir zaman kullanılmaz.
- Kasa dosyasına, yalnız mevcut kullanıcı ve SYSTEM erişebilen **protected
  DACL** uygulanır. ACL Windows API ile yazılır (`icacls` kabuk komutu
  kullanılmaz) ve geri okunarak doğrulanır. Uygulanamazsa işlem **başarısız
  olur**; sessizce devam edilmez.
- Yazma **atomiktir**; yarım kasa veya orphan DB kaydı bırakılmaz.
- Önerilen mod `dpapi+passphrase`: seed önce Argon2id (64 MiB, 3 iterasyon)
  ile türetilen anahtarla ChaCha20-Poly1305 kullanılarak sarılır.
- Parola uygulama açılışında değil, yalnız secret kullanan işlemlerde istenir.
- Paroladan seed türetilmez.
- Raw seed **HTTP üzerinden kabul edilmez**; import yalnız yerel CLI ile,
  `getpass` kullanılarak yapılır.
- **Python belleği güvenilir biçimde sıfırlanamaz.** Seed kullanım sonrası
  en-iyi-çaba ile sıfırlanır; bu bir garanti değildir.
- OpenAPI response modellerinde `seed`, `private_key`, `secret`, `mnemonic`
  alanı bulunamaz — bu otomatik testle doğrulanır.
- Evidence ve log yazılmadan önce secret-pattern taraması uygulanır.
- İmzalama seed'i **hiçbir nesnede uzun ömürlü saklanmaz**: anahtar kurulur,
  kullanılır ve bırakılır; `repr`, log veya cache'e girmez. `CanonicalPayload`
  seed taşımaz ve `repr`'i kullanıcı metnini değil uzunlukları yazar.
- `technocore-conform` CLI'ında **`sign` komutu yoktur**; seed, parola,
  seed-dosyası veya ortam değişkeni seçeneği de yoktur. Seed asla bir komut
  satırı argümanı olamaz — argv başka süreçlerden görünür, shell geçmişine ve
  crash dump'larına düşer.

## 6.1 Uygunluk yüzeyi (Aşama 2B)

- `GET /api/conformance/status` **salt okunur** ve session korumalıdır; yanıt
  yalnız public metadata taşır (kontrol adları, vektör sayıları, bundle
  digest'i, pinlenmiş commit, paket/Python/Unicode sürümleri). Vektör içeriği
  ve içindeki TEST-ONLY seed'ler serialize **edilmez**.
- Uygunluk self-test'i **fail-closed**'dur ve asla exception fırlatmaz; bir
  crash "geçti" sayılamaz. Vektör paketinin SHA-256'sı kodda pinlenmiştir, bu
  yüzden vektörleri düzenleyerek kapıyı gevşetmek mümkün değildir.
- Başarılı bir self-test **dış yazma kapısını açmaz**. Manifest drift
  kontrolü (Aşama 3) gelene kadar kapı kapalı kalır.
- Doğrulama için kullanılan PyNaCl yalnız bir **test** bağımlılığıdır;
  production import grafiğinde bulunmadığı testle doğrulanır.

## 6.2 Salt okunur dış yüzey (Aşama 3)

- **Tek origin:** `https://technocore.chat`. Şema HTTPS, host tam eşleşme,
  yalnız varsayılan port. Alt domain, trailing-dot, userinfo, fragment, farklı
  port, IP adresi ve path traversal reddedilir.
- **Kapalı registry:** istemci `SourceId` alır, URL almaz. Technocore'da bazı
  **GET yolları yazma yapar** (`/r/{room}/say-signed/...`,
  `/kv/{ns}/{key}/set/...`), bu yüzden "yalnız GET gönderiyoruz" bir güvenlik
  özelliği değildir; registry o özelliğin kendisidir.
- **TLS doğrulaması kapatılamaz.** `verify` parametresi hiçbir yerde
  geçirilmez, dışarıya açılmaz ve bir bypass seçeneği yoktur.
- **Redirect takip edilmez.** 3xx bir hatadır.
- Faz bazlı timeout; decompress edilmiş bayt üzerinde boyut sınırı; sınırlı
  retry; `Retry-After` üst sınırla ele alınır.
- Giden isteğe cookie, authorization, DID, fingerprint, CSRF veya kullanıcıya
  ait başka hiçbir veri eklenmez. Sabit ve kişisel bilgi içermeyen User-Agent.
- Yanıttan yalnız `Content-Type`, `ETag`, `Last-Modified` saklanır; keyfi
  header ve `Set-Cookie` istemci sınırında düşürülür.
- Yanıt gövdesi **API'den dönmez**; sınırlandırılmış ve sweep edilmiş bir
  alıntı yalnız veritabanında insan incelemesi için tutulur.
- Uzak değerler UI'a girmeden önce sweep edilir ve kısaltılır; hiçbir uzak
  metin HTML veya tıklanabilir link olarak render edilmez (AC-17).

## 6.3 Paket D'den Paket I'ya: bugün açık olan yüzeyler

Bu bölüm **dar tutulur**. Her paketin ayrıntısı
[`docs/security-invariants.md`](docs/security-invariants.md) içindedir ve
orada her satır bir test adı taşır; burada tekrarlanan bir ayrıntı
**dördüncü bir bayatlama yüzeyi** olurdu. Aşağıdakiler yalnız "bu yüzey
var ve politikası şudur" der.

- **İmzalama ve onay zinciri (Paket D).** Dış yazma üç adımdır — taslak,
  imzala, gönder — ve kapı **her adımda yeniden koşar**; UI'ın disable
  durumuna güvenilmez. Gönderim onayı **tek kullanımlık**, oturuma bağlı
  ve **180 saniyede** dolar; metin, hedef, kimlik veya manifest verdict'i
  değişirse düşer. Yazma yolunda **hiçbir otomatik tekrar yoktur** ve sonuç
  üç durumludur: `accepted`, `refused`, `outcome_unknown` — üçüncüsü
  gizlenmez. Lobby açıkça reddedilir (§9e: SI-55, SI-129…SI-170).
- **Kanıt defteri ve HMAC audit zinciri (Paket E).** Kanıt **ham baytlardır**
  ve asla budanmaz. Zincir materyali ve zincir başı **ayrı DPAPI
  zarflarındadır**, hiçbir tabloya girmez. Zincirin iddiası
  **"çevrimdışı değişikliğe karşı tespit edicidir"**; "değişmez kayıt"
  değildir — baş da birlikte yeniden yazılırsa kesme görünmez ve bunu
  ölçen bir test vardır. Materyal açılamıyorsa sonuç `unavailable`'dır,
  asla "geçti" değil. Dışa aktarım **açık onay** ister
  (§9f: SI-171…SI-209).
- **Provider API anahtarı (Paket G).** OpenCode bağlantısı için bir sağlayıcı
  anahtarı **girilebilir**. Bu, INV-01'in bir istisnası değil, ADR-0001
  §6'nın yetkilendirdiği **dar** bir istisnadır: anahtar kullanıcının kendi
  üçüncü-taraf kimlik bilgisidir, seed veya private key değildir. Ayrı bir
  DPAPI zarfında saklanır, veritabanına yalnız **fingerprint** ve yol
  girer, ve **hiçbir alan anahtarı geri göstermez** — reddedilen bir gövde
  bile 422'de yankılanmaz. Anahtar tam olarak **bir** giden header'da
  görünür ve istek bitince redaksiyon registry'sinden düşer
  (§9h: SI-234, SI-243, SI-257).
- **Agent çalışma ortamı (Paket H2).** Keyfi kod ve kabuk yürütmesi
  **yapısal olarak kapalıdır**: `agent/` ağacında `subprocess`,
  `multiprocessing`, `ctypes`, `importlib` importu ve `exec`/`eval`/
  `__import__`/`system`/`popen` adı yoktur, ve bunu tarayan denetim ekili
  bir çağrıyla sürülmüştür. Ölçülemeyen bir izolasyon olanağı **"yok" diye
  yazılmaz**; envanterdeki her bulgu `relied_upon: false` taşır. Koşu
  tavanı `agent/budget.py`'dedir ve **agent kendi tavanını yükseltemez**
  (§9j: SI-285…SI-297).
- **Kanıt çalışma alanı ve dış paylaşım (Paket H3).** Dış paylaşım
  **tek kullanımlık** bir onay ister; onay paket digest'ine, göreve, içerik
  sürümüne ve oturuma bağlıdır ve **reddedilen bir teslimde bile**
  harcanır. Onaylama tek katta, `Literal[True]` ve varsayılansız bir alan
  olarak uygulanır (§9k: SI-300…SI-310).
- **Windows paketleme (Paket I).** Yayımlanan artefakt **imzasızdır**.
  Yanındaki SHA-256 yalnız **o derlemenin** bütünlüğünü tanımlar; kimin
  ürettiğini kanıtlamaz ve iki derleme farklı hash verdi. Windows
  SmartScreen imzasız bir indirme için uyarı gösterecektir; bu **beklenen**
  davranıştır ve bu belge SmartScreen'i **kapatmanızı istemez**
  (§9l: SI-314…SI-329, ADR-0010 §9).

## 7. Bilinen sınırlar (dürüst kapsam)

Bu ürünün **savunmadığı** durumlar:

- Aynı Windows kullanıcısı olarak çalışan malware, keylogger veya debugger.
- Host izni verilmiş kötü niyetli tarayıcı uzantısı.
- Kullanıcının makinesinde çalışan diğer kötü niyetli yerel süreçler.
- Zayıf recovery parolası.
- Resmî FLOP/Technocore domain'inin ele geçirilmesi.
- Güvenilen bir upstream paketin ele geçirilmesi (supply-chain).
- Kullanıcının manuel port yönlendirmesi yapması.
- **DPAPI, aynı Windows kullanıcısı olarak çalışan malware'e karşı mutlak
  koruma değildir.**
- **`.tcrec` güvenliği tamamen recovery parolasının gücüne bağlıdır.**
- Revoke bir **güvenli disk silme değildir** ve mevcut recovery dosyaları
  geçerli kalmaya devam eder.
- **Yayımlanan Windows artefaktı imzasızdır.** Kod imzalama sertifikası
  yoktur; SmartScreen uyarısı beklenir ve SHA-256 özeti bütünlüğü
  tanımlar, **kaynağı değil**. Derleme ayrıca **bit-bit yeniden
  üretilebilir değildir** — bu ölçüldü ve olumsuz çıktı.
- **Bu ürün bir insan güvenlik incelemesinden geçmedi.** Buradaki ve
  `docs/security-invariants.md`'deki iddiaların tamamı **kendi
  testlerimizin** ölçtüğü şeydir. INV-06 "güvenlik testleri
  gevşetilemez" der, ama bir coding agent dosyayı değiştirebilir; test
  tabanı yalnız **yardımcı** bir kontroldür. Bağımsız inceleme
  **ertelenmiş, kapatılmamış** bir risktir (ADR-0001 §5) ve Paket J onu
  kapatmaz — görünür kılar.

Audit zinciri için kullanılan ifade **"çevrimdışı değişikliğe karşı
tespit edici"**dir; "değişmez kayıt" veya "güvenilir zaman kanıtı" değildir.

## 8. Kanıt dili

`docs/evidence-model.md` içindeki dört seviye dışında iddia üretilmez.
Şu ifadeler **yasaktır**: "sunucu kanıtı", "değişmez kayıt",
"güvenilir zaman kanıtı", "airdrop uygunluk kanıtı".

## 9. Zafiyet bildirimi

Bu depo şu an **özel ve yerel** bir projedir; public bir güvenlik iletişim
kanalı yayımlanmamıştır. Bir zafiyet bulursanız depo sahibine doğrudan
bildirin. Upstream Technocore zafiyetleri için:
<https://github.com/flop-labs/technocore-chat/blob/main/SECURITY.md>

**Lütfen zafiyet bildiriminde gerçek seed veya private key paylaşmayın.**
