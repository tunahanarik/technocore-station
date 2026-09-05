# Kullanıcı kabul listesi

> Kapsam kararları:
> [`ADR-0011 §6`](decisions/0011-paket-j-kapsam-kararlari-2026-09-05.md) ·
> Kılavuz: [`kullanim-kilavuzu.md`](kullanim-kilavuzu.md) ·
> Kaynak raporlar: [`verification/`](verification/)

Bu liste **otomatik testlerin ölçemediği** şeyler içindir. Her maddenin
yanında hangi doğrulama raporunun onu "ölçülmedi" veya "kalan risk" diye
kaydettiği yazılıdır; yani bu liste bir dilek listesi değil, on bir raporun
kendi beyanlarının toplamıdır.

**Durum: `CODE_COMPLETE_USER_ACCEPTANCE_PENDING`.** Kod tamamdır; kabul
kullanıcının kendi işidir ve bu belge onun sırasıdır.

## Nasıl kullanılır

- Sırayla gidin. A bölümü olmadan B, B olmadan C anlamlı değildir.
- Her madde **gözlemlenebilir** bir sonuç ister: bir ekran, bir dosya, bir
  ret mesajı. "Doğru görünüyor" bir sonuç değildir.
- **Bir madde başarısız olursa durun ve not edin.** Hata kutularındaki
  "Tani bilgisini kopyala" çıktısı bu iş içindir; redaktedir ve sağlayıcı
  anahtarı taşımaz.
- **F bölümü ayrıdır ve isteğe bağlıdır.** Oraya, gerçekten istemedikçe
  girmeyin.

**Bu listede hiçbir gerçek gönderim, gerçek harcama veya `lobby` hedefi
yoktur.** F bölümü bile bir ön koşul listesidir, bir yordam değil.

---

## A. İlk açılış ve tek örnek

Kaynak: [`paket-i.md` §6, §12](verification/paket-i.md) ·
[`packaging.md` §5](packaging.md)

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| A1 | Uygulamayı başlatın (depodan veya ZIP'ten) | Varsayılan tarayıcınız kendiliğinden açılır ve adres çubuğunda `127.0.0.1:<port>` görünür; port her açılışta farklıdır |
| A2 | Adres çubuğuna bakın | Yönlenme tamamlandığında adreste **token yoktur** — temiz `/` adresindesiniz |
| A3 | Açılışı **30 saniyeden fazla** bekleyip terminaldeki bağlantıyı elle açmayı deneyin | Bağlantı çalışmaz; token süresi dolmuştur. Uygulamayı yeniden başlatmanız gerekir |
| A4 | Uygulama açıkken **ikinci bir kopya** başlatın | İkinci kopya başlamaz ve ret mesajı **silinecek kilit dosyasının yolunu** söyler |
| A5 | Uygulamayı Ctrl+C ile kapatın, sonra yeniden başlatın | İkinci başlatma sorunsuz açılır; kilit dosyası ortada kalmamıştır |
| A6 | Terminal çıktısını gözden geçirin | Hiçbir satırda açılış token'ı veya `/session/<...>` yolu yoktur |

> **A4'ün ölçülmemiş yanı** ([`paket-i.md` §12.4](verification/paket-i.md)):
> kilidin kendisi ölçüldü, ama **iki kopyanın aynı anda yarışması**
> ölçülmedi. İki kopyayı gerçekten aynı saniyede başlatmayı denerseniz
> gördüğünüzü not edin — bu, kimsenin ölçmediği bir davranıştır.

---

## B. Kimlik ve recovery

Kaynak: [`identity-lifecycle.md`](identity-lifecycle.md) ·
[`browser-qa.md` §5](browser-qa.md) (hiçbir otomatik test kimlik
oluşturmaz, seed üretmez, kasa yazmaz veya gerçek `.tcrec` üretmez)

Bu bölüm **gerçek bir kimlik oluşturur**. Bu, bu depodaki hiçbir testin
yapmadığı şeydir; bu yüzden buradaki her adım gerçekten yenidir.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| B1 | Kimlik ve Guvenlik → "Yeni kimlik olustur", **parolalı** modu seçin | Onay metnini tam yazmadan düğme etkin olmaz; 16 karakterden kısa parola kabul edilmez |
| B2 | Oluşturduktan sonra kapı listesine bakın | `identity_present`, `identity_not_revoked`, `vault_present` yeşil; **`recovery_verified` bekliyor** ve dış yazma **kapalı** |
| B3 | Olustur ve Dogrula bölümüne gidin | Metin alanı ve gönderim düğmesi **hiç yoktur**; eksik ön koşullar madde madde listelenir |
| B4 | "Recovery dosyasi olustur", ayrı bir recovery parolası verin | `.tcrec` dosyası tarayıcınıza iner. **Uygulama dizinlerinde bu dosyanın bir kopyası oluşmaz** — kontrol edin |
| B5 | "Restore-test yap", **yanlış** parolayla deneyin | Test başarısız olur ve **hiçbir şey değişmez**: durum hâlâ `recovery_pending` |
| B6 | "Restore-test yap", doğru parolayla | Durum `ready` olur ve `recovery_verified` yeşile döner |
| B7 | Kapı listesine tekrar bakın | Dış yazma **hâlâ kapalıdır**: `conformance_verified` ve `manifest_current` beklemektedir |
| B8 | Kaynaklar → "Resmi kaynaklari denetle" | Denetim sonucu üç ayrı başlıkta raporlanır ve `manifest_current` durumu değişir |
| B9 | Uygulamayı kapatıp yeniden açın, kapıya bakın | `manifest_current` **yeniden `never_checked`'tir** — dünkü denetim bugün geçmiş sayılmaz |
| B10 | `.tcrec` dosyasını ve parolasını **iki bağımsız çevrimdışı kopyaya** ayırın | Bu bir ekran kontrolü değil, sizin işinizdir. Kılavuzun en önemli cümlesi budur |

> **Ölçülmemiş** ([`identity-lifecycle.md` §4.4](identity-lifecycle.md)):
> temiz profilden kurtarma otomatik olarak **aynı Windows hesabı içinde**,
> bağımsız bir veri köküyle doğrulanmıştır. Farklı bir Windows hesabında
> test edilmemiştir. Aşağıdaki "istenmeyecekler" listesine bakın: bunu
> denemenizi **istemiyoruz**.

---

## C. Bölümlerin gerçek tarayıcı davranışı

Kaynak: [`paket-c.md` "Bilinçli ertelenenler"](verification/paket-c.md) —
dashboard kabuğu ve hata/loading/timeout sözleşmesi tarayıcı QA kapsama
alınmadan **önce** yazıldı; bütün manuel kabul maddeleri bu listeye
ertelendi. [`browser-qa.md` §5](browser-qa.md) hata sözleşmesinin
**çoğunun hâlâ ağırlıkla Vitest ile** kanıtlı olduğunu söylüyor.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| C1 | Dokuz bölümün her birini bir kez açın | Dokuzu da açılır; hiçbir bölüm boş bir iskelet göstermez |
| C2 | Bir bölümdeyken sayfayı **yenileyin** | **Genel Bakis**'e dönersiniz. Bu beklenen davranıştır (derin link yok) — sizi rahatsız edip etmediğini not edin |
| C3 | Servisi kapatın, sonra arayüzde bir düğmeye basın | Hata bölgesi bir hata kodu, istek kimliği ve "Yeniden dene" ile çıkar; sayfa boş kalmaz |
| C4 | "Yeniden dene"ye **hızlıca iki kez** basın | İkinci tık yutulur; çift istek gitmez |
| C5 | "Tani bilgisini kopyala"ya basıp panoyu bir metin dosyasına yapıştırın | Yalnız altı alan vardır: hata kodu, HTTP durumu, hata sınıfı, istek kimliği, bölüm adı, zaman damgası. **DID, yol veya anahtar yoktur** |
| C6 | Sol menüyü daraltıp yalnız klavyeyle bölümler arasında gezin | Gezinme çalışır; daraltılmış hâlde de bölüm düğmeleri erişilebilir kalır |
| C7 | Temayı değiştirin, sonra uygulamayı yeniden başlatın | Seçim **kaybolur** ve sistem teması izlenir. Bu kayıtlı bir karardır (tarayıcı deposu yok) |

---

## D. Olustur ve Dogrula — sayaç ve ekran okuyucu

Kaynak: [`paket-d.md` "Kalan riskler" m.7](verification/paket-d.md) — geri
sayım, `aria-describedby` bağlantısı ve `TextField`+`TextArea` bileşimi
**yalnız jsdom'da** kanıtlıdır.

Bu bölüm B6'yı gerektirir, ama **gerçek gönderim gerektirmez**. Kapı kapalı
olsa bile ilk iki adımın çoğunu göremezsiniz; gördüklerinizi not etmeniz
yeterlidir.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| D1 | Kapı kapalıyken bölüme bakın | Metin alanı yoktur. **Devre dışı bir buton değil, hiç olmayan bir alan** görmelisiniz |
| D2 | Kapı açıksa bir taslak hazırlayın ve imzalayın; 3. adımdaki sayaca bakın | Sayaç **gerçekten geriye** sayar ve sıfırlandığında düğme kapanır, "Onay suresi doldu" uyarısı çıkar |
| D3 | Bir ekran okuyucu (Anlatıcı/NVDA) ile parola ve metin alanlarını gezin | Her alanın yardım metni ve hata mesajı okunur; bir alanın açıklaması sessiz kalmaz |
| D4 | Metne görünmez karakter içeren bir metin yapıştırın (örn. sıfır genişlikli boşluk) | Sweep farkı gösterilir; **farkı onaylamadan imzalama düğmesi açılmaz** |
| D5 | İmzaladıktan sonra metni değiştirin | Taslak, imza ve gönderim onayının **üçü birden** düşer ve ekran bunu söyler |
| D6 | Hedef oda olarak `lobby` yazmayı deneyin | Reddedilir. `meta` de reddedilir |

---

## E. Kanitlar — indirme ve yavaş akış

Kaynak: [`paket-e.md` "Kalan riskler" m.8](verification/paket-e.md) — blob
indirme yolu, `URL.createObjectURL` ve gerçek `Content-Disposition` gidiş
dönüşü **yalnız jsdom'da**; ve **90 saniyelik yakalama deadline'ı gerçek
yavaş bir akışa karşı ölçülmedi**, backend'in faz bütçesinden akıl
yürütüldü.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| E1 | Kanitlar → Dışa aktarım; onay kutusunu **işaretlemeden** düğmeye bakın | Düğme etkin değildir ve uyarı düğmeden **önce** yazılıdır |
| E2 | Onaylayıp JSON ve Markdown olarak dışa aktarın | İki dosya da tarayıcıya iner, doğru adla; **sunucu hiçbir yola dosya yazmaz** |
| E3 | İnen dosyayı açın | İçinde public DID ve imzalar vardır; **seed, private key veya recovery secret'ı yoktur** |
| E4 | Aynı işlemi **yavaş bir diskte veya çok sayıda kayıtla** deneyin ve süreyi not edin | Ölçülmemiş olan budur: indirme yakalama deadline'ı gerçek bir yavaş akışta hiç sınanmadı. Takılırsa **bu bilinen boşluğun ilk gerçek ölçümüdür** |
| E5 | Kanıt çalışma alanında bir paket için tek kullanımlık onay hazırlayın, sonra paketi **yeniden okuyun** | Bekleyen onay **düşer** ve ekran bunu söyler |

> **F bölümü bilerek en sondadır** ve harf sırasını bozar: gerçek gönderim
> ayrı ve isteğe bağlı bir bölümdür, listenin ortasında sıradan bir adım
> değil. Önce G, H ve I'daki ölçülmemiş yüzeyler gelir.

---

## G. OpenCode paneli — odak sırası ve lint boşluğu

Kaynak: [`paket-g.md` "Kalan riskler" m.3](verification/paket-g.md) —
**34 satırlık model listesinin gerçek odak sırası tarayıcıda ölçülmedi**
(panel testleri jsdom + hedefli e2e). Ve
[`paket-g.md` "Bilinen boşluk"](verification/paket-g.md): `eslint.config.js`
bir depo hook'u tarafından yazmaya kapalı olduğu için **`e2e/**` ağacı lint
edilmiyor**.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| G1 | Ayarlar → OpenCode paneli; model kataloğunu açın ve **yalnız Tab ile** listeyi baştan sona gezin | Odak sırası görsel sırayla aynıdır; hiçbir satır atlanmaz, hiçbir yerde odak listenin dışına kaçmaz |
| G2 | Aynı listeyi bir ekran okuyucuyla gezin | Her satır kendi adını ve durumunu okur |
| G3 | Panelin "Sözleşme notları" bloğunu okuyun | Üç uyarıyı da görürsünüz: kimlik doğrulama başlığı doğrulanmadı, akış/araç çağrısı yok, anahtarın bağlı olması dosya paylaşımı demek değil |
| G4 | Bir anahtar kaydedin, sonra sayfayı yenileyin | Anahtar **hiçbir yerde geri gösterilmez** — maskeli olarak bile |

> **G-lint (kabul edilecek bir gerçek, düzeltilecek bir madde değil):**
> uçtan uca test ağacı ESLint kapsamında değildir ve bunu **bir agent
> kaldıramaz** — dosya bir depo hook'uyla yazmaya kapalıdır. Telafi
> ölçülmüştür: `tsconfig.e2e.json` `tsc -b`'ye bağlıdır (yani `npm run build`
> kapsar) ve bir disiplin testi sleep, commit edilmiş `test.only`, sıfırdan
> farklı retry, birden fazla worker veya Chromium dışı proje görürse koşuyu
> kırar. Bu maddede sizden istenen tek şey **bu boşluğun bilindiğini kabul
> etmenizdir**; hook'u kaldırıp ESLint bloğunu eklemek deponun sahibinin
> kararıdır.

---

## H. Görev, tarama ve kanıt yüzeyleri

### H1. Is Tara — süre ve iptal yokluğu

Kaynak: [`paket-h1.md` "Kalan riskler" m.3, m.4](verification/paket-h1.md) —
tarama **10 oda için ~6,8 dakikaya** çıkabilir ve **iptal kontrolü yoktur**;
sinyal tablosunun gerçek recall'u düşüktür ve **hiçbir test bunu ölçemez**.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| H1-1 | **Tek bir odayla** başlayın ve süreyi ölçün | Sonuç gelir; süreyi not edin |
| H1-2 | Sonra daha fazla odayla deneyin ve süreyi ölçün | Süre oda sayısıyla birlikte artar. **Beklerken iptal edemezsiniz** — bunun sizin için kabul edilebilir olup olmadığı bu maddenin asıl sorusudur |
| H1-3 | Sonuçlardaki adayları, gerçekten okuduğunuz odalarla karşılaştırın | Kaçırılan fırsatlar olacaktır. **Bunu hiçbir test ölçemez**; kaba bir kalıp eşleştirmesinin size yetip yetmediğine yalnız siz karar verebilirsiniz |
| H1-4 | "Bu taramanın sınırı" bloğunu okuyun | Anlamsal çıkarım olmadığı **her okumada**, sonuçların üstünde yazılıdır |
| H1-5 | Halka düşüşü uyarısını okuyun | Ayrı bir uyarı olarak durur: **sinyal hiç üretilmiyor** ve alan uydurulmamıştır |

### H2. Gorevler — plan bestecisinin tipli alanları

Kaynak: [`paket-h2.md` "Kalan riskler" m.4](verification/paket-h2.md) —
tarayıcı QA otomatiktir; **plan bestecisinin tipli parametre alanlarına
insan gözü değmedi** (ertelenmiş manuel kabul, ADR-0001 m.4).

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| H2-1 | Bir görev açın, "Plan olustur"a gidin, bir araç seçin | Aracın **beyan ettiği** parametre alanları çıkar; her alanın etiketi anlaşılırdır |
| H2-2 | Bir alanı boş bırakıp adımı eklemeyi deneyin | Reddedilir ve **hangi alanın** eksik olduğu anlaşılır |
| H2-3 | Farklı araçlar arasında geçiş yapın | Alanlar araca göre değişir; önceki aracın alanları ekranda kalmaz |
| H2-4 | Planı kaydedin | "Plani kaydet (calistirmaz)" der ve **hiçbir şey koşmaz**. Yanındaki cümle bunu söyler |
| H2-5 | Dört onayı işaretlemeden "Onayli plani calistir"a bakın; sonra dördünü işaretleyip planı **değiştirin** | Önce etkin değildir; plan değişince onaylar yeni plana **geçmez** |
| H2-6 | Yürütme durumu bloğunu okuyun | `execution_unavailable` gerekçesiyle **ve** ölçülen izolasyon envanteriyle yazılıdır: Docker var, `relied_upon: false` yanında |

### H3. Kanıt çalışma alanı — dolu durum

Kaynak: [`paket-h3.md` "Ölçülmeyenler"](verification/paket-h3.md) —
a11y/CSP/klavye döngüleri canlı backend'e karşı koşuyor **ama panel orada
hiçbir görev bulamıyor**: o döngüler **boş durumu** sürüyor, dolu durumu
değil.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| H3-1 | Önce bir görev oluşturup **dosya üreten** bir plan çalıştırın | Kanıt çalışma alanında gerçekten dolu bir paket olur |
| H3-2 | Dolu paneli **yalnız klavyeyle** baştan sona gezin | Odak sırası mantıklıdır, hiçbir kontrol atlanmaz, odak bir yerde kilitlenmez |
| H3-3 | Dolu paneli ekran okuyucuyla gezin | Dosya listesi, özetler ve **"Eksikler"** bölümü ayrı ayrı okunur |
| H3-4 | Tarayıcı konsolunu açıp paneli kullanın | **Sıfır CSP reddi** ve sıfır sayfa hatası. Boş durumda ölçülen budur; dolu durumda ölçülmedi |
| H3-5 | "Eksikler" bölümünü okuyun | Eksikler **adıyla** yazılıdır; bir paket bir sonuç değil, toplanmış malzemedir |

---

## I. Paketlenmiş sürüm ve kaldırma

Kaynak: [`paket-i.md` §12.2, §12.3, §12.5](verification/paket-i.md) —
**kaldırma akışı elle denenmedi**, artefakt hiçbir yere **kurulmadı**;
**imzalama doğrulanamaz** (sertifika yok, secret yok); ve temiz Windows
profilinde kendi kendine yeterlilik **bu makinede ölçülmedi**.

Bu bölüm yalnız ZIP yolunu seçerseniz geçerlidir.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| I1 | ZIP'i `%LOCALAPPDATA%\Programs\TechnocoreStation\` altına açıp çalıştırın | **Yönetici hakkı istenmez.** SmartScreen bir uyarı gösterir — bu beklenen davranıştır ve uyarıyı gördüğünüzü not edin |
| I2 | Uygulama açıldıktan sonra `%LOCALAPPDATA%\TechnocoreStation\` dizinine bakın | Veri dizini burada oluşur; program dizininden **ayrıdır** |
| I3 | **uv, Node ve Python kurulu olmayan** bir makinede (veya bu üçünü `PATH`'ten çıkardığınız bir kabukta) çalıştırın | Uygulama yine açılır. **Bu, bu depoda hiç ölçülmemiş bir şeydir**: artefakt her zaman bu araçlar `PATH`'te iken çalıştırıldı |
| I4 | Kaldırın: **yalnız** `%LOCALAPPDATA%\Programs\TechnocoreStation\` dizinini silin | Uygulama gider. **Veri diziniz olduğu gibi durur** — dosya adları, boyutları ve tarihleri değişmemiştir |
| I5 | Yeniden kurup açın | Kimliğiniz, kanıtlarınız ve denetim zinciriniz yerindedir |
| I6 | Veri dizinini silmeden **önce** B10'u tamamladığınızdan emin olun | Bu maddede yapılacak bir şey yok; **`.tcrec` ve parolası yoksa geri dönüş yoktur** |

---

## İstenmeyecekler — ve nedenleri

Bu belge aşağıdakileri **istemez**. Hiçbiri unutulmuş değildir; her biri
ölçülmüş bir sebeple dışarıda bırakılmıştır.

- **"İmzanın geçerli olduğunu doğrulayın" istenmez.** Artefakt
  **imzasızdır** ([`paket-i.md` §12.3](verification/paket-i.md)): bu
  makinede kod imzalama sertifikası yok, CI'da secret yok. Doğrulanacak bir
  imza olmadığı için bunu istemek, olmayan bir şeye "tamam" dedirtmek olurdu.
- **"İki derlemenin aynı hash'i verdiğini doğrulayın" istenmez.**
  **Ölçüldü ve vermiyor** ([`paket-i.md` §12.7](verification/paket-i.md)):
  aynı kaynaktan arka arkaya alınan iki yapının boyutu aynı, SHA-256'sı
  farklı. PyInstaller çıktısı bit-bit yeniden üretilebilir değildir ve öyle
  olduğu iddia da edilmiyor.
- **"Başlık hiyerarşisini doğrulayın" istenmez.** Her bölümde h1 → h3
  atlaması vardır; sebebi HeroUI v3 `Card.Title`'ın `<h3>` üretmesidir
  ([`paket-g.md` "Açık bulgu"](verification/paket-g.md)). **Bilinen ve
  kabul edilmiş** bir kusurdur ve bir a11y testi mevcut durumu pinler.
  Sizden düzeltemeyeceğiniz bir şeyi onaylamanızı istemek, kabul listesini
  bir formaliteye çevirirdi.
- **"Recovery'nizi başka bir Windows profilinde deneyin" istenmez.** DPAPI
  zarfı Windows **hesabınıza** bağlıdır; başka bir profilde yapılan deneme
  **tek yönlüdür** — başarısız olursa size hiçbir şey öğretmez, başarılı
  olursa kimliği o profile taşımış olursunuz. Bu, bir kabul adımının değil,
  bilinçli bir taşıma kararının konusudur.

---

## F. Gerçek gönderim — **ayrı ve isteğe bağlı**

> **Bu bölüm bir yordam değildir ve bir onay kutusu değildir.** Buraya kadar
> olan hiçbir madde bir gerçek Technocore write gerektirmez ve bu bölümdeki
> hiçbir madde de sizi ona sokmaz. Aşağıdakiler yalnızca **ön koşullardır**:
> siz açıkça "başlayalım" demeden hiçbir gerçek gönderim yapılmaz, ve bu
> koruma bir kutuya çevrilirse erir.

**Bu depoda hiçbir gerçek Technocore write hiç yapılmadı.** Bütün sonuçlar
mock taşıyıcıya karşı, autouse ağ kesici altında üretildi
([`paket-d.md` m.1](verification/paket-d.md),
[`paket-e.md` m.1](verification/paket-e.md)). **İlk gerçek gönderim hâlâ
incelenmemiş bir adımdır ve insan güvenlik incelemesi zorunludur**
(ADR-0001 §5).

Bir gün gerçekten göndermek isterseniz, öncesinde şunların **hepsi**
sağlanmış olmalıdır:

1. **Bir recovery dosyası ürettiniz** ve parolasını ondan ayrı bir yerde
   saklıyorsunuz (B4).
2. **Restore-testi geçtiniz** (B6). Bu, dosyanın gerçekten çalıştığını
   göstermenin tek yoludur.
3. **En az iki bağımsız çevrimdışı kopyanız var** (B10).
4. **Altı kapının altısı da yeşil**: `identity_present`,
   `identity_not_revoked`, `vault_present`, `recovery_verified`,
   `conformance_verified`, `manifest_current`. Beşi yeşil, biri bekliyorsa
   gönderim yoktur — ve olmamalıdır.
5. **`manifest_current` bu oturumda** doğrulandı (B8). Her açılışta yeniden
   yapılır; dünkü denetim bugün geçmez.
6. **Hedef `lobby` değildir.** `lobby` ve `meta` reddedilir ve bu bir
   politika kararıdır, bir protokol zorunluluğu değil.
7. **İnsan güvenlik incelemesi**, ADR-0001 §5'in ertelenmiş kalan riski,
   kapatılmıştır — ya da siz onun açık olduğunu bilerek ilerliyorsunuz.
8. Gönderdiğiniz metnin, **imza ekranında gördüğünüz canonical dizinin tam
   kendisi** olduğunu okudunuz.

Ve gönderdikten sonra bilmeniz gerekenler:

- **Sonuç üç değerli olabilir.** `outcome_unknown` "sunucu yazmış olabilir"
  demektir ve **bu sürümde bir çıkışı yoktur**: uzlaştırma oda okumayı
  gerektirir ve bu yol bilerek açılmadı. Yeniden deneme düğmesi yoktur
  ve **olmaması bir eksiklik değil**, ikinci kez yayımlama riskine karşı
  alınmış bir karardır.
- **Onay tek kullanımlıktır.** Sonuç ne olursa olsun nonce harcanır.
- **Sonuç alanı yeniden yüklemede kaybolur**; kalıcı kayıt Kanitlar
  bölümündedir.
- **Nonce tabanı saatinizin kabaca doğru olmasını varsayar.** Çok ileri
  kurulmuş bir saat o `(did, room)` çifti için geniş bir aralığı kalıcı
  yakar; monotonluk bozulmaz ama **aralık geri alınamaz**
  ([`paket-d.md` m.4](verification/paket-d.md)).
