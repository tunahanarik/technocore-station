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

## 2b. Aşama 2 uygulama kararları

| ID | Karar | Gerekçe |
|---|---|---|
| IMP-201 | Kasa yolu `<data_dir>/vault/v1/<identity_id>.vault.json` | Sürümlü dizin, gelecekteki bir zarf biçimine sorunsuz geçiş sağlar |
| IMP-202 | Kasa dosya adı uygulama üretimi 32-hex identity id'den gelir | Tahmin edilebilir kullanıcı girdisi yol bileşenine giremez |
| IMP-203 | ACL, SDDL + `SetNamedSecurityInfoW` ile uygulanır (`D:P(A;;FA;;;SY)(A;;FA;;;<sid>)`) | `icacls` bir kabuk enjeksiyon yüzeyidir ve hatası sessizce kaybolur; API ile hem uygulanır hem geri okunup doğrulanır |
| IMP-204 | Parola katmanı DPAPI zarfının **içinde** | Kopyalanan dosya DPAPI ile, yerel saldırgan Argon2id ile karşılaşır |
| IMP-205 | Tek aktif kimlik, nullable UNIQUE `active_slot` sütunuyla şemada zorlanır | SQLite NULL'ları eşit saymaz; kural servis katmanına bırakılmaz |
| IMP-206 | `KdfPolicy` hem üretim hem **kabul sınırlarını** taşır | Testler ucuz politika enjekte edebilir, fakat production alt sınırı bunu bir downgrade yoluna dönüşmekten alıkoyar |
| IMP-207 | Argon2 kütüphane hataları `VaultUnlockError`a eşlenir | `memory_cost < 8 x parallelism` gibi kombinasyonlar aksi hâlde istisna sızdırırdı |
| IMP-208 | Write gate'te `not_implemented` ayrı bir durumdur | Uygulanmamış gereksinim asla `passed` sayılmaz; ürün boşluğu kullanıcı hatasından ayrılır |
| IMP-209 | Raw seed importu yalnız CLI; HTTP endpoint yok | Seed request body'sine, proxy tamponuna ve loga girmemelidir |
| IMP-210 | Import yalnız 64-hex biçimi kabul eder; passphrase yolu reddedilir | Resmî `sign.py` bu iki yolu sunar, künye §8.3 ikincisini yasaklar |

## 2c. Aşama 2B uygulama kararları

| ID | Karar | Gerekçe |
|---|---|---|
| IMP-211 | İmzalama yalnız `CanonicalPayload` alır; `sign_arbitrary_string` benzeri public yol yoktur | Ham metni imzalamak sunucudan 403 alır ve saklanan kayda karşı yeniden doğrulanamaz; ulaşılamaz kılmak her çağrı yerinde test etmekten ucuzdur |
| IMP-212 | Sweep limitleri `SweepPolicy` tipiyle taşınır, çıplak `int` ile değil | 4096 ile 8192'yi takas etmek tip denetiminden geçen, sessiz ve her imzayı bozan bir hata olurdu |
| IMP-213 | Sweep oracle'ı, pinlenmiş `store.py`'nin AST'sinden normatif düğümler izole edilerek **çalıştırılır** | `store.py` `orjson`/`config`/`didkey`/`fcntl` çektiği için import edilemez; elle yazılmış bir "beklenen sweep" yalnız kendi anlayışımızı test ederdi |
| IMP-214 | Self-test vektörleri pakette gelir ve SHA-256'ları kodda pinlenir | Son kullanıcıda `vendor/` yoktur; digest pini, vektörleri düzenleyerek kapıyı gevşetmeyi imkânsız kılar |
| IMP-215 | `run_self_test` asla exception fırlatmaz; başarısızlık bir sonuçtur | Bir çağıranın `except` bloğu crash'i sessizce "geçti"ye çeviremesin |
| IMP-216 | Unicode veritabanı sürümü uyuşmazlığı **başarısızlık** sayılır | Sweep Unicode kategorileri üzerinden tanımlıdır; kapsanmayan bir sürümde elimizde kanıt yoktur, kanıtsızlık uyumluluk değildir |
| IMP-217 | AC-05 doğrulayıcısı PyNaCl'dir, vendor pini genişletilmez | Resmî `didkey.py` vendorlanmamıştır ve bu aşamada pini sessizce genişletmek yasaktır; PyNaCl aynı libsodium'dur ve yalnız test bağımlılığıdır |
| IMP-218 | CLI'da `sign` komutu ve seed/parola argümanı yoktur | argv başka süreçlerden görünür, shell geçmişine ve crash dump'larına düşer |
| IMP-219 | Nonce `int`'e çevrilmez; leading zero korunur | `"007"` ile `"7"` farklı wire baytlarıdır ve imza baytları kapsar |
| IMP-220 | Uygunluk verdicti process başına bir kez hesaplanır ve gate ile status endpoint'i **aynı** nesneyi okur | İkisinin uygunluk hakkında farklı şey söylemesi mümkün olmasın |

## 2d. Aşama 3 uygulama kararları

| ID | Karar | Gerekçe |
|---|---|---|
| IMP-221 | İstemci `SourceId` alır, URL almaz; erişilebilir yollar kapalı registry | Technocore GET üzerinden yazma yapar, bu yüzden "yalnız GET" bir güvenlik özelliği değildir; keyfi path kabul eden bir API canlı bir odaya yazmaktan bir hata uzakta olurdu |
| IMP-222 | `verify` parametresi hiçbir yerde geçirilmez | httpx varsayılan olarak doğrular; parametreyi hiç yazmamak, `False` yapılacak bir satır bırakmamak demektir |
| IMP-223 | Redirect takip edilmez | Redirect izlemek, allow-list'in dışlamak için yazıldığı host'a sessizce gitmenin tam olarak yoludur |
| IMP-224 | Boyut sınırı decompress edilmiş bayt üzerinde, streaming ile | Küçük bir gzip'in gigabaytlara açılması tamponlanmadan reddedilmeli |
| IMP-225 | Verdict process içinde tutulur; DB yalnız kanıt | Bir gün önce kaydedilmiş başarılı kontrol, bugünkü protokol hakkında hiçbir şey söylemez; geçmişi bugünmüş gibi raporlamak kapının önlemek için var olduğu hatadır |
| IMP-226 | `openapi` ve `agent.json` zorunlu, diğer dört kaynak tamamlayıcı | `/healthz` ve `/config` aralıklı 503 dönüyor ve protokol sözleşmesi taşımıyor; altyapı hıçkırığında kapının titremesi yanlış olurdu |
| IMP-227 | Ham hash yerine alan bazlı kritik projeksiyon | Ham hash her yazım düzeltmesini drift sayar ve bir hafta içinde göz ardı edilir |
| IMP-228 | `signature_encoding` token karşılaştırmasıyla ele alınır | İfade yeniden yazılabilir; fakat `unpadded` veya `86` kaybolursa sözleşme gerçekten değişmiştir |
| IMP-229 | Limit/kapasite değişikliği uyarıdır, drift değil | Künye §14.4; imza geçerliliğini etkilemez |
| IMP-230 | Uzak değerler saklanmadan ve gösterilmeden önce sweep edilip kısaltılır | Otorite seviyesi 1 doğruluk satın alır, güvenlik değil |
| IMP-231 | Refresh endpoint'i gövde almaz | Kullanıcının yönlendirebileceği bir adres bırakmamak |
| IMP-232 | Dosya seçici native input'u sarar; input tab sırasından çıkarılır | Çıplak `input[type=file]` görünür sınırı ve adı olmayan bir kontroldür; tek klavye durağı ve gerçek erişilebilir ad daha iyidir |
| IMP-233 | Identity "sonraki adım" metni backend gate verisinden türetilir | Hardcoded roadmap metni Aşama 2B biter bitmez sessizce yanlış olmuştu |
| IMP-234 | İmzalı lane kısıtları `dependentSchemas.did` altından okunur | Resmî referans onları `properties` altında yayımlamaz; oradan okumak dört kritik alanı "yok" gösterip yanlış drift alarmı üretti |
| IMP-235 | Alan yolları JSON Pointer segmentleridir, noktalı string değil | Noktalı yolu en uzun anahtarla çözmek, uzaktaki düz bir anahtarın gerçek konumu gölgelemesine izin veriyordu |
| IMP-236 | Karşılaştırma özgün ve tipi doğrulanmış değer üzerinde yapılır | `safe_display` çıktısını karşılaştırmak `"86"` ile `86`'yı ve sonunda newline olan payload'ı özgün payload'la eşit sayıyordu |
| IMP-237 | Beklenen kalıplar `technocore_conform`'dan türetilir | Canlıdan kopyalanan bir beklenti kendini doğrular ve hiçbir şey tespit etmez; ayrıca geniş `{86}` kalıbı kendi motorumuzla çelişiyordu |
| IMP-238 | Okunamayan alan `drifted` değil `unavailable` üretir | Yokluk ile farklılık aynı şey değildir; kanıt olmadan "sunucu imza biçimini değiştirdi" demek ilk hatanın kaynağıydı |
| IMP-239 | Desteklenmeyen JSON Schema anahtarında fail-closed | `$ref`/`allOf`/`if` anlamı değiştirebilir; genel bir schema motoru eklemek yerine "okuyamıyorum" demek doğru cevaptır |
| IMP-240 | `signature_encoding` sınırlı olumsuzlama listesiyle denetlenir | Kelime içerme kontrolü, sözleşmeyi reddeden bir cümleyi reddettiği kelimeler yüzünden geçiriyordu; asıl dayanak makine şemasıdır |
| IMP-241 | Test referans belgeleri pinlenmiş üreticiden üretilir | Elle yazılmış fixture ile kod aynı hatayı taşıyıp birbirini doğruluyordu; üretim + bayt karşılaştırması bu sınıfı ortadan kaldırır |
| IMP-242 | Beklenen servis sürümü uyarıyı susturmak için güncellenmez | Bu uyarı, pinin canlı servisin gerisinde kaldığını gösteren tek sinyaldir |
| IMP-243 | Şema anahtarları blok listesi değil **izin listesi** ile okunur | Reddedilecekleri saymak, düşünülmemiş her anahtarı görünmez yapar; üç ayrı belge her imzayı reddederken `current` raporladı |
| IMP-244 | Koşulsuz ve koşullu kısıtlar birlikte değerlendirilir | Aynı seviyedeki anahtarlar "ve" ile bağlanır; yalnız koşullu olanı okumak `maxLength: 1` ile `minLength: 86`'yı aynı anda doğru saydı |
| IMP-245 | Kanıtlanmış çelişki `mismatch`, okunamayan yapı `unsupported` | İkisi de kapıyı kapatır; ayrım kullanıcının okuduğu cümlenin doğru olması içindir |
| IMP-246 | `anyOf` yalnız referansın yayımladığı `required` dalları biçiminde kabul edilir | "Yalnız kısıt ekleyebilir" doğru fakat konu dışı: eklediği kısıt bizi reddedebilir |
| IMP-247 | Açıklama anahtarları kısıtlardan ayrı tutulur | Sabit anahtar listesi kullanan bir denetimde bu ayrım olmadan her metin düzeltmesi yazma kapısını kapatırdı |
| IMP-248 | `tests/` de projenin ruff kural setine bağlandı (kök `ruff.toml`) | Ruff yapılandırmayı dosyadan yukarı yürüyerek bulur; `tests/` varsayılan sete düşüyor, gerçekten zorunlu olan `S` kurallarını hiç çalıştırmıyordu |
| IMP-249 | İzin listesindeki anahtarın **değeri** de denetlenir | Adı denetleyip değerini atlamak, tek anahtarlık on bir mutasyonun `current` raporlamasına yol açtı |
| IMP-250 | Değerlendirmenin ölçütü **planlanan imzalı gövdedir** | Bir kısıt alışılmadık olduğu için değil, göndereceğimiz değeri dışladığı için yanlıştır; bu karşılaştırma kendi sözleşmemizden bir sayı gerektirir |
| IMP-251 | İmzalı gövdenin taşıdığı her alana bağlı `dependentSchemas` uygulanır | `did` dışındaki bağımlılıklar otomatik olarak etkisiz değildir; imzalı gövde `sig`, `nonce` ve payload alanını da taşır |
| IMP-252 | Bozuk şema `drifted` değil `unavailable` | `maxLength: "86"` okunabilir bir sözleşme farkı değil, bozuk bir şemadır; "sunucu şunu yaptı" demek elimizde olmayan kanıtı iddia etmektir |
| IMP-253 | `null`/`false`/`0` eksik anahtardan ayrılır | JSON'da her biri belirli bir şey söyler; "yok" saymak permissive yönde tahmin etmektir |
| IMP-254 | Şema ÜYELERİNDE de null ≠ yokluk | `properties.x = null` geçersiz üyedir (`unavailable`); üyenin silinmesi ise kısıt yayımlamamaktır — mesajlar ayrıdır |
| IMP-255 | Kimlik alanlarında SOME-exclusion | Meşru değerlerin bir kısmını dışlayan sınır da reddedilen istektir; nonce aralığı (1,19) kapsanmalı, kesişmek yetmez |
| IMP-256 | Payload sınırları uyarı + etkin limit (künye §14.4) | Kapasite değişikliği kapı kapatmaz; `effective_payload_limits` composer'ın gerçek istekte uygulayacağı, tavanla kırpılmış değerdir |
| IMP-257 | Pattern değerleri derlenir, asla uzak girdiyle çalıştırılmaz | Derlenemeyen kalıp uygulanamaz şemadır; payload'daki herhangi bir kalıp değerlendirilemez → kapı kapanır |
| IMP-258 | `required` tekliği metaşema gereğidir | Kendi metaşemasını kıran belge "doğru okundu" sayılamaz |

## 2e. Ayrı dosyalı ADR'ler

Künyeden sonra alınan ve tam metni ayrı dosyada yaşayan kararlar:

| Dosya | Başlık | Tarih | Durum |
|---|---|---|---|
| [`0001-kapsam-eki-2026-09-02.md`](0001-kapsam-eki-2026-09-02.md) | Kapsam eki: uçtan uca uygulama yetkisi (A→J paketleri, sol menü, OpenCode Go + görev agentı, manuel QA kullanıcıya, API anahtarı giriş istisnası) | 2026-09-02 | kabul edildi |

Çelişki durumunda tarihli kapsam eki, künyenin eski kapsam sınırlamalarının
önüne geçer (kullanıcının açık talimatı); güvenlik değişmezleri (INV-01…09)
hiçbir kapsam ekiyle gevşemez.

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
