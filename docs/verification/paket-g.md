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
| pytest | **1514 geçti** (1331 → 1514) |
| Vitest | **230 geçti** (206 → 230) |
| Playwright (e2e) | **51 geçti** (32.4 sn); agent tarafında beş ardışık koşuda 51/51, kararsızlık yok, `retries: 0` |
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

(PR üzerinde doldurulacak — temiz bağlamlı reviewer subagent koşulacak; bu
insan güvenlik incelemesi değildir, ADR-0001 §5 kalan risk.)

## Sınırlar

Kullanıcının gerçek OpenCode/Claude auth dosyaları **okunmadı, aranmadı**;
gerçek API anahtarı istenmedi ve kullanılmadı; ücretli çağrı yapılmadı.
Gerçek DID/kasa/recovery okunmadı; Technocore'a istek gönderilmedi; lobby
hiçbir testte hedef olmadı; pin (`7707cb63`) ve beklenen sürüm değişmedi;
tag/release/deploy yok.
