# Tarayıcı QA

> Yetki: [ADR-0006](decisions/0006-tarayici-qa-kapsama-alindi-2026-09-04.md)
> (4 Eylül 2026). Bu belge o kararın nasıl uygulandığını anlatır.
> Kod: `apps/station-web/e2e/`.

Bu paket, mevcut Vitest/jsdom testlerinin **yerine geçmez**; onların
kanıtlayamadığı şeyleri kanıtlar (ADR-0006 m.1). Kural basittir: bir iddia
jsdom'da kanıtlanabiliyorsa buraya girmez.

## 1. Çalıştırma

```bash
npm --prefix apps/station-web run test:e2e
```

`pretest:e2e` otomatik olarak `npm run build` çalıştırır. Bunun sebebi
gerçektir, kolaylık değil: testler **derlenmiş** SPA'yı backend'in kendi
origin'inden servis edildiği hâliyle sürer, ve bayat bir `dist/` sessizce
yanlış bir şeyi yeşil gösterirdi.

`npx playwright test` doğrudan çalıştırılırsa build adımı atlanır; global
setup `dist/index.html` yoksa açık bir mesajla durur ama **bayatlığı**
göremez. Elle koşarken önce `run build` yapın.

Tek tek dosya: `npx playwright test csp`. Arayüzle: `run test:e2e:ui`.

## 2. Uygulama test altında nasıl ayağa kalkıyor

`e2e/harness/serve.py` **gerçek** uygulamayı çalıştırır. `station_api`'nin
hiçbir satırı bu paket için değiştirilmemiştir; harness aynı
`reserve_loopback_socket`, aynı `create_app`, aynı middleware zinciri, aynı
`DEFAULT_WEB_DIST` ile çalışır. `station_api.launcher.main`'den yalnız iki
farkı vardır:

1. `webbrowser.open` çağrılmaz — bir test koşusu geliştiricinin tarayıcısını
   ele geçirmemelidir;
2. bootstrap token'ları istek üzerine üretilir.

Bunun sonuçları:

| Özellik | Değer | Neden |
|---|---|---|
| Bind | `127.0.0.1` + **efemer** port | INV-02. Port işletim sisteminden gelir; test onu koşan süreçten okur, hiçbir yerde sabit yazmaz. |
| Mod | **production** (`STATION_DEV=0`) | Dev modu portu sabitler ve kabul edilen origin kümesini genişletir; o hâlde CSP/origin iddiaları başka bir uygulamayı ölçerdi. |
| SPA | `dist/` üzerinden, backend'in kendi origin'inden | **Gerçek CSP başlıkları** ancak böyle devreye girer. A1-R1'i kanıtlamanın tek yolu budur. |
| `STATION_DATA_DIR` | `%TEMP%\station-e2e-*` | Kullanıcının kimlik verisine dokunulmaz. |
| Veritabanı | O geçici dizindeki SQLite | Koşu bitince dizin silinir. |

### Üretim veri dizini: bir ret, bir önleme, bir doğrulama

`%LOCALAPPDATA%\TechnocoreStation` hedef alınamaz. İlk yazım bunu "üç kez
reddedilir" diye özetliyordu; **üçü aynı şey değil** ve farkı yazmak daha
dürüst:

| Katman | Yer | Ne yapar |
|---|---|---|
| **Ret** | `e2e/harness/serve.py:51` | **Çözümlenmiş** yolu karşılaştırır ve eşleşirse `SystemExit` atar. Tek gerçek reddetme budur. |
| **Önleme** | `e2e/harness/station.ts:116` | Dizini `mkdtemp` ile kendisi üretir, yani üretim yolu hiç istenmez. Bir ret değil, o durumun oluşmaması. |
| **Doğrulama** | `shell.spec.ts:58` | Koşan sürecin gerçekte hangi dizini kullandığını okur ve üretim yolu olmadığını iddia eder. Bariyer değil, ölçüm. |

Üçü birden "üç bariyer" değildir: biri kapıyı kapatır, biri kapıya hiç
gelmez, biri kapının kapalı olduğunu ölçer.

### Oturum devri

Uygulama `/session/<token>` ile açılır; token 30 saniye yaşar ve ilk
kullanımda harcanır. Her test kendi oturumunu açtığı için token'lar önceden
dağıtılamaz. Harness, geçici koşu dizini içindeki bir **klasör** üzerinden
istek üzerine token üretir: `tokens/req/<id>` dosyası bir istek,
`tokens/out/<id>` cevaptır.

Neden soket değil: güvenlik hikâyesi "tek loopback portu, tek efemer numara"
olan bir sürece, bir testin rahatlığı için ikinci bir dinleyen port açmak
yanlış olurdu. Dosya kanalı koşu bitince dizinle birlikte silinir.

## 3. Dış ağ: nasıl bloklanıyor, nasıl **ölçülüyor**

ADR-0006 m.2 `technocore.chat` ve `opencode.ai`'ye sıfır istek der. "Öyle bir
şeye tıklamadık" bir argümandır, kanıt değildir. Bu yüzden dört ayrı katman
vardır ve hepsi **ölçülür**:

1. **Tarayıcı sayacı (ölçüm).** `context.on("request")` bu context'teki
   **her sayfanın** yaptığı her isteği kaydeder. Bir testin sonradan
   kaydettiği `page.route` mock'u onu susturamaz; yönlendirme ne yaparsa
   yapsın istek sayılır. Her testin sonunda otomatik olarak "uygulama
   origin'i dışına sıfır istek" iddia edilir (`e2e/fixtures.ts`,
   `OutboundLedger`).

   > **Düzeltme (inceleme bulgusu).** Bu dinleyici önce `page.on("request")`
   > idi ve fixture'a verilen **tek** sayfayı görüyordu: `context.newPage()`
   > ile açılan ikinci bir sayfanın istekleri bloklanıyor ama sayılmıyordu.
   > Sayaç kesiciden dardı ve hiçbir şey bunu söylemiyordu.
2. **Tarayıcı kesici (uygulama).** `context.route("**/*")` origin dışındaki
   her isteği `abort("blockedbyclient")` ile keser ve ayrı bir sayaca yazar.
3. **API isteği kanalı.** `context.request` ve `page.request`
   (`APIRequestContext`) `context.route` tarafından **hiç** yakalanmaz. Bir
   inceleme bu kanaldan gerçek bir DNS sorgusu çıkardı: ne bloklandı ne
   sayıldı. Bugün fixture bu iki nesnenin metotlarını sarmalıyor; origin dışı
   çağrı **sayılır ve reddedilir**, istek hiç gönderilmez. Playwright'ın
   bağımsız `request` fixture'ı ve `playwright.request.newContext()` hâlâ
   kapsam dışıdır, bu yüzden spec'lerde **kullanımı yasaktır** ve
   `harness/discipline.ts` koşuyu kırar.
4. **Aletin kendi negatif kontrolleri — her iki sayaç için.**
   `shell.spec.ts` içinde bir test tek kullanımlık bir sayfadan bilerek
   `https://technocore.chat/healthz`'e gider ve hem **bloklandığını** hem
   **sayıldığını** doğrular; ikinci bir test aynısını `context.request` ile
   yapar; üçüncüsü aynı-origin bir API çağrısının **geçtiğini ve ölçüldüğünü**
   doğrular. Yalnız kesicinin negatif kontrolü vardı, sayacınki yoktu; bu da
   sayacın dar olduğunun görülmemesinin sebebiydi.

Buna ek olarak **ürünün kendi CSP'si** ölçüldü: `connect-src`,
`default-src 'none'`'dan miras aldığı için sayfa dışarı bir istek
*oluşturamıyor* bile. `csp.spec.ts` bunu doğrudan iddia eder. Bu, harness'ın
kesicisinden daha güçlüdür ve üründe kalıcıdır.

**Sunucunun** yapabileceği bir isteği tarayıcı sayamaz. Bu yüzden koşunun
sonunda sunucuya ne yaptığı sorulur: `/api/technocore/status` →
`never_checked` + `last_attempt_at: null`, `/api/opencode/status` →
`catalog.state: never_fetched`. Her iki alan da **başarısız** bir denemede
bile zaman damgası yazdığı için, bu iki değer ancak hiç deneme olmadıysa
görülebilir. Dolayısıyla katalog yenileme ve kaynak denetimi kontrollerine
hiçbir test basmaz — ve basılsaydı bu iddia düşerdi.

## 4. Ne test ediliyor

53 test, dokuz dosya. Hepsi jsdom'da kanıtlanamayan bir şey içindir.

| Dosya | Konu | Neden tarayıcı gerekiyor |
|---|---|---|
| `csp.spec.ts` | **A1-R1**: React Aria inline `<style>` hash'i, katı CSP, güvenlik başlıkları, `connect-src` | jsdom CSP uygulamaz. Bu risk bugüne kadar hiçbir otomatik testle görülemiyordu. |
| `keyboard.spec.ts` | Tab sırası, `aria-current`, daraltılmış menüde landmark'ın kalması, Enter ile seçim | jsdom Tab ile odağı hiç taşımaz; `user-event` tarayıcının sırasını değil kendi simülasyonunu okur. |
| `focus.spec.ts` | Dialog focus trap (ileri **ve** geri), Esc, odağın tetikleyiciye dönmesi, arka planın `inert` olması | Focus trap tanımı gereği tarayıcının odak davranışıdır. |
| `downloads.spec.ts` | Kanıt export'u (uçtan uca gerçek), recovery export'un `Content-Disposition` adı | `URL.createObjectURL` jsdom'da yoktur ve Vitest onu stub'lar; orada "indirildi" iddiası bir çağrı sayacıdır. |
| `composer.spec.ts` | Taslak → imza → ayrı gönderim onayı; metin/oda değişince onayın düşmesi | Gerçek form etkileşimi ve gerçek bileşen durumu üzerinde. |
| `opencode.spec.ts` | Anahtar alanının maskeli olması, kaydedilen anahtarın DOM'da **hiçbir yerde** olmaması, eşlemesiz modelin `disabled` olması | "Tüm belgede yok" iddiası ancak gerçek bir DOM'da anlamlıdır. |
| `a11y.spec.ts` | Her bölümde tek `<h1>`, dört landmark, etiketsiz form alanı olmaması, başlık hiyerarşisi | Erişilebilirlik ağacı tarayıcıda hesaplanır. |
| `shell.spec.ts` | Oturum devri, cookie bayrakları, harcanan token'ın tekrarlanamaması, veri dizini, dış ağ | 303 + `Set-Cookie` gerçek bir tarayıcı gerektirir. |
| `suite-discipline.spec.ts` | Paketin kendi kuralları (aşağıda). Taramanın kendisi `harness/discipline.ts`'te ve `globalSetup`'ta koşar | — |

## 5. Ne test **edilmiyor**

Bunlar bilinçli boşluklardır ve öyle kalırlar:

- **Gerçek kimlik.** Hiçbir test kimlik oluşturmaz, seed üretmez, kasa yazmaz
  veya gerçek `.tcrec` üretmez (ADR-0006 m.3). Kimlik dialogları açılır,
  gezilir ve kapatılır; **gönderilmez**.
- **Gerçek Technocore yazması.** Composer'ın üçüncü adımı `route.fulfill` ile
  yerel olarak yanıtlanır. Gerçekten açık bir yazma kapısına ulaşmak gerçek
  kimlik + gerçek recovery + `technocore.chat`'e canlı manifest denetimi
  isterdi; üçü de yasak. Lobby hiçbir testte hedef değildir.
- **Gerçek OpenCode çağrısı.** Anahtar **gerçekten** kaydedilir (TEST-ONLY bir
  değerle, geçici dizindeki DPAPI zarfına), ama katalog yenileme ve ölçülü
  çağrı yapılmaz. Model tablosu yamalı bir status belgesiyle sürülür.
- **Hata/loading/timeout sözleşmesinin çoğu.** `docs/ui-action-map.md` §1
  hâlâ ağırlıkla Vitest ile kanıtlıdır.
- **WCAG denetimi.** `a11y.spec.ts` bir *duman testidir*: yapısal
  gerilemeleri yakalar, uygunluk iddia etmez. Yeni bir a11y bağımlılığı
  eklenmedi.
- **Chromium dışı motorlar.** Aşağıya bakın.
- **İnsan güvenlik incelemesi.** Tarayıcı testinin geçmesi onun yerine
  geçmez (ADR-0006 "Değişmeyenler"), ve kullanıcı kabulü değildir.

## 6. Neden yalnız Chromium

Ürün Windows-only bir yerel uygulamadır (ADR-008, risk A1-R6) ve kullanıcının
zaten sahip olduğu tarayıcıda açılır. Firefox ve WebKit indirmek hedeflenmeyen
iki motor için ~300 MB ve iki motor kadar kararsızlık eklerdi. Karar
gerektiğinde tersine çevrilebilir: `playwright.config.ts` içine proje eklemek
yeterlidir.

Tarayıcı sürümü **pinlidir**: `@playwright/test` `1.62.1` tam sürümle
(`^` yok) sabitlendiği için indirilen Chromium da sabittir —
**151.0.7922.34**, Playwright revizyon **1234**. Playwright'ı yükseltmek
tarayıcıyı da değiştirir; bu yüzden yükseltme ayrı ve açık bir karar adımıdır.

## 7. Kararsızlık (flaky) politikası

ADR-0006 m.6: **kararsız bir test yeşil sayılmaz.** Uygulaması mekaniktir:

- `retries: 0`. Retry bütçesi "bazen bozuk"u "geçti" diye raporlar.
- `workers: 1`. Tek backend süreci, tek SQLite dosyası, tek oturum tablosu;
  paralel worker'lar paylaşılan sunucu durumuna araya girerdi.
- **`waitForTimeout` yok.** Her bekleme durum tabanlıdır (`expect(...)`
  polling'i, `waitForEvent`).
- Kararsız bir test gizlenmez, `skip`/`xfail` edilmez ve iddiası
  zayıflatılmaz. Kırmızıysa sebep bulunur.

Bu kurallar normalde ESLint'e yazılırdı. `apps/station-web/eslint.config.js`
bu ortamda **yazma korumalıdır** (bir depo hook'u düzenlemeyi reddediyor), bu
yüzden kural TypeScript'te yaşar.

**Nerede yaşadığı bir inceleme sonrası değişti.** Tarama önce yalnız
`suite-discipline.spec.ts` içindeydi ve commit edilmiş bir `test.only` onu da
eliyordu: koşu `1 passed (4.5s)` yazıp **exit 0** veriyordu. Bir ihlalin
kapatabildiği guard, guard değildir. Tarama bugün
`e2e/harness/discipline.ts` içindedir ve **`globalSetup`'tan** çağrılır —
Playwright henüz tek bir test seçmemişken, yani `only`, `skip` veya
`--grep` onu atlatamaz. Spec aynı fonksiyonları çağırmayı sürdürür, çünkü
normal bir koşuda ihlali adlandırılmış bir test hatası olarak görmek
okunaklıdır.

Bugün koşuyu **kıran** şeyler:

| Kural | Neden değişti |
|---|---|
| Commit edilmiş `.only` | Suite'i 51'den 1'e indirip başarı raporluyordu. Ayrıca `forbidOnly` artık **koşulsuz** `true`; `!!process.env.CI` idi, yani tam da geliştiricinin baktığı koşu bunu kabul ediyordu. |
| Commit edilmiş `.skip` / `.fixme` | Hiç denetlenmiyordu. CSP spec'inin tamamı `skip` edilince koşu `5 skipped / 46 passed`, exit 0 diyordu — `CI=1` altında da. A1-R1'in kanıtı tek kelimeyle susturulabiliyordu. |
| `tests/**` altında herhangi bir `setTimeout` | Eski desen `setTimeout(` + `resolve` iki token'ıydı, yani bir **callback adına** bağlıydı: `setTimeout(done, 750)` geçiyordu. |
| Ölçülemeyen `request` kanalı | Playwright'ın bağımsız `request` fixture'ı ve `playwright.request` giden defterin göremediği bir `APIRequestContext` üretir. |
| `retries !== 0`, `workers !== 1`, Chromium dışı proje | Değişmedi; ikisi de mutasyonla doğrulandı. |

> Bunun sonucu bir boşluktur ve dürüstçe yazılıdır: `e2e/**` ESLint tarafından
> **linlenmiyor**. Tip denetimi vardır (`tsconfig.e2e.json`, `tsconfig.json`
> referanslarına eklendi, `npm run build` içindeki `tsc -b` ile koşar), ama
> ESLint kapsamı hook kaldırılıp `eslint.config.js`'e `e2e/**` bloğu eklenene
> kadar eksiktir.

### Gözlenen kararlılık

Aynı makinede art arda **beş** tam koşu: **51/51**, süre 31.9–34.0 s. Flaky
işaretli test yok, retry yok, quarantine yok. Bağımsız inceleme aynı ölçümü
üç koşuyla tekrarladı ve doğruladı. Paket G'nin inceleme düzeltmelerinden
sonra suite **53/53**'tür (iki yeni negatif kontrol).

## 8. Açık bulgular

1. **Başlık hiyerarşisi h1 → h3 atlıyor.** HeroUI v3'ün `Card.Title`
   bileşeni `<h3>` üretiyor; kabuğun `<h1>`'inden sonra ilk başlık her
   bölümde h3 oluyor. Gerçek ama küçük bir doküman-taslağı kusuru. Bu pakette
   **düzeltilmedi**: düzeltmek bir HeroUI bileşeninin ürettiği elementi
   değiştirmek demek ve CLAUDE.md m.7 HeroUI API'sini tahmin etmeyi yasaklıyor
   (önce `heroui-react` MCP'den doğrulanmalı). `a11y.spec.ts` durumu
   **pinliyor**: h4'e gerilerse kırar, HeroUI ileride h2'ye çekerse yanlış
   alarm vermez.
2. **`e2e/**` ESLint kapsamı dışında** — §7'deki not.
