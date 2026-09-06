# Kullanım kılavuzu

> Kapsam kararları:
> [`ADR-0011 §5`](decisions/0011-paket-j-kapsam-kararlari-2026-09-05.md) ·
> Kabul listesi: [`kullanici-kabul-listesi.md`](kullanici-kabul-listesi.md) ·
> Güncel durum: [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md)

Bu kılavuz Technocore Station'ın **bugün var olan** yüzeylerini anlatır.
Yalnız kodu okunarak doğrulanmış davranışlar yazılıdır; bir bölümün "ne
yapmadığı" da o bölümün altındadır, çünkü bu üründe bir eksiklik çoğu zaman
bir kaza değil, kayıtlı bir karardır.

Kılavuzun bilerek **söylemediği** şeyler vardır. Örneğin size "Technocore'a
mesaj gönderebilirsiniz" demez: gönderim yolu koddadır, ama bu depoda hiçbir
gerçek yazma **hiç** yapılmamıştır ve kapı altı koşulun **hepsini** ister.
Aynı sebeple "bir agent'a görev yaptırabilirsiniz", "OpenCode ile model
çalıştırabilirsiniz", "indirin ve kurun" veya "kaldığınız yerden devam
edersiniz" de demez. Neyin neden söylenmediği ilgili bölümlerde yazılıdır.

---

## 0. Ürün ne değildir

Station bir **wallet**, token claim uygulaması, airdrop puanlayıcısı,
otomatik mesaj botu veya kimlik sağlayıcısı **değildir**. Oluşturduğunuz
Ed25519 `did:key` bir anahtar sahipliği göstergesidir; gerçek kimliğinizi,
bir token sahipliğini veya bir airdrop hakkını kanıtlamaz. Bunu uygulamanın
kimlik oluşturma penceresi de aynı cümlelerle söyler.

Station telemetri toplamaz, bulut servisine bağlanmaz, tarayıcı deposu
(`localStorage` vb.) kullanmaz ve dışarıya yalnız sizin başlattığınız,
sayılı ve kayıtlı isteklerde çıkar.

---

## 1. Kurulum: iki eşit yol

**Ürünün birincil çalışma biçimi tarayıcıdır.** İki kurulum yolu da aynı
uygulamayı aynı biçimde açar; ikisi de desteklenir.

### 1.1 Depodan çalıştırma

Ön koşullar: Windows 10/11, [uv](https://docs.astral.sh/uv/) 0.11+,
Node.js 22+. Python 3.12'yi `uv` kendisi kurar.

```bash
uv python install 3.12
uv sync --project apps/station-api
npm --prefix apps/station-web install
```

Arayüzü bir kez derleyin, sonra servisi başlatın:

```bash
npm --prefix apps/station-web run build
uv run --project apps/station-api python -m station_api
```

Bu **tam ve desteklenen** bir yoldur. Aşağıdaki ZIP yolu bir kolaylıktır,
bir ön koşul değil.

### 1.2 Paketlenmiş ZIP

Son kullanıcı için hedeflenen biçim bir ZIP'tir:
`%LOCALAPPDATA%\Programs\TechnocoreStation\` altına açılır, yönetici hakkı
istemez, yalnız loopback dinler. Ayrıntı ve üretme adımları:
[`packaging.md`](packaging.md).

Bilmeniz gereken üç şey:

- **Bugün yayımlanmış bir artefakt yoktur.** Bu kılavuz size bir indirme
  bağlantısı veremez; ZIP'i bugün ancak kendiniz üretirsiniz
  (`packaging/build_bundle.py`).
- **Artefakt imzasızdır.** Windows SmartScreen imzasız bir indirmeyi uyarır;
  bu beklenen davranıştır. Bu kılavuz SmartScreen'i kapatmanızı **istemez**.
- **SHA-256 bir doğrulama yordamı olarak sunulmaz.** Build betiği bir özet
  basar ve o özet **yalnız o derlemeyi** tanımlar: aynı kaynaktan arka arkaya
  alınan iki yapının boyutu aynı, SHA-256'sı **farklı** çıktı
  ([`verification/paket-i.md` §12](verification/paket-i.md)). Yani "yayımlanan
  hash'i karşılaştırın" diyebileceğimiz kararlı bir referans yok; özet
  elinizdeki dosyanın **aynı dosya** olduğunu, artefakt imzasız olduğu için
  **kimin ürettiğini değil**, gösterir.

---

## 2. İlk açılış

Başlattığınızda sırayla şunlar olur:

1. **Tek örnek kilidi.** Veri dizininde `station.lock` `O_CREAT | O_EXCL`
   ile açılır. İkinci bir kopya aynı veritabanını ve aynı denetim zincirini
   açmaz; ret mesajı silinecek dosyanın yolunu söyler.
2. **`127.0.0.1:0`'a bind.** Port `0`, işletim sisteminden **efemer** bir
   port istemek demektir. `0.0.0.0` bind bu üründe yasaktır.
3. **Tek kullanımlık açılış token'ı.** Bellekte 30 saniyelik, tek
   kullanımlık bir token üretilir.
4. **Tarayıcı açılır.** Tarayıcı `/session/<token>` adresini bir kez
   kullanır, `HttpOnly` + `SameSite=Strict` cookie alır ve temiz `/`
   adresine yönlenir.

**Token neden loglanmaz?** Çünkü bir log satırı, canlı bir oturumu açan
anahtarı taşırsa o log dosyası artık oturumun kendisidir. Erişim logu da
kaynağında kapatılmıştır: aksi hâlde `/session/<token>` yolu kaydedilirdi.

Tarayıcı kendiliğinden açılmazsa terminaldeki bağlantıyı kullanın — ama
30 saniyeyi geçtiyse token harcanmış veya süresi dolmuş olur; uygulamayı
yeniden başlatın.

**Yapmadığı:** Station bir arka plan servisi olarak çalışmaz, oturum
açılışında başlamaz, kendini güncellemez ve kapalıyken hiçbir şey yapmaz.

---

## 3. Ekranın düzeni

Sol tarafta dokuz bölüm vardır ve dokuzu da açıktır:

| Bölüm | Ne için |
|---|---|
| Genel Bakis | Kimlik, Technocore, uygunluk ve servis sağlığının tek bakışlık özeti |
| Is Tara | Seçtiğiniz açık odaların salt okunur, tek seferlik taraması |
| Gorevler | Başlattığınız sınırlı görevlerin listesi, planı ve durumu |
| Aktivite | Agent çalışma ortamının adım adım olay kaydı |
| Kimlik ve Guvenlik | DID, koruma, recovery ve secret yaşam döngüsü |
| Olustur ve Dogrula | Metin, sweep farkı, canonical biçim, imza, onay, gönderim |
| Kaynaklar | Resmî belge erişimi, protokol değerlendirmesi ve kritik fark |
| Kanitlar | Kanıt kayıtları, dört güven seviyesi ve kanıt çalışma alanı |
| Ayarlar ve Yardim | Tema, uygulama bilgisi, güvenlik kapıları, OpenCode bağlantısı |

**Derin link yoktur.** Bölüm seçimi düz React state'tir; URL'e yazılmaz.
Sayfayı yenilerseniz **Genel Bakis**'e dönersiniz — kaldığınız yere değil.
Bu kayıtlı bir karardır (yeni bağımlılık istememek için router yok), bir
hata değil.

**Tema tercihi kalıcı değildir.** Tarayıcı deposu bu uygulamada
kullanılmadığı için seçim yalnız o oturum içindir; yeniden açılışta sistem
teması izlenir.

---

## 4. Kimlik ve recovery: bu kılavuzun merkezi

Bu bölüm ürünün en önemli sözleşmesidir. **ADR-014**: recovery, ilk gerçek
yazmadan **önce zorunludur** — ve bu bir öneri değil, kodda sayılabilen bir
kapıdır.

### 4.1 Altı kapı

`identity/write_gate.py` saf bir fonksiyondur ve **tüm dış yazmaların tek
kapısıdır**. Override bayrağı, ortam değişkeni veya debug bypass'ı yoktur.
Altı kontrol sayar ve **hepsi** geçmeden dış yazma açılmaz:

| # | Kontrol | Kapının kendi cümlesi (ekranda aynen görünür) |
|---:|---|---|
| 1 | `identity_present` | Aktif bir kimlik gerekli. |
| 2 | `identity_not_revoked` | Kimlik revoke edilmis olmamali. |
| 3 | `vault_present` | Secret kasasi bulunmali. |
| 4 | **`recovery_verified`** | **Recovery restore-test ile dogrulanmis olmali.** |
| 5 | `conformance_verified` | Sweep/canonical/imza uygunlugu self-test ile dogrulanmali. |
| 6 | `manifest_current` | Resmi kaynaklar bu oturumda denetlenmis ve guncel olmali. |

Dördüncü satır bu kılavuzun sebebidir: **`recovery_verified` geçmeden
hiçbir Technocore write açılmaz.** Kasanız yerinde, kimliğiniz sağlam ve
uygunluk motoru yeşil olsa bile, restore-test yapılmadıysa gönderim yolu
kapalıdır.

Altıncı satırın ayrı bir özelliği vardır: her açılışta `never_checked`'ten
başlar ve **veritabanından geri yüklenmez**. Dün başarılı bir denetim
yaptınız diye bugün geçmiş sayılmaz — çünkü protokolün bugün ne olduğu
hakkında dünkü denetim bir şey söylemez.

Kapıların canlı durumunu iki yerde görürsünüz: **Kimlik ve Guvenlik →
Teknik ayrintilar → Dis yazma kapisi** ve **Ayarlar ve Yardim → Guvenlik
kapilari**. **Olustur ve Dogrula** bölümü de aynı listeyi "Ön koşullar"
başlığı altında tekrar gösterir.

### 4.2 Beş pencere

Kimlik yüzeyinde beş iş vardır ve hepsi ayrı bir pencerede yapılır.

**1. Yeni kimlik olustur.** Seed yalnız `secrets.token_bytes(32)` ile
üretilir; paroladan türetme desteklenmez. İki koruma modu vardır:

| Mod | Katmanlar | Not |
|---|---|---|
| `dpapi+passphrase` | Argon2id + ChaCha20-Poly1305, sonra DPAPI | **varsayılan ve önerilen** |
| `dpapi` | Yalnız Windows DPAPI (current-user) | ayrıca risk onayı ister |

Parola en az 16 karakter olmalıdır. Yapay büyük/küçük/sembol kuralı yoktur;
bu kurallar tahmin edilebilir kalıplara iter. Parola **açılışta sorulmaz**,
yalnız secret kullanan işlemlerde sorulur (recovery üretimi ve imzalama);
salt okunur kullanımda sürtünme yoktur. Pencere ayrıca tam bir onay metnini
yazmanızı ister.

Bu adımdan sonra kimlik `recovery_pending` durumundadır ve **dış yazma hâlâ
kapalıdır**.

**2. Recovery dosyasi olustur.** Ayrı bir recovery parolası istenir (kasa
parolanızdan farklıdır ve hiçbir yerde saklanmaz). Şifreli `.tcrec` dosyası
doğrudan tarayıcınıza teslim edilir; sunucu onu hiçbir yola yazmaz.

> Ekrandaki uyarı aynen geçerlidir: dosyanın güvenliği tamamen seçtiğiniz
> parolaya bağlıdır. Dosyayı ve parolayı **ayrı yerlerde** saklayın, **en az
> iki bağımsız çevrimdışı kopya** alın. **Parola kaybolursa kimlik geri
> getirilemez.**

**3. Restore-test yap.** Bu, dördüncü kapıyı açan tek işlemdir. Dosyayı ve
recovery parolasını verirsiniz; Station dosyadan seed'i çözer, DID'i yeniden
türetir ve **üç yönlü** karşılaştırır: türetilen DID = başlıktaki DID =
kurulu DID. Test **kasaya dokunmaz** ve kurulu seed'i değiştirmez;
başarısızlıkta **hiçbir şey değişmez**. Başarıda durum `ready` olur.

Kısacası: bir recovery dosyanız olduğunu **iddia etmeniz** yetmez; onun
gerçekten çalıştığını göstermeniz gerekir.

**4. Recovery dosyasindan kur.** Kimlik bulunmayan bir profilde kullanılır.
Önce **inspect** yapılır — dosya ve parola ile yalnız public DID ve
fingerprint gösterilir, hiçbir şey yazılmaz. DID'i onaylarsınız, yeni koruma
modunu seçersiniz, ve seed yeni profilin kasasına yazılır. Bu yolda recovery
**doğrulanmış** sayılır: dosyayı açabilmek zaten restore-testin kendisidir.

**5. Revoke et.** Tam DID'i yazarak onaylarsınız. Kasa zarfı silinir,
metadata `revoked` olur. Arayüz açıkça söyler: bu bir **güvenli disk silme
değildir** ve **mevcut recovery dosyalarınız geçerli kalmaya devam eder**.

### 4.3 Bu yüzeyin yapmadıkları

- **Web arayüzünde raw seed alanı yoktur** ve HTTP üzerinden seed kabul eden
  bir uç yoktur. Mevcut resmî bir seed'i içe aktarmak yalnız kendi
  terminalinizde, CLI ile yapılır (`python -m station_api.cli import-seed`);
  seed ve parola komut satırı argümanı değildir, parolalar `getpass` ile
  alınır, ve kaynak dosya değiştirilmez veya silinmez.
- Seed hiçbir API yanıtına, loga veya ekrana çıkmaz.
- Seed bellekte `bytearray` olarak tutulur ve kullanım sonrası sıfırlanır —
  ama bu **bir garanti değildir**: CPython değeri tahsis veya çöp toplama
  sırasında kopyalamış olabilir. Ürün bunu gizlemez.

---

## 5. Bölüm bölüm

### 5.1 Genel Bakis

Üstte dört durum kartı (yerel servis, veritabanı, oturum güvenliği,
Technocore), altında üç özet kart: kimlik, Technocore durumu, protokol
uygunluğu. Her kart kendi ucunu okur ve **bağımsız** başarısız olur; bir uç
erişilemezse diğer kartlar boşalmaz. Her kart ilgili bölüme giden bir
düğmeyle biter.

Technocore durumu dört değer alır ve dördü de dürüsttür:
`Denetlenmedi` · `Salt okunur · guncel` · `Suruklenme var` · `Erisilemiyor`.
**"Denetlenmedi" bir başarısızlık değildir** — kimseye bağlanmamış bir
uygulamanın doğru tarifidir, ki siz istemedikçe Station tam olarak budur.

"Sonraki güvenli adım" satırı backend'in kendi kapı kontrollerinden türer,
yol haritasının frontend'e kopyalanmış bir nüshasından değil; bu yüzden bir
aşama teslim edildiğinde bayatlamaz.

**Yapmadığı:** hash koşturmaz, dekoratif metrik veya grafik göstermez,
kendiliğinden yenilenmez.

### 5.2 Is Tara

Seçtiğiniz açık odalar **bir kez** okunur ve okunanlardan aday iş çıkarılır.
Akış: "Oda listesini oku" → listeden oda seç → "Secili odalari tara" →
istersen "Secili adayi yerel gorev olarak ac".

Her aday **sekiz öğeyle** gösterilir: birebir alıntı ve kaynağı, kime
faydası var, teslimat, başarı koşulu ve nasıl test edileceği, araç/veri
yetkinliği, çalışma tahmini, gereken izinler ve riskler, ve işin durumu
hakkında söylenebilecek. Sekizi de her zaman ekrandadır.

Bilmeniz gerekenler:

- **Hiçbir şey kendiliğinden olmaz.** `setInterval` yok, `setTimeout` yok,
  arka plan görevi yok, otomatik yenileme yok. Her dış okuma bir tıklamanın
  içindedir; bir test hiçbir zamanlayıcının kurulmadığını sayar.
- **Kapsam sizin seçtiğiniz odalardır.** Bütün oda evreni hiçbir zaman
  taranmaz. Bir taramada en çok **10 oda** seçilebilir — bu seçilmiş bir
  sayıdır, yayımlanmış bir limitten türetilmedi.
- **Çıkarım deterministiktir.** Kalıp eşleştirmesi yapılır, anlamsal çıkarım
  yoktur; yani bir odadaki **her** fırsat görülmez. Bu cümle backend'in
  kendi cümlesidir ve sonuçların **üstünde**, her okumada gösterilir.
- **Oda içeriği topluluk verisidir.** Alıntılar biçimlendirilmemiş metin
  olarak gösterilir — asla markup, asla bağlantı. `did:key` kalıbına
  uymayan bir gönderen "kendi beyan ettiği takma ad" olarak işaretlenir.
- **"Açık" kelimesi kullanılmaz.** Bir işin açık olup olmadığını söyleyen
  bir rozet yoktur, çünkü bunu kuracak bir alan yoktur; onun yerine okuma
  anı ve servisin kendi beyanı yazılır.

**Yapmadıkları, adıyla:**

- **Tarama uzun sürebilir ve iptal edilemez.** 10 oda için ~6,8 dakikaya
  çıkabilir ve **iptal kontrolü yoktur**
  ([`verification/paket-h1.md`](verification/paket-h1.md)). Kısa bir
  deadline alternatifi sunucunun oda-başına hata listesini atardı, ki bu
  daha kötüydü. Az sayıda odayla başlayın.
- **Sinyal tablosu kabadır.** Dört tanıyıcı (yardım çağrısı, hata bildirimi,
  inceleme isteği, belge eksiği) elle yazılmış işaretlerden ibarettir;
  gerçek recall düşüktür ve **hiçbir test bunu ölçemez**.
- **Halka düşüşü sinyali hiç üretilmiyor.** Ekranda bunu söyleyen ayrı bir
  uyarı vardır: "liste üç saniye eski olabilir" ile "hiç okumadığınız
  mesajlar gitti" iki ayrı bulgudur ve biri diğerinin yerine geçemez.
  Şemada alan vardır, sunucu tarafında **üretilmemektedir**, ve
  uydurulmamıştır.
- Dış servis kayıtları için **hiçbir adapter yazılmadı ve hiçbir istek
  gönderilmedi**; kaydın doğrulanan ve doğrulanamayan sütunları yan yana
  gösterilir.

### 5.3 Gorevler

Bir görev alır, ona bir **plan** yazar, planı ayrı bir istekle
çalıştırırsınız. Sırayla: durum değiştirme → plan oluştur → dört onay →
"Onayli plani calistir".

**Plan yazmak çalıştırmak değildir.** Plan adımları, söz verilen çıktı
dosyalarını ve başarı ölçütünü kaydeder ve üçünü birden özetler; hiçbir şey
koşmaz. Planı sonradan değiştirmek başarı kriterini sessizce gevşetemez:
başlatma kaydedilen planı yeniden özetler ve uyuşmazlıkta reddeder. **Plan
düzenleme diye bir şey yoktur** — farklı bir plan yeni bir çalışmadır.

**Dört onay bir plana aittir**, bir oturuma değil: planı okudum, veri
paylaşımını onaylıyorum, çalışma alanını onaylıyorum, tavanı onaylıyorum.
Yeni bir plan **yapı gereği onaysızdır** — birinin hatırlaması gereken bir
sıfırlamayla değil. Plan içindeki küçük ve güvenli dosya işlemleri için her
adımda yeniden onay istenmez; kapsam veya risk değişirse yeni plan yeniden
sorar.

**Araçlar kapalı bir registry'den gelir.** Sekiz araç vardır: onaylı
içeriği oku, çalışma alanı dosyası oku, dosya yaz, dosya güncelle, JSON
doğrula, iki dosyayı karşılaştır, SHA-256 tutarlılığı doğrula, çalışmanın
kendi durumunu oku. Agent kendine araç **ekleyemez**: araç listesi bir tuple
literal'dir, kayıt fonksiyonu veya plugin yolu yoktur, ve `git`, `commit`,
`install`, `shell`, `sign`, `vault`, `credential` gibi parçalar taşıyan bir
kayıt olsa uygulama **başlamaz**. Bir araca **adres verilemez**: `path` ve
`url` diye bir parametre tipi yoktur.

**Tavan dört birimdir ve derleme zamanındadır:** en çok 32 araç çağrısı,
en çok 8 model çağrısı, en çok 120 saniye duvar saati, eşzamanlılık **1**.

Token ve para birimi **reddedilmiştir** ve reddedildikleri adıyla yayımlanır.
Gerekçesi değişti ve sertleşti: eskiden "model yolu kapalı olduğu için
sağlayıcıdan gelen bir kullanım değeri yok" idi; sağlayıcı artık hem `usage`
hem `cost` gönderiyor ve ikisi de **kaydediliyor**. Yine de tavan olmuyorlar,
çünkü **karşı tarafın bildirdiği bir sayıyla ifade edilen tavan, karşı tarafın
koyduğu tavandır.** Sayılan şey Station'ın kendi yaptığı istek sayısıdır.

Agent'ın tavanı okuyan veya yazan bir aracı yoktur.

**Çalışma alanı** `<veri dizini>/workspace/v1/<görev kimliği>/` altındadır ve
dört katman korur: dosya adı süzülmez, **yeniden kurulur**; her okuma ve her
yazımda yol çözülüp köke kapsanır; dosyadan köke kadar her bileşende symlink
**ve** NTFS junction denetlenir; ve tavanlar (en çok 64 dosya, dosya başına
512 KiB, toplam 4 MiB) sayaçtan değil **diskten** okunur. Arşiv açan hiçbir
kod yoktur — `zipfile`, `tarfile`, `shutil` import edilmez — yani kendi
arşivinizi bu ürünün dışında bir kez siz açarsınız.

**Yapmadıkları, adıyla:**

- **Keyfi kod ve kabuk yürütmesi kapalıdır** (`execution_unavailable`) ve
  bu ekranda gerekçesiyle birlikte yazılıdır. Bu makinede Docker ölçüldü ve
  **var** bulundu — ama yanında `relied_upon: false` yazar: geliştiricinin
  makinesinde bulunan bir sandbox, ürünün verebileceği bir garanti değildir.
  Dolayısıyla **bu sürüm kod çalıştıramaz** ve çalıştırma gerektiren iş
  `blocked`/`review_needed`'da **durur**. Bu bir eksiklik değil, kayıtlı bir
  karardır (ADR-0008 §1).
- **Model plan önerir, çalıştırmaz.** Bu üç madde önce "model çağrısı
  yoktur", "test sonucu hep `not_implemented` kalır" ve
  "`ready_to_publish`'e geçilemez" diyordu; **üçü de artık yanlış** ve
  ölçülerek düzeltildi (ADR-0012). Bugünkü gerçek şudur: model **öneri**
  üretir, ve önerdiği her araç adı **kapalı registry'de** aranır, her
  argüman **tipli doğrulamadan** geçer, hiçbir araç `path`/`url` almaz.
  Öneri, elle yazılmış bir planın geçtiği **aynı dört onaydan** geçer ve
  **model kendi planını onaylayamaz**. Yani "model çıktısı doğrudan
  yürütülmez" hâlâ yapısal bir gerçektir — ama artık "model çıktısı diye bir
  şey yok" diyerek değil, çıktıyı kapalı bir registry'den geçirerek.
- **Başarı ölçütü artık koşulabiliyor.** Planınız kabul koşulu taşıyorsa
  çalışma sonrası **gerçekten değerlendirilir** ve `test_result`
  `passed`/`failed` üretir. `not_implemented` yalnız **koşulsuz** bir plan
  için kalır, ve gerekçesini söyler. Koşullar planın özetinin **içindedir**:
  onaydan sonra bir koşulu düzenlemek planı geçersiz kılar.
- **`ready_to_publish` erişilebilir, ama istenebilir değil.** Yayın
  hazırlığını değerlendiren bir yol vardır; fakat o isteğin gövdesinde
  **hedef alanı yoktur**, yani hiçbir istek bu durumu **adıyla
  isteyemez** — kapı kanıttan türetir. Kullanıcının doğrudan
  isteyebileceği geçişler değişmedi: onaya al, incelemeye al, engellendi,
  başarısız, yayımlandı olarak işaretle.
- **Yeniden başlatma hiçbir şeyi sürdürmez.** Kesilen çalışmalar listelenir;
  devam etmek bir kişinin işidir ve yalnız zaten onaylanmış kapsamda ilerler.
- **Durdur ve devam et bilerek araç değildir.** Kendini devam ettirebilen
  bir çalışma sizin durdurma kararınızı geri alabilirdi.

**Ama Durdur ve Devam et düğmeleri vardır ve sizindir.** Yukarıdaki madde
*agent'ın* araç listesi hakkındadır; kendi arayüzünüzde iki düğme durur.
Çalışan bir çalışmada **Durdur** etkindir: basıldığında hemen bir
**"Durdurma istendi"** rozeti çıkar, çalışma sıradaki adım sınırında durur ve
**`Kullanıcı durdurdu`** durumuna geçer — bu bitmiş bir son değil, beklemedir.
**Devam et** yalnız durdurulmuş **ve** kapsamı hâlâ tam onaylı bir çalışmada
etkindir; onay eksikse düğme kapalı kalır. İkisi de yalnız bu iki durumda
tıklanabilir, başka hiçbirinde.

Bir çalışmanın **beş ayrı sonu** vardır ve ayrı gösterilir: tamamlandı,
iptal edildi, bütçe tükendi, araç hatası, söz verilen çıktı üretilmedi.
"Bütçen bitti" ile "girdin bozuk" arasındaki farkı göremeyen biri ikisine de
müdahale edemez. **Beşincisi hakkında dürüst olalım:** `iptal edildi` bu
sürümde tanımlı, bitmiş sayılan ve arayüzde adı olan bir sondur, ama **hiçbir
kod yolu onu üretmiyor** — durdurduğunuz bir çalışma `Kullanıcı durdurdu`da
kalır. Listede olmasının sebebi, ürünün onu göstermeye hazır olması; burada
yazmasının sebebi, göreceğiniz şeyin ne olduğunu bilmeniz.

### 5.4 Aktivite

Agent çalışma ortamının adım adım kaydı, en yenisi üstte. Bir çalışma
kimliğiyle filtreleyebilir veya filtreyi kaldırabilirsiniz.

- **Her satır gerçekleşmiş bir olaydır.** Hiçbir satır bir tahmin veya bir
  ilerleme göstergesi değildir; bu akışta yüzde yoktur.
- **Kendiliğinden yenilenmez.** Yeni satırları görmek için "Akisi oku"
  dersiniz.
- **Silme de bir olaydır.** Kapsamdaki işaretsiz satırları silebilirsiniz,
  ama **audit zincirinin atıfta bulunduğu satırlar silinemez ve budanmaz**;
  silme isteği onları korur. Silme işleminin kendisi zincire bir olay olarak
  yazılır, yani kayıt sessizce kaybolmaz. Rapor iki sayı verir — silinen ve
  zincir yüzünden korunan — çünkü bunlar iki ayrı sorunun cevabıdır.
- **Boş bir akış bir şey yapılmadığını kanıtlamaz**; yalnızca bu kapsamda
  kayıtlı satır olmadığını gösterir. Ekran bunu böyle söyler.

Bir saklama sınırı vardır ve ekranda yazılıdır: en yeni N satır tutulur,
toplam olay sayısı ve zincirin atıfta bulunduğu satır sayısı ayrı ayrı
gösterilir.

### 5.5 Kimlik ve Guvenlik

Yukarıdaki [§4](#4-kimlik-ve-recovery-bu-kılavuzun-merkezi) bu bölümü
anlatır. Burada ayrıca **Teknik ayrıntılar** vardır: kasa yeteneği (DPAPI ve
AEAD hazır mı), protokol uygunluk self-test'inin alan alan sonucu (sweep,
DID, canonical, imzalama, doğrulama, base64url, tamper reddi), pinlenmiş
referans commit ve dış yazma kapısının altı satırı.

Sayfa yalnız **public** malzeme gösterir: DID, fingerprint, koruma modu ve
recovery zaman damgaları. Seed alanı, seed gösterimi ve gizli bir şeyi
kopyalayan bir kontrol yoktur.

**Uygunluk ile güncellik aynı şey değildir** — bu ayrım ürünün her yerinde
tekrarlanır: uygunluk self-test'i **bu yapının** pinlenmiş referans commit
ile aynı davrandığını gösterir; salt okunur denetim ise **canlı sunucunun**
hâlâ o protokolü yayımladığını gösterir. Bir yapı, sunucunun çoktan
terk ettiği bir referansa kusursuzca uygun olabilir — ve bu, sunucunun
reddedeceği baytlar üzerinde geçerli bir imza üreten tam olarak o durumdur.

### 5.6 Olustur ve Dogrula

Dış yazma yolunun bulunduğu tek yüzey. Üstte altı kapının canlı durumu,
altında besteci.

**Kapı kapalıysa metin alanı ve gönderim kontrolü hiç görünmez** — ekran
bunu şöyle söyler: "Devre dışı bir buton bir güvenlik kontrolü değildir;
kapalı kapı sunucudadır ve üç adımın üçü de aynı kapıyı yeniden koşar."
Eksik ön koşullar madde madde listelenir.

Kapı açıksa akış üç adımdır ve **üçü de ayrı**:

1. **Taslak.** Hedef oda ve metin verirsiniz. Sunucu metni süpürür
   (görünmez karakterler silinir) ve canonical biçimi kurar. `lobby` ve
   `meta` odaları **reddedilir**.
2. **İmza onayı.** Süpürme metni değiştirdiyse **farkı görmeden
   imzalayamazsınız**: onay kutusu imzalama düğmesinin ön koşuludur, yanında
   duran bir not değil. Çünkü imzalanan şey yazdığınız şey değildir. Kasanız
   parolalıysa parola burada sorulur. Ekran açıkça der: **imzalamak
   göndermek değildir.**
3. **Gönderim onayı.** İmzanın kapsadığı canonical dizenin tam kendisi
   ekrana yazılır — gösterilen ile imzalanan aynıdır. Onay **tek
   kullanımlıktır ve süresi sınırlıdır**; kalan saniye ekranda sayar.
   Gönderim denemesi, sonuç ne olursa olsun, nonce'u harcar.

**Metni veya odayı değiştirirseniz üçü de düşer** — taslak, imza ve gönderim
onayı — ve ekran bunu söyler. Gönderim token'ı yalnız bu bileşenin
state'inde yaşar; düştüğünde bayat baytların yayımlanmasının bir yolu kalmaz.

**Sonuç üç değerlidir, iki değil:** kabul edildi, reddedildi, veya
**sonuç bilinmiyor — sunucu yazmış olabilir**. Üçüncüsü olduğu gibi
gösterilir ve **hiçbir dalda yeniden deneme düğmesi yoktur**: reddedilen bir
istek yine reddedilir, sonucu bilinmeyen bir istekte körlemesine tekrar
mesajı ikinci kez yayımlayabilir, ve bu sürümde uzlaştıracak bir oda okuma
yolu yoktur.

**Yapmadıkları:**

- **Otomatik gönderim yoktur.** Zamanlanmış mesaj, otomatik ping veya
  kendiliğinden oda katılımı bu üründe bulunmaz.
- **İmzalı note gönderimi yoktur.** Pinlenmiş protokol imzalı note yazmasını
  yalnız `room-owners` ve `room-allow` namespace'lerinde kabul ediyor;
  istenen DID profil notu ise imzasız lane'de yayımlanır ve imza kanıtı
  üretmez. İmzasız bir yazmayı "gönderildi" rozetiyle sunmak kanıt
  seviyelerini karıştırmak olurdu. Ekran bu cümleyi kendi başlığı altında
  gösterir.
- **Ne gönderildiğinin oturum kaydı yoktur.** Sonuç alanı yeniden yüklemede
  kaybolur; kalıcı kayıt **Kanitlar** bölümündedir.
- **`lobby` hiçbir bağlamda hedef değildir.**

### 5.7 Kaynaklar

"Resmi kaynaklari denetle" düğmesi sabit bir listedeki resmî belgeleri okur
ve üç şeyi ayrı ayrı raporlar: **1. Belge erişimi** (kaç belge alındı,
alınamayanlar hangileri), **2. Protokol değerlendirmesi** (değişen alanlar,
her biri kendi sonucuyla), **3. Kritik fark**.

Erişilebilirlik ile protokol uyumu **bilerek ayrı tutulur**: bu ayrım bir
503'ün "protokol değişti" diye okunmasını ve ayrıştıramadığımız bir şemanın
"ağ sorunu" diye okunmasını engeller.

Bu denetim altıncı kapıyı (`manifest_current`) açan işlemdir ve her
açılışta yeniden yapılması gerekir.

**Yapmadığı:** oda, mesaj veya note içeriği alınmaz; hiçbir yazma isteği
gönderilmez. Technocore'da bazı GET yolları yazma yapar, bu yüzden istemci
**keyfi bir adres kabul etmez** — yalnız kayıtlı listedeki belgeler okunur.

### 5.8 Kanitlar

Üç şey bir arada: **audit zinciri**, **kanıt kayıtları** ve **kanıt çalışma
alanı**. Buradaki hiçbir şey bir sonuç değildir; toplanmış malzemedir.

**Dört güven seviyesi** hiçbir zaman tek bir rozete toplanmaz:

| Seviye | Neyi kanıtlar | Neyi kanıtlamaz |
|---|---|---|
| 1 — İmza kanıtı | DID özel anahtarına sahip tarafın belirli canonical metni imzaladığı | Gerçek kimliği veya zamanı |
| 2 — Sunucu gözlemi | Station'ın belirli bir sunucu yanıtını gördüğü | Sunucunun dürüstlüğünü |
| 3 — Yerel kayıt zamanı | Yerel makinenin o anda gösterdiği saat | Güvenilir bir zaman damgası değildir |
| 4 — Harici anchor | — | **MVP kapsamında yoktur ve boş bırakılır** |

**Audit zinciri** kendi sınırını kendisi söyler: zincirin içinde kendi
uzunluğunu söyleyen bir şey yoktur, yani **sonun kesilmesi**, ayrı bir
zarfta tutulan zincir başı olmadan tespit edilemez. Zincir aynı Windows
kullanıcısı olarak çalışan bir saldırgana karşı **korumaz**; bu
belgelenmiştir, testle gösterilmiştir ve aksi iddia edilmemiştir.

**Dışa aktarım** (JSON veya Markdown) bir onay kutusunun arkasındadır ve
uyarı önce gelir: dosya public DID'inizi, imzalarınızı ve gönderim
kayıtlarınızı taşır. Bunlar gizli değerler değildir, ama paylaşıldıklarında
bu makinedeki kimlik ile dosyayı paylaştığınız yer arasında **kalıcı bir
kimlik bağlantısı** kurulur. Bu dosya, hata kutularındaki "Tani bilgisini
kopyala" çıktısıyla **aynı şey değildir** ve onun yerine kullanılmamalıdır.

**Kanıt çalışma alanı** bir görevin paketini gösterir: üretilen dosyalar,
özetleri, ve **eksikler adıyla**. Paketi dışarıya almak için hazırlanan onay
**tek kullanımlıktır, pakete bağlıdır ve reddedilen bir teslim de onu
harcar** — bu şartlar düğmeden **önce** yazılıdır. Bir dosya değişirse
paketin özeti değişir ve eski onay artık eşleşmez. Paketi yeniden okumak
bekleyen onayı **düşürür**, çünkü onay tam da yeniden okumanın değiştirmiş
olabileceği özete bağlıdır. Paket bu makinede hiçbir yola yazılmaz.

**Yapmadıkları:** sayfalama yoktur (kayıtlar budanmadığı için uzun ömürlü
bir kurulum uzun bir liste render eder); DPAPI yoksa kanıt katmanı çalışmaz
ve gönderim `evidence_recorded=false` raporlar; seviye 4 tasarım gereği
boştur.

### 5.9 Ayarlar ve Yardim

Beş blok: **Görünüm** (tema; kalıcı değil), **Uygulama ve servis** (yerel
servisin kendi bildirdiği durum: aşama, çalışma modu, veritabanı, oturum
taşıma), **Güvenlik kapıları** (altı kapının canlı durumu), **OpenCode Go
bağlantısı** ve **Yardım**.

**OpenCode bağlantısı hakkında.** Bu, **Ayarlar sayfasındaki tek** maskeli
alandır ve yalnız bir sağlayıcı API anahtarını kabul eder. (Uygulamanın
başka yerlerinde maskeli alanlar vardır — Oluştur ve Doğrula ile Kimlik ve
Güvenlik ekranlarındaki parola alanları; sınır bu sayfa hakkındadır.) Anahtar yalnız yazılır:
kaydedildikten sonra ne o sayfada kalır ne de herhangi bir yoldan geri
gösterilebilir. Bu istisna yalnızca sağlayıcı anahtarı içindir — bu
uygulamada hiçbir yerde DID seed'i, private key veya recovery secret'ı kabul
eden ya da gösteren bir alan **yoktur**.

Ama panelin kendisi de sınırlarını söyler ve bu kılavuz onları tekrarlar:

- **Kimlik doğrulama başlığı doğrulanmamıştır.** `Authorization: Bearer`
  varsayımı resmî belgede doğrulanmamıştır ve panelde de böyle gösterilir.
  Gerçek bir anahtarın çalışıp çalışmadığı hesap sahibinindir.
- **Akış (streaming) bu sürümde yoktur.** Bir değer değil, bir **tip**
  olarak `false`'tur; yani bu cümle bayatlayamaz. Akış biçimi yayımlanmadı ve
  ölçülmedi, bu yüzden uydurulmadı.
- **Araç çağrısı artık vardır ve nedeni ölçümdür.** Bu cümle eskiden akışla
  aynıydı; sözleşme hesap sahibinin kendi anahtarıyla `chat/completions`
  ucunda ölçüldükten sonra değişti (ADR-0012). Panel `tool_calls_supported`
  değerinin yanında **neyin ölçüldüğünü** de gösterir; ölçüm yalnız o
  protokol ailesi içindir ve diğerleri için bir şey iddia edilmez.
- **Anahtarın bağlı olması dosya paylaşımı demek değildir.** Kaydedilmiş bir
  anahtar, bilgisayarınızdaki dosyaların modele gönderilebileceği anlamına
  gelmez.
- **Model kataloğu bayat olabilir** ve panel bunu söyler.

**Kısacası (H4 öncesi cümle, tarihsel):** bu sürümde OpenCode ile model çalıştıramazsınız. Model lane'i
kapalıdır; bu panel bir bağlantı kaydı ve bir katalogdur, bir çalıştırma
yüzeyi değil.

**Sorun bildirirken** hata kutusundaki "Tani bilgisini kopyala" çıktısını
kullanın. O çıktı bilerek redaktedir: yalnızca hata kodu, HTTP durumu, hata
sınıfı, istek kimliği, bölüm adı ve zaman damgası taşır — sağlayıcı anahtarı
oraya hiçbir koşulda girmez.

---

## 6. Kaldırma ve veri dizini

> **Bunu okumadan silmeyin.**

**Kaldırma yalnız program dizinini siler:**

```
%LOCALAPPDATA%\Programs\TechnocoreStation\
```

**Veri dizinine dokunulmaz:**

```
%LOCALAPPDATA%\TechnocoreStation\
```

Bu dizinde **seed'in DPAPI zarfı**, **denetim zincirinin anahtarı**, kanıt
kayıtları ve çalışma alanı vardır.

> ### ⚠ Veri dizinini silmek geri alınamaz
>
> Veri dizinini elle silerseniz ve elinizde **`.tcrec` recovery dosyanız ile
> onun parolası yoksa, kimliğiniz geri gelmez.** Geri döndürülemez bu kayıp
> bilerek tek bir tıklamaya bağlanmamıştır: gerçekten temizlemek istiyorsanız
> dizini elle silersiniz.

DPAPI zarfı Windows **kullanıcı hesabınıza** bağlıdır, yola bağlı değildir:
dizini taşımak kimliği bozmaz, **silmek bozar**.

Ayrıca:

- **Kurulum veri dizinini oluşturmaz.** Dizin başka bir yerde önceden
  oluşturulursa veritabanı kalıtılmış izinlerle doğar
  (`ensure_data_dir` bugün ACL uygulamıyor).
- **Downgrade yoktur.** Eski bir sürüme dönmek isterseniz önce veri
  dizininin yedeğini alın; şemayı geri almanın desteklenen bir yolu yoktur
  ve olduğu iddia edilmez. Daha yeni bir şemayla işaretlenmiş bir dosyayı
  açan eski kod durur ve verinin değiştirilmediğini söyler.
- **Yükseltme yerinde yapılır** — arşivi aynı dizine açın. Kurulum kökü
  sürümsüzdür ve bir `current` bağlantısı yoktur.

---

## 7. Bu ürünün karakteri: yapmadıkları, tek yerde

- **Hiçbir gerçek Technocore write hiç yapılmadı.** Gönderim yolu koddadır,
  kapı altı koşulun hepsini ister, ve ilk gerçek gönderim hâlâ incelenmemiş
  bir adımdır. **İnsan güvenlik incelemesi ertelenmiş bir kalan risktir**
  (ADR-0001 §5) ve bu paket onu kapatmaz — görünür kılar.
- **Yürütme kapalıdır.** Bu sürüm kod çalıştıramaz; çalıştırma gerektiren iş
  `blocked`/`review_needed`'da durur.
- **Model çağrısı yoktur.** OpenCode paneli bir bağlantı kaydıdır.
- **Yayımlanmış bir artefakt yoktur** ve kaldırma akışı hiç denenmedi.
- **HTTP isteği iptali yoktur.** Uçuştaki bir istek iptal edilemez;
  uygulama genelinde bir boşluktur ve en görünür hâli iş taramasıdır. Bir
  agent **çalışmasını** durdurmak ayrı bir şeydir ve **vardır** — §5.3'teki
  Durdur/Devam et düğmeleri.
- **Note lane yoktur.**
- **Görev katmanında bütçe alanı yoktur** — tavan bir görevin değil, bir
  **çalışmanın** özelliğidir.
- **Derin link yoktur**; yenileme Genel Bakis'e döner.
- **Tarayıcı deposu kullanılmaz**; tema seçimi bile kalıcı değildir.
- **Telemetri, analytics ve bulut servisi yoktur.**
- **Uzak font, CDN veya harici UI varlığı yoktur.**

---

## 8. Sırada ne var

Bu kılavuz ürünü tarif eder; onu **kabul etmek** ayrı bir iştir ve sizindir.
Elle yapılacak kabul adımları, hangi doğrulama raporundan geldikleriyle
birlikte, [`kullanici-kabul-listesi.md`](kullanici-kabul-listesi.md)
dosyasındadır.

Daha derin belgeler:

| Konu | Belge |
|---|---|
| Kimlik durum makinesi ve akışlar | [`identity-lifecycle.md`](identity-lifecycle.md) |
| `.tcrec` biçimi | [`recovery-format-v1.md`](recovery-format-v1.md) |
| Savunulan ve **savunulmayan** tehditler | [`threat-model.md`](threat-model.md) |
| Kanıt modeli | [`evidence-model.md`](evidence-model.md) |
| Agent çalışma ortamı | [`agent-runtime.md`](agent-runtime.md) |
| İş taraması | [`work-scan.md`](work-scan.md) |
| Kanıt çalışma alanı | [`proof-workspace.md`](proof-workspace.md) |
| OpenCode bağlantısı | [`opencode-connection.md`](opencode-connection.md) |
| Paketleme, kurulum, kaldırma | [`packaging.md`](packaging.md) |
| Test edilebilir güvenlik değişmezleri | [`security-invariants.md`](security-invariants.md) |
