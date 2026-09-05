# Model plan yolu ve makinece denetlenen kabul koşulları (Paket H4)

Bu belge Paket H4'ün ne yaptığını, neyi **yapmadığını** ve her ikisinin de
neden böyle olduğunu kaydeder. Bağlayıcı karar
[`decisions/0012-model-yolu-sozlesme-dogrulamasi-2026-09-06.md`](decisions/0012-model-yolu-sozlesme-dogrulamasi-2026-09-06.md)
dosyasındadır; burada onun uygulanmış hâli anlatılır.

Tek cümlelik özet: **model bir plan önerir, bir kişi onaylar, deterministik
koşucu çalıştırır; sonra plan kendi kabul koşullarına göre ölçülür ve görev
gerçekten bitebilir.**

---

## 0. Neden bu bir kural gevşemesi değil

Üç paket boyunca iki cümle doğruydu ve artık biri doğru değil:

1. *"Tool-call tel formatı yayımlanmamıştır."* — **Artık geçerli değil.**
   ADR-0012 sözleşmeyi kullanıcının kendi anahtarıyla ölçtü. Kapalı olan şey
   bir yetenek değil, **doğrulanmamış bir varsayıma dayanarak yetenek açma**
   hakkıydı; koşul karşılandı.
2. *"Keyfi kod/kabuk yürütmesi kapalıdır."* — **Hâlâ geçerli.** H4 bunu
   açmaz. `station_api/planner` ağacında `subprocess`, `exec`, `eval`,
   `os.system` yoktur ve `test_planner_boundary.py` bunu sözdizim ağacından
   okur — `test_agent_boundary.py`'nin agent ağacında okuduğu gibi.

İkisini karıştırmamak önemlidir: ölçülen bir sözleşmeye dayanarak bir yol
açmak ile ölçülemeyen bir izolasyona güvenmek aynı şey değildir.

---

## 1. Model neyi görür, neyi görmez

Modele giden istek üç şeyden oluşur ve hiçbiri isteğe bağlı değildir:

| Parça | Kaynak | Not |
|---|---|---|
| sistem mesajı | `planner/service.py::SYSTEM_PROMPT` sabiti | istek gövdesinden değiştirilemez |
| görev özeti | görevin **kayıtlı** alanları + çalışma alanı envanteri | onaylı içeriğin **baytları gitmez**, yalnız özeti |
| araç listesi | `agent/tools.py::TOOLS`'un **tamamı** | alt küme sunulmaz |

`tool_choice` **`auto`**'dur. Zorlanmış bir çağrı modelin seçmediği bir
çağrıdır; "modelin önerdiği" cümlesinin doğru kalması için zorlama yoktur.

Modele **gitmeyenler**: çalışma alanı dosyalarının içeriği (yalnız ad, boyut
ve özet gider), sağlayıcı anahtarı dışında hiçbir kimlik bilgisi, DID, seed,
oturum çerezi, dosya yolu veya makineye özgü değer.

### 1.1 Taranmış bir isteğin metni

Yukarıdaki "baytlar gitmez" kuralı bir kusur üretmişti. Bir oda taramasından
açılan görevde okunur tek şey `title` idi — bir satırın ilk 120 karakteri — ve
isteğin geri kalanı `content_sha256` içinde hash'lenmişti. Model, yardım
edeceği isteği **göremiyordu**.

Metin artık taramanın görev açarken yazdığı bir **çalışma alanı dosyasıdır**
(`oda-istegi.md`, bkz. `work-scan.md` §7.1). Brief'e gövde **gömülmez**:
brief yalnız dosyanın orada olduğunu, adını, hangi araçla okunacağını ve
ikinci bölümünün **veri** olduğunu söyler
(`planner/service.py::REQUEST_FILE_BRIEF`). Kural değişmedi — bayt yine ancak
bir araç çağrısıyla ve çalışma alanının kendi tavanlarıyla okunur.

Cümle **envanterden** eklenir, görevin kaynağından değil: dosyası olmayan bir
çalışma alanı bu cümleyi üretmez, yani brief var olmayan bir dosyayı asla vaat
edemez.

## 2. Modelden gelen ne olur

Yanıt `station_api/opencode/planner.py` içinde **tek** bir fonksiyonda
ayrıştırılır ve orada üç şey olur:

1. **`reasoning_content` atılır.** Redakte edilmez — okunur ve düşürülür.
   Uygulamada onu yazabilecek bir sütun zaten yoktur
   (`test_no_agent_table_can_hold_a_model_reasoning_trace`), fakat bir
   görünüme ulaşan değer loglanabilir veya gösterilebilirdi. Bu yüzden alan,
   onu elinde tutan tek fonksiyonda yok edilir.
2. **`function.arguments` bir JSON dizesidir** ve ayrıştırılması başarısız
   olabilir. Başarısızlık bir **rettir**, "argümansız çağrı" değil.
3. **`usage` ve `cost` olduğu gibi alınır.** Yoksa `unknown`; sıfır
   uydurulmaz (SI-250). `cost` bir **dize** olarak kalır: ölçülen yanıt
   `"0"` dedi ve bunu `0.00` diye göstermek bizim aritmetiğimizi
   sağlayıcının beyanı gibi sunmak olurdu.

## 3. Dört kapı

`station_api/planner/service.py` sırayla:

1. **Tavan.** `agent/budget.py`'nin **aynı** saf `check` fonksiyonu, yeni
   birim `model_call_count` ile. İstek **kurulmadan önce** bakılır, böylece
   ret hiçbir şeye mal olmaz.
2. **Registry.** Her `function.name` kapalı araç registry'sinde aranır, her
   argüman o aracın **bildirdiği tiplere** karşı bağlanır. `path`/`url`
   parametre tipi **yoktur**; dosya adı sade bir addır ve çalışma alanı onu
   ikinci kez temizler.
3. **Ya hepsi ya hiçbiri.** Tek bir kayıtsız çağrı **tüm** öneriyi düşürür.
   Geçerli olanları saklamak, kullanıcıya modelin önermediği bir planı
   onaylatmak olurdu.
4. **Kişi.** Üretilen şey `planned` fazında bir çalışmadır. Başlatmak ayrı
   bir istektir ve `station_api/planner` ağacında `start_run` adı **hiç
   geçmez** — bu bir davranış değil, sözdizim ağacından okunan bir gerçektir.

## 4. Bütçe: neden `max_model_calls`, neden token değil

ADR-0008 §4 token ve para birimini reddetmişti; gerekçesi "model yolu kapalı,
ölçülecek bir şey yok" idi. O gerekçe düştü, **karar düşmedi** ve gerekçesi
sertleşti:

> Karşı tarafın bildirdiği bir sayıyla ifade edilen tavan, karşı tarafın
> koyduğu tavandır.

`usage` ve `cost` **kaydedilir** ve `model_called` satırında gösterilir;
`check` fonksiyonu ikisini de **okumaz**. Sayılan şey Station'ın kendi
yaptığı istek sayısıdır.

Birimler artık dört: `tool_call_count`, `model_call_count`,
`wall_clock_seconds`, `concurrency`. `refused_units` hâlâ `("token",
"currency")` ve gerekçesiyle birlikte telde görünür.

## 5. Döngü ve nerede durur

Onaylanan çalışma bittiğinde adımların **koşucunun kendi cümlesi**
`role:"tool"` mesajı olarak modele döner. Dosyanın baytları dönmez: oturumu
sürdürmek, bir çalışma alanı belgesini sağlayıcıya göndermenin yolu olamaz.

Döngü şunlarla biter, ve her biri kendi cümlesini söyler:

* model **arac çağırmayı bıraktığında** — yani `finish_reason` `stop`
  olduğunda (`finished`). Oturumu kapatan tek dal budur;
* model çağrısı tavanı dolduğunda (`budget_exhausted`);
* öneri registry'den geçmediğinde (`refused`);
* sağlayıcı reddettiğinde, hata verdiğinde veya cevap gelmediğinde
  (`provider_failed`).

Bir tur **hiçbir çağrı önermeden** bitebilir ve bu her zaman bir bitiş
değildir. Canlı bir koşu bunu gösterdi: sağlayıcı `finish_reason: "length"`
ve tam 1024 çıkış token'ı döndürdü — o günkü çıkış tavanı, token'ı token'ına
harcanmıştı. Model **kesilmişti**, bırakmamıştı; ürün ise "arac cagirmayi
birakti; oturum bitti" dedi ve oturumu kapattı, böylece kullanıcı yeniden
soramadı. İki iddia, ikisi de ölçülmemişti.

Bu yüzden çağrı önermeyen bir tur artık **nedene göre** ayrılır:

* `stop` → `finished`. Model bıraktı; oturum kapanır.
* `length` → `truncated`. Yanıt çıktı tavanına dayanıp kesildi. **Bitiş
  değildir**: oturum açık kalır ve aynı tur yeniden istenebilir.
* `content_filter`, boş bir `tool_calls`, tanımadığımız bir değer veya hiç
  neden bildirilmemesi → `inconclusive`. Hangisi olduğu cümlede yazar,
  sağlayıcının kendi yazımıyla; tanınmayan bir değer **olduğu gibi**
  aktarılır ve anlamı uydurulmaz. Oturum kapatılmaz.

Çıktı tavanı `1024`ten `4096`ya çıkarıldı. Bu bir **maliyet** kontrolü
değildir — harcamayı sınırlayan şey hâlâ model çağrısı sayısıdır (ADR-0008
§4, ADR-0012 §3) — **kesilmeyi önleme** ayarıdır. Sayının gerekçesi
ölçümdür: bir turun çağrı üretmeden harcadığı **1024** token, artı bu
build'in kendi koyduğu argüman tavanı (8000 karakter, ~2000 token); toplamı
~3072, bir üst iki kuvveti 4096.

Oturum **süreç belleğindedir** ve yeniden başlatmada kaybolur. Bu eksiklik
değil karardır: SI-224 yeniden başlatmanın hiçbir şeyi sürdürmediğini söyler
ve saklanmış bir konuşma tam da birinin sürdüreceği şeydir.

---

## 6. Kabul koşulları: `not_implemented` neden artık tek cevap değil

H2 boyunca planın `test_condition`'ı bir **cümleydi**: kaydedilirdi,
gösterilirdi ve hiçbir şey ona bakmazdı. Çalışma bu yüzden test alanını her
zaman `not_implemented` diye raporlardı, `test_result` kanıtı asla yazılmazdı
ve `ready_to_publish` yapısal olarak erişilemezdi. Dürüsttü — ve ürünün tek
bir görevi bile bitiremediği anlamına geliyordu.

Kapalı olan şey **keyfi yürütmedir** ve kapalı kalır. Bir cümle hâlâ
**koşulmaz**. H4'ün eklediği şey, makinenin diskteki baytları okuyarak
karar verebileceği **kapalı bir koşul kümesidir** — yedinci derleme zamanı
registry'si, `station_api/agent/acceptance.py`.

| Koşul | Ne sorar |
|---|---|
| `artifact_exists` | dosya çalışma alanında var mı |
| `artifact_is_json` | dosya geçerli JSON mu |
| `artifact_has_json_keys` | dosya, istenen üst düzey anahtarları taşıyan bir JSON nesnesi mi |
| `artifact_contains` | dosya istenen metni içeriyor mu |
| `artifact_digest_is` | dosyanın SHA-256'sı beklenen değer mi |

Kurallar araç registry'siyle **aynıdır** çünkü tipleri aynıdır: `path`/`url`
yoktur, dosya adı sadedir, serbest metin çalıştırılmaz ve kayıtsız bir koşul
adı **gösterilebilir bir rettir**.

### 6.1 Hüküm baytlara bağlıdır

Koşullar `plan_sha256`'nın içindedir (migration `0010`,
`agent_run.acceptance_json`), yani onaydan sonra bir koşulu düzenlemek
**planı değiştirmektir** ve `start_run` reddeder.

Hüküm **saklanmaz**: her okumada çalışma alanının o anki hâline karşı yeniden
hesaplanır. Ayrıca koşucunun yazdığı `test_result` kanıtı çıktı sürümüne
bağlıdır, yani çalışma alanı koşucunun dışından değiştiğinde kanıt
doğrulanmamışa düşer. İki bağımsız mekanizma, çünkü bayat bir "geçti" bu
dosyanın verebileceği en pahalı yanlış cevaptır.

### 6.2 Üç değer, üçü de ayrı

* `passed` — her koşul, diskteki baytlar üzerinde sağlandı;
* `failed` — en az biri sağlanmadı; **hangileri** olduğu kanıt kaydında yazar;
* `not_implemented` — plan makinece değerlendirilebilir bir koşul yazmadı.
  Bu durumda **hiçbir şey kaydedilmez**: doğrulanmamış bir satır, koşulmuş ve
  itiraz etmiş bir denetim gibi görünürdü.

Model önerisiyle kaydedilen planlar bilerek `not_implemented` raporlar:
öneriyi yapanın kendi ölçütünü de yazması, ölçüt olmaz. Kabul koşullarını bir
kişi ekler.

## 7. `ready_to_publish`: istenerek değil, türetilerek

Kapı zaten üç ayrı alan istiyordu ve `test_result` üretilebilir olmadığı için
hiç açılamıyordu. Artık açılabiliyor, fakat SI-222 aynen korunuyor:

* `TaskUserTransitionName` `ready_to_publish` **taşımaz** — hiçbir istek
  gövdesi bu durumu **adlandıramaz**;
* `POST /api/tasks/{id}/publish-readiness` gövdesinde **hedef alanı yoktur**.
  İstenen şey durumun *yeniden türetilmesidir*: üç alan da doğrulanmışsa
  geçiş olur, değilse ret eksik alanları **adıyla** söyler;
* geçişi yine `TaskService.transition` yazar — bu üründe bir görev durumunu
  yazan tek fonksiyon (SI-226).

Yol tam olarak şudur: koşucu `task_outcome`'ı yazar → kabul koşulları
`test_result`'ı üretir → bir kişi `user_acceptance`'ı kaydeder (H3'ün kabul
rotası) → `publish-readiness` durumu türetir.
