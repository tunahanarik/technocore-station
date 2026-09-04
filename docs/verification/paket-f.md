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
| pytest | **1302 geçti** (1229 → 1302; +73: registry 17, durumlar 20, kanıt 36) |
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

(PR üzerinde doldurulacak — temiz bağlamlı reviewer subagent koşulacak; bu
insan güvenlik incelemesi değildir, ADR-0001 §5 kalan risk.)

## Sınırlar

Gerçek DID/kasa/recovery okunmadı; Technocore'a hiçbir istek gönderilmedi;
lobby hiçbir testte hedef olmadı; yeni bağımlılık, yeni giden istemci ve
yeni HeroUI bileşeni yok; pin (`7707cb63`) ve beklenen sürüm değişmedi;
tag/release/deploy yok; PR #7'ye dokunulmadı.
