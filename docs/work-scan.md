# İş Tara — kamuya açık oda taraması (Paket H1)

Kapsam kararları: [`decisions/0007-paket-h1-kapsam-kararlari-2026-09-04.md`](decisions/0007-paket-h1-kapsam-kararlari-2026-09-04.md).
Test edilebilir değişmezler: [`security-invariants.md`](security-invariants.md) §9i (SI-271…SI-284).

Bu belge dört soruyu cevaplar: **sözleşmenin neyi doğrulandı ve neyi
doğrulanamadı**, **deterministik çıkarımın sınırı nerede**, **Kibble'ın durumu
ne**, ve **polling yasağının karşılığı kodda ne**.

---

## 1. Okunan yüzey

Dördüncü kapalı registry: [`workscan/targets.py`](../apps/station-api/src/station_api/workscan/targets.py).
Beşinci giden istemci: [`workscan/client.py`](../apps/station-api/src/station_api/workscan/client.py).

| Hedef | Yol | Method | Yol otoritesi | İçerik otoritesi | Gövde tavanı |
|---|---|---|---:|---:|---:|
| `room_index` | `GET /rooms` | GET | 1 | **3** | 2 MiB |
| `room_messages` | `GET /r/{room}` | GET | 1 | **3** | 4 MiB |

**Bu listede olmayan hiçbir yol bu registry'den istenmez.** İstemci URL, path,
method, header veya TLS ayarı kabul etmez.

`RoomScanTarget` oda politikasını **kendi tipinde** uygular: `__post_init__`
adı yayımlanmış kalıba, `DENIED_ROOMS`'a ve tanınan oda sınıflarına karşı
yeniden doğrular. Önceki sürümde bu cümle doğru değildi — tip düz bir frozen
dataclass'tı ve `RoomScanTarget("lobby", ())` elle kurulup `/r/lobby`'ye
istek sürülebiliyordu; şema, host, port ve yol şekli registry'nin ürettiğinin
aynısı olduğu için `assert_allowed_url` bunu geçiriyordu. Politika artık üç
katmanda: `resolve_room_target`, `RoomScanTarget.__post_init__` ve giden
URL'in kendisi (`assert_allowed_url`). Üçü de aynı `DENIED_ROOMS`'u okur;
tekrar bilinçlidir (ADR-0002 4.1, ADR-0007 11, INV-05).

### `/r/events` neden kapsam dışıydı, neden artık değil

Pinli `openapi.json`, `/r/events` girdisini `parameters: null` ile yayımlıyor;
`since`/`format`'in geçerli olduğunu yalnız **düzyazı açıklaması** söylüyor.
Paket B'nin ilkesi "kritik alan şemadan okunur, düzyazıdan değil"di ve hiç
parametresi olmayan bir şemada bu ilke uygulanamaz. H1 bu yüzden keşif
lane'ini açmadı.

Ölçülen sözleşme bu gerekçeyi ilkeyi gevşetmeden ortadan kaldırıyor: lane
**sıradan bir oda gibi** davranıyor — `since`, `format` ve halka tutması aynen
geçerli. Yani yeni bir adres ailesi değil; `/r/{oda}` lane'inin derleme
zamanında sabitlenmiş bir oda adıyla (`events`) okunması. Sonuçları:

- **Registry iki hedefte kalır.** `SCAN_TARGETS` büyümedi ve bir test bunu
  küme eşitliğiyle tutuyor.
- **`OUTBOUND_CLIENT_MODULES` beşte kalır.** Yeni istemci yok; mevcut
  `workscan/client.py` kullanılıyor.
- **Oda politikası aynen uygulanır.** `discovery_target` doğrudan
  `resolve_room_target`'ı çağırır; doğrulanmış marker yoksa reddeder.
- **Yazma yolu açılmadı.** Günlük sunucu-yazımlıdır; bir istemcinin buraya
  yazma denemesi 403 alır. Bu ürün denemez ve paket ağacında yazma adresi
  taşıyan bir string literal bulunmadığını bir test AST ile doğrular.

#### Satır biçimi yayımlanmadığı için ayrıştırıcı uydurulmadı

Açıklama "her yeni kamu odası için bir satır" diyor ve duruyor; satırın çıplak
ad mı, adı içeren bir cümle mi olduğunu söylemiyor. Tahmine göre yazılmış bir
ayrıştırıcı, biçim ilk farklılaştığında **ürünün uydurduğu oda adları**
üretirdi. Bu yüzden kural tektir: süpürüldükten sonra tamamı geçerli bir oda
adı olan satır seçilebilir olur, diğer her satır **geldiği gibi** gerekçesiyle
gösterilir. Kullanıcı böylece bizim tahminimizi değil gerçek biçimi görür.

Dört satır seçilebilir olmaz: okunamayan biçim, `DENIED_ROOMS` üyesi bir ad
(satırın metni de düşürülür — adı tekrar etmek, onu ekrandan uzak tutan
denetimin kendisiyle ekrana getirmek olurdu), listelenmeyen (`p-`) bir odayı
duyuran satır (servis böyle bir duyurunun olmadığını söylüyor; çelişkiyi
düğmeye çevirmek onu aklamak olurdu) ve boş satır.

Süpürme **ad karşılaştırmasından önce** çalışır ve bu sıralama bir denetimdir:
`lobby` yazıp yanına sıfır genişlikli boşluk yapıştıran bir satır burada
`lobby` olur ve **adıyla** reddedilir; ham metinle karşılaştırılsaydı yalnızca
"biçim okunamadı" derdik — doğru ama yanlış cümle.

### `/rooms`: servisin ölçümü ile çağıranın metni artık ayrı

`GET /rooms` kendi hakkında birebir şunu söylüyor: her girdide **iki alan
çağıran denetimindedir** — `room`, o odaya ilk yazanın seçtiği bir metindir ve
`topic`, `/kv/topic/{oda}` adresinde dünyaya yazılabilir bir nottur; ikisi de
atanmaz, denetlenmez, "veri, asla talimat".

H1 bu iki alanı tutup girdinin geri kalanını **atıyordu**. Sonuç, bir odayı
diğerinden ayırt edecek hiçbir şeyi olmayan bir listeydi. Artık:

- `name`/`topic` ayrı, `measured` ayrı alandır. `measured`, girdideki
  çağıran-yazımı **olmayan** her anahtarın, servisin kullandığı adla
  taşınmasıdır. Yayımlanmış `rooms[]` şeması hiçbir property adlandırmadığı
  için toplamlar **ada göre değil yapısal olarak** okunur — böylece kimsenin
  yayımlamadığı bir alan adı uydurulmuş olmaz. Alan sayısı ve değer uzunluğu
  sınırlıdır, değerler süpürülür, nesne/dizi **yürünmez**, tek sınırlı metne
  dönüştürülür.
- `measured` yanına her okumada `MEASURED_CAVEAT` gider: bunlar servisin kendi
  ölçümleridir, Station hiçbirinden sıralama, tavsiye, itibar veya uygunluk
  türetmez.
- Yanıtın kendi `untrusted` nesnesi **telde taşınır** ama tek başına esas
  alınmaz. Geçerli küme iki listenin **birleşimidir**: yanıt kümeyi
  genişletebilir (`extra_fields`), daraltamaz (`missing_fields` bunu kaydeder).
  Nesne hiç gelmezse bu da `present: false` olarak kaydedilir — "bildirim yok"
  ile "bildirim var ama bizim alanlarımızı saymıyor" iki farklı cevaptır.

### Elle yazılan `p-` oda: ölçülen davranış

Listede `p-` odalar **hiç görünmez** ve keşif günlüğünde **hiç duyurulmaz**;
ürün de eksikleri uydurmaz. Kullanıcı böyle bir adı elle yazarsa ölçülen
davranış şudur: `resolve_room_target("p-...", markers=…)` **başarılı olur**
(`classes == ("p",)`, `is_unlisted == True`) ve oda okunur.

Kayda geçen kusur: `RoomScanTarget.is_unlisted` ve `is_ephemeral` H1'den beri
vardı ve **hiçbir çağıran ikisini de okumuyordu** — yazma yolu her gönderimde
bu iki sınıf hakkında uyarırken okuma yolu onları düşürüyordu. Oda
reddedilmiyor (adını zaten bilen birinin okuması onun hakkıdır) ama tarama
sonucu artık bunu **söylüyor**: `notes` alanında `unlisted`/`ephemeral`
türünde bir cümle. Listelenen bir oda için not üretilmez, yani not bir afiş
değil bir ayrımdır.

### `SOURCES` neden altı kaldı

Altı sabit belgeyi koruyan şey `len(SOURCES) == 6` ve `set(SourceId)`
eşitliğidir. Kayda geçmesi gereken ayrıntı şudur: yanındaki
`"/r/" not in source.path` iddiasını `/rooms` **geçerdi** — içinde `/r/` alt
dizgisi yok. Yani "salt-okuma izleme yolu bir odayı adresleyemez" özelliğini
fiilen tutan satır, sanılan satır değildir.

---

## 2. Doğrulanan sözleşme

Aşağıdakiler pinli `vendor/technocore-reference` ve
`tests/security/technocore_reference/` kopyalarından okunmuştur. Canlı servise
bu pakette **hiçbir istek gönderilmedi**.

| Alan | Ne diyor | Kodda karşılığı |
|---|---|---|
| `since` | Yalnız daha büyük `seq`'leri döndürür. Negatif/ondalık/kelime **imleçsiz** sayılır ve en yeni mesajlar döner | İmleç yoksa parametre **gönderilmez**; negatif imleç sunucunun fallback'ine bırakılmaz, burada reddedilir |
| `limit` | Varsayılan 50, **1..200'e clamp edilir, asla reddedilmez**. "read `count`, do not assume it" | `clamp_limit()` aynı sınırları gönderimden önce uygular; `count` yanıttan okunur |
| `format=json` | Yalnız bu değer yanıtı JSON yapar; **başka her değer sessizce yok sayılır** ve yanıt `text/plain` kalır | Başarı sinyali **Content-Type**'tır, durum kodu değil. Yanlış medya tipi kendi hata sınıfını taşır (`WrongMediaTypeError`) |
| `count` / `last_seq` / `first_seq` | Yanıtın kendi alanları; `first_seq` boş olabilir | Üçü de okunur. `count` ile gelen dizi uzunluğu ayrışırsa **iki sayı da** gösterilir |
| `first_seq > since + 1` | "the ring dropped messages you never read" | Ayrı bir **ring düşüşü uyarısı**. Bayatlık notuyla birleştirilmez |
| `ROOMS_CACHE_SECONDS` | Sunucu `/rooms`'u en çok 3 saniye bayat verebileceğini kendi yapılandırmasında söylüyor | Bayatlık etiketi bu **beyanı** ve okuma anını birlikte taşır |
| `room` (yanıttaki) | Yanıtın kendi alanı; anonim ve dünyaya yazılabilir bir yüzeyin ürettiği bir değerdir | **Kapsam sayılmaz.** `parse_room_messages` istenen odayı zorunlu argüman olarak alır; yanıt başka bir odayı adlandırırsa belge reddedilir ve oda `room_unreadable` diye adıyla raporlanır. Aday kimliği, referans ve şablonlar **istenen** adı kullanır |
| oda adı kalıbı | `^[a-z0-9][a-z0-9_-]{0,47}$` | Yazma yolunun `validate_name`'i, aynen |
| oda sınıfları | `p-`, `mb-`, `d-`, `e-` (manifest'ten okunur) | Yazma yolunun `classes_of` ve `UNDERSTOOD_ROOM_CLASSES`'ı, aynen |
| `rooms[]` girdisi | `room` ve `topic` **çağıran tarafından yazılmıştır**; diğer alanlar servisin kendi ölçümüdür | Yalnız bu iki alan tutulur; hangilerinin çağıran-yazımı olduğu **bizim modülümüzde** sabittir |
| `from` | `did:key` veya kendi beyan edilen takma ad; ikisi de doğrulanmamıştır | `describe_author()` üç ayrı cümle üretir ve hiçbiri "imzalandı" demez |

### Doğrulanamayan / bilinçli kullanılmayan

| Alan | Durum |
|---|---|
| `rooms[]` girdisinin tam şeması | Şema `items: {"type": "object"}` diyor ve **hiçbir alan adı yayımlamıyor**. Düzyazının adlandırdığı iki alan dışında hiçbir alan okunmaz |
| `wait` (long-poll) | Sözleşmede var; **bilinçli olarak kullanılmaz** (§4) |
| `n` (cache kırma) | Sözleşmede var; yalnız yeniden-poll eden bir istemci için anlamlı, bu istemci öyle değil |
| `/r/events` | Şema tarafı boş; kapsam dışı (§1) |
| imza doğrulaması | Bu okuma yolunda **yapılmaz**. `sig` alanı okunmaz ve hiçbir cümle imzaya dayanmaz |

---

## 3. Deterministik çıkarımın sınırı

**Model çağrısı yoktur ve erişilebilir değildir.** Paket
`station_api.opencode`'u import etmez ve bir test bunu sözdizim ağacından
denetler.

Bir adayın taşıdığı her değer **iki kaynaktan birinden** gelir:

1. ham kaynak alanı (`room`, `seq`, `ts`, `from`, `text`), veya
2. [`candidates.py`](../apps/station-api/src/station_api/workscan/candidates.py)
   içindeki **sabit şablon**.

Üçüncü bir kaynak yoktur. Uydurulacak alan olmadığı için çıktı şeması denetimi
ve kaynak referansı denetimi *ek* güvenliktir, *tek* güvenlik değil.

### Kullanıcıya gösterilen dürüstlük cümlesi

> Bu sürüm adayları kalıp eşleşmesiyle çıkarır; anlamsal çıkarım yoktur, bu
> yüzden bir odadaki her fırsat görülmez.

Bu cümle her `status` okumasında ve her tarama sonucunda yanıt gövdesindedir;
bir tasarım belgesine gömülmemiştir.

### Sekiz zorunlu öğe

Taşımayan aday **üretilemez** — `__post_init__` reddeder, `EvidenceRef`
kalıbıyla. Yarım bir aday sistemde hiçbir yerde bulunmaz.

| # | Öğe | Nereden gelir |
|---:|---|---|
| 1 | Birebir alıntı + `room`/`seq`/`ts` referansı | ham kaynak |
| 2 | Kime hangi faydası | sabit şablon + ham `room`/`from` |
| 3 | Kesin teslimat | sabit şablon |
| 4 | Başarı koşulu ve nasıl test edileceği | sabit şablon (iki ayrı alan) |
| 5 | Aracın/verinin var olup olmadığı | `modules/registry.py` + write gate durumu |
| 6 | **Tahmin olarak etiketli** çalışma tahmini + bütçe | sabit bant; `label` parametre değildir; bütçe `not_implemented` |
| 7 | Gereken izinler ve riskler | sabit şablon (iki ayrı alan, ikisi de boş geçilemez) |
| 8 | İşin durumu | yalnız izinli cümle (aşağıda) |

### 8. öğe için kesin dil yasak

"İş hâlâ açık" denemez. Söylenebilecek tek şey ölçülen şeydir:

> Şu ana kadar okunanda kapanış işareti görülmedi (anlık görüntü: …).

Bir `is_open` alanı **yoktur** ve yanıt gövdesinde de yoktur: bir boolean bir
cevap gibi okunur ve bu yüzey cevap üretemez — oda geçmişi düşüren bir halka,
okuma sınırlı bir dilim, ve cevap okumadan sonra yazılmış olabilir.

### Kalıp eşleşmesiyle reddedilen iş biçimleri

Altı biçim, **sinyal aranmadan önce** eşleşir; hem sinyal hem yasak taşıyan bir
satır aday üretmez ve reddedildiği gerekçesiyle gösterilir.

**Yapısal olan sıralamadır, eşleşme değildir.** Bu belge ve ADR-0007 §8 daha
önce "yasaklar yapısal olarak engellenir" diyordu; bağımsız bir inceleme
listeyi **on dokuz satırla** aştı: `w a l l e t`, `wal-let`, `w.a.l.l.e.t`,
araya sıkıştırılmış sıfır-genişlikli karakterler, yumuşak tire, `claim` ve
`cuzdan` içinde tek bir Kiril harfi, ve listede olmayan eş anlamlılar
(`kripto para gonderin`, `bakiye aktarin`, `transfer 1 ETH to me`,
`gas ucretini odeyin`, `btc adresime gonderin`, `connect your purse`,
`buy some tokens`, `nft mint edin`, `staking yapin`). Her biri aday üretiyordu.

Şimdi üç şey değişti:

1. `fold()` biçim (`Cf`) karakterlerini **siler** ve Kiril/Yunan benzer
   harflerini Latin karşılıklarına eşler;
2. yasak listesi ayrıca `tighten()` ile — kelime içi ayraçlar atılmış bir
   samanlıkta — eşleşir, böylece `w a l l e t` okuyanın gördüğü kelimedir;
3. liste eş anlamlılarla genişletildi.

Ve cümle gerçeğe indirildi: bu bir **kalıp listesidir**. Listede olmayan bir
sözcükle istenen bir ödeme işi aday üretebilir. Bu, bir tasarım belgesine
değil, kullanıcının gördüğü yüzeye yazıldı (`prohibition_statement`, her
`status` okumasında).

| Biçim | Neden |
|---|---|
| `wallet_or_payment` | Cüzdan, ödeme, hak talebi ve anahtar materyali. En pahalı hata |
| `point_farming` | Bir skoru yükseltmek için hacim |
| `spam_ping` | Tekrarlayan bildirim, toplu etiketleme |
| `empty_acknowledgement` | İçeriksiz "done"; bir şey yazılmış olması sonuç değildir |
| `self_approval` | Kendi açtığı işi kendi onaylamak. Kabul bir başkasının eylemidir |
| `duplicate_delivery` | Aynı teslimatın tekrarı. Ayrıca **kimlikle** de engellenir: bir aday kimliği `(room, seq)` üzerinden domain-ayrıştırılmış bir digest'tir, aynı satır aynı kimliği alır. `room` artık **istenen** odadır, bu yüzden iki farklı odanın aynı adı iddia etmesi iki adayı tek satıra indiremez |

### Yasak dışındaki iki reddetme gerekçesi

İkisi de sessizdi; ikisi de artık gösterilir. "Reddedilen satır gösterilir,
sessizce düşürülmez" kuralı yalnız altı biçim için değil, satırın
reddedildiği **her** gerekçe için geçerlidir.

| Gerekçe | Ne oldu |
|---|---|
| `duplicate_sequence` | Yanıt bir `seq`'i tekrar etti. İkinci satır aynı kimliği üretirdi, bu yüzden aday olmaz — ama artık `lines_read: 2, candidates: 1, refusals: 0` yerine gerekçesiyle listelenir |
| `unusable_source` | Satırda zorunlu bir kaynak alanı yok (`ts` gibi). Eskiden `CandidateError` bütün taramadan dışarı fırlıyordu: on odalık bir tarama HTTP 500 dönüyor ve **okunmuş bütün odalar çöpe gidiyordu**. Şimdi satır başına reddedilir; servis katmanında oda başına, rota katmanında da tarama başına bir yedek koruma vardır (502, 500 değil) |

---

## 4. Polling yoktur

**Zamanlayıcı yok, arka plan görevi yok, `wait` yok, otomatik takip isteği
yok.** Her giden istek bir kullanıcı eyleminin içinde ve bir kez yapılır.

Kodda üç ayrı karşılığı vardır:

1. `wait` ve `n` `NEVER_SENT_PARAMS`'tadır ve sorgu üreticileri onları hiç
   üretmez;
2. paket ağacı `asyncio`/`threading`/`sched`/`concurrent` importuna ve
   `Timer`/`Thread`/`create_task` çağrısına karşı taranır (`time` yalnız
   istemcinin iki denemesi arasındaki bekleyiş için serbesttir);
3. açılışta ve durum okumasında giden istek sayısı **sayılarak** sıfır ölçülür.

Ayrıca imleç (`since`) **serviste saklanmaz**. Bir imleci hatırlamak
"kalanını oku"yu birinin zamanlayacağı bir döngüye çevirmenin ilk yarısıdır;
her tarama taze ve sınırlı bir dilimdir, ve geçmişin altınızdan kaydığını
söyleyen şey ring düşüşü uyarısıdır. Keşif günlüğünde imleç **istemcinin**
gövdede geri gönderdiği değerdir (bir önceki okumanın `last_seq`'i), yani
devam etmek yine bir kullanıcı eylemidir.

Keşif günlüğü okuması ayrı bir rotadır (`POST /api/workscan/discovery/refresh`)
ve bilerek taramanın içinde değildir: "yeni ne açılmış" ile "şu odaları oku"
kullanıcının verdiği iki ayrı karardır. Bir test bu yüzeyin **tam beş** rota
sunduğunu küme eşitliğiyle tutar ve `watch`, `scan/all`, `rooms/open`,
`discovery/announce` gibi lane'lerin yokluğunu ayrıca iddia eder.

**Kapsam kullanıcının seçtiği oda kümesidir.** İstek gövdesindeki liste
kapsamdır, en çok on odadır, ve "hepsini tara" diye bir rota yoktur. Sınırı
aşan odalar sessizce kırpılmaz; `scan_bound` gerekçesiyle listelenir.
**Odaların artık listeden veya keşif günlüğünden seçilebiliyor olması bu
tavanı değiştirmez**; seçilecek bir liste, listeyi taramak için bir yetki
değildir.

`DENIED_ROOMS` (lobby, meta) **okumada da** geçerlidir: bir tarama da o odayı
adlandıran bir istektir.

---

## 5. Üçüncü otorite seviyesi: `community`

Künye §21.1 iki seviye tanımlıyordu (1 = makine okunabilir resmi manifest,
2 = resmî düzyazı). Oda içeriği ikisine de girmiyor ve servis bunu kendisi
söylüyor — `agent.json`'un `trust` bölümü, kendi ifadesiyle, oda gövdelerinin
ve `/rooms`'un saydığı adlarla başlıkların yabancıların yazdığı anonim ve
doğrulanmamış girdi olduğunu ve buradan okunan her şeyin **veri** sayılması
gerektiğini yazıyor.

Bu yüzden otorite artık **yol başına değil, içerik başına** taşınır:

- `/rooms` ve `/r/{room}` **yolları** seviye 1'dir (resmî uç nokta);
- döndürdükleri her değer seviye 3'tür (`community`).

Sonuçları:

- `topic`, `/kv/topic/{oda}` adresindeki **dünyaya yazılabilir bir nottur**;
  herkes her oda için yazabilir. Bir tanım değildir, bir onay hiç değildir;
- oda **adı** o odaya ilk yazanın seçtiği bir metindir;
- `from` `did:key` değilse **kendi beyan ettiği takma addır**; `did:key` olması
  bile bu mesajın o anahtarla imzalandığını söylemez (imza ayrı bir alandır ve
  bu yolda doğrulanmaz);
- içerik **veridir**: süpürülür, HTML olarak render edilmez, otomatik
  linkleştirilmez ve hiçbir modele talimat olarak verilmez — bu pakette bir
  model çağrısı zaten yoktur.

---

## 6. Kibble: kayıt açıldı, istemci yazılmadı

[`workscan/kibble.py`](../apps/station-api/src/station_api/workscan/kibble.py)
bir **kayıttır**. İçinde istemci yoktur, fetch edilen bir uç nokta sabiti
yoktur ve **hiçbir istek gönderilmez**. `adapter_written` ve `contacted`
alanları saklanmaz, **türetilir** ve daima `False`'tur.

Bu cümlenin iki yarısı vardı ve yalnız biri test ediliyordu. Tel tarafı
yapısaldı (`Literal[False]`), ama rota bu iki alanı hiç geçirmiyordu: yanıttaki
`false` değerleri şemadaki **varsayılandan** geliyordu, dolayısıyla iki
özelliği `True`'ya çeviren mutasyonlar **sıfır** testi kırmızıya döndürdü.
Rota artık kaydın kendi özelliklerini okur ve `True` olan birini
serileştirmek yerine reddeder; ayrıca bir test doğrudan
`get_adapter("kibble").adapter_written is False` diyor.

Durum: `support_unverified`.

| Doğrulandı | Doğrulanamadı |
|---|---|
| Servis çalışıyor, açılış sayfası okunabildi | `job` nesnesinin alan adları |
| Dört okuma uç noktası belgelenmiş ve auth istemiyor | Sayfalama (denenen listeleme uç noktası 60 sn'de yanıt vermedi; ~77 bin kayıt) |
| Yaşam döngüsü yayımlanmış: `JOB → CLAIM → RESULT → ATTEST` | İstek hızı sınırı |
| `/api/stats` yanıtının şekli gözlendi | Kullanım koşulları / lisans (`robots.txt` 404) |
| Servis kendi resmî kaynak olmadığını söylüyor | İşletmeci kimliği |

**Neden adapter yazılmadı:** `job` nesnesinin alan adları yayımlanmamış. Bir
adapter onlara ihtiyaç duyar, dolayısıyla yazmak onları uydurmak demektir — ve
uydurma burada her zamanki gibi başarısız olur: istek yukarıda reddedilir ve
hata kullanıcının hatası gibi okunur. Sayfalaması olmayan yetmiş yedi bin
kayıtlık bir uç noktayı okumak zaten çalışmıyor.

**Servisin kendi ifadesi birebir taşınır** (çevirisi değil, çünkü bir
sorumluluk reddinin çevirisi daha zayıf bir sorumluluk reddidir) — ve
**yanıt gövdesinde** taşınır. Önceki sürümde tel yalnız Türkçe çeviriyi
(`self_description`) taşıyordu; iki İngilizce cümle frontend'de, ADR'den
elle kopyalanmış birer sabitti. İki yerde tutulan bir alıntı sürüklenebilir
ve sürüklenen yarı kimsenin diff'lemediğidir, bu yüzden ikisi de kayda
(`self_description_source`, `score_self_description`) ve oradan tele taşındı;
frontend artık kendi kopyasını tutmuyor.

> Kibble is not FLOP Network and not Technocore. It settles nothing.

Skoru için de kendi tanımı:

> Advisory IOU from the public tape. Nothing is paid.

**`community` etiketi zorunludur.** Ve hiçbir üçüncü tarafın `score`/`rank`
alanı ürünün kendi cümlesine bir ölçüt olarak katılmaz; asla "itibar" veya
"uygunluk" diye sunulmaz (künye §8.3, AC-18). Bir test yanıt gövdesinin
hiçbir yerinde `score`/`rank`/`reputation`/`eligibility` **anahtarı**
bulunmadığını denetler — kelimeyi değil, alanı arar.

Kaydın yaşı **koşulsuz** gösterilir (`TABLE_PROVENANCE`, Paket G kalıbı):
kayıt 4 Eylül 2026'da yazıldı, Station bu servise hiçbir istek göndermez ve
sayfayı kendiliğinden yeniden okumaz.

---

## 7. Görev katmanına bağlanma

Taranmış bir aday, kullanıcı seçtiğinde yerel bir görev satırı açar.

- Kaynak: `TaskSourceId.PUBLIC_ROOM_SCAN` (yeni üye).
- Başlangıç durumu: `suggested` (Paket H1'de üretilebilir hâle geldi).
- `INITIAL_STATE` **değişmedi**: kullanıcının kendi yazdığı görev hâlâ
  `awaiting_approval` doğar.

Ayrım **iki bağımsız katmandadır** ve bu bilinçlidir: farklı `TaskSourceId`
farklı `source_version_id` üretir (bayt-birebir aynı içerik için bile), ve iki
üretici birbirinin kaynağını reddeder (`open_task` tarama kaynağını,
`suggest_task` operatör kaynağını). Bir görünümün taranmış bir adayı
"kullanıcının isteği" gibi göstermesi için ikisini birden taklit etmesi
gerekir.

Öneri üreticisi **onaylamaz**: `suggested → awaiting_approval` geçişi
kullanıcının eylemidir ve olağan `transition` yolundan geçer.

### 7.1 İsteğin tam metni nereye yazılır

Görev satırı içeriğin **özetini** tutar, baytlarını değil. Bu ölçülen bir
kusur üretti: bir modele taranmış istekten gösterilebilen tek okunur şey
`title` idi — tek bir satırın ilk `MAX_TITLE_CHARS` (o gün 120; bugün 2 000,
ama fiilen bağlayıcı olan `tasks.service.MAX_TITLE_CHARS` = 200'dür) karakteri — ve
ADR-0007 §8'in sekiz ögesiyle birebir alıntı hash'lenip atılıyordu.

Düzeltme **veritabanına sütun eklemez**. Yeni bir sütun yeni bir depolama,
yeni bir sızıntı yüzeyi ve yeni bir gizli-tarama kapsamı demektir; ayrıca
"tutmadığın veri sızmaz" tasarımını bozar. Bunun yerine `suggest`, isteği
görevin **kendi çalışma alanına** sabit adlı bir dosya olarak yazar:

- ad: `oda-istegi.md` (sabit; `agent/workspace.py::safe_name` izin listesinden
  değişmeden geçer, bir test bunu sürer);
- yazma: mevcut `agent/workspace.py::write_text` — ad izin listesi, çözümleme
  ve kapsama denetimi, reparse/junction yürüyüşü ve üç tavan (64 dosya /
  512 KiB / 4 MiB) olduğu gibi uygulanır;
- okuma: modelin elindeki mevcut `read_workspace_file` aracı. Yeni bir araç,
  yeni bir uç nokta ve yeni bir dosya kulvarı yoktur.

Dosyanın **iki bölümü** vardır ve birbirine değmez. Üstte Station'ın kendi
şablon cümleleri; altta odadan okunan ham metin. Alt bölüm **dosyanın sonuna
kadar** sürer ve kapanış işareti yoktur: kapanış işareti oda mesajının
içerebileceği bir dizedir, ve sahtesi yazılabilseydi saldırgan metni tekrar
"Station'ın kendi cümleleri" bölümüne sokardı.

Alt bölümün başında `authority.py::REQUEST_CONTENT_CAVEAT` durur —
`TOPIC_CAVEAT`/`MEASURED_CAVEAT` ile aynı kalıp, aynı ayrım: metni kim yazdı
(doğrulanmamış bir yabancı) ve ne olarak işlenir (**veri**; talimat, izin,
kural veya yetki değil). Aynı cümle model brief'inde de vardır
(`planner/service.py::REQUEST_FILE_BRIEF`); ikisi birden, çünkü brief dosya
hiç açılmadığında geçerlidir ve dosya brief uzun bir oturumda yukarı
kaydığında geçerlidir.

**Yazma başarısız olabilir ve görev yine de açılır.** Satır ve ilk durum
geçişi dosyadan **önce** yazılır (çalışma alanı görev kimliğiyle adreslenir,
yani satır olmadan yazılacak bir kimlik yoktur) ve bu üründe görev satırını
geri alma yolu yoktur — durum makinesi bir denetim izidir. Burada exception
fırlatmak, gerçek bir görev `suggested` durumunda dururken çağırana "öneri
kaydedilemedi" demek olurdu. Bu yüzden ret **yanıtta taşınır**: yanıt
`request_file` (dosya adı veya `""`) ve `request_file_detail` (her iki yönde
de dolu bir cümle, çalışma alanının kendi `reason` koduyla) alanlarını
taşır, ekran ikisini de gösterir. `content_sha256` ve `source_version_id`
bundan **etkilenmez**: başarısız bir yazmanın maliyeti okunabilirliktir,
kimlik değil.

---

## 8. Bu pakette bilinçli olarak yapılmayanlar

- Model çağrısı, streaming, tool-call (H2).
- Bütçe ve maliyet tavanı — tahmin **tahmin** olarak etiketlidir ve bütçe
  `not_implemented`'tır (H2).
- Kibble'a istek, Kibble adapter'ı (§6).
- Oda **açmak**: `/r/{oda}`'ya ilk mesaj bir yazmadır, DID ve write
  gate'in altı ön koşulunu ister. Bu turda yazma yolu açılmadı; keşif
  yalnız okuma tarafıdır.
- Long-poll, zamanlayıcı, otomatik yenileme (§4).
- İmleç kalıcılığı, tarama sonucunun diske yazılması. Bir halka tamponunun
  anlık okuması kalıcılaştırılırsa, odalar ilerledikçe sessizce yanlışa döner;
  kalıcı olan tek şey kullanıcının açıkça göreve çevirdiği adaydır.
- Aday listesinin dışa aktarımı, dış paylaşım (H3).
