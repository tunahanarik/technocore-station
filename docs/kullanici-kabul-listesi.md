# Kullanıcı kabul listesi

> Kapsam kararları:
> [`ADR-0011 §6`](decisions/0011-paket-j-kapsam-kararlari-2026-09-05.md) ·
> Kılavuz: [`kullanim-kilavuzu.md`](kullanim-kilavuzu.md) ·
> Kaynak raporlar: [`verification/`](verification/)

Bu liste **otomatik testlerin ölçemediği** şeyler içindir. Her bölümün
başında hangi doğrulama raporunun o maddeleri "ölçülmedi" veya "kalan risk"
diye kaydettiği yazılıdır; yani bu liste bir dilek listesi değil,
[`verification/`](verification/) altındaki raporların kendi beyanlarının
toplamıdır.

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
- **Bir maddenin para harcayıp harcamadığı maddenin başında yazılıdır.**
  Yalnız H5'te böyle maddeler vardır ve orada tek tek işaretlidir.

**Bu listede hiçbir gerçek Technocore gönderimi ve hiçbir `lobby` hedefi
yoktur.** F bölümü bile bir ön koşul listesidir, bir yordam değil.

**Gerçek harcama tek bir yerdedir ve adıyla yazılıdır.** H5'teki model
turları, hesap sahibinin kendi anahtarıyla **ölçülü (metered) bir uca** giden
gerçek HTTP istekleridir
([`ADR-0012 §0`](decisions/0012-model-yolu-sozlesme-dogrulamasi-2026-09-06.md)
o ucu ölçerken "metered uç" diye kaydeder) ve faturası sizindir. Bu depodaki
hiçbir otomatik test böyle bir istek yapmaz — hepsi mock taşıyıcı kullanır —
yani o isteği yapan taraf sizsiniz. H5'te **bir tur harcayan tek bir madde**
vardır ve adıyla işaretlidir; kalanlar ya hiçbir şey harcamaz ya da o turun
sonucunu okur. Harcamayanlar bilerek önce gelir.

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
| E6 | Dosya üreten bir plan çalıştırın (H3-1), sonra dosya listesinin üstündeki iki sayıyı okuyun | "Govdesi pakete alinan dosya: n / m" yazar, ve altındaki cümle bu iki sayının **paketin kendi özet satırından değil**, listedeki dosyalar ile adıyla yazılmış dışlama gerekçelerinden türetildiğini söyler |
| E7 | Tek kullanımlık onayı hazırlayın ve paket yerine **"&lt;dosya&gt; dosyasini indir"** düğmesine basın | Dosyanın **kendisi** iner — düz metin, ek olarak, tarayıcıda çalıştırılabilecek bir biçimde değil. Ekranda görünen özet **sunucunun yanıt başlığında gönderdiği** özettir, o ekranın hesapladığı bir sayı değil |
| E8 | Aynı onayla ikinci bir teslim deneyin | Olmaz. Paketi indirmek ile tek bir dosyayı indirmek **aynı onayı harcayan iki seçenektir**; ikincisi için yeniden onay hazırlamanız gerekir ve bu şart düğmelerden **önce** yazılıdır |
| E9 | Bir planla, gövdesine **64 karakterlik onaltılık bir dizi** (örneğin bir SHA-256 özeti) yapıştırdığınız bir dosya yazdırın, sonra paketi okuyun | Dosya listede **adıyla, bayt sayısıyla ve özetiyle kalır**, ama gövdesi pakete alınmaz; gerekçe **kuralın adıyla** yazılıdır ve eşleşen değer hiçbir yere yazılmaz. O dosya için "dosyasini indir" düğmesi de çıkmaz. Dışlama dosyayı değil, yalnız içeriğin pakete alınmasını engeller |
| E10 | Bir dosyanın metnine, bu ürünün kendi cümlelerinde kullanmadığı bir ifade yazdırın (örneğin `test gecti`), sonra paketi **Markdown** olarak indirin ve o dosyanın bölümüne bakın | Gövde **değiştirilmeden** aktarılır ve üstünde, metinde böyle bir ifadenin geçtiği **adıyla** yazar. İfade silinmez, maskelenmez ve dosya reddedilmez: maskelemek özetin altındaki baytları değiştirirdi, ve bir veri metni size kendi kanıtınızı reddettiremez |

> **E6–E10'un kaynağı ayrıdır** ([`paket-h4.md` §5](verification/paket-h4.md),
> [`review-fixes.md` "Ölçülmeyenler"](verification/review-fixes.md)):
> paketin gövde taşıyan hâli ve tek dosya teslimi bu turda geldi, ve o turun
> kendi raporu **manuel tarayıcı ve görsel kabulün yapılmadığını**, hepsinin
> kullanıcıya ait olduğunu yazıyor. E9 ve E10 birbirinin zıddı değil, aynı
> kuralın iki yarısıdır: **gizli değer taraması bir rettir**, dil kaydı ise
> bir **rapordur** — biri gövdeyi dışarıda bırakır, öteki gövdeye
> dokunmadan yanına not düşer.

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
| G3 | Panelin "Sözleşme notları" bloğunu okuyun | Üç notu da görürsünüz: kimlik doğrulama başlığı doğrulanmadı; **akış yok, araç çağrısı ölçüldü** (ve neyin ölçüldüğü yazıyor); anahtarın bağlı olması dosya paylaşımı demek değil |
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

> **H4, H5 ve H6 sona eklendi, araya sokulmadı.** İçerik olarak H4 taramanın
> (H1), H5 ile H6 ise görev yüzeyinin (H2, H3) devamıdır; sonda durmalarının
> tek sebebi, var olan madde numaralarının **kaymamasıdır**. Bir kabul
> listesinde madde numarası bir adrestir: birinin not aldığı "H2-4 kırmızı"
> cümlesi, listeye bir satır eklendi diye başka bir maddeyi göstermeye
> başlamamalıdır.

### H4. Oda listesi ve keşif günlüğü — canlı, yabancı yazımı veri

Kaynak: [`paket-h1.md` "Kalan riskler"](verification/paket-h1.md) ·
[`review-fixes.md` "Ölçülmeyenler"](verification/review-fixes.md) — **hiçbir
otomatik test gerçek bir Technocore odası okumadı**; bütün oda belgeleri
sahtedir. Yani bu bölümdeki her şeyde canlı veriye bakan ilk taraf sizsiniz.

H1 taramanın **süresini** ve iptal yokluğunu sorar; bu bölüm taramadan
**önceki** iki yüzeyi sorar: neyi tarayacağınızı seçtiğiniz oda listesi ve
servisin kendi keşif günlüğü. Maddeler bilerek **hangi odaların
listelendiğinden bağımsızdır** — liste canlıdır ve yarın başka odalar taşır;
buradaki her beklenti listenin içeriğine değil, listenin **biçimine** bakar.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| H4-1 | Is Tara → "Oda listesini oku"; listenin üstündeki tek satırlık künyeyi okuyun | Dört şey yan yanadır: servisin bildirdiği **toplam**, burada **tutulan** sayı, listenin **kırpılıp kırpılmadığı** ve okunan belgenin **özeti**. Toplam ile tutulan farklıysa bunu satırın kendisi söyler; hiçbir yerde "hepsi bu" denmez |
| H4-2 | Aynı satırın altındaki bayatlık cümlesini okuyun | Üç şey ayrı ayrı yazılıdır: ölçülen **okuma anı**, sunucunun kendi saniye **beyanı**, ve o beyanın **nereden okunduğu**. Station "taze" veya "bayat" diye bir hüküm **vermez**; öyle bir eşik uydurulmadı |
| H4-3 | Listedeki herhangi bir odanın kutusuna bakın | Oda **adı** ve **başlığı** uyarı çerçeveli ayrı bir kutudadır, üstünde bu iki alanı bir yabancının yazdığı yazar, ve ikisi de biçimlendirilmemiş metin olarak durur — bağlantı yok, markup yok. Servisin kendi ölçümleri **başka** bir kutudadır ve ikisi hiçbir odada tek bir satırda birleşmez |
| H4-4 | Onuncudan sonra bir oda daha seçmeye çalışın | Kutular kapanır; tek bir taramada en çok on oda okunacağı ve kalanları ayrı bir taramayla seçebileceğiniz yazılır |
| H4-5 | Uygulamayı yeni açtıysanız — yani B9'daki gibi `manifest_current` henüz `never_checked` iken — "Kesif gunlugunu oku"ya basın | Reddedilir ve ret **önce resmî kaynak denetimini çalıştırmanızı** söyler: keşif günlüğü de bir odadır ve doğrulanmamış bir konvansiyonla adlandırılmaz |
| H4-6 | B8'i yapıp aynı düğmeye tekrar basın | Her satır ya seçilebilir bir oda adıdır ya da **olduğu gibi** gösterilen, seçilemez bir satırdır ve neden okunamadığı yanında yazar. Satır biçimi yayımlanmadığı için Station bir ad **uydurmaz**; okuyamadığını size ham hâliyle gösterir |
| H4-7 | Günlük boş geldiyse cümlesini okuyun | "Yeni oda açılmadı" der. Okunamayan bir günlük **hiçbir zaman** boş günlük olarak gösterilmez: okunamayan bir okuma bir rettir |
| H4-8 | Oda listesinde `lobby` veya `meta` görürseniz onu seçip tarayın. **Görmezseniz bu maddeyi "listede yoktu" diye not edin** | Reddedilir; ret "Okunamayan odalar" başlığı altında **odanın adıyla** yazılır ve o odaya hiçbir istek gitmez. Bu iki ad bu ürünün reddettiği tek iki addır ve ret **ada** bağlıdır, listeye değil — maddenin listeden bağımsız olmasının sebebi budur |
| H4-9 | Listeyi okuduktan sonra ekranı bir süre öylece bırakın | Hiçbir şey kendiliğinden yenilenmez. Liste, günlük ve tarama yalnız siz bir düğmeye bastığınızda okunur; beklemek yeni bir satır getirmez |

> **H4-8'in keşif günlüğündeki karşılığı bilerek farklıdır:** reddedilen bir
> oda günlükte **ne adıyla ne de satırıyla** görünür — yalnız okunamayan bir
> satır olarak, gerekçesiyle durur. Bir adın, o adı ekrandan uzak tutmak için
> var olan denetimin **içinden geçerek** ekrana gelmesi istenmedi. Yani
> günlükte o odayı seçebileceğiniz bir kutu hiç oluşmaz; listede ise oluşur
> ve tarama anında reddedilir. İki yüzeyde iki farklı davranış görmeniz
> beklenen sonuçtur.

### H5. Modelden plan önerisi — **bu bölümün bir kısmı gerçek para harcar**

Kaynak: [`paket-h4.md` §5](verification/paket-h4.md) ·
[`review-fixes.md` "Ölçülmeyenler"](verification/review-fixes.md) — **gerçek
bir sağlayıcı isteği hiçbir testte yapılmadı**; her model turu mock taşıyıcı
üzerinden koştu ve kimlik bilgisi depodaki sentetik `TEST-ONLY` sabitidir.
Aynı rapor manuel tarayıcı kabulünün yapılmadığını da yazıyor.

**Önce parayı konuşalım.** Bir model turu, kaydettiğiniz anahtarla **ölçülü
(metered) bir uca** giden gerçek bir HTTP isteğidir
([`ADR-0012 §0`](decisions/0012-model-yolu-sozlesme-dogrulamasi-2026-09-06.md)).
Aşağıda her maddenin başında **bir tur harcayıp harcamadığı** yazılıdır.
Harcamayanlar önce gelir; onlarla, hiçbir şey ödemeden bu yüzeyin
söylediklerinin doğru olup olmadığını görebilirsiniz.

Bir uyarı daha, ve bu maliyetten önce gelir: **kaybolan bir yanıt da
harcanmış olabilir.** İstek çıktıysa ve cevabı gelmediyse ürün bunu ayrı bir
sonuç olarak söyler ve **kendiliğinden yeniden denemez** — yeniden deneme,
"belki ödendi"yi "kesin ödendi"ye çevirir.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| H5-1 | **(harcamaz)** Bir görev açın, "Modelden plan onerisi" bölümündeki uyarı bloğunu ve tur kuralını **düğmeye basmadan** okuyun | Dört şey düğmelerden **önce** yazılıdır: önerinin elle yazılmış bir planla aynı dört onaydan geçtiği; modelin kendi planını onaylayamayacağı ve bir çalışmayı başlatamayacağı; listede olmayan bir araç adının öneriyi **bütünüyle** reddettireceği; ve araçlara yol veya adres verilemeyeceği |
| H5-2 | **(harcamaz)** "Hangi model secili, oku"ya basın | Kimseye bağlanılmaz. Seçili model, kimlik bilgisinin kayıtlı olup olmadığı ve **neyin ölçüldüğü** yazılır. Basmadan önce ekran zaten "okunmadı" der ve bir model adı **göstermez**: bir tur yanıtı model kimliği taşımaz ve bu ekran bir ad uydurmaz |
| H5-3 | **(harcamaz; hiçbir istek gitmez)** Anahtarı **kaydetmeden** ya da bir model **seçmeden** "Modelden plan oner (calistirmaz)"a basın | Bir sonuç çıkar, eksiği **adıyla** söyler ve **"Harcanan model turu" sayacı 0'da kalır**: istek hiç kurulmadı. Station sizin yerinize model seçmez |
| H5-4 | **(harcamaz; hiçbir istek gitmez)** Ayarlar → OpenCode'da model listesinde her satırın protokol ailesi yazılıdır; `chat/completions` **dışında** bir aileden seçilebilir bir model seçin ve aynı düğmeye basın | Yine bir ret çıkar ve bu kez modeli **adıyla** reddeder: araç çağrısı biçimi yalnız bir protokol ailesi için ölçüldü ve ötekiler için bir şey iddia edilmez. Sayaç yine 0'dadır. Ölçülmemiş bir sözleşmeye istek göndermemenin ekrandaki hâli budur |
| H5-5 | **(bir tur harcar — gerçek para)** `chat/completions` ailesinden bir model seçiliyken ve anahtar kayıtlıyken aynı düğmeye basın | Sonuçlardan biri çıkar ve **hiçbiri "çalıştı" değildir**: en iyisi "plan önerildi ve kaydedildi (hiçbir şey çalıştırılmadı)". Sayaç bir artar. Sonuç ne olursa olsun hiçbir adım koşmaz |
| H5-6 | **(ek tur harcamaz)** Sonuç "plan önerildi" ise "Calismalar" listesine bakın | Öneri orada `planned` fazında ve **dört onayı da işaretsiz** durur. "Onayli plani calistir" etkin değildir; başlatmak sizin ayrı işleminizdir. Ekran ayrıca modelin bir çalışmayı başlatamayacağını yazar |
| H5-7 | **(ek tur harcamaz)** Sonuç bir plan üretmediyse sonucun etiketini ve altındaki cümleyi okuyun | Turun **nasıl** bittiği ayrı ayrı adlandırılır: modelin araç çağırmayı bırakması, yanıtın çıktı tavanında **kesilmesi** ve nedeni okunamayan bir bitiş aynı cümleyle anlatılmaz. Yalnız birincisi oturumu kapatır; öteki ikisi "oturum kapanmadı, yeniden isteyebilirsiniz" der — ve kesilme için her isteğin bir tur harcadığı da yazılıdır |
| H5-8 | **(ek tur harcamaz)** Sonucun altındaki sağlayıcı beyanı satırını okuyun | Kullanım ve maliyet **sağlayıcının kendi bildirimi** olarak, olduğu gibi yazılıdır ve satır bunun bizim ölçümümüz olmadığını, tavan olarak kullanılmadığını söyler. Tavan Station'ın kendi sayabildiği birimdedir ve yanında durur: "Harcanan model turu: n / 8" |
| H5-9 | **(harcamaz)** Aynı ekranda modelin muhakemesini arayın | Yoktur, ve ekran **neden** olmadığını söyler: alan okunur, kullanılmaz, saklanmaz, loglanmaz ve gösterilmez. Gizlenmiş bir blok, açılır bir panel veya "daha fazla göster" yoktur |
| H5-10 | **(harcamaz)** "Oturumu unut ve bastan basla"ya basın, sonra "Calismalar" listesine ve Kanitlar'a bakın | Yalnız bellekteki konuşma düşer. **Kaydedilmiş planlar, çalışma alanı ve kanıtlar olduğu gibi durur**; unutmak hiçbir kaydı silmez |

> **Ölçülmemiş olan** ([`paket-h4.md` §5](verification/paket-h4.md)): bu
> yüzeyin bütün testleri mock bir taşıyıcıya karşı koşar. Gerçek bir
> sağlayıcının gerçek bir turda ne döndüreceği — hangi aracı seçeceği, kaç
> adım önereceği, cevabının tavanda kesilip kesilmeyeceği — **hiçbir testin
> ölçebileceği bir şey değildir**. H5-5'te gördüğünüz sonuç, o sonucun bu
> ürüne ne yaptırdığından ayrı bir şeydir; bu bölüm ikincisini sorar.

### H6. Kabul koşulları, test sonucu ve yayın hazırlığı

Kaynak: [`paket-h4.md` §3, §5](verification/paket-h4.md) ·
[`proof-workspace.md` §10](proof-workspace.md) — kabul koşulları ve
`ready_to_publish` yolu bu turda geldi ve turun kendi raporu **manuel kabulün
yapılmadığını** yazıyor.

Bu bölüm **hiçbir model turu gerektirmez ve hiçbir şey harcamaz**: elle
yazılmış bir plan da kabul koşulu taşıyabilir, ve buradaki her madde öyle bir
planla yapılabilir.

| # | Yapın | Görmeyi beklediğiniz |
|---|---|---|
| H6-1 | Hiç kabul koşulu **yazmadan** bir plan kaydedin, dört onayı verip çalıştırın, sonra çalışmanın "Test sonucu" satırına bakın | "Uygulanmadi" yazar **ve gerekçesini söyler**: plan makinenin karar verebileceği bir koşul yazmadı, yalnız bir cümle kaydetti ve cümle koşulmaz. Plan söz verdiği bütün dosyaları üretmiş olsa bile bu değişmez |
| H6-2 | Aynı görevde yeni bir plan yazın; bu kez "Dosya calisma alaninda var mi" koşulunu üreteceğiniz dosyanın adıyla ekleyip çalıştırın | Test sonucu "Gecti" olur, ve hükmün bir kabuk komutunun çıktısı değil **dosyaların okunmasıyla** verildiği yazılıdır |
| H6-3 | Üçüncü bir planda, aynı koşulu plana **yazmadığınız** bir dosya adıyla ekleyin, "Soz verilen cikti dosyalari" alanını boş bırakın ve çalıştırın | Çalışma **tamamlanır**, ama test sonucu "Kaldi" olur ve **sağlanmayan koşul adıyla** yazılır. "Tamamlandı" ile "geçti" bu üründe iki ayrı cümledir ve ayrı ayrı gösterilir |
| H6-4 | Koşul listesine bakın: kayıtlı olmayan bir koşul adı yazmayı deneyin | Yazacak yer yoktur. Koşul kümesi sabit bir radyo listesidir ve serbest metin kabul eden bir alan **hiç yoktur**; her koşulun ne yaptığı yanında yazılıdır |
| H6-5 | Bir koşula yol benzeri bir dosya adı verin (`..\gizli.txt` gibi) ve planı kaydetmeye çalışın | Plan **kaydedilmez** ve ret gerekçesiyle ekrana çıkar; ret ayrıca Aktivite'de bir karar noktası olarak durur. Bir koşul bir dosyayı yalnız **sade adıyla** anar |
| H6-6 | Çalışma bittikten sonra "Yayin hazirligi" bölümünde, **hiçbir düğmeye basmadan**, bekleyen alanları okuyun | Doğrulanmamış alanlar **adıyla** yazılıdır, yani bir deneme yapmadan neden reddedileceğinizi görürsünüz. Ekran ayrıca "yayıma hazır"ın **istenemeyeceğini** söyler: durum değiştirme düğmelerinin arasında karşılığı yoktur ve yayın hazırlığı isteği bir **hedef alanı taşımaz** |
| H6-7 | Üç alandan biri eksikken "Yayin hazirligini degerlendir (durumu istemez)"e basın | Reddedilir, ret **eksik alanları adıyla** sayar ve durum değişmez. Aynı isteği kaç kez yaparsanız yapın cevap aynıdır: cevap kanıtın bir fonksiyonudur |
| H6-8 | Üç alan da doğrulandıktan sonra (çıktı üretildi, test sonucu "Gecti", ve Kanitlar'da siz kabul ettiniz) aynı düğmeye basın | Durum "Yayima hazir" olur ve ekran bunun bir **yayım olmadığını** söyler: hiçbir şey gönderilmedi, dış paylaşım ayrı bir işlemdir |

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
ölçülmüş ya da koddan okunmuş bir sebeple dışarıda bırakılmıştır. Ortak
ölçüt tektir: bir madde, ekranın başında oturan bir kişinin **gerçekten
gözlemleyip yargılayabileceği** bir şey istemiyorsa listeye girmez.

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
- **"Modelin iyi bir plan önerdiğini doğrulayın" istenmez.** Bir önerinin
  "iyi" olup olmadığı ölçülebilir bir şey değildir ve bu üründe böyle bir
  hüküm veren bir alan yoktur; olsaydı, uydurulmuş olurdu. Doğrulanabilir
  olan, öneriye **ne yapıldığıdır** — adı kapalı registry'de aranır,
  argümanları tiplenir, sonuç dört onayı bekleyen bir plandır — ve H5 tam
  olarak bunları ister.
- **"Modele kayıtlı olmayan bir araç adı önerdirip reddi görün" istenmez.**
  Ret yolu gerçektir ve `refused` sonucu olarak ekranda vardır, ama onu
  **siz üretemezsiniz**: modelin o turda ne döndüreceği sizin elinizde
  değildir, ve sizden tetikleyemeyeceğiniz bir davranışı onaylamanızı
  istemek bir kabul maddesini bir temenniye çevirir. Yerine H5-1 kuralın
  **ekranda, düğmeden önce** yazılı olduğunu, H5-4 ise sizin kendi
  seçiminizle üretebileceğiniz, hiçbir istek göndermeyen bir reddi ister.
- **"Onayladığınız bir planın kabul koşulunu düzenleyip planın geçersiz
  olduğunu doğrulayın" istenmez.** Bu üründe **plan düzenleme diye bir şey
  yoktur**; farklı bir plan yeni bir çalışmadır ve yeni bir çalışma yapı
  gereği onaysızdır. Koşullar planın özetinin içindedir ve düzenlenmiş bir
  plan başlatmada reddedilir — ama bunu ekranda **yapabileceğiniz bir yol
  olmadığı için**, madde sizden ulaşamayacağınız bir kapıyı yoklamanızı
  istemiş olurdu. H2-5 bu davranışın gözlemlenebilir yarısını —
  değişen bir plana onayların **geçmediğini** — zaten istiyor.
- **"Bir dosyayı tavanın üstüne çıkarıp gövdesinin pakete alınmadığını
  doğrulayın" istenmez.** Bu ürünün tek bir araç çağrısında yazabileceği en
  büyük dosya **20 000 karakterdir**, tekil dosya tavanı ise **512 KiB**, ve
  çalışma alanı zaten en çok **64 dosya** tutar. Yani bu ürünle üretilen bir
  çalışma alanı bu tavanların hiçbirini geçemez; tavan dışlaması ancak
  dosyanın oraya **başka bir yoldan** konmasıyla görülebilir ve bir kabul
  adımı sizden dizine elle dosya koymanızı istememelidir. E9, aynı per-dosya
  ret mekanizmasını sizin **gerçekten üretebileceğiniz** bir yoldan sorar.

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
