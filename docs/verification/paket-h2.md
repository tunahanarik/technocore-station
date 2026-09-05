# Paket H2 doğrulama raporu — Agent çalışma ortamı ve Activity Desk

Tarih: 2026-09-05 · Kapsam kararları:
[`ADR-0008`](../decisions/0008-paket-h2-kapsam-kararlari-2026-09-05.md).

## En büyük karar: yürütme kapalı

Prompt açık: *"Güvenilir izolasyon yoksa arbitrary code/shell yürütmesini
kapat"* ve *"Yeni Docker/WSL/VM kurulumunu veya admin yetkisini
kendiliğinden yapma."*

Ölçüm (hiçbir şey kurulmadan, hiçbir konteyner çalıştırılmadan): **Docker
Desktop 4.89.0 kurulu ve daemon cevap veriyor**; WSL2 var; Windows Sandbox
**yok**; Hyper-V yönetim yüzeyi **yok**; kullanıcı **local admin değil**;
optional feature durumları admin gerektiği için **ölçülemedi**.

**Yürütme yine de kapatıldı**, üç sebeple: (a) Docker bir **kullanıcı
kurulumudur, ürünün değil** — Station admin istemeyen, `%LOCALAPPDATA%`'ya
kurulan bir masaüstü uygulaması ve Docker'ı ön koşul yapmak kendi kurulum
sözleşmesini değiştirir; (b) ölçülen tek gerçek sandbox odur, AppContainer/
Job Object için ne kod ne kütüphane var ve "ayrı klasör + `subprocess`"
promptun açıkça reddettiği şeydir; (c) konteyner çalıştıran bir yol CI'da
veya temiz bir makinede **doğrulanamaz** — yerel imaj varlığı bu makineye
özgü, `docker pull` yasak bir dış istek.

`execution_unavailable` bir **durum gerekçesi** olarak tanımlandı ve UI'da
ölçülen envanterle birlikte gösteriliyor; `not_measured` ile `absent`
bilinçli olarak **ayrı** tutuluyor. Docker "kayıtlı ama uygulanmadı" olarak
yazıldı.

**Çalıştırılmamış kod test edilmiş sayılmıyor:** test sonucu alanı
`not_implemented` kalıyor, dolayısıyla görev `ready_to_publish`'e
**geçemiyor**. Ürün kaynağında `subprocess`/`exec`/`eval`/`os.system`
**hâlâ yok** ve bu paket onu getirmedi.

## Model lane'i kapalı; araç şeması Station'ın

Keşif bir varsayımı düzeltti: `post_completion` ve üç protokol ailesinin
non-streaming şekli **zaten vardı**. Eksik olan **tool-call wire
formatıydı** ve o hâlâ yayımlanmamış (ADR-0005 §1.2).

`tool_calls_supported: Literal[False]` **değişmedi**; `post_completion`
prodüksiyonda **çağrılmıyor**; `OUTBOUND_CLIENT_MODULES` **beşte kaldı**.

Fakat **aracın kendi şeması** Station'ın **altıncı kapalı registry**'si:
derleme zamanı tuple, `frozen dataclass`, `StrEnum` kimlikler, tipli
parametreler — ve **`path`/`url` parametresi yok**, yani araca adres
verilemez. Sekiz araç: onaylı snapshot okuma, workspace dosyası okuma,
üretme, güncelleme, üç deterministik doğrulayıcı, run durumu. Durdur/devam
bilerek **araç değil**, yalnız kullanıcı rotası. Kayıtsız kimlik
**gösterilebilir bir ret** döndürüyor.

Böylece "model çıktısı doğrudan yürütülmez" kuralı boş bir vaat değil,
**yapısal bir gerçek**: bu sürümde model çıktısı diye bir şey yok.

## Güven sınırı: geliştirme yetkisi ürüne miras verilmedi

Araç registry'sinde git, PR, merge, paket kurulumu, ayar düzenleme, izin
listesi değiştirme ve plugin **yok** — ve bu **import zamanında**
denetleniyor, ekili bir `git_commit` kaydıyla sürüldü. Agent signer, vault,
recovery, provider credential, global environment, kullanıcı home'u ve
Station'ın kendi reposuna erişemiyor; SI-213'ün yasağı yeni `agent/`
paketine de **taşındı**, yoksa yeni paket muaf kalırdı.

## Bütçe: yalnız ölçülebilir birimler, reddedilenler yayımlı

Birimler: **araç çağrısı (32), duvar saati (120 sn), eşzamanlılık
`Literal[1]`**. Token ve para birimi **gerekçesiyle reddedildi** ve telde
`refused_units` olarak **yayımlanıyor** — sessizce yok sayılmadı.

"Agent kendi bütçesini yükseltemez" üç kilitle yapısal: tavan derleme
zamanı `frozen` sabiti; registry'de tavanı değiştiren araç yok; ve **hiçbir
kod yolu yazmıyor** — dört yazımı (atama, öznitelik, artırmalı, `setattr`)
tarayan bir AST testi ekili bir yazıcıyla sürülüp dört offender gördü.

`tasks/` ve `modules/` **hiç dokunulmadı**, dolayısıyla SI-225'in "görev
katmanında bütçe yok" iddiası **harfiyen doğru kaldı**; yalnız
`BUDGET_DETAIL`'in "H2'ye ertelenmiştir" cümlesi artık yalan olacağı için
güncellendi.

## Workspace: savunma sıfırdan yazıldı

`<data_dir>/workspace/v1/<32-hex>`. Depoda symlink/junction/zip-slip
emsali **yoktu**. Dört katman: ad allow-list'ten **yeniden kurulur ve
yeniden yazılacaksa reddedilir** (kısaltılmaz); her okuma/yazımda
`resolve()` + `is_relative_to`; dosyadan köke kadar `is_symlink()` **ve**
`os.path.isjunction()`; tavanlar (64 dosya / 512 KiB / 4 MiB) **diskten**
okunur. **Arşiv açma yolu hiç yok** — zip-slip yüzeyi doğmadı.

Kırma denemeleri: 15 düşmanca ad (`../`, `..\`, `..%2f`, mutlak yol, UNC,
`/etc/passwd`, `con.json`, NUL, CRLF, bidi, aşırı uzunluk), iki görev arası
okuma, yaprakta **ve üst dizinde** bağ, listeleme sırasında bağ — hepsi
reddedildi. Symlink işletim sistemi izin verdiğinde **gerçekten
oluşturulup** denendi; vermediğinde predikat zorlandı, yani hiçbir makinede
sessiz skip yok.

## Durum makinesi: boşalan testler sessiz bırakılmadı

`RUNNING`/`PAUSED` açıldı; `ALLOWED_TRANSITIONS` ve `INITIAL_STATE`
**değişmedi**; `UNPRODUCIBLE_STATES` boşaldı.

Üç test boş parametreyle **sessizce yeşile düşecekti**; hiçbiri öyle
bırakılmadı. Saf-fonksiyon testi artık mekanizmayı **sürüyor** — bir durum
test süresince kapatılıyor ve kapatmadan **önce** aynı kenarın izinli
olduğu da denetleniyor, yoksa "her şeyi reddeden" bir fonksiyon da geçerdi.
Servis testinin sessiz-skip'e düşen boş `parametrize`'ı kaldırıldı ve bugün
gerçekten karşılaşılan ret kendi testine kavuştu. Tablo testi vacuous
değildi ama adı yanlıştı; yeniden adlandırılıp iddiaları güçlendirildi.

`STATE_DETAIL[RUNNING]`/`[PAUSED]`'ın "bu sürümde hiçbir kod yolu bu durumu
üretemez" cümleleri **yalan olduğu için düzeltildi**. `_state_writers`
taraması `agent` paketini de kapsıyor — yoksa SI-226 sessizce delinirdi.

Frontend'de aynı sorun aynı disiplinle ele alındı: `HIDDEN_SECTIONS` artık
elle yazılmış bir liste değil, `SECTIONS`'tan **türetiliyor**, ve boşluğu
kendi adlandırılmış iddiası olarak ölçülüyor. `never shows a section that is
not ready` testinin gövdesi **değişmedi** ve onuncu hazır-olmayan bölüm
kaydedildiği gün yine ateşlenecek.

## Activity Desk: ayrı tablo, yalnız karar noktaları zincirde

Ayrı **yalnız-ekleme** `activity_event` tablosu, kendi retention'ı (500),
satırları zincir halkası **değil**. Zincire yalnız **beş karar noktası**
giriyor. `chain_referenced` bayrağı append başarılı olduktan **sonra**
yazılıyor; retention ve kullanıcı silmesi işaretli satırı **reddediyor**.
Silme bir audit olayı (`activity_deleted`) ve sonrasında zincir `INTACT`
doğrulanıyor; iki sayı **ayrı** raporlanıyor.

Modelin muhakemesi veya ham provider payload'ı için **sütun yok** (şema
testi + yanıt anahtarı testi). On dört eylem, on dört etiket; yük taşıyan
beşi benzersiz **etiket sayısıyla** test ediliyor (`Set(labels).size === 5`),
yalnız varlıkla değil. `approval_awaited` `bekliyor` render ediyor, asla
`tamam` değil. Sahte progress yok.

## Mutasyon kontrolü ve yakalanan gerçek kusur

Ürün kaynağı fiilen düzenlenip geri yüklendi:

| Mutasyon | Ölçülen |
|---|---|
| `ActivityLog.record`'daki guard çağrısı silindi | **3 kırmızı** |
| `read_text`'teki reparse-point yürüyüşü silindi | **2 kırmızı** |
| `start_run`'daki `_assert_plan_intact` silindi | **1 kırmızı** |
| `safe_name` reddetmek yerine yeniden adlandırdı | **17 kırmızı** |

Ayrıca ekili `subprocess`/`exec`/`os.system`, ekili `git_commit` aracı,
dört yazımlı tavan yazıcısı, düzenlenmiş plan ve adım argümanları, çağrı
sırasında kalkan durdurma bayrağı.

**Mutasyon gerçek bir kusur yakaladı:** `activity._clean` denetimden
**önce** nötrlüyordu ve guard'ı sessizce no-op yapıyordu — koruma orada
duruyor görünüyordu ama hiçbir şey yakalamıyordu. Nötrleme servis sınırına
taşındı (IMP-420).

## Testler ve kapılar (birleşik ağaç, orkestratör koşusu)

| Kapı | Sonuç |
|---|---|
| pytest | **1974 geçti** (1769 → 1974; +205) |
| Vitest | **289 geçti** (256 → 289) |
| Playwright (e2e) | **65 geçti** (58 → 65) |
| ruff (iki koşu) / mypy strict | geçti / 0 hata |
| eslint / build | geçti / geçti |
| `git diff --check` | 0 |

Yeni HeroUI bileşeni **yok** (küme 11'de). Yeni bağımlılık yok. Aşama
numarası **beş** giriş noktasında ve suite'in pinli sabitinde `7 → 8`.
Mevcut testlerden hiçbiri silinmedi/gevşetilmedi; gerçekleri değiştiği için
**kaydedilerek** güncellenenler ayrıca yazıldı.

## Kalan riskler

1. **Yürütme kapalı olduğu için bu sürüm kod çalıştıramaz.** Çalıştırma
   gerektiren iş `blocked`/`review_needed`'da durur ve bu bir eksiklik
   değil, kayıtlı bir karardır (ADR-0008 §1).
2. **Model lane'i kapalı** — tool-call sözleşmesi yayımlanana kadar.
3. **Junction yalnız zorlanmış predikatla sürüldü**; gerçek NTFS junction
   ya admin ya `subprocess` ister, ikisi de yasak. Symlink gerçekten
   oluşturulup denendi.
4. **Tarayıcı QA otomatik**; plan bestecisinin tipli parametre alanlarına
   insan gözü değmedi (ertelenmiş manuel kabul, ADR-0001 m.4).
5. e2e agent spec'i `/api/tasks*` ve `/api/activity*`'yi mock'luyor; render
   ve etkileşimi kanıtlıyor, runner davranışını değil. A11y/CSP/klavye
   döngüleri **canlı backend'e** karşı koşuyor (boş görev listesiyle).
6. **HeroUI `Card.Title` h1→h3 boşluğu** iki yeni bölümde de geçerli;
   run kartı başlıkları `h4` yapıldı, yani hiçbir atlama bir seviyeyi
   aşmıyor.
7. İnsan güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5) — bu
   paketin savunmalarının çoğunun deponun kalanında **emsali yoktu**.

## Bağımsız inceleme sonucu

(PR üzerinde doldurulacak — temiz bağlamlı reviewer subagent koşulacak; bu
insan güvenlik incelemesi değildir, ADR-0001 §5 kalan risk.)

## Sınırlar

Hiçbir dış servise istek gönderilmedi; hiçbir şey kurulmadı; hiçbir
konteyner çalıştırılmadı. Gerçek DID/kasa/recovery/API anahtarı okunmadı;
lobby hiçbir testte hedef olmadı; yeni bağımlılık yok; pin (`7707cb63`) ve
beklenen sürüm değişmedi; tag/release/deploy yok.
