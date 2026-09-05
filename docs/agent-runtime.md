# Agent çalışma ortamı ve Activity Desk (Paket H2)

Bu belge Paket H2'nin ne yaptığını, neyi **yapmadığını** ve her ikisinin de
neden böyle olduğunu kaydeder. Bağlayıcı kararlar
[`decisions/0008-paket-h2-kapsam-kararlari-2026-09-05.md`](decisions/0008-paket-h2-kapsam-kararlari-2026-09-05.md)
dosyasındadır; burada onların uygulanmış hâli anlatılır.

Tek cümlelik özet: **agent, bir kişinin önceden yazdığı planı, kapalı bir
registry'den gelen araçlarla, bir tavan altında yürütür. Model çağrısı yoktur,
kabuk komutu yoktur, keyfi kod yürütmesi yoktur.**

---

## 1. Yürütme kapalı: ölçüm, karar ve nedeni

### 1.1 Ölçülen envanter

Hiçbir şey kurulmadan, hiçbir konteyner çalıştırılmadan, 5 Eylül 2026'da
ölçüldü. Kod içinde `station_api.agent.isolation.ISOLATION_INVENTORY` olarak
**veri** hâlinde durur, bir yorum satırı olarak değil.

| Olanak | Ölçüm | Not |
|---|---|---|
| Docker Desktop 4.89.0 | **var** (daemon cevap veriyor) | güvenilmiyor, aşağıya bakın |
| WSL2 | **var** | güvenilmiyor |
| Windows Sandbox | **yok** | |
| Hyper-V yönetim yüzeyi | **yok** | |
| Local admin yetkisi | **yok** | Station zaten istemez |
| Windows optional feature durumları | **ölçülemedi** | sorgu admin istiyor |

Son satır önemlidir: **ölçülemeyen bir şey "yok" diye yazılmaz.**
`MeasuredState` üç değerlidir (`present` / `absent` / `not_measured`) ve
`not_measured`'ı `absent`'a çevirmek, yapılmamış bir ölçümü yapılmış gibi
göstermek olurdu.

### 1.2 Karar: yine de kapalı

Docker'ın bu makinede bulunması onu ürünün garantisi yapmaz. Üç gerekçe, ve
hiçbiri "kimse yapmadı" değil:

1. **Kod yok.** Ölçülen tek gerçek sandbox Docker/WSL2'dir; AppContainer veya
   Job Object için ne kütüphane ne kod var. "Ayrı klasör + `subprocess`" ise
   künyenin açıkça reddettiği şeydir.
2. **Docker kullanıcının kurulumudur, ürünün değil.** Station
   `%LOCALAPPDATA%`'ya kurulan, admin istemeyen, loopback-only bir masaüstü
   uygulamasıdır. "Docker kurulu, açık ve kullanıcı `docker-users` grubunda"
   ön koşulunu koymak ürünün kendi kurulum sözleşmesini değiştirir — bu bir
   mimari karardır, H2'nin sessizce varsayacağı bir şey değil.
3. **Test edilemez.** Konteyner çalıştıran bir yol CI'da veya temiz bir
   makinede doğrulanamaz; yerel imaj varlığı bu makineye özgüdür ve
   `docker pull` yasak bir dış istektir. **Çalıştırılmamış kod test edilmiş
   sayılmaz**, dolayısıyla sevk edilmez.

### 1.3 Bu, kodda nasıl bir gerçeğe dönüşüyor

`execution_unavailable` bir **durum gerekçesidir**: `TransitionVerdict`
kalıbını kullanır (`allowed=False`, `reason`, `detail`), bir değer olarak
taşınır, `GET /api/tasks/surface` ile gösterilir ve zincire bir karar noktası
olarak girer. Eksik bir düğmeden çıkarılması gereken bir sessizlik değildir.

Yapısal tarafı: `station_api/agent` ağacında ve önündeki rota dosyasında
`subprocess`, `os.system`, `exec`, `eval`, `compile` (çıplak ad), `importlib`,
`ctypes` **yoktur**; bir AST taraması bunu her koşuda denetler ve tarama, ekili
bir örnek üzerinde sürülerek doğrulanmıştır
(`test_agent_boundary.py::test_the_execution_scan_would_catch_a_planted_call`).

### 1.4 Kapalı olmanın bedeli, saklanmadan

- Plan bir **başarı ölçütü** kaydeder ve onu **koşmaz**.
- Bu yüzden `test_result` alanı `not_implemented` kalır, hiçbir kod yolu ona
  kanıt yazmaz, ve görev `review_needed`'da durur: `ready_to_publish`'e
  **geçemez** (SI-222).
- Ekranda `RUN_HONESTY_SENTENCE` ile söylenir; "test geçti" ifadesi yasak
  ifade registry'sindedir.

---

## 2. Araç registry'si — altıncı kapalı registry

| Registry | Konu |
|---|---|
| `technocore/sources.py` | resmî belge okuma |
| `technocore/write_targets.py` | imzalı yazma |
| `technocore/evidence_targets.py` | kanıt okuma |
| `workscan/targets.py` | iş taraması okuma |
| `opencode/registry.py` | sağlayıcı uçları + model tablosu |
| **`agent/tools.py`** | **araç şeması** |

### 2.1 Neden bu uydurma değil

Bir sağlayıcının aracı **çağırmak** için kullanacağı tel formatı
yayımlanmamıştır ve ADR-0005 §1.2 yayımlanmamış bir sözleşmeyi uydurmayı
yasaklar. Bu yüzden `tool_calls_supported` `Literal[False]` **kalır**,
`post_completion` prodüksiyonda **çağrılmaz** ve `OUTBOUND_CLIENT_MODULES`
**beşte** kalır.

Aracın **kendi şeması** ise Station'ındır: adı, tipli parametreleri, izin
kapsamı ve tavana maliyeti. Hiçbir dış sözleşme iddia etmez.

Sonuç: "model çıktısı doğrudan yürütülmez" boş bir vaat değil, **yapısal bir
gerçektir** — bu sürümde model çıktısı diye bir şey yoktur. Bir "adım", bir
kişinin yazdığı, kayıtlı bir araç kimliği ve tipleri denetlenmiş
argümanlardır.

### 2.2 Sekiz araç

| Araç | Kapsam | Ne yapar |
|---|---|---|
| `read_approved_snapshot` | `read_approved_input` | görevin onaylı içerik sürümünü okur |
| `read_workspace_file` | `read_approved_input` | çalışma alanındaki bir dosyayı okur |
| `write_workspace_file` | `write_workspace` | metin/kod/rapor/yama üretir |
| `update_workspace_file` | `write_workspace` | var olan dosyayı baştan yazar |
| `validate_json_file` | `deterministic_check` | JSON geçerliliği |
| `diff_workspace_files` | `deterministic_check` | iki dosya arasındaki fark |
| `verify_file_digest` | `deterministic_check` | SHA-256 tutarlılığı |
| `read_run_status` | `read_run_state` | çalışmanın kendi durumu |

**Durdur ve devam et bilerek araç değildir.** Kendini devam ettirebilen bir
çalışma, kullanıcının durdurma kararını geri alabilir; bu ikisi yalnızca
kullanıcının rotalarıdır.

### 2.3 Agent kendine araç ekleyemez

Üç ayrı kilit:

1. `TOOLS` bir **tuple literal**'dir; kayıt fonksiyonu, plugin yolu,
   entry-point grubu yoktur ve arama tablosu hiç mutasyona uğramaz — bir AST
   taraması `TOOLS` ve `_BY_ID`'nin tam olarak birer kez atandığını ve
   üzerlerinde `append`/`update` çağrılmadığını denetler.
2. Kayıtsız bir kimlik **gösterilebilir bir ret** döndürür
   (`ToolRegistryError`, `reason="tool_unknown"`) — çıplak bir `KeyError`
   değil, çünkü o zırhlı bir 500'e dönüşür (F-11 dersi).
3. **Import zamanında** güven sınırı denetlenir: `git`, `commit`, `merge`,
   `install`, `setting`, `permission`, `plugin`, `shell`, `sign`, `vault`,
   `credential`, `env`, `home`, `repo` ve benzeri parçaları taşıyan bir kayıt
   varsa uygulama **başlamaz**. Denetim ekili bir `git_commit` kaydıyla
   sürülerek doğrulanmıştır.

### 2.4 Tool runner: tipli araç + doğrulanmış argüman

Kabuk dizesi yoktur ve kurulabileceği bir yer de yoktur. `bind_arguments`
her argümanı aracın **beyan ettiği** parametre tipine göre doğrular
(`text`, `file_name`, `digest`, `json_text`), tanınmayan bir anahtarı
reddeder ve eksik zorunlu argümanı reddeder. `path` ve `url` diye bir
parametre tipi **yoktur**: bir araca adres verilemez.

---

## 3. Bütçe: yalnız ölçülebilir birimler

| Birim | Değer |
|---|---|
| `tool_call_count` | en çok 32 |
| `wall_clock_seconds` | en çok 120 |
| `concurrency` | **1** (`Literal[1]`) |

**Token ve para birimi yoktur** — ve bu bir eksiklik değil, gerekçeli bir
rettir: model yolu kapalı olduğu için sağlayıcıdan gelen bir kullanım değeri
yoktur, SI-250 de gelmiyorsa sıfır uydurmayı zaten yasaklar. Ölçülemeyen bir
birimle ifade edilen tavan, birine sayı lazım olduğu ilk anda "sınırsız"a
yuvarlanır. Reddedilen birimler `refused_units` alanında **adıyla** yayımlanır.

### 3.1 Neden `agent/`, `tasks/` değil

`test_the_task_layer_opens_no_budget_field`, `station_api/tasks` ve
`station_api/modules` ağaçlarında `budget|cost|spend|quota|credit` içeren
**hiçbir tanımlayıcıya** izin vermez. SI-225'in "görev katmanında bütçe yok"
iddiasının **harfiyen** doğru kalması istendiği için tavan bu pakete girdi;
görev katmanında bir tane bile alan yoktur. `budget_available` hâlâ
`Literal[False]`'tır — bir görev tavan taşımaz, **bir çalışma taşır**.

Görev yanıtındaki `budget_detail` cümlesi H2 ile güncellendi: eskiden "G ve
H2'ye ertelenmiştir" diyordu, H2 onu yazdı, ve sevk edilmiş bir şey için
erteleme duyurusu bırakmak yalan olurdu.

### 3.2 "Agent kendi tavanını yükseltemez" yapısaldır

- `CEILING` derleme zamanında, literal'lerden kurulan bir `frozen dataclass`;
  constructor argümanı, ortam değişkeni veya satır yoktur.
- Araç registry'sinde tavanı okuyan/yazan bir araç **yoktur**.
- **Hiçbir kod yolu tavana yazmaz.** Bir AST taraması (`CEILING` ataması,
  öznitelik ataması, artırmalı atama ve sabit adlı `setattr` — dört yazım)
  bunu sabitler ve tarama ekili bir yazıcı üzerinde sürülerek doğrulanmıştır.

---

## 4. Çalışma alanı savunması

```
<data_dir>/workspace/v1/<32-hex task_id>/
```

`vault/paths.py`'nin kalıbı: **sürümlü** ve **uygulama tarafından
doğrulanmış kimlikle** adreslenir. Veri dizininin altında olması bedava bir
test kazandırır: `test_no_plaintext_artefact_is_left_in_the_data_directory`
oradaki **her dosyayı** okur, dolayısıyla çalışma alanı dosyaları seed ve
API-anahtarı taramalarına otomatik girer.

**Emsal yoktu.** Depoda hiçbir yerde traversal, symlink, junction veya
zip-slip savunması yoktu; aşağıdakiler sıfırdan yazıldı.

### 4.1 Katman 1 — ad yeniden kurulur, süzülmez

Her dosya adı `downloads.safe_download_filename`'den geçer: `[A-Za-z0-9._-]`
allow-list'i, gövde/uzantı tavanları, Windows ayrılmış aygıt adları. **Yeniden
yazılacak bir ad kabul edilmez, reddedilir.** İndirme başlığı serbestçe
yeniden adlandırabilir; burada edemez, çünkü çalışma sonradan o dosyanın
özetini alır ve sessiz bir yeniden adlandırma o karşılaştırmayı başka bir
dosya hakkında yapar.

### 4.2 Katman 2 — çöz ve kapsa

Her okuma ve **her** yazımda `resolve()` + `is_relative_to(root.resolve())`.
Bir kez, en tepede değil.

### 4.3 Katman 3 — reparse point'ler, tepeye kadar

Dosyadan köke kadar **her bileşende** `is_symlink()` **ve**
`os.path.isjunction()`. İkincisi POSIX alışkanlığıyla yazılmış bir denetimin
atlayacağı olandır: NTFS junction bir sembolik bağ **değildir**, `is_symlink`
ona `False` der, ve yetkisiz bir Windows kullanıcısının gerçekten
oluşturabildiği reparse point odur.

Paket ayrıca **hiç bağ oluşturmaz**: `symlink_to`, `os.symlink`, `os.link`,
`hardlink_to` ağaçta yoktur (AST taraması).

**Kırma denemeleri ve sonuçları** (`test_agent_workspace.py`):
`../escape.txt`, `..\escape.txt`, `../../../../Windows/System32/...`,
`..%2fescape.txt`, `sub/dir.txt`, `sub\dir.txt`, `C:\Windows\win.ini`,
`\\server\share\file.txt`, `/etc/passwd`, `..`, `.`, `con.json`, NUL, CRLF,
bidi override — **hepsi reddedildi**. İki görevin birbirinin çalışma alanını
okuma denemesi reddedildi. Symlink hem **gerçekten oluşturularak** (OS izin
verdiğinde) hem de predikat zorlanarak sürüldü, böylece hiçbir makinede test
atlanmıyor; junction hem yaprakta hem de **bir üst dizinde** denendi.

### 4.4 Katman 4 — tavanlar, diskten okunarak

En çok 64 dosya, dosya başına 512 KiB, toplam 4 MiB. Sayaçtan değil,
**yazımdan hemen önce dizinin kendisinden** okunur: bir sayaç ile bir dizin
(çökme, elle silme, yeniden başlatma sonrası) ayrılabilir ve kullanıcının
elinde olan yalnızca ikincisidir.

### 4.5 Arşiv yolu hiç yok

`zipfile`, `tarfile`, `shutil`, `gzip`, `bz2`, `lzma`, `zlib` **import
edilmez**. Zip-slip, hiçbir şey açmayan bir üründe var olamayan bir hata
sınıfıdır. Bedeli: kullanıcı kendi arşivini bir kez, bu ürünün dışında açar.

### 4.6 ACL

Dizin ve her dosya SYSTEM + geçerli kullanıcıya kısıtlanır (SI-265 kalıbı,
`O_CREAT|O_EXCL` ile boş oluştur → ACL → yaz). Bu dosyalar sır değildir — bir
rapor okunmak içindir — bu yüzden burada bir güven sınırı değil, derinlemesine
savunma olarak yazılmıştır ve öyle anlatılır.

---

## 5. Yürütme, plan ve kanıt

### 5.1 Plan önce yazılır

`POST /api/tasks/{id}/runs` adımları, **söz verilen çıktıları** ve **başarı
ölçütünü** kaydeder ve üçünü birden `plan_sha256`'ya özetler. Hiçbir şey
çalışmaz. Başlatma ayrı bir istektir (besteci'nin iki-onay kalıbı,
ADR-0002 §2).

**Planı değiştirmek başarı kriterini sessizce gevşetemez:**
`start_run` kaydedilen planı yeniden özetler ve uyuşmazlıkta reddeder
(`plan_changed`); her adımın argümanları **çağrıdan hemen önce** yeniden
doğrulanır ve yeniden özetlenir (`plan_arguments_changed`). Testler bu ikisini
**satırı doğrudan düzenleyerek** — yani her rotayı atlayarak — sürüyor.

Plan düzenleme diye bir şey yoktur: farklı bir plan **yeni bir çalışmadır** ve
eskisi yargılandığı ölçütü korur.

### 5.2 Dört ayrı son

| Faz | Anlamı | Zincire giren karar |
|---|---|---|
| `completed` | her adım koştu, söz verilen her çıktı var | — |
| `budget_exhausted` | tavana ulaşıldı | `budget_exhausted` |
| `tool_error` | bir araç reddetti veya başarısız oldu | `task_execution_refused` |
| `artifact_missing` | söz verilen çıktı üretilmedi | `task_execution_refused` |
| `paused` / `cancelled` | kullanıcı durdurdu | — |

"Bütçen bitti" ile "girdin bozuk" arasındaki farkı göremeyen bir kullanıcı
ikisine de müdahale edemez.

### 5.3 Durdur ve geç yanıt

Durdur bir **bayraktır**; runner onu **her araç çağrısından önce** okur.
Kesilecek bir şey yoktur: aynı anda tek çağrı, senkron.

İptalden sonra dönen geç bir yanıt **yan etki üretmez**: sonucu kaydedilmez,
adım `skipped` olarak yazılır ve **ürettiği dosya çalışma alanından
kaldırılır**. Bu, çağrı sırasında durdurma bayrağını kaldıran bir araçla
sürülerek test edilmiştir.

### 5.4 Çökme sonrası

Bir yeniden başlatma `running` fazında satır bırakır. `interrupted_runs()`
onu **listeler**; plan diskte olduğu için yüklenebilir. **Otomatik devam
yoktur** ve `create_app` bu servise yapıcıdan başka hiç dokunmaz (SI-224).
Devam etmek kullanıcının `resume` rotasıdır. Yeni bir dış paylaşım zaten
yoktur.

### 5.5 Kapsam dışı istek

Kayıtsız bir araç, çalışma alanı dışına çıkan bir ad veya bir secret'a uzanan
bir istek **`permission_denied` olarak kaydedilir** ve zincire
`tool_call_refused` olarak girer. **Görev otomatik olarak başka bir hedefe
kaydırılmaz** — kendi hedefini seçen bir agent, kullanıcının hedefini seçmiş
olur.

---

## 6. Activity Desk: iki katman, karıştırılmadan

| | `activity_event` | audit zinciri |
|---|---|---|
| İçerik | adım adım her şey | yalnız karar noktaları |
| Hacim | yüksek | sınırlı |
| Retention | var (`RETAINED_EVENTS = 500`) | **yok, asla budanmaz** |
| Zincir halkası mı | **hayır** | evet |

Bu ayrım, çelişen iki kuralı uzlaştırır: zincir asla budanmaz (ADR-0003 §7),
ama adım adım bir zaman çizelgesi doğası gereği hacimlidir. Tek tablo ikisini
birden taşıyamaz.

`chain_referenced` bayrağı ikisini yalnızca komşu değil **uyumlu** yapar: bir
karar noktası zincire yazıldığında halkanın `subject`'i o satırın kimliğidir ve
satır işaretlenir. Hem retention hem de kullanıcının silme isteği işaretli bir
satırı **reddeder**. Böylece "zincirin atıfta bulunduğu hiçbir satır
budanamaz" bir yorum değil, koddur.

### 6.1 Ayrı olaylar, tek bir `step_done` değil

`run_planned`, `run_started`, `tool_called`, `artifact_produced`,
`check_recorded`, `approval_awaited`, `run_stopped`, `run_resumed`,
`run_finished`, `run_failed`, `permission_denied`, `budget_exhausted`,
`execution_unavailable`, `activity_deleted`.

"Planlandı" ile "çalıştırıldı", "çıktı oluşturuldu" ile "denetim kaydedildi",
"bitti" ile "onay bekleniyor" ayrı olaylardır. Onları tek bir olaya
katlamak, zaman çizelgesinin "gerçekten bir şey denetlendi mi?" sorusuna
cevap veremez hâle gelmesinin yoludur. `approval_awaited` olayının sonucu
`pending`'dir, `ok` değil.

### 6.2 Yazılmayanlar

**Modelin muhakemesi ve ham sağlayıcı payload'ı yazılmaz** — "önce
temizlenir" değil, **koyacak sütun yoktur**, ve zaten üretecek bir model yolu
yoktur. `actor` yalnızca `user` veya `station_runner` olabilir; `model` diye
bir aktör yoktur. Bir migration olmadan böyle bir sütun eklenemez ve
migration'ı bir inceleyen okur.

### 6.3 Silme bir audit olayıdır

`POST /api/activity/delete` işaretsiz satırları siler, işaretlileri **korur**
ve iki sayıyı **ayrı ayrı** raporlar. Silme işlemi zincire
`activity_deleted` olarak yazılır; zincir sonrasında hâlâ `intact` doğrular —
zaten aktivite satırları halka olmadığı için silinmeleri hiçbir MAC'i kıramaz.

---

## 7. Güven sınırı: geliştirme yetkisi ürüne miras verilmez

Geliştirme sırasında bir kodlama asistanına verilen commit/PR/merge yetkisi
son üründeki agent'a **geçmez**. Araç registry'sinde git, PR, merge, paket
kurulumu, ayar düzenleme, izin listesi değiştirme ve plugin **yoktur ve
eklenemez** (§2.3).

SI-213'ün yasağı yeni pakete de taşındı — aksi hâlde yeni paket muaf olurdu.
`station_api/agent` ve `routes/agent.py` üzerinde:

- giden yüzey yok: `httpx`, `requests`, `socket`, `urllib`, `ssl`, üç
  Technocore istemcisi, `workscan.client` ve **`station_api.opencode`'un
  tamamı** yasak;
- secret sınırı yok: `vault.service`, `vault.dpapi`, `vault.passphrase`,
  `vault.paths`, `compose`, `recovery`, `seed_import`,
  `opencode.credential_store` yasak;
- `station_api.vault`'tan **tam olarak iki** modül serbesttir:
  `vault.windows_acl` (dosya sistemi ACL yardımcısı, anahtar malzemesine
  dokunmaz) ve `vault.errors` (istisna sınıfları). Bu bir önek muafiyeti değil,
  **birebir allow-list**'tir: üçüncü bir isim testi kırar;
- ikinci gate yok: `CheckState`, `WriteGateStatus`, `WriteGateInput` bu
  pakette **tanımlanmaz**;
- zamanlayıcı yok: `asyncio`, `threading`, `sched`, `concurrent`, `signal`
  import edilmez, `create_task`/`Timer`/`Thread` çağrılmaz (SI-272).

Agent kullanıcının home dizinine ve Station'ın kendi kaynak reposuna
erişemez: erişebileceği tek dizin `<data_dir>/workspace/v1/<task_id>`'dir ve
oraya bile ancak §4'ün dört katmanından geçerek yazar.

---

## 8. Durum makinesi: `running` ve `paused` açıldı

`ALLOWED_TRANSITIONS` **değişmedi** — Paket F kenarları, hiçbir şey onlardan
geçemezken yazmıştı, tam da H2'nin makineyi hafızadan yeniden icat etmemesi
için. H2 yürütücüyü yazdı ve tabloyu düzenlemeden aynı kenarlardan geçti.

`INITIAL_STATE` `awaiting_approval` **kaldı**: kullanıcının kendi görevi ile
bir taramanın önerisi hâlâ satırın kendisiyle ayrılır (SI-277).

`UNPRODUCIBLE_STATES` artık **boştur**. Bu, üç testi sessizce boş parametreyle
yeşile düşürüyordu; hiçbiri öyle bırakılmadı:

| Eski test | Ne yapıldı |
|---|---|
| `test_the_pure_function_refuses_every_edge_into_an_unbuilt_state` | boş döngü yerine mekanizma **sürülüyor**: bir durum test süresince kapatılıp her kenarın reddedildiği doğrulanıyor; kapatmadan önce aynı kenarın izinli olduğu da denetleniyor |
| `test_the_service_refuses_a_direct_request_for_an_unbuilt_state` | boş `parametrize` (sessiz skip) kaldırıldı; aynı şekilde sürülüyor, ayrıca bugün gerçekten karşılaşılabilen ret (`transition_not_allowed`) kendi testine kavuştu |
| `test_the_table_still_lists_the_edges_into_unbuilt_states` | vacuous değildi ama adı ve gerekçesi yanlış olmuştu; yeniden adlandırıldı ve iddiaları **güçlendirildi** (kenarlar var **ve** izinli) |

`STATE_DETAIL[RUNNING]` / `[PAUSED]`'ın "bu sürümde hiçbir kod yolu bu durumu
üretemez" cümleleri yalan hâline geldiği için **düzeltildi**.

`_state_writers` taraması artık `modules`, `tasks` ve **`agent`** ağaçlarını
okur. Bu üçüncü ad taşıyıcıdır: `running`/`paused`'ı üreten kod o ağaçtadır ve
tarama genişletilmeseydi SI-226 tam da onu delen commit'te sessizce delinmiş
olurdu. Agent paketi taramayı geçer çünkü **hiç durum yazıcısı yoktur**:
görevi `TaskService.transition` ile taşır ve kendi defter sütununu bilerek
`state` değil `phase` diye adlandırır.

---

## 9. Rotalar

```
GET  /api/tasks                                  görevler, sınırlı
GET  /api/tasks/surface                          araçlar, tavan, izolasyon
GET  /api/tasks/{task_id}                        bir görev, dört alan ayrı
POST /api/tasks/{task_id}/transition             kullanıcının durum değişikliği
GET  /api/tasks/{task_id}/runs                   çalışmalar + çalışma alanı
POST /api/tasks/{task_id}/runs                   plan kaydeder; hiçbir şey koşmaz
POST /api/tasks/{task_id}/runs/{run_id}/start    kaydedilmiş planı yürütür
POST /api/tasks/{task_id}/runs/{run_id}/stop     sonraki araç çağrısını engeller
POST /api/tasks/{task_id}/runs/{run_id}/resume   onaylı kapsamda devam
GET  /api/activity                               zaman çizelgesi
POST /api/activity/delete                        satır siler; olay olarak yazılır
```

Hepsi `no-store`; durum değiştiren hepsi CSRF, Host, Origin ve
`Sec-Fetch-Site` kapılarının arkasında (middleware, opt-out edilemez); her
gövde `StrictModel(extra="forbid")`.

**Bilerek yok olanlar:** komut çalıştıran rota; kanıt kaydeden rota
(`test_result`'ı doğrulanmış işaretleyen bir POST, kanıt modelini tek istekte
çökertirdi); `running`/`paused`'a doğrudan geçiş (`TaskUserTransitionName`
onları taşımaz — plan yazılmadan yürütme durumuna girilemez); plan düzenleme;
zamanlayıcı; ve herhangi bir yol/adres parametresi.

---

## 10. Kalan riskler

- **İnsan güvenlik incelemesi hâlâ ertelenmiş bir risktir** (ADR-0001 §5). Bu
  paketin savunmalarının çoğunun emsali yoktu; sıfırdan yazılmış bir traversal
  ve reparse-point savunması, gözden geçirilmiş bir tanesiyle aynı şey değildir.
- **Junction ölçümü düzeltildi.** Bu bölüm önce "gerçek bir NTFS junction
  oluşturmak ya admin ya da `subprocess` ister" diyordu; **bu yanlıştı.**
  Bağımsız inceleme `mklink /J` ile **admin olmadan** gerçek bir junction
  oluşturdu ve reparse savunmasının onu görmediğini ölçtü. Symlink ise bu
  makinede oluşturulamıyor (`WinError 1314`), o yüzden symlink tarafı
  işletim sistemi izin verdiğinde gerçek bağla, vermediğinde zorlanmış
  predikatla sürülüyor.
- **Aşama numarası 8'e çekildi.** Bu bölüm önce "7'de bırakıldı" diyordu;
  değişiklik backend turundan sonra, beş giriş noktasını
  (`cli/__main__.py`, `launcher.py`, `routes/api.py`,
  `e2e/harness/serve.py`, `tests/conftest.py`) ve `CURRENT_SCHEMA_STAGE`'i
  birlikte düzenleyen bir turda **atomik olarak** yapıldı; SI-232/SI-262
  sağlanıyor.
- **Ön yüz açıldı.** Bu bölüm önce "açılmadı" diyordu; `tasks` ve
  `activity` bölümleri aynı pakette `ready: true` yapıldı ve iki panel
  (`TasksPanel.tsx`, `ActivityPanel.tsx`) eklendi. Activity Desk'in ekran
  karşılığı vardır.
- **`docs/task-modules.md` güncellendi.** Bu bölüm önce "hâlâ bütçenin
  H2'ye ertelendiğini söylüyor" diyordu; belgenin eskiyen üç yüzeyi aynı
  pakette düzeltildi.
