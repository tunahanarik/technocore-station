# SECURITY.md — Technocore Station

Technocore Station **local-first** bir Windows uygulamasıdır. Tehdit modeli,
güvenlik değişmezleri ve kalan riskler burada özetlenir.

Ayrıntılı ve test edilebilir liste:
[`docs/security-invariants.md`](docs/security-invariants.md).
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
- Seed ayrı bir Windows **DPAPI** zarfında saklanır (Aşama 2).
- Paroladan seed türetilmez.
- OpenAPI response modellerinde `seed`, `private_key`, `secret`, `mnemonic`
  alanı bulunamaz — bu otomatik testle doğrulanır.
- Evidence ve log yazılmadan önce secret-pattern taraması uygulanır.

## 7. Bilinen sınırlar (dürüst kapsam)

Bu ürünün **savunmadığı** durumlar:

- Aynı Windows kullanıcısı olarak çalışan malware, keylogger veya debugger.
- Host izni verilmiş kötü niyetli tarayıcı uzantısı.
- Kullanıcının makinesinde çalışan diğer kötü niyetli yerel süreçler.
- Zayıf recovery parolası.
- Resmî FLOP/Technocore domain'inin ele geçirilmesi.
- Güvenilen bir upstream paketin ele geçirilmesi (supply-chain).
- Kullanıcının manuel port yönlendirmesi yapması.

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
