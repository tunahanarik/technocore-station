# Paket G doğrulama raporu — OpenCode Go bağlantısı

Tarih: 2026-09-04 · Taban: `23395f4dfdc783119236a90c6339e104ad40e738` (Paket F merge'ü)

Kapsam kararları: [`ADR-0005`](../decisions/0005-paket-g-kapsam-kararlari-2026-09-04.md).
Tarayıcı QA'nın kapsama alınması: [`ADR-0006`](../decisions/0006-tarayici-qa-kapsama-alindi-2026-09-04.md).

## Sözleşme doğrulaması kapsamı belirledi

Prompt §11.1 sözleşmenin resmî belgeden doğrulanmasını şart koşuyor ve
tahmin etmeyi yasaklıyor. `opencode.ai/docs/go/` (altbilgi: "Last updated:
Sep 3, 2026") ve üç yan sayfa okundu; katalog **kimliksiz** çekildi. Hiçbir
API anahtarı kullanılmadı, ücretli çağrı yapılmadı.

**Doğrulandı:** üç protokol yolu, base URL, model kataloğu endpoint'i,
kullanım limitleri (5sa $12 / hafta $30 / ay $60), "Use balance"ın konsolda
kontrol edildiği, veri saklama/eğitim tablosu, `x-opencode-session`
zorunluluğu ve `opencode-go/` önekinin **provider öneki** olduğu (wire id
çıplaktır).

**Doğrulanamadı ve uydurulmadı:** auth header'ının adı ve formatı; üç
protokol ailesinin request/response şekli, streaming/SSE ve tool-call
formatı; hata gövdelerinin şekli. Web'de dolaşan header iddialarının kaynağı
üçüncü taraf proxy repolarıdır ve sözleşme sayılmadı.

## Kendi kendini kapatan bir hata: "doğrulayamadık" yanlış olabilir

İlk uygulama, belgenin protokol ailesini model başına söylemediğini varsayıp
**34 modelin hepsini `unverified`** işaretledi. Sonuç: `selectable_model_ids()`
boş döndü, **hiçbir model seçilemedi** — yani özellik tam da promptun
yasakladığı "göstermelik API kutusu" durumuna düştü.

Orkestratör sayfayı doğrudan çekip kontrol etti: "Endpoints" tablosunun
ayrı bir `Endpoint` sütunu var ve **27 satırın hepsinde dolu**. Dahası kod
`grok-4.6`'yı `chat/completions`'a koymuştu; belge onu **`responses`** diyor
— yani yazılan eşleme sadece işaretlenmemiş değil, **yanlıştı**.

Ders kayda geçti (ADR-0005 §1.2, silinmeden düzeltilerek): *ihtiyatlı görünen
bir "doğrulayamadık" cümlesi, kaynak söylüyorken **yanlış** bir cümledir* —
ve bu kez özelliğin kendisini kapatmıştı. Yeni bir değişmez (SI-256) bu
gerilemeyi sabitliyor: desteklenen bir modelin gerçekten seçilebilir olması.

Düzeltmenin tehlikeli yarısı testlerdeydi: **sekiz test yanlış iddiayı
sabitliyordu**, yani bir sonraki düzenlemede yanlış geri gelirdi. Yeniden
yazıldılar ve 27 satır testte **bağımsız olarak yeniden bildirildi** —
kendi kendini kontrol eden bir transkripsiyon hiçbir şeyi kontrol etmez.

## Muse Spark: doğru ret, yanlış ret değil

İki `muse-spark-*` modeli belgede **eğitim için kullanılıyor / Not ZDR**
olarak işaretli. Bunları `unverified` yapmak **yanlış ret** olurdu: ailenin
bilinmediğini söylemek, oysa biliniyor. `selectable` ile
`requires_training_acknowledgement` ayrı iki özellik; modeller seçilebilir
ama kapı veri işleme koşuludur ve **yalnız kullanıcı onayıyla** kalkar. Bir
test onayın **ana anahtar olmadığını** — eşlemesi olmayan bir modeli
açamayacağını — sabitliyor.

Canlı katalog 34 kimlik döndürmüştü; tabloda olmayan **7 fazlalık**
`unverified` kalır, **listelenir ama seçilemez** ve nedeni kullanıcıya gider.
"Satır yok" ile "satır var, ailesi yayımlanmamış" ayrı cümlelerle pinlendi.

## Dürüstlük yüzeyi

- **"Bağlantıyı denetle" yeşil rozet üretemez** — `VerificationState`'te
  `verified` diye bir değer yok ve UI'ın ton haritasında `ok` girdisi yok,
  yani rozet **boyanamaz**. Katalog anahtarsız cevap verdiği için listeyi
  çekebilmek anahtarı doğrulamaz; bu yazılı.
- **Auth header'ının doğrulanmamış olduğu** backend'den birebir taşınıp
  kullanıcıya gösteriliyor.
- **Streaming ve tool-call yok**; tipleri `false` olduğu için sonraki bir
  düzenleme `true` atayamaz.
- **Bütçe açılmadı** (ADR-0005 §9): `budget_available: Literal[False]`
  değişmedi. Abonelik "sınırsız" denmiyor (testle), maliyet bilinmiyorsa
  `unknown` yazılıyor ve sıfır uydurulmuyor, yerel sayacın paylaşılan
  aboneliği kanıtlamadığı belirtiliyor, "Use balance" sağlayıcı konsoluna
  havale ediliyor ve Station bunu engellediğini iddia etmiyor.
- **Anahtarın bağlı olması dosya paylaşımı izni değildir** — yazılı.

## Verilen sözün bilinçli revizyonu

`SettingsHelpPage` şöyle söz veriyordu: "bu ekranda bilerek hicbir secret
giris veya gosterim alani yoktur". Provider anahtarı girişi bunu geçersiz
kılıyor, dolayısıyla söz **sessizce değil, açıkça** revize edildi ve testi
**daraltılarak** güçlendirildi: sayfada **tam olarak bir** maskeli alan
olabilir, o da OpenCode anahtarıdır, `autocomplete="off"` taşır; seed,
private key, recovery ve kasa parolası alanları **hâlâ yok**; `textarea`
hâlâ 0. "En az bir password alanı var" demek ikincisinin sessizce
belirmesine izin verirdi.

İstisna ADR-0001 §6'da zaten yetkilendirilmişti ve yalnız provider
anahtarını kapsıyor — DID seed/private key/recovery için **hiçbir frontend
istisnası yok**.

## Tarayıcı QA (ADR-0006)

Kullanıcının 4 Eylül 2026 talimatıyla tarayıcı testleri kapsama alındı.
Playwright **1.62.1** (tam pin), yalnız Chromium **151.0.7922.34**;
`npm audit` **0 açık**, 3 paket eklendi.

Uygulama test altında **gerçek** `create_app` + gerçek middleware + gerçek
`dist/` ile, production modda, loopback + efemer portta ve geçici
`STATION_DATA_DIR` ile kalkıyor. Üretim veri dizini **üç ayrı yerde**
reddediliyor.

**Sıfır dış istek ölçüldü, varsayılmadı:** her istek kaydediliyor ve her
testten sonra sıfır iddia ediliyor; off-origin istekler ayrıca sayaçla
abort ediliyor; ve bir **negatif kontrol** testi bilerek
`technocore.chat`'e gidip bunun **bloklandığını ve sayıldığını** doğruluyor —
o olmadan her yerdeki "sıfır", bozuk bir sayaç anlamına da gelebilirdi.
Sunucu tarafında `never_checked` / `never_fetched` alanları başarısız
denemede bile zaman damgası aldığı için, bu değerler ancak hiç giden çağrı
yapılmadıysa okunabilir.

**A1-R1 sonucu: ihlal yok.** Pinli `REACT_ARIA_PRESSABLE_STYLE_HASH`
geçerli. Test boşa geçemiyor: CSP başlığının varlığı ve katılığı, enjekte
edilen `<style>`'ın varlığı **ve** `sheet.cssRules.length > 0` ayrı ayrı
iddia ediliyor — CSP tarafından bloklanan bir inline style DOM'a parse olur
ama `sheet` almaz, "hash tuttu" ile "hiçbir şey çalışmadığı için hiçbir şey
kırılmadı" farkı buradadır. Altı bölümde sıfır CSP reddi, sıfır sayfa hatası.

Yan bulgu: ürünün kendi CSP'si (`default-src 'none'` mirasıyla
`connect-src`) sayfanın giden bir istek **oluşturmasını** dahi engelliyor —
test kilidinden daha güçlü ve üründe.

## Testler ve kapılar (birleşik ağaç, orkestratör koşusu)

| Kapı | Sonuç |
|---|---|
| pytest | **1555 geçti** (1331 → 1514 → inceleme düzeltmeleriyle 1555) |
| Vitest | **233 geçti** (206 → 233) |
| Playwright (e2e) | **53 geçti**; bağımsız incelemecinin üç ardışık koşusunda 51/51 kararsızlık yok (36.1 / 34.4 / 34.6 sn), `retries: 0` |
| ruff (iki koşu) / mypy strict | geçti / 103 dosya 0 hata |
| eslint / build (tsc+vite) | geçti / geçti |
| `npm audit` | 0 açık |
| `git diff --check` | 0 |

CI'a ayrı bir `browser` işi eklendi (windows-latest, 25 dk, tarayıcı
lockfile pininden kuruluyor, hata artefaktları yükleniyor). Gerekçe: A1-R1
pinli bir hash'tir ve bir HeroUI/React Aria yükseltmesi onu **sessizce**
geçersiz kılabilir — üstelik bağımlılık yükseltme PR'ı, tarayıcı suite'ini
elle kimsenin koşmadığı andır.

## Açık bulgu (düzeltilmedi, sabitlendi)

Her bölümün başlık hiyerarşisi **h1 → h3** atlıyor; sebebi HeroUI v3
`Card.Title`'ın `<h3>` render etmesi. Düzeltmek bir HeroUI bileşeninin
elementini değiştirmek demek ve CLAUDE.md kural 7 bunu tahminle yapmayı
yasaklıyor (`heroui-react` MCP'den doğrulama gerekir). `a11y.spec.ts`
**mevcut durumu pinliyor**: oraya bir `h4` girerse test kırılır, HeroUI
`h2`'ye çevirirse yanlış alarm vermez.

## Bilinen boşluk

`apps/station-web/eslint.config.js` bir depo hook'u tarafından yazmaya
kapalı, bu yüzden `e2e/**` **lint edilmiyor**. Telafi: `tsconfig.e2e.json`
`tsc -b`'ye bağlı (yani `npm run build` kapsıyor) ve bir
`suite-discipline.spec.ts` sleep, commit edilmiş `test.only`,
`retries !== 0`, `workers !== 1` veya Chromium dışı proje görürse koşuyu
kırıyor. Hook kaldırılıp ESLint bloğu eklenirse boşluk tam kapanır.

## Kalan riskler

1. **Gerçek hesaba karşı hiçbir şey doğrulanmadı.** Her şey sahte
   transport'a karşı kanıtlandı. `Authorization: Bearer` varsayımı resmî
   belgede doğrulanmamıştır ve öyle gösterilmektedir; gerçek bir anahtarın
   çalışıp çalışmadığı hesap sahibinindir.
2. **Anahtar başarısız kayıtta bileşen state'inde kalır** (yalnız
   başarısızlıkta, kullanıcı yeniden yazmasın diye); başarıda, vazgeçmede
   ve kaldırmada siliniyor.
3. **34 satırlık model listesinin** gerçek odak sırası tarayıcıda
   ölçülmedi (panel testleri jsdom + hedefli e2e).
4. Tarayıcı testinin geçmesi **kullanıcı kabulü değildir** (Paket J).
5. İnsan güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5).

## Bağımsız inceleme sonucu

Bu pakette **iki ayrı** inceleme koşuldu ve ikincisi ilkinin açtığı bir
boşluk yüzünden zorunlu hale geldi.

### CI, yerel suite'in göremediğini yakaladı

Yerelde 1514 pytest, temiz mypy ve 51 tarayıcı testi yeşilken CI taze
checkout'ta `ModuleNotFoundError: station_api.opencode.credentials` ile
patladı. Sebep: `.gitignore`'daki `credentials.*` — gerçek bir credential
dosyasının depoya girmesini engellemek için konmuş bir **güvenlik kuralı** —
aynı adı taşıyan **kaynak modülü** sessizce yuttu.

Modül `credential_store.py` olarak **yeniden adlandırıldı, muafiyet
verilmedi**: o kurala açılan delik, sonradan gerçeğini içeri alacak olan
deliktir. Diskte var olup git'te izlenmeyen kaynak dosyayı yakalayan bir
koruma eklendi (kendini denetleyen ikiziyle).

**Asıl sonuç:** dosya diff'e hiç girmediği için **paketin en
güvenlik-kritik modülünü hiçbir incelemeci okumamıştı.** Görünür hale
gelince ayrı bir denetim yaptırıldı.

### Birinci inceleme (PR diffi)

Bir dürüstlük notu: incelemeci ilk raporunda tarayıcı QA bölümünü **hiç
ölçmeden** yazdığını fark edip **geri çekti**. O maddeler sonra fiilen
koşuldu; çoğu doğru çıktı ve düzeltme doğrulanmış hallerine göre yapıldı.

| Bulgu | Düzeltme |
|---|---|
| **P1:** provider anahtarı **422 gövdesinde geri yansıyor**. `SecretStr` parse edilmiş değerin repr'ini korur; tip hatası sarmalamadan önce olduğu için FastAPI ham girdiyi yankılar. Mevcut sızıntı testi yalnız başarılı store sonrası GET'lere bakıyordu | Her Pydantic hata girdisinden `input` ve `ctx` düşürülür, `loc`/`msg`/`type` kalır. Prob yeniden koşuldu: `CANARY PRESENT: False` |
| **P1:** dördüncü-yüzey allow-list'i **çıplak dizin adına** bakıyordu. `station_api/plugins/opencode/client.py` yerleştirilip içinden dışarı POST atıldı: **27 test sessizce geçti** | Allow-list kaynak köküne **göreli tam yola** anahtarlandı; gerçek prob depoya konulup testin **isim vererek** kırıldığı doğrulandı, sonra iki regresyon testine dönüştürüldü |
| **P2:** dört koruma mutasyonda **hiç ateşlenmiyordu** | Kök neden (M4): dala ulaşan her satır aynı zamanda veri koşuluyla da kapalıydı, bir satır sonra aynı kelimeyle reddediliyordu. Kapısız bir tablo eklenip mesaj kendi cümlesine pinlendi. Dördü de artık kırmızıya dönüyor |
| **P2:** model tablosu **bayatladı** (belge `omen-alpha` eklemiş, katalog 35) ve kullanıcıya *kaynak hakkında olgu* diye söylenen cümle artık doğru değildi | Ret cümleleri **bu build hakkında** konuşuyor; **koşulsuz** bir köken satırı (satır sayısı + okuma tarihi + sayfa altbilgisi) ve bir **sürüklenme uyarısı** eklendi. `omen-alpha` **tabloya eklenmedi** — eklemek yeni bir transkripsiyon ve doğrulama ister |
| **P2:** tarayıcı QA'nın **öz-denetimi** zayıftı: `test.only` koşuyu 51'den 1'e indirip **başarı** raporluyordu, `test.skip` `CI=1` altında bile denetlenmiyordu, sleep yasağı bir callback **adına** bağlıydı | Disiplin taraması spec'ten çıkarılıp `global-setup`'a alındı — Playwright tek bir test seçmeden koşuyor, yani `only`/`skip`/`--grep` onu eleyemiyor |
| **P2:** "origin'i terk eden her isteği bloklar ve sayar" iddiası **literal olarak yanlıştı** — `context.request` ne bloklanıyor ne sayılıyordu, istek DNS'e kadar gitti | Sayaç `context` seviyesine taşındı; `context.request`/`page.request` sarmalandı ve origin dışı çağrı **gönderilmeden önce** reddediliyor. Kapsanmayan kanal kaynak taramasıyla yasaklandı; `seen` için eksik negatif kontrol eklendi |
| **P3'ler:** `sınırsız` kelimesindeki noktalı-ı körlüğü (guard ile test **aynı körlüğü paylaşıyordu**), beşinci aşama-numarası yeri, belgelerin allow-list gerekçesini ters anlatması, `execution-state.json` zaman damgasının geriye gitmesi | Hepsi doğrulanıp düzeltildi; katlama Paket E'den alındı ve test iğneyi **bağımsız** yazıyor. "Doğrulanmamış" bırakılan üç iddia da kontrol edildi, **üçü de doğru** çıktı — biri üç değil **dört** yerdeymiş |

### İkinci inceleme (hiç okunmamış credential modülü)

| Bulgu | Düzeltme |
|---|---|
| **P1:** dosya ile DB **ayrışabiliyordu**. Zarf önce diske yazılıyor, DB satırı ayrı oturumda güncelleniyordu; ikinci adım başarısız olursa diskteki anahtar yeni, gösterilen fingerprint eskiydi (prob: durum `9359c4e2` derken zarfta `1b97b5e5` duruyordu). İkinci yol: `os.replace` sonrası hata, çağıran başarısızlık görürken eski anahtarı yok ediyordu | Sıra tersine çevrildi: satır **önce geri çekiliyor**, zarf yazılıyor, sonra diskteki anahtarı adlandıran satır ekleniyor. Her kesinti "eski satır + eski dosya uyumlu" ya da "satır yok → yapılandırılmamış" ile bitiyor; **yanlış fingerprint erişilemez**. `_atomic_write` `os.replace`'in **iki yanında da** fail-closed. Fingerprint'i `describe()`'ta yeniden hesaplamak **reddedildi** — her `/status` yoklamasında anahtarı çözmek, bir raporlama hatasını düzeltmek için maruziyeti en çok çağrılan route'a yaymak olurdu |
| **P2:** vault hataları OpenCode hiyerarşisinden **kaçıyordu**; en olası iki gerçek arıza opak 500 üretiyordu (sızıntı yok, sözleşme yanlış) | DPAPI/ACL arızaları **503** ile adlandırılıyor, diğerleri 400; orijinal istisna `from` ile bağlı |
| **P2:** eşzamanlı okuma/yazma ham `PermissionError` fırlatıyordu (53 hata) | Modül düzeyinde kilit + sınırlı retry; prob teste dönüştü, **0 hata** |
| **P2:** SI-239'un `kind`/`format` yarısını **hiçbir test tutmuyordu** — test döngüsü dosyayı **birikmeli** bozuyor, `version=99` ilk turda takılıp sonrakileri hiç tetiklemiyordu | Döngü her turda taze zarftan başlıyor ve turun kendi mutasyonunun reddi tetiklediğini kanıtlıyor; eksik/fazla/yanlış-tip alan testi eklendi |
| **P3:** `_atomic_write` docstring'i "ACL yeniden adlandırmadan önce uygulanır" diyordu; izleme sırayı `write → flush → fsync → ACL` gösterdi. Aynı cümle vault ve audit zarflarında da vardı; vault'unki üstüne "ve doğrulanır" deyip hiçbir doğrulama yapmıyordu | Metin değil **kod** düzeltildi: boş dosya → sıfır baytta ACL → yazma → fsync → replace → ACL. Vault/audit yazma yolları **bilinçli değiştirilmedi** (audit zarfı zincirin doğrulamasının dayandığı tek dosya) ve bu **kabul edilmiş sınır** olarak kaydedildi |
| **P3:** anahtar için bellek temizliği yok ve bu **hiçbir yerde kabul edilmemişti** | Dürüst docstring seçildi: anahtar Pydantic'ten itibaren `str`; yalnız zarf katmanını çevirmek, üç canlı çerçeve aynı değişmez nesneyi tutarken **koruma değil tiyatro** olurdu. Gerçek korumalar adlandırıldı, crash dump'ın kapsanmadığı yazıldı |
| **P3:** `load()`'un üretim çağıranı yoktu ama docstring **var olmayan bir garanti** veriyordu | `opened()` contextmanager eklendi — register/forget çağırandan alınamıyor; `load()` docstring'i eski iddiayı **yanlış olarak adlandırıyor** |
| **P3:** dizin ACL'i yoktu; belge eski dosya adını gösteriyordu | Credential dizinine ACL uygulandı (testli); vault/audit'teki miras boşluk **kabul edilmiş sınır** olarak kaydedildi; belge düzeltildi |

**On üç mutasyon kontrolünün hepsi** artık en az bir testi öldürüyor.
Eklenen değişmezlerin **ikisi bilinçli olarak "kabul edilmiş sınır"dır**,
düzeltme iddiası değil.

Bu inceleme bir **insan güvenlik incelemesi değildir** (ADR-0001 §5).

## Sınırlar

Kullanıcının gerçek OpenCode/Claude auth dosyaları **okunmadı, aranmadı**;
gerçek API anahtarı istenmedi ve kullanılmadı; ücretli çağrı yapılmadı.
Gerçek DID/kasa/recovery okunmadı; Technocore'a istek gönderilmedi; lobby
hiçbir testte hedef olmadı; pin (`7707cb63`) ve beklenen sürüm değişmedi;
tag/release/deploy yok.
