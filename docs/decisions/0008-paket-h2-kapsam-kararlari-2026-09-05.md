# ADR-0008 — Paket H2 kapsam kararları (5 Eylül 2026)

Durum: **kabul edildi** · Bağlam: uçtan uca prompt §13 (Agent çalışma ortamı, Activity Desk)

Bu paket agent'ın gerçekten araç çalıştırdığı yerdir. Keşif on karar boşluğu
çıkardı. ADR-0001…0007 gibi bu da künyeye üstündür ve **hiçbir güvenlik
değişmezini gevşetmez**.

## 1. Keyfi kod/shell yürütmesi KAPALI

Prompt: *"Güvenilir izolasyon yoksa arbitrary code/shell yürütmesini kapat;
bunu UI'da açık `execution_unavailable` nedeni olarak göster."* Ve ayrıca:
*"Yeni Docker/WSL/VM/global servis kurulumunu veya admin yetkisini
kendiliğinden yapma."*

Ölçüm (hiçbir şey kurulmadan, hiçbir konteyner çalıştırılmadan): **Docker
Desktop 4.89.0 kurulu ve daemon cevap veriyor**; WSL2 var; Windows Sandbox
**yok**; Hyper-V yönetim yüzeyi **yok**; kullanıcı **local admin değil**;
`Get-WindowsOptionalFeature` admin istediği için feature durumları
**ölçülemedi**.

**Karar: yürütme yine de kapatılır.** Docker'ın bu makinede bulunması onu
ürünün garantisi yapmaz:

1. Ölçülen tek gerçek sandbox Docker/WSL2'dir; AppContainer/Job Object için
   ne kütüphane ne kod var, ve "ayrı klasör + `subprocess`" promptun açıkça
   reddettiği şeydir.
2. Docker bir **kullanıcı kurulumudur, ürünün değil**. Station
   `%LOCALAPPDATA%`'ya kurulan, admin istemeyen, loopback-only bir masaüstü
   uygulaması. Docker'ın kurulu, açık ve kullanıcının `docker-users`
   grubunda olmasını ön koşul yapmak, ürünün kendi kurulum sözleşmesini
   değiştirir — bu bir mimari karardır, H2'nin sessizce varsayacağı bir şey
   değil.
3. **Test edilemez.** Konteyner çalıştıran bir yol CI'da veya temiz bir
   makinede doğrulanamaz; yerel imaj varlığı bu makineye özgüdür ve
   `docker pull` yasak bir dış istektir.

`execution_unavailable` bir **durum gerekçesi** olarak tanımlanır ve
`TransitionVerdict.reason` kalıbını kullanır. Docker "kayıtlı ama
uygulanmadı" olarak yazılır (ADR-0005 §2'nin streaming kalıbı: yokluk
söylenir, uydurulmaz).

**Rapor/patch üretimi ve deterministik araçlar çalışmaya devam eder.**
Ürün kaynağında bugün hiç `subprocess`/`exec`/`eval` yok; H2 bunu
**getirmez**.

## 2. Model lane'i kapalı kalır; araç şeması Station'ındır

Keşif bir varsayımı düzeltti: `post_completion` **zaten var**
(`opencode/client.py`) ve üç protokol ailesinin non-streaming şekli de var.
Eksik olan üç şey: prodüksiyon çağıranı, HTTP rotası, ve **tool-call wire
formatı** — sonuncusu ADR-0005 §1.2'ye göre **yayımlanmamıştır**.

**Karar:** `tool_calls_supported: Literal[False]` **değişmez**;
`post_completion` prodüksiyonda çağrılmaz; altıncı giden yüzey açılmaz.

Fakat **aracın kendi şeması** (ad, tipli parametreler, izin kapsamı, bütçe
maliyeti) **Station'ın kapalı registry'sidir** — `SOURCES`,
`write_targets`, `evidence_targets`, `workscan/targets` ve `MODEL_MAPPINGS`
kalıbının altıncısı. Bu uydurma değildir çünkü hiçbir dış sözleşmeyi iddia
etmez.

Böylece promptun "model çıktısı doğrudan yürütülmez" kuralı **boş bir vaat
değil, yapısal bir gerçek** olur: bu sürümde model çıktısı diye bir şey
yoktur.

## 3. `RUNNING` ve `PAUSED` açılır — deterministik araç koşusu için

`ALLOWED_TRANSITIONS` kenarları zaten taşıyor ve tablo **değişmez**.
`INITIAL_STATE` `AWAITING_APPROVAL` **kalır**.

`RUNNING` = "sunucu şu an tanımlı bir araç zincirini yürütüyor";
`PAUSED` = kullanıcı durdurdu. Model ve shell yok.

**Çalıştırılmamış kod test edilmiş sayılmaz:** test sonucu alanı
`not_implemented` kalır, dolayısıyla görev `review_needed`/`blocked`'ta
durur ve `ready_to_publish`'e **geçemez** (SI-222 zaten bunu zorluyor).

**Dürüstlük şartı:** `UNPRODUCIBLE_STATES` boşalınca bazı testler **boş
parametreyle sessizce yeşile** düşer. Bunlar **sessizce bırakılamaz**: ya
"artık üretilemez durum yok" iddiasına çevrilir ya kaldırılır. Boş bir
döngü, geçen bir test gibi görünen hiçbir şey kanıtlamaz.
`STATE_DETAIL[RUNNING]`/`[PAUSED]`'ın "bu sürümde hiçbir kod yolu bu durumu
üretemez" cümleleri **yalan olur** ve düzeltilir; SI-216 ve SI-277
güncellenir, silinmez.

**Tehlike:** `_state_writers` yalnız `modules/` ve `tasks/` ağaçlarını
tarıyor. Yürütücü yeni bir `agent/` paketindeyse ve orada duruma yazarsa
tarama **görmez** — `PACKAGE_F_DIRS` genişletilmeli, yoksa SI-226 sessizce
delinir.

## 4. Bütçe açılır: yalnız ölçülebilir birimler

**Karar:** birimler **araç çağrısı sayısı**, **duvar saati süresi** ve
**eşzamanlılık (=1)**. Token ve para birimi **yok** — SI-250 zaten
"sağlayıcıdan gelmiyorsa `unknown`, sıfır uydurulmaz" diyor ve model lane'i
kapalıyken token diye bir şey yoktur.

Kod **yeni `agent/` paketine** girer, `tasks/` ve `modules/` **dokunulmaz**
— `test_the_task_layer_opens_no_budget_field` o iki ağaçta `budget|cost|
spend|quota|credit` içeren **hiçbir tanımlayıcıya** izin vermiyor, ve
SI-225'in "görev katmanında bütçe yok" iddiası böylece **harfiyen doğru
kalır**.

**"Agent kendi bütçesini yükseltemez" yapısal olur:** tavan derleme
zamanında yazılmış bir `frozen dataclass`'tır, araç registry'sinde bir araç
olarak **temsil edilmez**, ve tavana yazan hiçbir kod yolu yoktur — tavan
hiç yazılmaz, yalnız okunur. Bunu bir AST taraması sabitler
(`test_only_the_transition_method_writes_a_task_state` kalıbı).

## 5. Workspace: veri dizini altında, savunması sıfırdan

**Karar:** `<data_dir>/workspace/v1/<32-hex task_id>/` — `vault/paths.py`'nin
sürümlü + doğrulanmış-kimlik kalıbı. Buraya konması bir avantaj getirir:
`test_no_plaintext_artefact_is_left_in_the_data_directory` veri dizinindeki
**her dosyayı** okur, yani workspace seed **ve** API-anahtarı canary'si
taramasına **otomatik** girer.

**Emsal yok:** depoda hiçbir yerde symlink/junction/reparse/zip-slip
savunması yok. Sıfırdan yazılır: her yazımda `resolve()` +
`is_relative_to(workspace_root.resolve())`, symlink/junction oluşturma
yasağı, dosya adı `downloads`'un sanitizer'ından, ve toplam bayt/dosya
sayısı tavanı. Dizin ACL'i uygulanır (SI-265 kalıbı).

**Arşiv açma yolu hiç olmaz** — zip-slip yüzeyi doğmaz. Dış koddan gelen
hiçbir şey açılmaz.

## 6. Activity Desk: ayrı tablo, yalnız karar noktaları zincire

`AuditEventName` kapalı bir enum (beş üye) ve zincir **asla budanmaz**
(ADR-0003 §7).

**Karar: iki katman, karıştırılmaz.**

- **`activity_event` ayrı, yalnız-ekleme tablo** — adım adım kayıt,
  hacimli, kendi retention'ı (`RETAINED_CHECKS` kalıbı, emsali var).
- **Yalnız karar noktaları zincire girer**: yeni `AuditEventName` üyeleri
  (`task_execution_refused`, `tool_call_refused`, `budget_exhausted`,
  `execution_unavailable`, `activity_deleted`). Bunlar sınırlı sayıdadır ve
  kullanıcı/politika kaynaklıdır; zincir budanmadan da patlamaz.

Böylece "sessiz silme Evidence/audit bütünlüğünü bozmasın" kuralı ile
"zincir budanmaz" kararı uzlaşır: activity satırları **zincir linki
değildir**, silinmeleri hiçbir MAC'i kıramaz. Kullanıcı bir kaydı silerse
**silme işlemi zincire bir olay olarak yazılır**. Otomatik budama
uygulanırsa **zincirin referans verdiği hiçbir satır budanamaz** kuralı
yapısal olur.

Timeline'a **modelin gizli muhakemesi veya ham provider payload'ı
yazılmaz** (model lane'i zaten kapalı). Sahte progress yok; olaylar
backend'den gelir.

## 7. Güven sınırı: geliştirme yetkisi ürüne miras verilmez

Prompt: *"Geliştirme sırasında Claude'a verilmiş commit/PR/merge yetkisini
son üründeki agent'a miras verme."*

**Karar:** Runtime agent'ın araç registry'sinde git, PR, merge, paket
kurulumu, ayar düzenleme, izin listesi değiştirme veya plugin ekleme
**yoktur ve eklenemez** — registry derleme zamanıdır ve runtime'da hiç
yazılmaz. Agent signer, vault, recovery, provider credential, global
environment, kullanıcı home'u ve Station'ın kendi kaynak reposuna
erişemez; bunların çoğu SI-213 ile **zaten yapısal olarak** kapalı ve o
yasak yeni `agent/` paketine de taşınır (aksi halde yeni paket muaf olur).

## 8. Bölümler birlikte açılır

`tasks` (`Gorevler`) ve `activity` (`Aktivite`) **birlikte** `ready: true`
olur — aksi halde Activity Desk sahibi olmayan olayları gösterir.
`App.test.tsx`'in testi **değişmez**, yalnız verisi güncellenir (ADR-0007
§9 kalıbı). `modules/registry.py`'de `AGENT_WORKSPACE` kaydı `PLANNED →
AVAILABLE`'a taşınır ve `owners` doldurulur.

## 9. Diğer bağlayıcılar

Şemalar **`schemas.py`'ye** eklenir — `test_no_secret_fields.py`'nin üç
testi `vars(schemas)` ile **yalnız o modülü** tarıyor; ayrı bir modül
sessizce muaf olurdu. Aşama numarası **beş** giriş noktasında `7 → 8`
(SI-232/SI-262). H2 kendi paketindeki **her string literal'i tarayan** bir
yasak-ifade denetimi kurar (SI-280 kalıbı). `OUTBOUND_CLIENT_MODULES`
**beşte kalır**. Yeni bağımlılık **yok**; HeroUI kümesi 11'de kalmalı,
gerekirse önce MCP'den doğrulanır. Dosya adları `.gitignore` ile
çakışmamalı (Paket G dersi).

## 10. Değişmeyenler

Gerçek harcama yok, gerçek yazma yok, gerçek anahtar/DID/seed yok. Açılışta
otomatik devam yok (SI-224). Zamanlayıcı/arka plan/long-poll yok (SI-272).
Durdur düğmesi yeni araç çağrısını engeller ve iptal sonrası geciken yanıt
yan etki üretemez. Çökme sonrası plan/durum yüklenebilir ama **eski onayla
yeni dış paylaşım veya otomatik tekrar başlamaz**. İnsan güvenlik
incelemesi ertelenmiş kalan risktir (ADR-0001 §5).
