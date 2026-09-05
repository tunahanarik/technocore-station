# Proje/görev modülü temeli (Paket F)

> Kapsam kararları: [`decisions/0004-paket-f-kapsam-kararlari-2026-09-04.md`](decisions/0004-paket-f-kapsam-kararlari-2026-09-04.md)
> — **bağlayıcıdır**. Bu belge o kararların **uygulanmış** hâlini tarif eder.

Bu paket bir **temel** paketidir. Görünür bir görev yüzeyi açmaz: `work-scan`,
`tasks` ve `activity` bölümleri `ready: false` kalır (ADR-0004 §9) ve bu
sürümde görev katmanının hiçbir HTTP route'u yoktur. Açılan şey, sonraki
paketlerin (H1/H2/H3) üzerine kuracağı registry, durum makinesi, dört alanlı
kanıt modeli ve içerik sürümü kimliğidir.

---

## 1. "Modül" nedir — kayıt, dizin değil

Bir modül `station_api/modules/registry.py` içinde **derleme zamanında sabit**
bir kayıttır. Sorumlu kod yerinde durur; registry ona işaret eder.

**Proje 0 taşınmadı.** Keşif fiziksel taşımanın bedelini saydı: en az altı
test modül yollarını adıyla pinliyor (o tarihte `OUTBOUND_CLIENT_MODULES`
`technocore/` dizinini adıyla sabitliyordu — bugün kaynak köküne göreli tam
yolla —, `test_write_gate.py` literal yol kullanıyor, üç yerde route kümesi
denetleniyor) ve karşılığında hiçbir davranış kazanılmıyordu. Kayıt, sahibi olan modülleri `owners` alanında
adlandırır ve bir test her adın gerçekten bir dosyaya çözüldüğünü doğrular —
kaybolmuş bir hedefe işaret eden kayıt, kayıt olmayandan kötüdür.

| Kayıt | Durum | Sahibi olan kod / açan paket |
|---|---|---|
| `project_zero` | `available` | `identity`, `recovery`, `conformance`, `technocore`, `compose`, `evidence` |
| `work_scan` | `available` | Paket H1'de acildi |
| `agent_workspace` | `available` | Paket H2'de acildi |
| `proof_workspace` | `available` | Paket H3'te acildi |

`planned` kayıtlar `sections.ts` kalıbını izler: hedef yerleşim kod
incelemesinde görünür kalsın diye kaydedilir, fakat bir özellikmiş gibi
sunulmaz.

**Diskten yükleme yoktur.** Plugin dizini, entry-point grubu, ada göre import
ve metinden kod üretimi — hiçbiri yok. Bir güvenlik testi iki paketin
sözdizim ağacını yürüyerek dört yazımı birden arar (künye ADR-017,
AGENTS.md §2.9):

| Yazım | Örnek | Neden ayrı |
|---|---|---|
| yasak import | `import importlib`, `from importlib import import_module` | ilk sürümün yakaladığı tek şey buydu |
| yasak **ad** | `runner = __import__` | atama bir çağrı değildir; sözdizim ağacı `Call` görmez |
| yasak **attribute** | `builtins.__import__`, `mod.exec` | `__import__`/`exec`/`eval` için attribute yazımı da yasak |
| yasak **ad alanı** | `sys.modules[...] = ...`, `getattr(builtins, 'ex'+'ec')` | hiçbir şey import etmeden import makinesine ulaşır |

`compile`'ın **yalnız** bare adı yasaktır, attribute yazımı değil: `re.compile`
bir desen derleyicisidir ve bu kuralla ilgisi yoktur. Bu istisna listedeki
başka hiçbir ad için geçerli değil — eski yorum tek bir adın gerekçesini
listenin tamamı için yazıyordu ve inceleme üç ayrı yoldan yanından geçti.
`test_the_dynamic_loading_scan_catches_the_indirect_spellings` bu dört yazımın
her birini taramaya besler; `..._leaves_the_innocent_spellings_alone` ise
`re.compile` ve hesaplanmış `getattr` sütun adının temiz kaldığını denetler.

**Kayıtsız modül kimliği gösterilebilir bir rettir.** `get_module` çıplak
`KeyError` yerine `ModuleRegistryError` (bir `KeyError` alt sınıfı) yükseltir
ve `TaskService` onu `TaskError(reason="module_unknown")`'a çevirir —
geçersiz kaynağın `source_invalid` ile reddedildiği gibi. Aynı sınıf hatanın
biri gösterilebilir ret, diğeri zırhlı 500 üretmez.

### Proje 0'ın dokuz çıktısı ve üçünün dürüst durumu

Künye §7.2'nin dokuz maddesi registry'de gereksinim olarak durur. Üçü bu
sürümde **üretilemez** ve `not_implemented` raporlar — asla `passed`:

| Gereksinim | Durum | Neden |
|---|---|---|
| `profile_note_published` | `not_implemented` | Note lane bu sürümde yok (ADR-0002 §1) |
| `lobby_greeting_sent` | `not_implemented` + **politika reddi** | Lobby `DENIED_ROOMS` içinde (IMP-281, INV-05) |
| `module_marked_complete` | `not_implemented` | Görevler bölümü kapalı (ADR-0004 §9) |

`lobby_greeting_sent` ayrı bir işaret taşır (`policy_refused`). "Henüz kimse
yazmadı" ile "bu ürün bunu yapmaz" bir durum sütununda aynı görünür ve yalnız
biri bir kuyruk maddesidir. Proje 0 bu nedenle bu sürümde **tamamlanamaz** ve
`complete` daima `False`'tur.

---

## 2. Dokuz durum ve açık geçiş tablosu

`station_api/tasks/states.py`. Dokuz durum tanımlıdır ve makine
`ALLOWED_TRANSITIONS` içinde **tek yerde** yazılıdır — bu paketten önce
kurallar veritabanı kısıtlarına ve "başarısızlıkta ileri değil iptale git"
alışkanlığına dağılmıştı.

```text
awaiting_approval → running | blocked | review_needed | failed
running           → paused | blocked | review_needed | failed
paused            → running | blocked | failed
blocked           → awaiting_approval | failed
review_needed     → ready_to_publish | blocked | failed
ready_to_publish  → published | review_needed | blocked
suggested         → awaiting_approval | failed
failed            → (son durum)
published         → (son durum)
```

Geçiş doğrulaması **saf bir fonksiyondur** (`validate_transition`); servis onu
çağırır ve geçersiz geçişi reddeder.

### Üretilemeyen üç durum — artık üretilebilir

Paket F'te `suggested` bir öneri üreticisi (H1), `running` ve `paused` bir
yürütücü (H2) beklediği için üçü de **tanımlı ama üretilemez** tutulmuştu.
H1 öneri üreticisini, H2 deterministik yürütücüyü getirdi; bu yüzden
`UNPRODUCIBLE_STATES` bugün **boştur**. `validate_transition`'ın reddi
silinmedi — mekanizma yerinde durur ve bir durum yeniden üretilemez hâle
gelirse yine ateşlenir; testi bunu boş bir döngüyle değil, testin süresince
bir durumu kapatarak sürer.

Bunu **dört** test sabitler; hangisinin neyi tuttuğu ayrı ayrı yazılıdır,
çünkü ilk sürümde tek bir cümle üç ayrı iddiayı birden üstleniyordu ve
üçünden yalnız biri doğruydu:

| Test | Ne tutar | Neyi tutmaz |
|---|---|---|
| `test_no_code_path_can_produce_an_unproducible_state` | `TaskService`'in **her public metodunu** introspection ile bulur, annotation'larının izin verdiği her argümanla sürer ve ulaşılan durumları **doğrudan tablodan** okur | çağrılamayan bir üreticiyi (adı olmayan, argümanı tanınmayan) — o durumda test *hata* verir, atlamaz |
| `test_only_the_transition_method_writes_a_task_state` | `modules/` + `tasks/` sözdizim ağacında `.state`'e yazan **tek** yerin `TaskService.transition` olduğunu (atama, `setattr` ve artırmalı atama dâhil) | çalışma zamanı davranışını — bu yapısal yarıdır |
| `test_the_service_refuses_a_direct_request_for_an_unbuilt_state` | üç durum için doğrudan isteğin `state_not_producible` ile reddedildiğini | dolaylı yolları |
| `test_the_state_write_scan_would_see_a_second_writer` | yapısal taramanın gerçekten ateşlediğini (sentetik ikinci yazıcı besleyerek) | üretim kodunu |

**Oracle sabitten bağımsızdır.** `UNPRODUCIBLE_STATES` `PRODUCIBLE_STATES`'ten
türetilir ve `validate_transition` tam olarak o türetilmiş kümeye bakar; yani
`PRODUCIBLE_STATES`'e `running` eklemek hem reddi kaldırır hem beklenen kümeyi
büyütür. İnceleme bunu mutasyonla gösterdi: eski test kırılmıyordu. Beklenen
küme artık testin içinde `EXPECTED_PRODUCIBLE` olarak **elle yazılıdır** (ADR-0004
§3'ten), sabit ise ayrı bir satırda denetlenir. "Sabiti hiçbir şey açmadan
düzenlemek de kırar" cümlesi bu yüzden artık doğrudur.

Bu, `CheckState.NOT_IMPLEMENTED`'ın kuralının durum makinesine uygulanmış
hâlidir: erişilemez bir durum, sessizce erişilebilirmiş gibi durmaz.

---

## 3. Dört alan, asla tek boolean

`station_api/modules/fields.py`. `EvidenceRecord`'un dört güven seviyesi
kalıbı birebir uygulanır: dört alan, dört ayrı sütun grubu, hiçbir zaman tek
bir "tamamlandı" bayrağı.

| Alan | Ne söyler |
|---|---|
| `task_outcome` | İşin kendi çıktısı üretildi ve **denetlendi** |
| `test_result` | Çıktının üzerinde koşan denetimin sonucu |
| `user_acceptance` | Bir kişinin açık kabulü |
| `public_share` | Kanıtın bu makinenin dışında paylaşılmış olması |

`public_share` Paket F'te **doldurulamaz** bir alandı ve yokluğun
*söylenebilmesi* için vardı (Seviye 4'ün `null` yazılmasıyla aynı kural).
Paket H3 onu doldurulabilir yaptı ve **koşulu yapısal tuttu** (ADR-0009 §1):
`ref_id` yalnızca **arşivlenmiş bir gönderimin kanıt kaydı kimliği** olabilir.
Bu iki ayrı reddetmedir ve ikisi de tek başına yeterli değildir —
`EvidenceRef` yapıcısı **şekli** (32 küçük harf hex) denetler ve veritabanı
görmez; `TaskService.record_evidence` **satırın gerçekten var olduğunu**
denetler. `verified` **`ProofService` yolunda** çağırandan alınmaz: servis arşivdeki
kaydın kendi `write_outcome` değerini okur, yani `outcome_unknown` dönmüş bir
gönderim kaydedilir fakat **doğrulanmış sayılmaz**. Bu cümle önce koşulsuz
yazılmıştı ve **yanlıştı**: `TaskService.record_evidence` `verified`'ı
çağırandan alır ve bugün `write_outcome`'u `refused` olan bir kayda
`verified=True` yazan doğrudan bir çağrı `PASSED` üretebilir. Bugün o
çağrıyı açan **hiçbir HTTP rotası yok**, yani bu bir belge kusuruydu, bir
delik değil — ama koşulsuz yazılması onu deliğe çevirirdi.

Alan `PUBLICATION_FIELDS`'e **girmedi** ve girmeyecek. `ready_to_publish`'i
engellemez — dış paylaşımı bitirme koşulu yapmak, hiçbir görevin
yayımlanmadan tamamlanamaması demek olurdu.

`UNFILLABLE_FIELDS` bu yüzden **boştur**, fakat silinmedi: onu okuyan dört dal
(görev kapısı, satır okuyucu, modül tamamlanması ve yapıcı) ileride
doldurulamayan bir alan tanımlanırsa gereken reddetme mekanizmasıdır. Boş bir
küme üzerinde dönen döngü hiçbir şey kanıtlamadığı için bu dört dal, test
süresince **geçici olarak kapatılmış** gerçek bir alanla sürülür — ve
kapatmadan önce aynı yolun izinli olduğu da denetlenir (ADR-0009 §2).

**Bir kaydın varlığı tek başına başarı değildir.** `EvidenceRef.verified`'ın
varsayılanı yoktur: çağıran, işaret ettiği şeyin denetlenip denetlenmediğini
söylemek zorundadır. `verified=False` bir kayıt `blocked` raporlar, `passed`
değil. Eksik bir check `not_implemented` raporlar, `passed` değil.

`ready_to_publish` **kanıttan türer**: üç yayım alanının üçü de bu görevin
kendi içerik sürümüne karşı ayrı ayrı doğrulanmış olmalıdır. Durum elle
istenemez; `evidence_incomplete` ile reddedilir.

**Boş kontrol kümesi "hazır" değildir.** `TaskGateStatus.ready_to_publish`
önce `all(...)` idi; boş bir `all()` `True` döndüğü için `TaskGateStatus(checks=())`
hiç kanıtı olmayan bir görevi yayıma hazır sayıyordu. `evaluate()` asla boş
dönmüyordu, ama tip de engellemiyordu. Artık üç yayım alanının **var olup
geçtiği** küme eşitliğiyle sorulur: yokluk, başarısızlık kadar yüksek sesle
engeller. `blocking_fields` de aynı gerekli kümeden türetilir.

**Kanıt işaretçisi de süpürülür ve sınırlanır.** `detail` ve `title`
`sweep_untrusted(...)[:200]`'den geçiyordu; `ref_id` ham geçiyordu ve bidi
override, NUL ve 406 karakterlik bir değer `TaskFieldStatus.ref_id`'ye kadar
ulaşıyordu (`String(64)` var ama SQLite dayatmıyor). `ref_id` artık süpürülüp
`MAX_REF_ID_CHARS` = 64'e kesilir; hiçbir şeye inen bir işaretçi
`evidence_field_refused` ile reddedilir. Bugün önünde route yok — H1/H2
devralacağı için şimdi kapatıldı.

**Bayat sürüm kontrolü iki yolda da testlidir.** `tasks/gate.py` ve
`modules/completion.py` aynı karşılaştırmayı ayrı ayrı yapar. İkincisi
kapsanmıyordu: karşılaştırmasını `if False` yapmak hiçbir testi kırmıyordu,
çünkü oraya varan her durumda `verified` zaten `False`'tu.
`test_a_module_check_refuses_evidence_bound_to_another_content_version`
doğrulanmış ama **başka sürüme bağlı** bir referansla o dalı doğrudan sürer.

---

## 4. Deduplication: içerik sürümü kimliği

```python
source_version_id = domain_digest(
    b"technocore-station/task-source/v1", source_id, content_sha256
)
```

`source_id` **registry enum'undan** gelir (`TaskSourceId`), çağıranın verdiği
serbest string'ten değil. `StrEnum` her `isinstance(value, str)` kontrolünden
geçtiği için serbest metni dışarıda tutan tek şey açık bir enum kontrolüdür ve
o kontrol oradadır.

İçerik değişince kimlik değişir ve **eski kanıt eşleşmez**: kanıt kaydı hangi
sürüme karşı üretildiğini taşır, kapı karşılaştırır ve uyuşmazsa `blocked`
raporlar — yok saymaz, gerekçesiyle reddeder. Bu, `verdict_id`'nin fail-closed
okumasının birebir uygulamasıdır.

---

## 5. Restart uzlaştırması: okur, yazmaz

`station_api/tasks/reconciliation.py`.

Keşif bulgusu: `WriteOutcomeValue.IN_FLIGHT` Paket D'den beri yazılıyor ve
**hiçbir başlangıç hook'u onu okumuyordu**. `app.py`'de `lifespan`/`on_event`
yok; çökmüş bir gönderim veritabanı ömrü boyunca `in_flight` kalıyordu.

Paket F yalnız okuma yarısını kapatır. Tarama uygulama kurulurken bir kez
koşar (`app.state.task_reconciliation`), tek bir `SELECT` yapar ve:

- **hiçbir giden istek göndermez.** Test, httpx taşıyıcısını ve
  `socket.connect`'i sayarak tarama sırasında süreçten çıkan istek sayısının
  **sıfır** olduğunu ölçer (gerçek `create_app` çağrısıyla birlikte);
- **hiçbir satırı değiştirmez.** Defter taramadan önce ve sonra bayt bayt
  aynıdır ve satır hâlâ `in_flight`'tır;
- **hiçbir gönderimi sürdürmez.** `ReconciliationReport.resumed_any` bir alan
  değil, `Literal[False]` dönen bir **property**'dir: kurucu argümanı yoktur,
  yani `ReconciliationReport(..., resumed_any=True)` `TypeError` verir. Daha
  önce varsayılanı `False` olan sıradan bir alandı ve `Literal[False]` olan
  yalnız Pydantic modeliydi — "yapısal" cümlesi bir katman öteyi tarif
  ediyordu. `tasks/views.py` de değeri artık **rapordan okur**
  (`resumed_any=report.resumed_any`); modelin kendi varsayılanına bırakmak
  "F alanı hiç doldurmadı" demekti, "tarama öyle söyledi" değil.

Devam kararı kullanıcınındır ve devam edilirse bütün kontroller baştan koşar
(ADR-0003 §4'ün daralmasıyla aynı biçim: yakalama denenebilir, yeniden
gönderim asla).

---

## 6. Bütçe bu pakette **yoktur** — ertelendi, düşürülmedi

Gereksinim "devam kararı onay/**bütçe**/izinlerle uzlaştırılsın" diyor. Depoda
bütçe kavramı yok (`budget` yalnız HTTP timeout bütçesi olarak geçiyor) ve
yürütme planı bütçe/izin sınırını **H2**'ye, harcama bağlamını **G**'ye
koyuyor.

**Karar (ADR-0004 §7):** Paket F bütçe alanı **açmaz** ve bütçe varmış gibi
davranmaz. Onay ve izin yarısı F'de karşılanır: hiçbir şey onaysız
ilerlemez ve `ready_to_publish` kanıtsız verilmez.

Bu erteleme sessiz değildir:

- `TaskStatusResponse.budget_available` `Literal[False]`'tur ve
  `budget_detail` ertelemeyi cümleyle söyler — composer'ın
  `note_lane_available` alanıyla aynı kalıp;
- `test_the_task_layer_opens_no_budget_field` görev/registry paketlerinde
  bütçe biçimli bir sütun veya tanımlayıcı olmadığını denetler;
- `test_the_deferral_is_recorded_in_the_documents` bu bölümün varlığını
  denetler.

**Kalan yarım gereksinim (F'te):** harcama bağlamı Paket G'ye, bütçe/izin
sınırı Paket H2'ye ertelenmişti. **Her ikisi de kapandı:** G harcama
bağlamını getirdi, H2 bütçeyi yeni `agent/` paketinde açtı — araç çağrısı
sayısı, duvar saati ve eşzamanlılık. Token ve para birimi **sayılmaz** ve bu
ret telde `refused_units` olarak yayımlanır. Görev katmanına (`tasks/`,
`modules/`) **bütçe alanı eklenmedi** — dosyaların kendisi H2'de durum
makinesi için değişti, ama `test_the_task_layer_opens_no_budget_field`
bütçe biçimli hiçbir tanımlayıcıya izin vermiyor, dolayısıyla yukarıdaki
"F bütçe alanı açmaz" kararı bugün de doğrudur.

---

## 7. Yeniden kullanılan çekirdek, kopyalanmayan üç şey

ADR-0004 §2'nin yasakladığı üç kopyalama:

- **Yeni HTTP istemcisi yok.** `modules/` ve `tasks/` paketlerinde `httpx`,
  `socket`, `urllib` veya herhangi bir giden istemci import'u yoktur (testle).
  (`OUTBOUND_CLIENT_MODULES` bu yazıldığında üçte kilitliydi; Paket G
  OpenCode bağlantısı için bilinçli olarak dördüncüyü açtı — orada, buradan
  değil.)
- **İkinci vault/signer yok.** İki paket de `station_api.vault` ve
  `station_api.compose` sınırına dokunmaz (testle).
- **İkinci gate yok.** `tasks/gate.py` `write_gate.evaluate()`'in saf-fonksiyon
  kalıbını izler ve onun `CheckState`'ini **import eder**; paralel bir enum
  tanımlamaz (testle). Yazma kapısı değişmedi ve composer onu üç adımında da
  yeniden koşturmaya devam ediyor.

Bağımlılıklar constructor'dan gelir (`ComposeService` kalıbı); `TaskService`
yalnız `engine` alır ve hiçbir bağımlılığını kendisi yaratmaz. Registry
**import edilir, enjekte edilmez**: modül kümesi bir constructor argümanı
olduğu anda onu üreten bir şey gerekir ve o şeyin bariz hâli bir dosyadır.

---

## 8. Şemalar `schemas.py`'de

`tests/security/test_no_secret_fields.py`'nin üç testi de `vars(schemas)` ile
yalnız `station_api/schemas.py`'yi tarar. Görev modellerini yeni bir modüle
koymak bu üç korumayı **sessizce kapsam dışı** bırakırdı — sızıntı değil,
koruma kaybı, ve tam da bu projenin yakalamak istediği türden sessiz gerileme
(ADR-0004 §8). Modeller `schemas.py`'de; onları dolduran saf projeksiyon
fonksiyonları `station_api/tasks/views.py`'dedir.

---

## 9. Depolama

Migration `0007` (`down_revision = "0006"`, tek head). Yalnız ekleme yapar;
hiçbir mevcut tablo, sütun veya kayıt kimliği değişmez.

| Tablo | İçerik |
|---|---|
| `task_record` | Bir görev: modül, kaynak, içerik özeti, sürüm kimliği, durum |
| `task_evidence_outcome` | **Dört alan, dört ayrı sütun grubu** (her biri `_ref_id`, `_verified`, `_version_id`, `_detail`, `_recorded_at`) |
| `task_state_transition` | Kabul edilen her durum değişikliği, yalnız-ekleme |

Hiçbir sütun adında `seed`, `secret`, `key`, `private`, `mnemonic`,
`passphrase` veya `password` geçmez; görev tabloları için bu denetim
`key` parçasını da kapsayacak şekilde şema geneli kuraldan **daha sıkıdır**.
Saklanan her değer bir registry kimliği, bir digest, public bir işaretçi veya
Türkçe bir cümledir.

**Aşama numarası tek bir sayıdır.** `launcher.py` ve `cli/__main__.py`
veritabanını açarken, `routes/api.py` ise `/api/app/status` üzerinden
gösterirken aynı numarayı taşır. `cli/__main__.py` üç sürüm geride
(`stage=3`) kalmıştı ve hiçbir şey bunu söylemiyordu; uygulamanın kendini test
edilen sürümden eski göstermesi küçük bir yalandır.
`test_every_entry_point_names_the_same_release_stage` üç üretim çağrısını da
tarar ve hepsinin `CURRENT_SCHEMA_STAGE` ile aynı olmasını ister.
