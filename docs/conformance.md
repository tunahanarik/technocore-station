# Uygunluk (conformance) — Aşama 2B

> Ana karar kaynağı: [`../Technocore-Station-Proje-Kunyesi.md`](../Technocore-Station-Proje-Kunyesi.md) §14, §18.
> Sözleşme: [`protocol-contract.md`](protocol-contract.md).
> Resmî referans: `flop-labs/technocore-chat` @ `7707cb63ebf638e8ef0cf59d1364818b9fef7d24`.

**Uygulama durumu: UYGULANDI (Aşama 2B).** `technocore-conform` paketi sweep,
canonical string, `did:key`, Ed25519 imzalama ve doğrulama yüzeylerini
sağlar. **Bu aşamada Technocore'a hiçbir ağ bağlantısı yoktur**; giden bir
HTTP istemcisi yazılmamıştır ve dış yazma kapısı kapalıdır.

---

## 1. Bu belgenin en önemli cümlesi

> Uygunluk self-test'i, **bu yapının pinlenmiş referans commit ile aynı
> davrandığını** gösterir. **Canlı Technocore sunucusunun hâlâ aynı
> protokolde olduğunu göstermez.**

Bu iki iddia karıştırılmamalıdır. İkincisi *manifest drift* kontrolüdür,
Aşama 3'e aittir ve o gelene kadar write gate'in `manifest_current` kontrolü
`not_implemented` kalır.

---

## 2. Sweep sözleşmesi

Unicode kategorisi `Cc`, `Cf`, `Cs`, `Co`, `Zl` veya `Zp` olan **her**
karakter tek bir ASCII boşluk (U+0020) ile değiştirilir, ardından
`str.strip()` ile iki uç temizlenir.

**Sweep normalization yapmaz ve boşlukları collapse etmez.**

| Yapılmayan | Neden önemli |
|---|---|
| **Collapse yok** | Art arda üç kontrol karakteri üç boşluk olur, bir boşluk değil. Collapse eden bir uygulama sunucunun sakladığından kısa bir metin üretir ve **her imza geçersiz olur**. |
| **Normalization yok** | NFC/NFD kullanıcının metnini farklı code point'lere yeniden yazar. Sunucu normalize etmez; biz de etmeyiz. |
| **Case folding yok** | — |

### İnce bir davranış: U+00A0

`str.strip()` `str.isspace()` doğru olan her karakteri kırpar; buna `Zs`
kategorisindeki U+00A0 (no-break space) da dahildir. Fakat U+00A0 sweep'in
**değiştirdiği** kategorilerde değildir. Sonuç:

```
" a b "   ->   "a b"      # uçlardaki NBSP kırpılır, ortadaki korunur
```

Bu davranış referansın davranışıdır ve bilinçli olarak korunmuştur; bir test
onu sabitler.

### Uzunluk

Uzunluk **sweep'ten sonraki Python code point sayısıyla** ölçülür.

| Yüzey | Sınır | API |
|---|---:|---|
| Mesaj | 4096 | `sweep_message` / `MESSAGE_POLICY` |
| Note değeri | 8192 | `sweep_note_value` / `NOTE_VALUE_POLICY` |

Ayrı fonksiyonlar ve `SweepPolicy` tipi, iki limitin yanlışlıkla
karıştırılmasını zorlaştırmak içindir: çıplak bir `int` alsaydı limitleri
takas etmek tip denetiminden geçen, sessiz ve imza bozan bir hata olurdu.

Sweep **idempotenttir**: `sweep(sweep(x)) == sweep(x)` (AC-03).

---

## 3. İsim ve nonce

```text
room / namespace / key :  [a-z0-9][a-z0-9_-]{0,47}     (fullmatch)
nonce                  :  [0-9]{1,19}                  (fullmatch)
```

İsim allow-list'i dar tutulur, çünkü **canonical string'i kaçışlama olmadan
birleştirmeyi güvenli kılan şey odur**: yapısal bir alan hiçbir zaman `|`
içeremez.

Nonce kuralları:

- Yalnız **ASCII** rakam. `str.isdigit()` U+0661 gibi Unicode rakamlar için de
  doğrudur; onları kabul eden bir imzalayıcı, sunucunun reddedeceği bir nonce'ı
  imzalayıp kullanıcıya "imza geçerli" derdi.
- **Leading zero korunur.** `"007"` ve `"7"` farklı wire değerleridir; imza
  baytları kapsar. İmzalama yolunda nonce'ı `int`'e çevirmek `"007"` değerini
  sessizce `"7"` yapardı.

**Anti-replay ve monoton sayaç bu aşamanın sorumluluğu değildir.** Nonce
tahsisi, `(did, room)` başına monotonluk ve transaction içinde rezervasyon
**Aşama 4** kapsamındadır. Bu paket hiçbir durum tutmaz.

---

## 4. Canonical string

```text
message:  <room>|<nonce>|<swept_text>
note:     <namespace>|<key>|<nonce>|<swept_value>
```

UTF-8 olarak kodlanır. Normalization, sonuna newline veya dolgu baytı yoktur.

**Canonical metin, sunucunun saklayacağı swept metni kapsar** — kullanıcının
yazdığı ham metni değil. Ham metin imzalanırsa sunucu 403 döner. Bu bilinçli
bir tasarımdır: saklanan bir kayıt, sonradan diskteki baytlara karşı yeniden
doğrulanabilmelidir.

Mesajda **tam iki**, note'ta **tam üç** yapısal ayraç bulunur. Son alandaki
metin istediği kadar `|` içerebilir; alanlar soldan okunur.

### `sign_arbitrary_string` neden yok

İmzalama `CanonicalPayload` alır, serbest bir string almaz. Payload yalnız
sweep'ten geçerek üretilebilir. Böylece ham metni yanlışlıkla imzalamak
**mümkün değildir** — bunu her çağrı yerinde test etmektense ulaşılamaz
kılmak daha ucuzdur.

---

## 5. İmza

| Alan | Değer |
|---|---|
| Algoritma | Ed25519 |
| Ham imza | 64 bayt |
| Wire biçimi | padding'siz base64url, **tam 86 karakter** |
| Son karakter | yalnız `A`, `Q`, `g` veya `w` |
| Regex | `[A-Za-z0-9_-]{85}[AQgw]` |

86 base64 karakteri 516 bit taşır, imza ise 512 bittir; son karakterin alt
dört biti **slack**'tir ve sıfır olmalıdır. Bu özelliğe sahip tam dört
karakter vardır. Slack bitleri yok sayan bir decoder aynı imzanın 16 farklı
yazımını kabul ederdi; bu paket birini kabul eder.

**İmza canonical string'i kapsar; JSON request gövdesinin tamamını
kapsamaz.** Exact JSON baytları Evidence için saklanabilir, fakat *"imza bu
JSON'u kapsıyor"* denmez.

### Seed

- Tam **32 ham bayt**. String seed kabul edilmez.
- **Paroladan seed türetme yoktur.** Resmî `scripts/sign.py` 64-hex olmayan
  girdiyi SHA-256'dan geçirir; künye §8.3 bunu yasaklar ve Station bu yolu
  uygulamaz. Bu bilinçli ve belgelenmiş bir sapmadır.
- Hiçbir nesne seed'i uzun ömürlü saklamaz, `repr`'e veya cache'e koymaz.
  `sign_payload` anahtarı kurar, kullanır ve bırakır.

### DID

`did:key` **yalnızca özel anahtar sahipliğinin** göstergesidir. Gerçek kimlik,
kurum, dürüstlük, içerik doğruluğu veya güvenilir zaman **kanıtlamaz**.

---

## 6. Runtime self-test

`technocore_conform.run_self_test()` paketin içinde gelen TEST-ONLY vektör
paketini yeniden çalıştırır.

| Özellik | Değer |
|---|---|
| Ağ | kullanılmaz |
| `vendor/` dizini | production runtime'da **gerekmez** |
| Vektör kaynağı | pinlenmiş oracle'dan türetilmiş, pakette gelen bundle |
| Başarısızlık | **fail-closed**; `run_self_test` asla exception fırlatmaz |

Kontrol edilen alanlar: `sweep`, `did`, `canonical`, `signing`,
`verification`, `encoding`, `tamper`, `unicode_database`.

### İki katmanlı fail-closed

1. Bundle'ın SHA-256'sı `selftest.py` içinde **pinlenmiştir**. Bir kontrolü
   geçirmek için vektörleri elle düzenlemek digest'i değiştirir ve bunun
   yerine digest kontrolü başarısız olur. Vektörleri zayıflatarak kapıyı
   zayıflatmanın bir yolu yoktur.
2. `run_self_test` hiçbir zaman exception fırlatmaz. Eksik bundle, bozuk
   digest ve beklenmeyen bir hata `passed=False` üretir. Bir çağıran, crash'i
   yanlışlıkla "geçti" diye yorumlayamaz.

### Unicode veritabanı sürümü sonucun parçasıdır

Sweep Unicode kategorileri üzerinden tanımlıdır, dolayısıyla çıktısı Python'un
derlendiği Unicode veritabanına bağlıdır. Çalışma zamanı sürümü vektörlerin
üretildiği sürümden farklıysa, vektör kümemizin kapsamadığı karakterler farklı
süpürülebilir ve elimizde **hiçbir kanıt olmaz**. Bu durum sessizce "uyumlu"
sayılmaz; `unicode_database` kontrolü başarısız olur.

### Rapor edilen alanlar

`passed`, kontrol listesi ve vektör sayıları, bundle SHA-256'sı, pinlenmiş
upstream commit, paket sürümü, Python sürümü ve `unicodedata.unidata_version`.

---

## 7. Vektörlerin provenansı

Bundle **elle yazılmamıştır**; `tests/conformance/vector_builder.py`
tarafından pinlenmiş oracle'dan türetilir. `tests/conformance/test_vectors.py`
her çalışmada bundle'ı oracle'dan yeniden üretir ve **bayt-eşitliğini**
doğrular. Böylece "bu vektörler referanstan geldi" iddiası bir yorum değil,
her koşuda sınanan bir testtir.

Oracle'ın kendisi de ikinci elden bir kopya değildir: `src/store.py`
`orjson`, `config`, `didkey` ve Linux'a özgü `fcntl` çektiği için import
edilemez, bu yüzden modül `ast` ile ayrıştırılır ve **yalnız normatif
düğümler** (sabitler + `clean_text`) izole edilip çalıştırılır. Çalışan
baytlar pinlenmiş baytlardır. Her iki oracle da kullanılmadan önce vendor
SHA-256 toplamlarını doğrular.

---

## 8. Bağımsız doğrulayıcı (AC-05)

İmzaları `cryptography` üretiyor; aynı kütüphanenin onları doğrulaması az şey
kanıtlar. **PyNaCl** (libsodium) bağımsız bir uygulamadır ve resmî sunucunun
`didkey.verify` fonksiyonunun kullandığı kütüphanedir.

Her iki yön de test edilir:

- Station imzalar → PyNaCl doğrular.
- Resmî `scripts/sign.py` imzalar → Station doğrular **ve** PyNaCl doğrular.

PyNaCl yalnız bir **test** bağımlılığıdır. Production import grafiğine
girmediği, uygulamayı temiz bir yorumlayıcıda import edip `sys.modules`
içeriğine bakan bir testle doğrulanır.

---

## 9. CLI

```bash
technocore-conform sweep message           # stdin -> saklanacak biçim
technocore-conform sweep note
technocore-conform canonical message --room <r> --nonce <n>
technocore-conform canonical note --namespace <ns> --key <k> --nonce <n>
technocore-conform verify message --room <r> --nonce <n> --did <did> --signature <sig>
technocore-conform verify note --namespace <ns> --key <k> --nonce <n> --did <did> --signature <sig>
technocore-conform self-test
technocore-conform version
```

- Metin ve değer **yalnız stdin'den** okunur; shell quoting wire semantiğini
  değiştiremez. Bir adet satır sonu karakteri kırpılır.
- `--stored` bayrağı, stdin'in sunucunun sakladığı biçim olduğunu **iddia
  eder**: swept biçimde değilse düzeltmez, reddeder.
- DID ve imza public veri olduğu için argüman olabilir.
- **`sign` komutu yoktur.** İmzalama seed gerektirir; seed asla komut satırı
  argümanı olamaz (argv başka süreçlerden görünür, shell geçmişine ve crash
  dump'larına düşer). Gerçek imzalama Aşama 4'te Station vault'u üzerinden
  yapılacaktır.
- Seed, parola, seed dosyası veya ortam değişkeni seçeneği **yoktur**.
- Ağ isteği ve telemetri **yoktur**.

Çıkış kodları: `0` başarı, `1` uygunluk başarısızlığı (reddedilen metin,
bozuk imza, doğrulama hatası, başarısız self-test), `2` kullanım hatası.
`--json` çıktısı strict ve sürümlüdür (`output_version`).

---

## 10. Write gate entegrasyonu

`conformance_verified` artık **gerçek** self-test sonucuna bağlıdır.

| Kontrol | Durum | Aşama |
|---|---|---|
| `identity_present` … `recovery_verified` | gerçek | 2 |
| `conformance_verified` | **gerçek** (Aşama 2B) | 2B |
| `manifest_current` | `not_implemented` | 3 |

Başarılı bir self-test **kapıyı açmaz**: manifest drift kontrolü henüz
yoktur, dolayısıyla dış yazma yolu kapalıdır ve Compose & Verify kilitlidir.
Self-test başarısız olursa kapı ayrıca `conformance_verified` üzerinden de
kapanır.

`WriteGateInput.conformance_verified` varsayılanı `False`'tır: alanı
unutan bir çağıran kapalı bir kapı alır, açık bir kapı değil.

Session korumalı salt okunur endpoint: `GET /api/conformance/status`. Yanıt
yalnız public metadata taşır — vektör içeriği ve TEST-ONLY seed'ler
serialize edilmez.

---

## 11. Bu aşamada bilinçli olarak yapılmayanlar

- Technocore'a **hiçbir bağlantı** — giden HTTP istemcisi yoktur.
- Identity vault üzerinden operasyonel imzalama (Aşama 4).
- Compose ekranının gerçek yazma yüzeyine dönüşmesi (Aşama 4).
- Manifest/config okuma (Aşama 3).
- Nonce sayacı, rezervasyon, replay reddi (Aşama 4).
- Evidence kaydı (Aşama 5).
- LLM veya Agent Runtime.
