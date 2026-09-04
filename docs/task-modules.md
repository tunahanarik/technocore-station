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
test modül yollarını adıyla pinliyor (`OUTBOUND_CLIENT_MODULES`
`technocore/` dizinini adıyla sabitliyor, `test_write_gate.py` literal yol
kullanıyor, üç yerde route kümesi denetleniyor) ve karşılığında hiçbir
davranış kazanılmıyordu. Kayıt, sahibi olan modülleri `owners` alanında
adlandırır ve bir test her adın gerçekten bir dosyaya çözüldüğünü doğrular —
kaybolmuş bir hedefe işaret eden kayıt, kayıt olmayandan kötüdür.

| Kayıt | Durum | Sahibi olan kod / açan paket |
|---|---|---|
| `project_zero` | `available` | `identity`, `recovery`, `conformance`, `technocore`, `compose`, `evidence` |
| `work_scan` | `planned` | Paket H1 |
| `agent_workspace` | `planned` | Paket H2 |
| `proof_workspace` | `planned` | Paket H3 |

`planned` kayıtlar `sections.ts` kalıbını izler: hedef yerleşim kod
incelemesinde görünür kalsın diye kaydedilir, fakat bir özellikmiş gibi
sunulmaz.

**Diskten yükleme yoktur.** Plugin dizini, entry-point grubu, ada göre import
ve metinden kod üretimi — hiçbiri yok. Bir güvenlik testi iki paketin
sözdizim ağacını yürüyerek `importlib`, `pkgutil`, `__import__`, `exec`,
`eval`, `import_module`, `iter_modules`, `entry_points` ve benzerlerini arar
(künye ADR-017, AGENTS.md §2.9).

### Proje 0'ın dokuz çıktısı ve ikisinin dürüst durumu

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

### Üretilemeyen üç durum

`suggested` bir öneri üreticisi (H1), `running` ve `paused` bir yürütücü (H2)
ister. Üçü de **tanımlı kalır** — tablodan silmek H2'nin makineyi hafızadan
yeniden türetmesi demek olurdu — fakat **hiçbir kod yolu onları üretemez**:
`validate_transition` hedef `UNPRODUCIBLE_STATES` içindeyse geçişi adıyla
reddeder.

Bunu iki test sabitler:

- `test_no_code_path_can_produce_an_unproducible_state` — gerçek servisi
  gerçek veritabanı üzerinde makinenin sunduğu her geçişten sürer, **ulaşılan
  durumların kümesini toplar** ve `PRODUCIBLE_STATES` ile karşılaştırır.
  Gelecekte biri `running`'i sabiti düzenlemeden açarsa test kırılır; sabiti
  hiçbir şey açmadan düzenlerse de kırılır.
- `test_the_service_refuses_a_direct_request_for_an_unbuilt_state` — üç durum
  için doğrudan istek `state_not_producible` ile reddedilir.

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
| `public_share` | **Bu sürümde daima boş** — H3'ün konusu |

`public_share` için bir `EvidenceRef` **kurulamaz**: yapıcı reddeder. Alan,
yokluğun *söylenebilmesi* için vardır (Seviye 4'ün `null` yazılmasıyla aynı
kural). `ready_to_publish`'i engellemez — dış paylaşımı bitirme koşulu yapmak,
hiçbir görevin yayımlanmadan tamamlanamaması demek olurdu.

**Bir kaydın varlığı tek başına başarı değildir.** `EvidenceRef.verified`'ın
varsayılanı yoktur: çağıran, işaret ettiği şeyin denetlenip denetlenmediğini
söylemek zorundadır. `verified=False` bir kayıt `blocked` raporlar, `passed`
değil. Eksik bir check `not_implemented` raporlar, `passed` değil.

`ready_to_publish` **kanıttan türer**: üç yayım alanının üçü de bu görevin
kendi içerik sürümüne karşı ayrı ayrı doğrulanmış olmalıdır. Durum elle
istenemez; `evidence_incomplete` ile reddedilir.

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
- **hiçbir gönderimi sürdürmez.** `resumed_any` yapısal olarak `False`'tur.

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

**Kalan yarım gereksinim:** harcama bağlamı Paket G'ye, bütçe/izin sınırı
Paket H2'ye ertelenmiştir.

---

## 7. Yeniden kullanılan çekirdek, kopyalanmayan üç şey

ADR-0004 §2'nin yasakladığı üç kopyalama:

- **Yeni HTTP istemcisi yok.** `OUTBOUND_CLIENT_MODULES` üçte kilitli kalır;
  `modules/` ve `tasks/` paketlerinde `httpx`, `socket`, `urllib` veya
  herhangi bir giden istemci import'u yoktur (testle).
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
