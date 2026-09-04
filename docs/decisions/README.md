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

## 2f. Paket C uygulama kararları

| ID | Karar | Gerekçe |
|---|---|---|
| IMP-259 | `RequestIdMiddleware` SecurityHeaders'ın hemen içine yerleştirilir; kimlik `uuid4().hex` olarak sunucuda üretilir, istemciden yansıtılmaz | SecurityHeaders en dışta kalır (SI-33) ve guard retleri dahil her yanıt kimliği taşır (SI-125); rastgele kimlik hiçbir istek içeriği taşımadığı için redaksiyon katmanıyla çakışmaz |
| IMP-260 | `Exception` zırhı sertleştirme başlıklarını ve request id'yi paylaşılan `apply_security_headers` yardımcıyla **kendisi** uygular | Starlette `Exception` handler'ını ServerErrorMiddleware'de, yani SecurityHeaders'ın da dışında çalıştırır; başlıklar orada otomatik eklenmez, tek kaynaklı yardımcı iki yolun birbirinden sapmasını imkânsız kılar (SI-126) |
| IMP-261 | `RedactingFilter` traceback'i **kendisi** üretip `record.exc_text`'e yazar; `stack_info` ve önceden dolmuş `exc_text` de redakte edilir | Filtre yalnız `getMessage()`'ı temizlerken traceback'i `Formatter.formatException` daha *sonra* `exc_info`'dan üretiyordu — Paket C uygulama katmanında bilerek `exc_info` logladığı için bu bypass ilk kez gerçek oldu. `Formatter.format` dolu gelen `exc_text`'i yeniden üretmez; istisnanın kendi `repr`'i (ör. `ResponseValidationError`) yanıt gövdesini gömdüğünden mesaja hiçbir şey konmadan sızıntı olur (SI-127) |
| IMP-262 | Filtre kök handler'ın yanı sıra `uvicorn`, `uvicorn.error`, `uvicorn.access`, `uvicorn.asgi` logger'larına **doğrudan** takılır; uvicorn'un kendi handler'ları ezilmez | `ServerErrorMiddleware` handler'dan sonra istisnayı her zaman yeniden fırlatır, uvicorn da aynı traceback'i `uvicorn.error` üzerinden ikinci kez yazar. Bugün `log_config=None` sayesinde bu kayıtlar köke propagate olur; filtreyi kaynağa bağlamak, uvicorn ileride kendi handler'ını kurarsa da yolu kapalı tutar — üçüncü parti handler'ı ezmekten daha az kırılgan (SI-127) |
| IMP-263 | Zırh `apply_security_headers(..., no_store=True)` çağırır; `NO_STORE_PREFIXES` genişletilmez | `NO_STORE_PREFIXES` oturum durumu taşıyan iki yol ailesini kapsar, hata ise her yolda doğabilir (üretimde SPA catch-all'ı dahil). Prefix listesini genişletmek statik varlıkların önbelleklenmesini de bozardı; kararı çağrı yerine taşımak yalnız hata yanıtını etkiler (SI-128) |

## 2g. Paket D uygulama kararları — Composer & Participation

Kapsam kararları [`0002-paket-d-kapsam-kararlari-2026-09-03.md`](0002-paket-d-kapsam-kararlari-2026-09-03.md)
dosyasındadır ve **bağlayıcıdır**. Aşağıdakiler o kararların uygulama
detaylarıdır.

| ID | Karar | Gerekçe |
|---|---|---|
| IMP-264 | Nonce sayacı **ayrı bir "son değer" satırı değil**, rezervasyon tablosunun kendisidir; sıradaki değer bütün satırların `MAX(nonce_value)`'ından türetilir | İki kayıt birbirinden sapabilir; tek kayıt sapamaz. Rezervasyon ile gönderim arasında ölen bir süreç sayıyı harcanmış bırakır — sayaç ayrı olsaydı geri düşerdi |
| IMP-265 | Eşzamanlılık iki katmanla korunur: process kilidi **ve** `UNIQUE(did, room, nonce_value)` | Gerçekçi yarış tek process'te iki tıklamadır (kilit); fakat kilit aynı DB dosyasını açan ikinci bir Station'a ulaşamaz (kısıt). Kısıt reddettiğinde sınırlı bir yeniden okuma yapılır — bu **yerel** bir yazma çakışmasıdır, giden isteğin tekrarı değildir (ADR-0002 §3 ile karışmasın) |
| IMP-266 | Nonce tavanı `min(10^19 - 1, 2^63 - 1)` | Protokol 19 hane, SQLite 64 işaretli bit verir; düşük olan gerçek tavandır. Tutulamayan bir sayıyı ayırmak sayacı sessizce bozardı, reddetmek daha iyidir |
| IMP-267 | Nonce hem metin (`nonce`) hem sayı (`nonce_value`) olarak saklanır | İmza metni, sunucu sayıyı karşılaştırır. İmzalanan tam karakterleri saklamak, `int` üzerinden bir gidiş-dönüşün leading zero üretmesini imkânsız kılar |
| IMP-268 | `cancelled` bir nonce dolaşıma **dönmez** | Sayaç kesin artandır; verilip bırakılan sayı yine harcanmıştır. Yeniden vermek tek nonce altında iki farklı payload imzalamak olurdu |
| IMP-269 | Nonce, gönderimden **önce** `spent` işaretlenir | Crash, öldürülen süreç veya kaybolan yanıt sayıyı harcanmış bırakmalıdır. Sonra işaretlemek, "belki yazıldı" durumunda sayıyı yeniden kullanılabilir gösterirdi |
| IMP-270 | Signer ince bir katmandır; yalnız `CanonicalPayload` alır, seed `bytearray`'de açılıp `finally`'de sıfırlanır | Ham metin imzalamak temsil edilemez kalır (IMP-211). Politika, gate, nonce ve ağ signer'ın dışındadır; signer'a ulaşan katmanın anahtara ulaşmasının başka yolu yoktur |
| IMP-271 | Composer `IdentityService`'e değil, iki metotlu `ComposeIdentity` protokolüne bağlıdır | Composer'ın kasa yeteneği, recovery dosyası veya yaşam döngüsüyle işi yoktur; tüm servisi adlandıran bir bağımlılık onlara doğru büyüyebilirdi. Ayrıca DPAPI olmayan bir makinede de gerçek davranış test edilebilir |
| IMP-272 | `send_token` yükü **beş** şeye bağlanır: canonical bayt digest'i, oda, ayrılan nonce, DID ve imza anındaki manifest verdict kimliği (ayrıca oturum) | ADR-0002 §2. Beşinin de bayatlaması mümkündür; biri bile bayatladıysa kullanıcının onayladığı gerçeklik artık yoktur |
| IMP-273 | Verdict kimliği `(state, checked_at, check_id)` üzerinden türetilir; **yeni bir denetim her zaman yeni kimliktir** | Aynı sonucu bulan bir yeniden denetim bile kullanıcının sonucunu görmediği yeni bir kanıttır. Fail-closed okuma budur |
| IMP-274 | Digest'ler alan uzunluğu ön ekli ve domain ayrımlıdır (`station_api/digests.py`) | Ayırıcıyla birleştirmek, ayırıcıyı içerebilen bir alanın başka bir alan demetini taklit etmesine izin verir. Oda adları bugün ayırıcı içeremez; bu, o durumun sürmesine bağlı olmasın |
| IMP-275 | Taslak tek kullanımlık **değildir**, oturuma bağlı ve 180 saniyeliktir | Reddedilmiş bir gönderimden sonra aynı içeriği yeniden yazdırmak kullanıcıyı dikkatli okumaktan çok hızlı onaylamaya iter. Onay (send_token) tek kullanımlıktır; içerik değildir |
| IMP-276 | `security/tokens.py` genel `SingleUseStore[T]` ile genişletildi; `BootstrapTokenStore` onun üzerinde ince bir katmandır | İki token da bir yeteneği bir kez devreder ve replay'i reddetmelidir; kalıbı ikinci kez yazmak ikisinin sapmasına davetiye olurdu |
| IMP-277 | Yazma istemcisi ayrı modüldür ve salt-okuma istemcisinin retry politikasını **devralmaz** | İki istemcinin hata politikası zıttır; birleştirmek yanlış olanı miras almak demektir. Tekrarlanan bir yazma, tek onaylı mesajı birden çok yayımlanmış mesaja çevirir |
| IMP-278 | 3xx yanıt `refused` değil `outcome_unknown` sayılır | Origin yanıt vermeden önce işlemiş olabilir; hop'u takip etmek de allow-list'in dışına çıkmanın tam olarak yoludur |
| IMP-279 | Yazma isteğinde `Accept-Encoding: identity` | Yazma makbuzu küçüktür; kazanılacak bant genişliği yok. **Düzeltme (IMP-290):** bu satır başlangıçta bunun decompression-bomb sorusunu "ortadan kaldırdığını" iddia ediyordu; header bir istektir ve sunucu yok sayabilir, dolayısıyla tek başına kaldırmaz. Kaldıran şey aynı kuralın yanıt tarafında da zorlanmasıdır |
| IMP-280 | Oda sınıfı ayrıştırma kuralı referansın kendi algoritmasıdır; **işaretçiler** canlı manifest'ten okunur | Kural pinli, veri canlı. Tanınmayan bir sınıf işaretçisi taşıyan oda reddedilir: oraya yazmanın ne demek olduğunu bilmiyoruz |
| IMP-281 | `DENIED_ROOMS = {lobby, meta}` | ADR-0002 §4.1 lobby'yi zorunlu kılar; pinli referans ikisini de "her ajana söylenen buluşma noktaları" olarak hardcode eder (`UNOWNABLE_ROOMS`). Bu bir sıkılaştırmadır, gevşetme değil |
| IMP-282 | İmza adımı ayrıca `vault_passphrase` alır (ADR-0002 §2 tablosunda yok) | ADR tablosu onayı bağlayan alanları listeler; parola-korumalı kasa parolasız açılamaz ve künye ADR-016 parolanın **secret kullanıldığı anda** istenmesini şart koşar. `SecretStr`'dir, saklanmaz, loglanmaz, yankılanmaz |
| IMP-283 | Ret sebebi gövdede değil `X-Station-Compose-Reason` başlığındadır | Hata sözleşmesi (SI-126) gövdenin tam olarak `{"detail": ...}` olmasını gerektirir; sebep kodunu gövdeye koymak o sözleşmeyi bozardı |
| IMP-284 | `/api/compose/capability` salt-okuma bir uçtur | Kapalı kapıyı açıklamak için UI'nın gate verisine ihtiyacı var; devre dışı bir düğmenin kapıyı kapalı tutan **kontrol** olmadığı burada da geçerli — uç yalnız açıklar, karar vermez |
| IMP-285 | Test oturumu için autouse giden-taşıyıcı yaması; loopback serbest | ADR-0002 §4.4. `tests/integration` gerçek uvicorn ile gerçek soket üzerinden konuşur; bunu da engelleyen bir kontrol devre dışı bırakılır veya etrafından dolaşılır, ve etrafından dolaşılan kontrol kontrol değildir |
| IMP-286 | Yama istisnası `AssertionError` türevidir, `httpx` hiyerarşisinde değildir | Okuma istemcisi `TransportError`'ı `unavailable`'a, yazma istemcisi `outcome_unknown`'a çevirir; httpx şeklinde bir istisna makul görünen bir sonuca yutulur ve unutulan mock hiç fark edilmezdi |
| IMP-287 | Route sayımı `_IncludedRouter` sarmalayıcılarını **özyinelemeli** yürür ve bilinen bir yola karşı da doğrulanır | Eski `{getattr(route, "path", "")}` yazımı bu FastAPI sürümünde boş string kümesi döndürüyordu: üç ayrı güvenlik testi hiçbir şeye bakmadan geçiyordu |
| IMP-288 | Composer testleri gerçek kasa yerine enjekte edilmiş TEST-ONLY signer kullanır; gerçek kasa yolu ayrı ve Windows'a bağlı bir entegrasyon testindedir | Kasa seam'i `IdentityService`'in zaten sunduğu seam ile aynıdır. Böylece davranış testleri platforma bağlı olmaz, gerçek DPAPI yolu da uçtan uca kanıtlanır — hiçbir güvenlik testi atlanmadan |
| IMP-289 | Yazma yanıtı `client.stream` + `iter_bytes` ile okunur; `response.content[:cap]` kaldırıldı | `.content` **önce** bütün gövdeyi belleğe alır, dilim sonra çalışır — yani bir cap değildir. Okuma istemcisi zaten akış üstünde sınırlıyordu; yazma istemcisi deseni devralmamıştı |
| IMP-290 | `Accept-Encoding: identity` artık **yanıt tarafında da** zorlanır: istenmeyen bir `Content-Encoding` taşıyan gövde hiç açılmaz | Header bir *istektir*; sunucu yok sayabilir. IMP-279'un "soruyu tamamen ortadan kaldırır" gerekçesi yalnız bu kontrolle doğru olur. Durum kodu yine sınıflandırılır: okunamayan bir makbuz `accepted`'ı `outcome_unknown`'a çevirmez |
| IMP-291 | Her iki giden istemcinin `transport` seam'i `httpx.MockTransport` ile sınırlandırıldı | Docstring "verify hiçbir zaman yapılandırılamaz" diyordu ama `HTTPTransport(verify=False)` enjekte edilebiliyordu. SSL context'i httpx'in özel alanlarından okumak, bir sürüm yükseltmesinde sessizce eşleşmeyi bırakır; tip kontrolü çürüyemez ve mock taşıyıcı zaten hiç TLS konuşmaz |
| IMP-292 | Üretim wiring'ini doğrulayan güvenlik testi **yazıldı** (signer.py'nin iddia ettiği test) | Var olmayan bir kontrolü adlandıran docstring, hiçbir şey adlandırmayandan kötüdür: incelemecinin şüphesini emekliye ayırır, riski ayırmaz |
| IMP-293 | Kasa parolası `sign()` süresince `register_secret`/`forget_secret` ile korunur | Bugün bilinen bir sızıntı yolu yok; mekanizma tam bu durum için var ve "bugün hiçbir formatter basmıyor" kimsenin sürdürmediği bir özelliktir. Kayıt çağrıyla sınırlıdır: sürekli büyüyen bir registry ilgisiz log satırlarını da bozar |
| IMP-294 | `_build_body` reddi de `cancel(...)` çağırır | Yeniden kullanım deliği değil — numara yanmış kalır — ama `send`'in diğer bütün ret yolları *neden* bittiğini kaydediyordu. Tek sessiz çıkışı olan bir defter, sonradan okunamayan bir defterdir |
| IMP-295 | Nonce katmanı `OperationalError`'ı da yakalar ve `NonceStorageError`'a çevirir; mesaj çakışmadan ayrıdır | İki Station süreci aynı SQLite dosyasında yarışırsa "database is locked" gelir. `ComposeService` yalnız `NonceReservationError` yakaladığı için bu zırhlı 500'e çıkıyordu. "Tekrar deneyin" çakışma için doğru, tutulan dosya için yanlış tavsiyedir |
| IMP-296 | `POST /api/compose/sign` ve `/send` `async def` yerine `def`'tir | FastAPI senkron path operation'ı worker thread'de koşturur. `send` 15 saniyelik read timeout'u, `sign` Argon2id türetmesini event loop üzerinde tutuyordu; o pencerede başka hiçbir istek servis edilmiyordu. Tam-bir-kez özelliği etkilenmez: onay token'ı gönderimden önce kilit altında tüketilir |
| IMP-297 | Test ağ kesicisine `socket.socket.connect` katmanı eklendi; docstring httpx katmanı için daraltıldı | Eski docstring httpx yüzeyinden fazlasını ima ediyordu; `socket`, `urllib` ve çıplak `httpcore` kaçıyordu. Kütüphane saymak yerine hepsinin altındaki katman yamandı. Bu makinenin kendi adresleri serbesttir: `test_bind.py` loopback bind'ı **onları sondalayarak** kanıtlar ve o reddi işletim sistemi vermelidir |

## 2h. Paket E uygulama kararları — Evidence & Audit

Kapsam kararları [`0003-paket-e-kapsam-kararlari-2026-09-04.md`](0003-paket-e-kapsam-kararlari-2026-09-04.md)
dosyasındadır ve **bağlayıcıdır**. Aşağıdakiler o kararların uygulama
detaylarıdır.

| ID | Karar | Gerekçe |
|---|---|---|
| IMP-298 | Kanıt okuma **üçüncü** kapalı registry'yi alır (`evidence_targets.py`), `SOURCES` altı belge olarak kalır | `SOURCES`'ın her girdisi parametresiz sabit bir yoldur; oraya bir şablon koymak "izleme yolu bir odayı adresleyemez" özelliğini hiçbir kazanç olmadan silerdi. Şekil farklı, hata politikası farklı, çağıran farklı |
| IMP-299 | `evidence_targets.resolve_export_target` oda politikasını **yeniden türetmez**, `write_targets.resolve_message_target`'a delege eder | İki kopya oda politikası birbirinden sapabilir ve sapan, kimsenin bakmadığı olur. `DENIED_ROOMS` böylece okumada da geçerlidir: yakalama bir okuma olsa da o odayı **adlandıran** bir istektir |
| IMP-300 | `OUTBOUND_CLIENT_MODULES` iki'den üçe genişletildi; listedeki her adın var olduğu da doğrulanır | Genişleyen liste, kural değil: "başka hiçbir modül HTTP istemcisi import edemez" aynen durur. Kaybolmuş bir ada izin bırakmak sessiz bir genişlemedir |
| IMP-301 | Yeni bir **akış tarayıcı** yazıldı; `_read_capped` yeniden kullanılmadı | `b"".join(chunks)` bir tavan değil bir tampondur — 2 MiB manifest için doğru takas, 10 MiB ring için yanlış. IMP-289 aynı hatayı yazma istemcisinde düzeltmişti; kopyalamak onu geri getirirdi |
| IMP-302 | Tarama tavanı **12 MiB**: 10 MiB ring + başlık payı; eşleşmeden sonra tampon bırakılır, hash ve satır sayımı sürer | Tavanı ring'e eşitlemek, sınırındaki bir ring'i birkaç yüz bayt yüzünden "truncated" gösterirdi. Eşleşme sonrası tamponlamayı bırakmak, tepe belleği gövde boyutundan bağımsız kılar; hash'i bırakmak ise "bütünlük notu"nu sessizce bir ön eke indirirdi |
| IMP-303 | Çevre penceresi hem **satır** hem **bayt** ile sınırlıdır | Üç kısa satır ile üç 10 MiB'lık satır ikisi de "üç satır"dır; tek başına satır sayısı hiçbir şeyi sınırlamaz |
| IMP-304 | Satır `loads_strict` ile okunur; yinelenen anahtar taşıyan satır **okunamaz** sayılır | `json.loads` yinelenenin sonuncusunu tutar: kurgulanmış bir satır bir okuyucuya başkasının `sig`'ini, diğerine bizimkini gösterebilirdi. İki şey söyleyen bir belge ikisinin de kanıtı değildir |
| IMP-305 | Nonce `int` olarak karşılaştırılır; JSON float olarak gelen nonce eşleşmeye **yuvarlanmaz** | Pinli açıklama açıkça uyarıyor: 19 hane 2^53'ü aşar ve float'a yuvarlanmış nonce iyi imzaları bozar. Yuvarlayarak eşleştirmek başkasının kaydını bizimki sanmaktır |
| IMP-306 | Sonlandırıcısı olmayan son satır **yalnız tamamlanmış taramada** okunur | Referans yarım kalan kuyruğu bir sonraki append'te onarır, yani sonlandırılmamış son satır çoğu zaman gerçek bir kayıttır. Tavanda ise kuyruk, taramanın bitirmediği bir satırın parçasıdır; parçayı kayıt saymak tarayıcının kanıt uydurmasıdır |
| IMP-307 | `generation_changed`, **bulunmuş bir satıra bile baskındır** | "Farklı bir generation altında bir şey bulduk" ile "onu bulduk" aynı iddia değildir; güçlü olanı raporlamak fazla iddia olur |
| IMP-308 | Header'daki generation yalnız rakamsa saklanır, yoksa düşürülür ve **var olan değer ezilmez** | Okunamayan bir generation eksik bir generation'dır; eksik olan kaydı karşılaştırılamaz yapar, eşit değil. Bilinen bir değeri `""` ile ezmek bir sonraki karşılaştırmanın ihtiyaç duyduğu veriyi silerdi |
| IMP-309 | `evidence_record.reservation_id` FK'sı **CASCADE etmez** | Şemadaki diğer bütün FK'lar eder, çünkü sahibi olmayan snapshot anlamsızdır. Kanıt tersidir: defter temizlenirken kaybolan bir arşiv satırının yokluğunu kimse açıklayamaz |
| IMP-310 | Evidence ve audit **budanmaz**; `snapshot.py`'nin `_prune` kalıbı kopyalanmadı | Elli koşu bir izleme günlüğü için doğru. Zinciri kapsayan satırlardan birini silmek, zincirin göstermek için var olduğu şeydir — bunu bir politikaya bağlamak kendi kanıtımızı programlı olarak bozmaktır |
| IMP-311 | Audit anahtarı için **ayrı** bir DPAPI zarfı yazıldı; `DpapiVault` yeniden kullanılmadı | Kasa beş yerde kimliğe bağlıdır (32-hex id dayatması, dosya adı, zarf alanı, iç AAD, `store()`'un asla ezmemesi). Zincir kuruluma aittir ve kimlikten uzun yaşar: bir anahtarı iptal etmek o anahtarın ne yaptığının kaydını öksüz bırakmamalıdır |
| IMP-312 | Zincir zarfında parola katmanı **yoktur** | Materyal, onu elinde tutmayan çevrimdışı bir tarafa karşı korur. Aynı Windows kullanıcısı olarak çalışan saldırganın DPAPI'si de vardır, parola istemi de; ikinci katman bir cümle satın alır, bir özellik değil |
| IMP-313 | Canonical audit satırı `strict_json.canonical_json_bytes` ile üretilir ve satırın sakladığı **her alan** MAC içindedir | Kodlama zaten bayt bayt pinli; ad hoc bir biçim, birisi bir sözlük değişmezini yeniden biçimlendirdiğinde değişirdi. MAC'in kapsamadığı bir alan, saldırganın serbestçe düzenleyebileceği alandır |
| IMP-314 | `recorded_at` MAC'e **normalize** edilerek girer (`canonical_timestamp`) | SQLite'ın timestamp tipi yoktur: `DateTime(timezone=True)` değeri **naive** geri verir. Ham `isoformat()` ile MAC almak, zincirin diskten ilk doğrulanışında **her** satırı bozuk göstermesi demekti — bir kurcalama tespiti için mümkün olan en kötü hata |
| IMP-315 | Zincir **başı** ayrı zarfta, append ile aynı transaction sınırında yazılır; baş önce, commit sonra | Dosya ile SQLite atomik commit edemez. Sırayı sabitlemek, çökme penceresinin sonucunu belirli kılar ("baş bir ileride") ve `verify()` bunu saldırı değil, yarıda kalan yazma olarak adlandırır |
| IMP-316 | Truncation tespiti **garanti olarak sunulmaz**; bir test saldırıyı uygulayıp `intact` sonucunu gösterir | Aynı Windows kullanıcısı hem zinciri hem başı yeniden hesaplayabilir. Bunu yazmak yerine **kanıtlamak**, ifadenin zamanla iyimserleşmesini engeller |
| IMP-317 | Yasak ifade listesi backend'e taşındı, iki truncation ifadesi eklendi ve karşılaştırma **katlanmış** biçimde yapılır | Kural yalnız frontend testindeydi: kullanıcının okuduğu ekranı kapsıyor, dışa aktardığı dosyayı kapsamıyordu. Aynı iddianın iki yazımı (Türkçe harfli ve ASCII) vardır; birini yakalayan bir denetim kazara geçilebilir |
| IMP-318 | Secret taraması **token bazlıdır ve allow-list önce çalışır**; isabet yazmayı reddeder, redakte etmez | İmzalı gövde yüksek entropili public değerlerden yapılmıştır; red-önce her gerçek kaydı reddeder ve bunun "düzeltmesi" kuralları işe yaramaz hâle getirmektir. Redaksiyon ise kanıtın tek özelliğini — değiştirilmemiş olmasını — yok eder |
| IMP-319 | 64-hex koşu, SHA-256 digest'i olsa bile reddedilir | Taranan alanların çıplak bir digest taşıması için sebep yok; istisna açmak, gerçek bir seed'in girebileceği kılığı açmak olurdu |
| IMP-320 | Export onayı **yapısaldır**: `ExportConsent` yalnız `Literal[True]` ile kurulur, istek modelinde varsayılan yoktur, route ayrıca kontrol eder | "Yine de dışa aktar"ın hem tip denetiminden geçen hem çalışan bir yazımı olmamalı. Üç kontrol pahalı değil; bu karar pahalı |
| IMP-321 | Markdown için **ayrı bir escaper** yazıldı; `safe_display` yeterli değildir | `safe_display` kontrol/bidi karakterlerini süpürür ve hiçbir markup escape etmez — depolama ve karşılaştırma için yazıldı. Mesaj gövdesi kullanıcı metnidir ve bir `.md` dosyasında link, ham HTML, tablo satırı veya fence açar |
| IMP-322 | `Content-Disposition` adı bir **allow-list'ten yeniden kurulur**, filtrelenmez; recovery indirmesi de aynı yardımcıya geçti | Deny-list, birinin aklına gelen saldırıların listesidir. Recovery'deki ham f-string bugün güvenliydi çünkü tek değişkeni base58 bir DID kuyruğuydu — yani kimse yeniden bakmadığında doğru olmayı bırakan türden bir güvenlik |
| IMP-323 | Yazma istemcisi gövdeyi **kendisi** serialize edip ham bayt olarak gönderir (`content=`), `json=` değil | Arşivlenen baytların **gönderilen** baytlar olması gerekir; sonradan request nesnesinden okumak da çalışırdı, fakat tek bir değerin hem gönderilip hem saklanması iki farklı kodlama ihtimalini ortadan kaldırır. Ayrıca kodlama bir bağımlılığın varsayılanına değil bu projeye ait olur |
| IMP-324 | Composer `EvidenceRecorder` protokolüne bağlıdır ve arşivleme hatası gönderimi **hiçbir zaman** hataya çevirmez | IMP-271'in aynısı: composer'ın yakalama, dışa aktarım veya zincirle işi yok. Tamamlanmış bir gönderimi 500'e çevirmek, kullanıcıyı ADR-0002 §3'ün çıkarmak için var olduğu belirsizlikte bırakır |
| IMP-325 | Kanıt katmanı kurulamazsa uygulama yine açılır; `evidence_recorded=False` ve gerekçe döner | DPAPI'si olmayan bir makinede arşiv kurulamaz. Orada yayımlamayı reddetmek, eksik bir kaydı eksik bir mesajla takas etmek olurdu |
| IMP-326 | `reservation_id` yanıtta döner; public bir uuid'dir, capability değildir | UI'nın hangi gönderim için yakalama isteyeceğini bilmesi gerekir. Rezervasyon id'si bir defter satırını adlandırır ve hiçbir yetki devretmez — send token'ı ise tek kullanımlıktır ve dönmez |

### Paket E — bağımsız inceleme sonrası düzeltmeler

| ID | Karar | Gerekçe |
|---|---|---|
| IMP-327 | Yasak ifade denetimi **ürünün kendi cümlelerine** uygulanır; içe alınan metin **veri**dir ve nötrlenir, reddedilmez | Denetim bitmiş dışa aktarım belgesine uygulanıyordu. O belge bir **mesaj gövdesi** ve bir **uzak hata alıntısı** taşır: 429 ile "sunucu kanıtı sayılmaz" diyen bir sunucu, kaydı hem JSON hem Markdown dışa aktarımından **kalıcı olarak** çıkarıyordu — üstelik `ValueError` olarak, yani 500. Uzak bir sunucunun (veya kullanıcının kendi cümlesinin) arşivin bir daha makineden çıkamayacağına karar vermesi, kuralın korumak istediği şeyin tam tersi |
| IMP-328 | Nötrleme **katlanmış eşleşmeyle, kaynak metnin üzerinde** yapılır; sonuç yetkili tarayıcıyla yeniden denetlenir ve şüphede alıntının tamamı düşer | Katlama uzunluğu değiştirir (NFKD, casefold, boşluk daraltma), yani katlanmış bir offset ham metinde hiçbir şeyi göstermez. Karakter başına köken aralığı tutmak ifadeyi **okunabilir metnin içinden** çıkarmayı mümkün kılar; iki katlama uygulamasının ayrışma ihtimaline karşı fail-closed yol açık bırakılır — alıntı bir nezakettir, bir cümle kaybetmek bir dosya kaybetmekten ucuzdur |
| IMP-329 | `EVIDENCE_DELETED` enum'u **kaldırıldı**; silme route'u uygulanmadı ve ADR-0003 §7'nin bu yarısının **ertelendiği** açıkça kaydedildi | Enum ölüydü: hiçbir yol onu üretemiyordu. Var olmayan bir özelliğin adını kodda bırakmak, okuyucuya o özelliğin var olduğuna dair kanıt sunar. Route'u şimdi yazmak da doğru değil: yıkıcı, durum değiştiren, hiçbir ekranın kullanmadığı yeni bir yüzey olurdu ve onu zorunlu kılan aciliyet — IMP-327 öncesi zehirlenen kaydın temizlenememesi — artık yok. Erteleme görünür bir satır; sessiz bir eksiklik değil |
| IMP-330 | Secret tarama allow-list'i **şekil listesi olmaktan çıkıp çağıranın bildirdiği tam değerler** oldu | Üç prob şekil allow-list'inin içinden geçti: 64-hex bir seed `0` içermediği için geçerli bir base58 kuyruğudur (`did:key:z` + seed), 43 karakterlik bir seed 86'ya doldurulunca imza **şeklinin kendisi**dir, ve `{64}` sınırındaki lookaround'lar 65 haneyi hiç yakalamıyordu. İlki bir regex hatasıydı; diğer ikisi şekille çözülemez — 86 karakterlik base64url'de dolgulu seed ile gerçek imza aynı şeydir. Ayıran şey **köken**dir: `record_send` did'i, imzayı ve nonce'u kendisi üretti. Bildirilen değer ayrıca public şekli sağlamak zorunda, yani bildirim de bir kaçış yolu değil |
| IMP-331 | Red kuralları `{64,}` ve `{43,}`; `did:key` kuyruğu **yayımlanmış tam uzunluğa** sabitlendi | "Tam olarak seed uzunluğu" aranması, dolgu eklemeyi bir atlatma yöntemi yapıyordu. `{1,64}` ise seed'in hex yazımıyla aynı uzunlukta bir kuyruğa izin veriyordu; gerçek bir `did:key` kuyruğunun tek bir uzunluğu var |
| IMP-332 | `exported_at` gövdeden **header'a** taşındı (`X-Station-Exported-At`) | "İki kez dışa aktarıp diff alan hiçbir şey görmemeli" iddiası, dosyanın içindeki damga yüzünden hiçbir zaman doğru değildi; testler dürüsttü (alanı silip karşılaştırıyorlardı), belgeler değildi. İki seçenekten cümleyi düzeltmek iddiayı koşullu bırakırdı; damgayı çıkarmak **koşulsuz doğru** yapar. Kayıp yok: dışa aktarımın ne zaman olduğu kanıt hakkında değil **kopya** hakkında bir olgudur, zaten bir audit olayıdır ve her kaydın kendi `recorded_at`'i dosyada durur |
| IMP-333 | Kanonik metin **Markdown dışa aktarımına da** yazıldı; ham baytlar JSON'a özel kaldı ve bu fark dosyanın **içine** yazıldı | Bir SHA-256, elinizde zaten olan bir metni doğrular. Kanonik metni taşımayan bir özet, imzayla karşılaştırılabilecek hiçbir şey taşımaz — dekordur. Ham baytları (yakalanan satır, pencere, istek/yanıt gövdesi) base64 olarak Markdown'a koymak ise onu okunmaz yapar ve zaten JSON'da olan bir şeyi tekrarlar; o yüzden eşitlenmedi, **yazıldı** — Seviye 4'ün `null` yazılmasıyla aynı kural |
| IMP-334 | `room_generation` **baseline**'dır ve bir kez yazılır; `capture_generation` satırın hangi dönemde okunduğunu söyler; `generation_changed` yapışkandır | Tek sütun iki şeyi tutuyordu ve üzerine yazılınca ikisi de bozuluyordu: üçüncü yakalama yeni odayı kendisiyle karşılaştırıp `line_not_found` diyordu — "mesajınız orada değil", aynı oda olmayan bir oda hakkında. Bir kez ulaşılabilen durum, durum değil bildirimdir. `generation_changed` iken satır **değiştirilmez**: ürünün kendisi karşılaştırılamaz dediği bir okumadan gelen baytları eski baseline'ın yanına koymak, yan yana iki döneme ait iki değer üretirdi |
| IMP-335 | `content_disposition` adı **uzantısıyla birlikte** ayrıştırır; Windows aygıt adları yeniden adlandırılır | Emniyet ağı, tam adı yeniden bir stem sanıp `MAX_STEM_CHARS`'ta kesiyordu: 300 karakterlik bir ad `.json`'ını kaybediyordu. Testler yalnız `safe_download_filename`'ı kapsıyordu; tele giden fonksiyon kapsanmıyordu. `CON.json` ise Windows'ta bir dosyayı değil bir aygıtı adlandırır — tehlikeli değil, ama ücretsiz kaldırılabilir bir karışıklık |
| IMP-336 | `escape_markdown` `safe_display` yerine `sweep_untrusted` kullanır: kırpma yok, uçlardan silme yok | `safe_display` 200 karakterde kırpar ve uçları siler. Bu bir log satırı için doğru, **arşiv** için yanlış: kullanıcının göndermediği bir metni kaydetmiş olurduk. "Hiçbir şey sessizce düşmüyor" iddiası ancak bu değişiklikle doğru; görünmez karakterler siliniyor değil, **görünür bir boşluğa** dönüşüyor |
| IMP-337 | `verify()` materyal açılamasa da **gerçek satır sayısını** döndürür | `link_count=0` + `unavailable`, verdikti okumayan biri için boş bir zincirdir. Beş satırlık bir zincirin asla üretmemesi gereken okuma tam olarak budur |
| IMP-338 | Generation başlığı yalnız **ASCII** rakam kabul eder | `str.isdigit()` Arabic-Indic ve başka rakam kümeleri için de doğrudur. Generation eşitlik için karşılaştırılır, yani `٧` yediyi okuyan ama `7`'ye asla eşit olmayan ikinci bir yazımdır: sunucunun seçtiği bir değerle oda sessizce ve kalıcı olarak "farklı dönem" hâline gelir |
| IMP-339 | Tavanda `stream_sha256` **taranan önekin** hash'idir (belge düzeltildi); pencere tamamlandıktan sonra sonlandırıcısız son satır da sayılır; CRLF'te sondaki `\r` saklanır | Üçü de aynı ailedendir: tarayıcının ne yaptığını olduğundan farklı anlatmak. 201 satır 200 diye raporlanıyordu çünkü hızlı yol yalnız sonlandırıcı sayıyordu; `\r` ise ham bayttır ve onu kırpmak, export lane'in var olma sebebi olan "yeniden serialize edilmemiş bayt" özelliğini bozardı — o yüzden normalleştirilmedi, **belgelendi** |
| IMP-340 | Yasak ifade koruması artık **mutasyonla doğrulanır** ve `evidence` paketindeki her string literal statik olarak taranır | İncelemeci `assert_no_forbidden_claim`'i no-op yaptığında 156 testin hepsi geçiyordu: hiçbir test ihlalin **reddedildiğini** iddia etmiyordu, yalnız ürünün metinlerinin temiz olduğunu. Bir koruma, onu kapattığınızda hiçbir şey kırılmıyorsa koruma değildir. Statik tarama, registry'ye eklenmeyi unutulan yeni bir etiketin de yakalanmasını sağlar |

## 2e. Ayrı dosyalı ADR'ler

Künyeden sonra alınan ve tam metni ayrı dosyada yaşayan kararlar:

| Dosya | Başlık | Tarih | Durum |
|---|---|---|---|
| [`0001-kapsam-eki-2026-09-02.md`](0001-kapsam-eki-2026-09-02.md) | Kapsam eki: uçtan uca uygulama yetkisi (A→J paketleri, sol menü, OpenCode Go + görev agentı, manuel QA kullanıcıya, API anahtarı giriş istisnası) | 2026-09-02 | kabul edildi |
| [`0002-paket-d-kapsam-kararlari-2026-09-03.md`](0002-paket-d-kapsam-kararlari-2026-09-03.md) | Paket D kapsam kararları: note lane kapsam dışı, üç adımlı onay zinciri (TTL 180 sn), üç durumlu gönderim sonucu ve kör tekrar yasağı, leading-zero yasağı, test emniyet ağı | 2026-09-03 | kabul edildi |
| [`0003-paket-e-kapsam-kararlari-2026-09-04.md`](0003-paket-e-kapsam-kararlari-2026-09-04.md) | Paket E kapsam kararları: üçüncü kapalı registry (`/r/{room}/export`), akış üstünde 12 MiB tarama, altı yakalama durumu, budanmayan kanıt ve audit zinciri, ayrı DPAPI zarfı ve dürüst truncation ifadesi, fail-closed secret taraması, onaylı ve deterministik dışa aktarım | 2026-09-04 | kabul edildi |

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
