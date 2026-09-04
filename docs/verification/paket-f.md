# Paket F doğrulama raporu — proje/görev modülü temeli

Tarih: 2026-09-04 · Taban: `e6732f83a86bab058e4f90768a85a59f99c3414f` (Paket E merge'ü)

Kapsam kararları: [`ADR-0004`](../decisions/0004-paket-f-kapsam-kararlari-2026-09-04.md).
Künye Aşama 6.

## Keşif bulgusu: "Proje 0" kodda hiç yoktu

`apps/` ve `packages/` altında `Proje 0` / `project_0` / `ProjectZero` için
**sıfır** eşleşme; ne tablo, ne bölüm kimliği, ne "tamamlandı" işareti.
Künye §7.2 m.8 bugüne kadar karşılanmamıştı.

Yol haritası "Proje 0 modül sınırına taşınmış" diyor, görev ise "mevcut
kayıt kimlikleri ve migration geçmişi bozulmasın" diyor. Keşif fiziksel
taşımanın bedelini saydı — `OUTBOUND_CLIENT_MODULES` `technocore/` dizinini
**adıyla** pinliyor, üç yerde `collect_route_paths` route kümesini
denetliyor, `test_write_gate.py` modül yollarını literal kullanıyor: en az
altı test kırılır ve karşılığında **hiçbir davranış kazanılmaz**.

Bu yüzden "modül" **derleme zamanı registry kaydı** olarak tanımlandı.
Sorumlu kod yerinde kaldı; `MODULES` tuple'ı ona işaret ediyor ve kaydın
`owners` alanı kodu bugün sahiplenen yedi modülü adlandırıyor. Bir test her
noktalı yolun gerçek bir dosyaya çözüldüğünü doğruluyor
(`test_every_reviewed_client_module_actually_exists`'in dersi).

## Yüzeye çıkan çelişki: künye çıktısı 5 asla karşılanamaz

Künye §7.2'nin beşinci çıktısı lobby'ye imzalı bir selam gönderilmesini
istiyor. `lobby` ise `DENIED_ROOMS` içinde (IMP-281, INV-05) — yani bu
çıktı **bu ürün tarafından hiçbir zaman üretilemez**.

Kayıt bunu ayrı bir `policy_refused` bayrağıyla taşıyor, böylece "henüz
kimse yazmadı" ile "bu ürün bunu yapmayacak" **aynı görünmüyor**. Dokuz
çıktının üçü `not_implemented` olduğu için `complete` kalıcı olarak
`False` — ve bu dürüst sonuç, gizlenen bir eksiklik değil.

## Dokuz durum ve geçiş tablosu

`ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]]` makineyi **tek
yerde** yazıyor; daha önce doğrulama DB kısıtlarına ve "başarısızlıkta ileri
değil iptale git" konvansiyonuna dağılmıştı. `validate_transition` saf bir
fonksiyon.

**Üretilemeyen durumları ne sabitliyor:** `test_no_code_path_can_produce_an_unproducible_state`
kaynağı okumuyor ve sabite güvenmiyor. Gerçek `TaskService`'i gerçek bir
veritabanına karşı, dokuz hedefe doğru enine arama ile sürüyor, **fiilen
ulaşılan** durumları topluyor ve `PRODUCIBLE_STATES` ile eşitliyor. Yani
`running`'i ileride sabiti düzenlemeden açmak testi kırar; sabiti hiçbir şey
açmadan düzenlemek de kırar. Geçiş tablosu o durumlara giden kenarları yine
listeliyor, böylece H2 makineyi hafızadan yeniden türetmek zorunda kalmıyor.

## Dört alan ayrık

Dört kolon grubu (`_ref_id`, `_verified`, `_version_id`, `_detail`,
`_recorded_at`) — `EvidenceRecord` kalıbı. Bir test `done`/`success`/
`completed`/`passed`/`score` adlı bir kolonun **var olmadığını** doğruluyor.

`public_share` **temsil edilemez**: `EvidenceRef.__post_init__` böyle bir
referansın kurulmasını reddediyor, servis reddediyor, gate daima
`not_implemented` raporluyor — ve bilinçli olarak `ready_to_publish`'i
**engellemiyor**, aksi halde hiçbir görev dışarı yayımlanmadan bitemezdi.

`verified`'ın varsayılanı yok; `verified=False` `blocked` üretiyor ve
cümlesi şu: *"bir kaydin varligi tek basina basari degildir"*.

## Deduplication

`domain_digest(b"technocore-station/task-source/v1", source_id,
content_sha256)`. `source_version_id` açık bir `isinstance(source,
TaskSourceId)` kontrolü yapıyor — bir `StrEnum` kod tabanındaki her
`isinstance(x, str)` testini geçtiği için **serbest bir string'i kimliğin
dışında tutan tek şey bu**. Kanıt, üretildiği sürümü taşıyor; yeni içeriğe
karşı bayat bir referans **gerekçesiyle reddediliyor**, sessizce yok
sayılmıyor.

## Başlangıç taraması: sıfır yazma, ölçülmüş

Keşif doğrulandı — `IN_FLIGHT` Paket D'den beri yazılıyordu ve **hiçbir şey
onu geri okumuyordu**; çökmüş bir gönderim sonsuza dek `in_flight` kalıyordu.
Tarama tek bir `SELECT`.

Sıfır iddiası **iddia edilmedi, ölçüldü**: `test_the_startup_scan_makes_zero_outbound_requests`
ve `test_building_the_application_makes_zero_outbound_requests` hem
`httpx.HTTPTransport.handle_request`'i hem `socket.socket.connect`'i sayaçla
sarıp `attempts == 0` iddia ediyor. Saymak, "istisna çıkmadı"ya güvenmekten
önemli: suite'in ağ kesicisi yalnız yabancı hostlar için fırlatıyor,
dolayısıyla bir loopback isteği sessizce geçerdi. Ayrıca defter
öncesi/sonrası bayt-özdeş, satır hâlâ `in_flight`, `resumed_any` yapısal
olarak `False`, ve bir AST testi modülün herhangi bir yazma yolunu
çağıramayacağını doğruluyor.

## Bütçe yok, görünür şekilde ertelendi

Bütçe alanı açılmadı. Erteleme üç yerde görünür: `budget_available:
Literal[False]` + `budget_detail` (`note_lane_available` kalıbı), bütçe
şekilli tanımlayıcıları yasaklayan bir AST/kolon testi, ve
`docs/task-modules.md` §6 — belgenin bunu söylediğini iddia eden bir testle
birlikte.

## Testler ve kapılar (orkestratör koşusu)

| Kapı | Sonuç |
|---|---|
| pytest | **1331 geçti** (1229 → 1302 → inceleme düzeltmeleriyle 1331) |
| Vitest | **206 geçti** (frontend'e dokunulmadı) |
| ruff (iki koşu) | geçti |
| mypy strict | 0 hata |
| eslint / build | geçti / geçti |
| `git diff --check` | 0 |

`apps/station-web`, `packages/technocore-conform` ve `vendor/` **hiç
değişmedi** (`git status` ile doğrulandı). Migration `0007`
(`down_revision="0006"`), tek head, yalnız ekleme; mevcut tablo adları ve
kayıt kimlikleri değişmedi.

## Aşama numarası (orkestratör düzeltmesi)

Paket E'de API ve launcher 5'e getirilmişti; F ile ikisi de **6** oldu.
`tests/conftest.py` ise hâlâ `stage=4` damgalıyordu — testte kurulan bir
veritabanının kendini test edilen sürümden eski göstermesi küçük bir
yalandır ve tam da kimse geri okumadığı için fark edilmez. O da 6 oldu.

## Bilinçli ertelenenler ve kalan riskler

1. **Görünür görev yüzeyi yok.** `work-scan`/`tasks`/`activity`
   `ready: false` kaldı (ADR-0004 §9); `sections.ts`'in kendi kuralı gereği
   boş bir bölüm özellikmiş gibi gösterilmez. Yüzey H1/H2'nindir.
2. **`suggested`, `running`, `paused` üretilemez** — tanımlı, geçiş
   tablosunda kenarları var, ama hiçbir kod yolu onlara ulaşamıyor ve bunu
   davranışsal bir test sabitliyor.
3. **Bütçe G/H2'de.**
4. **Public paylaşım H3'te** — alan açık, daima boş, temsil edilemez.
5. **Künye çıktısı 5 kalıcı olarak karşılanamaz** (lobby yasağı); bu bir
   eksiklik değil, kayıtlı bir politika sonucudur.
6. İnsan güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5).

## Bağımsız inceleme sonucu

Temiz bağlamlı, yazardan ayrı bir Claude reviewer subagent'ı head `d7d8541`
diffini inceledi, kapıları kendi koştu ve **18 mutasyon** çalıştırdı.
**11 bulgu**; hepsi merge öncesi kapatıldı.

### P1 — koruma yalancıydı

"Hiçbir kod yolu `suggested`/`running`/`paused` üretemez" iddiası aslında
**yalnız `transition()` için** sabitlenmişti: erişilebilirlik yürüyüşü
enine aramayı tek metot üzerinden yapıyordu. İncelemeci servise durumu
doğrudan yazan üç satırlık bir `start_running()` ekledi ve **hiçbir test
kırılmadı**. Ürün doğruydu — kırılan korumanın kendisiydi, ve H2 `running`'i
`transition` dışından açsaydı suite onu sessizce onaylayacaktı. Bu, Paket
E'de bulunan yalancı korumanın kardeşi.

Düzeltme iki yarımdan oluşuyor. **Davranışsal:** yürüyüş artık
`TaskService`'in **her public metodunu** `dir()` + `get_type_hints()` ile
sayıyor ve her metodu, annotation'larının kabul ettiği bütün değerlerle
(dokuz durum, dört kanıt alanı, iki bool) sürüyor; durumlar
`service.get()`'ten değil doğrudan tablodan okunuyor; tanınmayan bir
annotation `AssertionError` fırlatıyor, yani yeni bir üretici sessizce
sürülmeden kalamıyor. **Yapısal:** bir AST taraması `modules/` ve `tasks/`
ağaçlarında `.state`'e yazan tek yerin `service.py:transition` olmasını
şart koşuyor. İncelemecinin probu artık **iki testi** kırıyor.

### P2 — test kendi kehanetini doğruluyordu

Üretilemeyen durumlar kümesi üretilebilirlerden türetiliyor ve reddin
kendisi de aynı kümeye bakıyordu; dolayısıyla sabiti genişletmek hem reddi
kaldırıyor hem beklentiyi büyütüyordu. Mutasyonda o test kırılmadı.
Beklenen küme artık testte ADR-0004 §3'ten **elle yazılıyor** ve sabitle
eşitliği ayrı bir satırda iddia ediliyor — iki iddia ayrılabilir hale geldi.
Belgeyi geri çekmek yerine iddiayı gerçek kılmak seçildi.

### P2 — test edilmeyen dal

`modules/completion.py`'deki bayat-kanıt kontrolü `if False:` yapıldığında
**sıfır test kırılıyordu**; ikizi (`tasks/gate.py`) test edildiği için
değişmez listesi iki yolu da kapsıyormuş gibi görünüyordu. Artık kendi
testi var, boşuna geçmesin diye eşleşen-sürüm ikiziyle birlikte.

### Diğer bulgular

| Bulgu | Düzeltme |
|---|---|
| `_refs_from_row` docstring'i "böyle bir satır burada hata fırlatır" diyordu; gerçekte **sessizce atlanıyor** | Cümle gerçeğe indirildi ve davranış testle sabitlendi |
| `resumed_any` "yapısal olarak False" değildi — yalnız varsayılandı ve projeksiyon onu hiç okumuyordu | `@property -> Literal[False]`, constructor argümanı yok; projeksiyon artık okuyor |
| `ref_id` süpürülmüyor ve sınırlanmıyordu (bidi override, NUL ve 406 karakter yanıt modeline ulaşıyordu) | `sweep_untrusted` + 64 karakter sınırı; hiçliğe süpürülen bir işaretçi reddediliyor |
| Dinamik yükleme yasağı atlatılabiliyordu (`builtins.__import__` attribute yazımı, `getattr` ile parçalı ad, `sys.modules` poke) | Tarama dört yazıma genişletildi; `compile` muafiyeti yalnız attribute formunda; on sentetik bypass ve dört masum yazım parametrik test |
| Kod "iki çıktı üretilemez" diyordu, kendi assertion'ı **üç** sayıyordu | Üçe düzeltildi |
| Boş `checks` ile `ready_to_publish` boş `all()` yüzünden `True` oluyordu | Küme eşitliğine çevrildi |
| `cli/__main__.py` hâlâ `stage=3` damgalıyordu | 6 oldu; üç üretim çağrı yerinin aynı aşamayı söylediğini bir test sabitliyor |
| Geçersiz `module_id` **çıplak `KeyError`** fırlatıyordu (zırhlı 500), geçersiz kaynak ise gösterilebilir ret veriyordu | `ModuleRegistryError(KeyError)` + `module_unknown` reddi; `KeyError` alt sınıflandığı için eski iddia tam güçte kaldı |

### Kıramadıkları

Başlangıç taramasının **sıfır giden istek** ve **sıfır yazma** iddiası
incelemecinin kendi sayaçlarıyla — async transport, `connect_ex`, WAL ve
SHM dosyalarının SHA-256'sı ve `PRAGMA user_version` dahil — doğrulandı ve
paketin kendi testinden **daha geniş** çıktı. Dedup kimliği dört saldırıya
dayandı. `isinstance(TaskSourceId)` kontrolü düz `str`, `__eq__` override
eden `str` alt sınıfı, aynı üyeli başka bir `StrEnum` ve alt sınıflama
denemelerinin hiçbirinden geçmedi. `public_share` doğrudan DB yazımıyla
bile gate'e sızmadı. Şemalar `schemas.py`'de kaldığı için üç secret testi
yedi yeni modeli de kapsıyor. `architecture.md` güncellemesi dürüst: eski
yanlış cümle **alıntılanıp** düzeltilmiş, sessizce silinmemiş.

On sekiz mutasyonun on beşi doğru testleri kırmızıya döndürdü; kalan üçü
yukarıdaki P1/P2 bulgularıydı.

Düzeltmeler sonrası tam suite: **1331 pytest** + **206 Vitest**.
Bu inceleme bir **insan güvenlik incelemesi değildir** (ADR-0001 §5).

## Sınırlar

Gerçek DID/kasa/recovery okunmadı; Technocore'a hiçbir istek gönderilmedi;
lobby hiçbir testte hedef olmadı; yeni bağımlılık, yeni giden istemci ve
yeni HeroUI bileşeni yok; pin (`7707cb63`) ve beklenen sürüm değişmedi;
tag/release/deploy yok; PR #7'ye dokunulmadı.
