# İş Tara — kamuya açık oda taraması (Paket H1)

Kapsam kararları: [`decisions/0007-paket-h1-kapsam-kararlari-2026-09-04.md`](decisions/0007-paket-h1-kapsam-kararlari-2026-09-04.md).
Test edilebilir değişmezler: [`security-invariants.md`](security-invariants.md) §9i (SI-271…SI-281).

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
method, header veya TLS ayarı kabul etmez; `RoomScanTarget` yalnız yazma
yolunun oda politikasından geçerek üretilebilir.

### `/r/events` neden kapsam dışı

Pinli `openapi.json`, `/r/events` girdisini `parameters: null` ile yayımlıyor;
`since`/`format`/`wait`'in geçerli olduğunu yalnız **düzyazı açıklaması**
söylüyor. Paket B'nin ilkesi "kritik alan şemadan okunur, düzyazıdan değil"di
ve hiç parametresi olmayan bir şemada bu ilke uygulanamaz. `/rooms` tam tipli
şemasıyla yeterli bir keşif yüzeyidir, dolayısıyla keşif lane'i açılmadı.

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

### Yapısal olarak engellenen iş biçimleri

Altı biçim, **sinyal aranmadan önce** eşleşir; hem sinyal hem yasak taşıyan bir
satır aday üretmez ve reddedildiği gerekçesiyle gösterilir.

| Biçim | Neden |
|---|---|
| `wallet_or_payment` | Cüzdan, ödeme, hak talebi ve anahtar materyali. En pahalı hata |
| `point_farming` | Bir skoru yükseltmek için hacim |
| `spam_ping` | Tekrarlayan bildirim, toplu etiketleme |
| `empty_acknowledgement` | İçeriksiz "done"; bir şey yazılmış olması sonuç değildir |
| `self_approval` | Kendi açtığı işi kendi onaylamak. Kabul bir başkasının eylemidir |
| `duplicate_delivery` | Aynı teslimatın tekrarı. Ayrıca **kimlikle** de engellenir: bir aday kimliği `(room, seq)` üzerinden domain-ayrıştırılmış bir digest'tir, aynı satır aynı kimliği alır |

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

Ayrıca imleç (`since`) **taramalar arasında saklanmaz**. Bir imleci hatırlamak
"kalanını oku"yu birinin zamanlayacağı bir döngüye çevirmenin ilk yarısıdır;
her tarama taze ve sınırlı bir dilimdir, ve geçmişin altınızdan kaydığını
söyleyen şey ring düşüşü uyarısıdır.

**Kapsam kullanıcının seçtiği oda kümesidir.** İstek gövdesindeki liste
kapsamdır, en çok on odadır, ve "hepsini tara" diye bir rota yoktur. Sınırı
aşan odalar sessizce kırpılmaz; `scan_bound` gerekçesiyle listelenir.

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
sorumluluk reddinin çevirisi daha zayıf bir sorumluluk reddidir):

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

---

## 8. Bu pakette bilinçli olarak yapılmayanlar

- Model çağrısı, streaming, tool-call (H2).
- Bütçe ve maliyet tavanı — tahmin **tahmin** olarak etiketlidir ve bütçe
  `not_implemented`'tır (H2).
- Kibble'a istek, Kibble adapter'ı (§6).
- `/r/events` keşif lane'i (§1).
- Long-poll, zamanlayıcı, otomatik yenileme (§4).
- İmleç kalıcılığı, tarama sonucunun diske yazılması. Bir halka tamponunun
  anlık okuması kalıcılaştırılırsa, odalar ilerledikçe sessizce yanlışa döner;
  kalıcı olan tek şey kullanıcının açıkça göreve çevirdiği adaydır.
- Aday listesinin dışa aktarımı, dış paylaşım (H3).
