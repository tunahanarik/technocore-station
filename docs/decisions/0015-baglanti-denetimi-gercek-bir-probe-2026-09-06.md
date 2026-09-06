# ADR-0015 — "Bağlantıyı denetle" gerçek bir probe olur (6 Eylül 2026)

Durum: **kabul edildi** · Bağlam: kullanıcının gerçek kullanımda gördüğü kusur
(anahtar kaydedildi, düğmeye basıldı, rozet hiç değişmedi) · **ADR-0005 §4'ün
sonucunu değiştirir, gerekçesini değiştirmez**; ADR-0012'nin ölçtüğü sözleşmeye
ve ADR-0013'ün koyduğu tavana dayanır.

Bu ADR hiçbir güvenlik değişmezini gevşetmez. `OUTBOUND_CLIENT_MODULES`
**beşte kalır**, yeni bir zamanlayıcı yoktur, `0.0.0.0` bind yoktur, CORS
yoktur, TLS doğrulaması kapatılamaz, gerçek Technocore write yoktur.

## 0. Kusur: kontrol ile karar birbirini yalanlıyordu

`opencode/service.py::check_connection` **sabit** bir hüküm döndürüyordu ve
docstring'i bunu açıkça söylüyordu:

> *Deliberately does not call anything. A probe that cost money would need the
> user's explicit request; a probe that did not cost money would not prove
> anything.*

Gerekçe doğruydu. **Sonucu yanlıştı:** düğme *zaten* kullanıcının açık
isteğidir, ve arkasında hiçbir şey yoktu. Ön yüzde
`OpenCodeConnectionPanel.tsx::load("check")`, `load("read")` ile **aynı işi**
yapıyordu — `GET /api/opencode/status`. `as` argümanı yalnız meşgul etiketini
ve hata başlığını değiştiriyordu. Bir check ucu yoktu; rotalar `/status`,
`/credential`, `/credential/forget`, `/catalog/refresh`, `/model` idi.

Yani: kaydedilmiş bir anahtarla hüküm **hiçbir koşulda** ilerleyemezdi. Bu, bu
deponun bütün tur boyunca kovaladığı kusurun ürün yüzeyindeki hâlidir — bir şey
yapıyormuş gibi duran, yapmayan bir kontrol.

O gerekçe ayrıca **ADR-0012'den öncedir**. ADR-0012 bağlantıyı canlı ölçtü:
`Authorization: Bearer` ölçülü uçta kabul ediliyor, protokol OpenAI
`chat/completions` şeklinde, ve ölçüm `cost: "0"` döndürdü.

## 1. Probe ne olacak: kimliksiz başarabilen bir istek hiçbir şey kanıtlamaz

**Katalog probe olamaz ve bu ölçülmüş bir olgudur, tercih değil.**
`client.py::fetch_catalog`, `_with_bounded_retry(..., api_key=None)` çağırır —
kimlik bilgisi **eklemez** — ve uç kimliksiz de `200` döner. Kimlik bilgisi
olmadan da başarılı olan bir istek, kimlik bilgisi hakkında hiçbir şey
söylemez. Registry'deki diğer serbest adresler için de aynısı geçerlidir.

Geriye tek bir aday kalır: sağlayıcının **kimlik bilgisi olmadan reddedeceği**
istek. Bu sağlayıcıda o, ölçülü `chat/completions` ucudur.

**Karar:** probe, ADR-0012'nin ölçtüğü gövde biçiminde **tek bir
`POST /zen/go/v1/chat/completions`** isteğidir:

| Alan | Değer | Neden |
|---|---|---|
| `model` | kullanıcının **seçtiği** model | Station model seçmez (ADR-0005 §11). Seçim yoksa reddedilir. |
| `messages` | tek `user` turu, `"ping"` | Dört karakter. Talimat yok, kullanıcı verisi yok, makine hakkında bir şey yok. |
| `max_tokens` | `16` | Üretimi tavanlar. `DEFAULT_MAX_OUTPUT_TOKENS` (131072) **bilerek değil**: o bir kesilme koruması, bu bir maliyet tavanı. |
| `tools` | **yok** | Araç registry'si bir *planın* modele sunduğu şeydir. Bir bağlantı denetiminin bütün yetenek yüzeyini sunmaya işi yoktur. |
| `stream` | `false` | Non-streaming davranış istenerek istenir, varsayılana güvenilmez. |

### Maliyeti — açıkça

**Bir model çağrısı.** ADR-0012'nin ölçtüğü tur bundan kesinlikle **büyüktü**
(bütün araç registry'si + gerçek bir brief: 184 giriş, 46 çıkış token'ı) ve
`cost: "0"` bildirdi. Probe o promptun küçük bir kesrini gönderir ve üretimi on
altı token'da tavanlar. **"Ucuz", "bedava" değildir**; sağlayıcının yayımlanmış
pencere limitleri geçerlidir ve bu yüzden çağrı sayılır (§3).

### Hüküm neden metinden değil, durum satırından okunur

`adapters.parse_response`, bir `200`'ü başarı saymadan önce okunabilir
asistan metni ister — ve hizmet ettiği şerit için bu doğrudur. Burada
yanlıştır. Probe **tek bir soru** sorar: *bu kimlik bilgisi kabul edildi mi.*
O sorunun cevabı durum satırıyla gelmiştir. On altı token'ın hepsini
muhakemeye harcayan bir model `200` + `finish_reason: "length"` + boş `content`
döndürür (ADR-0012 §0'ın ölçtüğü davranış), ve bunu "doğrulanmadı" diye okumak
kanıtlanmış bir anahtarı model kısa konuştu diye kanıtsız saymaktır.

Bu yüzden `probe.py` durum kodunu okur, artı durum kodunun yalan söylediği
bilinen tek şeyi: `error` üyesi taşıyan bir `200` (`adapters._carries_error`'ın
zaten tanıdığı hâl).

## 2. Yalnız açık basışla

Probe **hiçbir yerden** kendiliğinden çağrılamaz:

* `describe()` çağırmaz — dolayısıyla `GET /api/opencode/status` çağırmaz, ve
  o rota bir sayfa açılışının vurduğu rotadır;
* `store_credential` çağırmaz — kaydetmek denetlemek değildir;
* `refresh_catalog` çağırmaz;
* zamanlayıcı yoktur, poll yoktur, ön yüzde `useEffect` içinde değildir.

Bunu tutan **testler**, yorum değil: `test_opencode_probe.py::
test_reading_the_status_sends_nothing`, `::test_storing_a_key_does_not_probe_it`,
`::test_a_catalog_refresh_is_not_a_probe`, `test_opencode_http.py::
test_the_status_read_never_reaches_the_provider` — hepsi *her istekte patlayan*
bir transport sürer ve sayacı ayrıca okur; ve
`OpenCodeConnectionPanel.test.tsx::never calls the metered check on mount`.

Rota `POST /api/opencode/check`'tir, `GET` değil. Üç sebep aynı yeri gösterir:
para harcar, yani gezinme değil basış olmalıdır; saklanan durumu değiştirir,
yani CSRF/Origin/Sec-Fetch-Site middleware'inin arkasına aittir; ve bir `GET`
tarayıcının, prefetcher'ın ve yeniden yüklemenin **kendiliğinden tekrarladığı**
şeydir.

## 3. Tavan: sayılmayan bir model çağrısı, tavanın etrafından dolaşmaktır

ADR-0013 model çağrısı sayısını bu ürünün **sahip olduğu tek harcama
kontrolü** yaptı. Sayılmayan ölçülü bir çağrı, o tavanın yanındaki açık
kapıdır — `forget` düğmesinin kusurunun başka bir düğmedeki hâli.

**Karar:** probe **kimlik bilgisi başına** sayılır ve tavanlanır.

Yeni tablo: `opencode_probe_ledger` (migration `0012`, yalnız ekleme).

```
fingerprint     PK — opencode_credential_metadata'nın da tuttuğu parmak izi
probes_used     tamsayı, yalnız artar
first_probe_at  ilk sayılan denetimin anı
last_probe_at   son denetimin anı
state           verified | provider_refused | probe_failed
http_status     durum satırı, yanıt gelmediyse 0
detail          sınırlı, redakte, muhakemesi ayıklanmış alıntı
```

Tavan: `agent/budget.py::MAX_CONNECTION_PROBES = 8`.

### Neden `task_id` değil, parmak izi

ADR-0013'ün defteri `task_record.id`'ye FK'lidir ve bir bağlantı denetiminin
görevi yoktur. Üç aday tartıldı:

| Aday | Neden değil |
|---|---|
| `model_call_ledger`'a satır | `task_id` birincil anahtardır ve `task_record`'a FK'lidir. Probe'un görevi yoktur; olmayan bir görev uydurmak deftere yalan yazmaktır. |
| `opencode_credential_metadata`'ya sütun | O satır anahtar unutulduğunda ve **değiştirildiğinde** silinir (`_withdraw_credential_row`). Sayaç onunla gitseydi tavan iki basışla geri gelirdi: ADR-0013'ün adını koyduğu `forget` kusuru, bu özellikte yeniden. |
| Kurulum başına tek sayaç | Yeni bir anahtar hiç sorulmamış bir sorudur ve kendi bütçesini hak eder. Kurulum başına bir sayaç, bir anahtarın harcamasını başka bir anahtara yazardı. |

Parmak izi, `forget` + aynı anahtarı yeniden kaydet dizisini **aynı satıra**
düşürür (`::test_forgetting_and_re_saving_the_same_key_does_not_hand_back_the_ceiling`),
ve yeniden başlatma da hiçbir şey sıfırlamaz
(`::test_the_ceiling_survives_a_restart_of_the_process`).

### Neden tavan `budget.py`'de, probe'un yanında değil

ADR-0013 §2 bu soruyu bir kez cevapladı: `budget.py` **sınırın kendisidir**.
Sınırı sınırladığı şeyin yanına yazmak, limitlerin aranacağı ikinci yeri
açmaktır. `budget.py` yalnız standart kütüphaneyi import eder, bu yüzden
`opencode.service`'in ona bağlanması ne döngü ne yetenek getirir. Bunun bedeli
görünürdür: `test_task_evidence.py::
test_the_ceiling_is_named_by_exactly_the_modules_written_down_here` tavanı
**import eden modülleri sayıyla** sabitler, ve bu ADR o listeye dördüncü satırı
gerekçesiyle ekler — muhafız tam da bunun için yazılmıştı.

Birim yenilenmedi: `BUDGET_UNITS` zaten `model_call_count` diyor. ADR-0008 §4'ün
token ve para birimi reddi yerinde durur.

### Kaybedilen yanıt neden sayılır (ADR-0013 §3.4'ten kasıtlı fark)

ADR-0013 planlama turunu ancak sağlayıcı yanıtı ayrıştırıldıktan sonra sayar ve
bu, bir kişinin oturumu izlediği bir şerit için doğrudur. Burada tavan, bir
düğme ile ölçülü uç arasındaki **tek** şeydir, ve `OpenCodeLostResponseError`
tam olarak *bu istek zaten ücretlenmiş olabilir* demektir. Belki-ücretlenmiş bir
çağrıyı geri veren tavan, içinde bir yeniden deneme döngüsü olan tavandır.
İstemciye ulaşan her deneme sayılır.

### Bedeli — açıkça (ADR-0013 §3'ün kuralı)

1. **Sekiz denetimi biten bir anahtarın hakkı geri gelmez.** Sıfırlama rotası,
   metodu veya aracı **yoktur** ve bilerek yoktur; bir sıfırlama `forget`'in
   başka bir adla dönüşüdür. Kullanıcının yolu **başka bir anahtar**dır — ki bu
   ona anahtarın kendisine mal olur, bir düğmenin olmayacağı şekilde.
2. **Bir şema değişikliği ve bir migration.** Yalnız ekleme; backfill yoktur ve
   dürüst olmazdı: `0012`'den önce hiçbir kurulum probe çalıştırmadı, yani her
   kimlik bilgisinin gerçek sayısı sıfırdır — "satır yok"un zaten dediği şey.
3. **Satır kimlik bilgisinden uzun yaşar.** Bu, tabloda anahtarını unuttuğunuz
   bir kimlik bilgisinin parmak izinin durması demektir. Parmak izi anahtarı
   adlandırır, açığa çıkarmaz (SI-242), ve o satır zaten `forget`'in
   silemeyeceği tek şeydir — bütün mesele budur.

## 4. Hüküm sözlüğü: üç yeni durum, üç ayrı cümle

`VerificationState` artık beş değer taşır ve hiçbiri diğerine katlanmaz:

| Durum | Ne zaman | Rozet |
|---|---|---|
| `not_configured` | anahtar yok | `inactive` |
| `key_saved_unverified` | anahtar var, **kimse sormadı** | `pending` |
| `verified` | ölçülü uç `200` döndü | `ok` |
| `provider_refused` | sağlayıcı baktı ve reddetti (401/403) | `problem` |
| `probe_failed` | yanıt gelmedi ya da gelen yanıt bir şey söylemiyor | `problem` |

**Üçüncüsü neden `unreachable` değil.** Bir 429 veya bir 500, açıkça
ulaşılmış bir sunucudan gelen cevaptır; onu "ulaşılamadı" diye adlandırmak
ölçülmemiş bir ağ iddiasıdır. Kovanın tuttuğu şey "bilmiyoruz"dur ve adı bunu
söyler. Kişinin ihtiyaç duyduğu ayrımı `detail` taşır: sağlayıcının kendi
cümlesi.

`never_checked` **kaldırıldı**. Hiçbir kod yolu onu üretmiyordu, ve o enum'ın
kendi docstring'i tam olarak böyle bir değere karşı uyarıyordu.

**Yeşil rozet artık var ve tek bir üreticisi var.** ADR-0005 §4'ün "tek yeşil
rozet" korkusu bir *azaltma* korkusuydu: kazanılmamış bir onay. Kazanılmış
olanı göstermemek de aynı ailedendir, ters yönde.

## 5. Gerekçe listesi: bayat cümle taze hükmün yanında durmaz

Gerekçeler duruma göre kurulur, paylaşılmaz:

* `_NOT_VERIFIABLE_REASON` ("Anahtar dogrulanmadi…") — probe başarınca
  **düşürülür**. Yeşil rozetin altında durması, bu turun düzelttiği kusurun
  aynı paragrafta tekrarı olurdu.
* `_NO_PROBE_REASON` — **silindi**. "…ve henuz uygulanmamistir" diyordu; bu
  düğmenin kendi itirafıydı, kimsenin açmadığı bir listeye dosyalanmış. Yerine
  `_PROBE_ON_REQUEST_REASON` geldi: neyin tetiklediğini ve neye mal olduğunu
  söyler.
* `AUTH_HEADER_CAVEAT` — **her durumda kalır**, `verified` dahil. Bugün ne
  diyorsa hâlâ doğrudur: başlık çalışıyor (ADR-0012 ölçtü) **ve** resmî belge
  onu hâlâ yayımlamıyor, yani sağlayıcı onu bir sözleşmeye dayanmadan
  değiştirebilir. Bu, hükmün neden daha güçlü olmadığının gerçek bir
  sebebidir — listenin işi tam olarak budur.
* `_VERIFIED_SCOPE_REASON` — yeni. Doğrulamanın **tek bir çağrıya** ve
  **kimlik doğrulamasına** ait olduğunu söyler: sonraki çağrıları, kotayı veya
  başka bir modeli kapsamaz.
* Tavan dolduğunda listeye sayılarla birlikte bir cümle eklenir (ADR-0013 §4:
  nerede durduğunu söylemeyen tavan cümlesi tartışılan cümledir).

Bunu sabitleyen: `::test_a_verified_verdict_drops_the_sentences_the_probe_made_false`
ve `::test_no_reason_anywhere_still_says_the_probe_is_unimplemented`.

## 6. Kimlik bilgisi dışarı çıkmaz

Probe, anahtarı sağlayıcıya **bilerek** gönderen tek işlemdir. Bu yüzden
kanarya, bir upstream'in koyacağı yere ekilir — kendisini taşıyan isteğin hata
gövdesine — ve sonra bu özelliğin yazdığı her yerde aranır: kişinin okuduğu
hüküm, yanındaki her gerekçe, saklanan defter satırı ve veritabanı dosyasının
baytları (`::test_a_provider_that_echoes_the_credential_leaks_it_nowhere`).

Mekanizma yeni değildir ve olmamalıdır: `client.py::_excerpt`, alıntıyı
kimlik bilgisi redaksiyon penceresinin **içinde** hesaplar ve
`DISCARDED_MESSAGE_FIELDS`'i aynı fonksiyonda uygular. Probe o yolu kullanır;
test onun bu yolu da kapsadığını **ölçer** ve `<redacted>`'ın gerçekten
göründüğünü ister — hiçbir şey göstermeyen bir tanı, birinin sildiği tanıdır.

## 7. Muhafızlar

| Test | Ne sabitler |
|---|---|
| `test_opencode_probe.py::test_a_saved_key_can_reach_a_verified_verdict_when_the_provider_accepts_it` | Kusurun kendisi: kaydedilmiş anahtar + kabul eden sağlayıcı → `verified` |
| `::test_the_verdict_survives_a_status_read_and_carries_its_own_date` | Hüküm kalıcıdır; sonraki okuma onu unutmaz |
| `::test_reading_the_status_sends_nothing`, `::test_storing_a_key_does_not_probe_it`, `::test_a_catalog_refresh_is_not_a_probe` | Yalnız açık basış — sayan taraf **transport recorder** |
| `::test_the_probe_request_carries_the_credential_and_no_tool_registry` | Telde ne var: ölçülen biçim, araç registry'si yok |
| `::test_a_rejected_credential_is_its_own_verdict`, `::test_a_forbidden_model_is_reported_as_the_provider_stated_it`, `::test_an_answer_that_settles_nothing_is_neither_verified_nor_refused` | Üç sonuç, üç ayrı hüküm |
| `::test_a_failed_probe_replaces_a_verified_verdict_rather_than_leaving_it` | Bayat rozet bırakılmaz |
| `::test_the_ceiling_stops_the_button_and_says_where_you_stand` | Tavandan sonra hiçbir istek çıkmaz |
| `::test_forgetting_and_re_saving_the_same_key_does_not_hand_back_the_ceiling`, `::test_the_ceiling_survives_a_restart_of_the_process` | İki sıfırlama kapısı da kapalı |
| `::test_nothing_lowers_the_connection_probe_counter`, `::test_the_probe_ledger_row_is_never_deleted_and_reaches_only_two_modules` | Sözdizimi ağacı: tek yazıcı, ve satırı silen yok |
| `::test_migration_0012_added_one_table_and_touched_nothing_else` | Tablonun **şekli**: parmak izi PK, FK yok |
| `test_model_lane_claims.py` iki yeni kalıp | Yanlış cümleler geri gelemez |
| `OpenCodeConnectionPanel.test.tsx::sends the check to its own endpoint and shows what came back` | Ön yüz gerçekten probe rotasına basar |

**Yerine geçtiği test kaydedilir.** `::produces no verified verdict and no
green badge from a check` beş paket boyunca yeşildi ve **kırmızıya
dönemezdi**: stub her isteğe aynı belgeyi veriyordu, panelin denetimi zaten
mount'ta yapılmış `GET /status`'u çağırıyordu, ve iddia hükmün *hareket
etmediğiydi*. Konusu "hiçbir şey olmadı" olan bir test, kontrol bağlı da olsa
yok da olsa yeşildir. `TasksPanel.test.tsx`'in tavan cümlesini yerinde tutması
(ADR-0013 §4) ile aynı şekil.

## 8. Değişmeyenler

`OUTBOUND_CLIENT_MODULES` **beştedir**; probe mevcut `opencode/client.py`'yi
kullanır. Keyfi kod/kabuk yürütmesi kapalıdır (ADR-0008 §1). Model plan
**önerir**, çalıştırmaz. Hiçbir otomatik test gerçek sağlayıcıya istek yapmaz;
hepsi mock transport sürer. Anahtar koda, teste, belgeye, loga veya PR'a
yazılmaz. Token ve para birimi hâlâ tavan değildir (ADR-0012 §3).
