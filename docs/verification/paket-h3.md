# Paket H3 doğrulama raporu — Kanıt çalışma alanı

Tarih: 2026-09-05 · Kapsam kararları:
[`ADR-0009`](../decisions/0009-paket-h3-kapsam-kararlari-2026-09-05.md) ·
Uygulama ayrıntısı: [`../proof-workspace.md`](../proof-workspace.md).

Bu raporun gövdesi **backend** turunda yazıldı; frontend ayrı bir ajanın
işiydi ve aşağıdaki "Frontend" bölümü o tur bittikten sonra eklendi.
**Bu rapor bir noktada kendisiyle çelişiyordu** — girişi
`apps/station-web/src/**`'in hiç değiştirilmediğini söylerken aynı raporda
dolu bir frontend bölümü vardı. Ölçüm: `git show f5d6b97 --stat --
apps/station-web/src` → **8 dosya, +2590/−7**. Doğrusu şudur: backend turu
`src/` altına dokunmadı (tek istisna `e2e/harness/serve.py`'nin aşama
numarası, çünkü o dosya veritabanını açan beş giriş noktasından biridir,
ADR-0009 §10); frontend turu dokundu.

## En büyük karar: alan açıldı, koşulu yapısal tutuldu

`public_share` Paket F'te dört ayrı katmanla kapalıydı. H3 onu açtı, fakat
"açtı" demek "serbest bıraktı" demek değil: `ref_id` yalnızca **arşivlenmiş
bir gönderimin kanıt kaydı kimliği** olabilir ve bunu birbirinin yerine
geçmeyen **üç** kontrol sağlar (ADR-0009 §1).

1. `EvidenceRef.__post_init__` **şekli** denetler: 32 küçük harf hex, yani
   `uuid4().hex`'in ürettiği tek şekil. Bu kontrol veritabanı görmez ve
   göremez — `modules/` paketi `station_api.evidence`'ı import edemez
   (`test_no_module_record_moved_code_into_the_registry_package`), bu yüzden
   şekil orada, varlık başka yerde denetlenir.
2. `TaskService.record_evidence` **satırın gerçekten var olduğunu** denetler
   (`evidence_record_missing`). Şekli doğru fakat uydurulmuş bir kimlik
   burada durur.
3. `ProofService.record_public_share` kaydın kendi `write_outcome` değerini
   okur ve `verified`'ı **ondan** türetir. `outcome_unknown` dönmüş bir
   gönderim kaydedilir ve **doğrulanmış sayılmaz**.

Değişmeyen iki şey: `PUBLICATION_FIELDS` **üçte** kaldı, ve alan
`ready_to_publish`'i engellemez. `test_public_share_does_not_block_a_finished_task`
gerekçesiyle birlikte duruyor; beklenen durum `not_implemented` yerine
`blocked`, ve bu test artık **daha keskin**: eski hâli alan inert olduğu için
de geçebilirdi.

### Yan etki: açılan alan bir okuma yolunu kırabilirdi

Alan kapalıyken `_refs_from_row` `public_share` sütunlarını **okumadan**
atlıyordu, yani elle düzenlenmiş bir satır yapıcıya hiç ulaşamıyordu. Alanı
açmak o yolu doğrudan **yükselten** bir yapıcıya çeviriyordu: bozuk değer
taşıyan bir satır o görevin **her okumasını** — listeleme dâhil —
yakalanmamış bir hatayla düşürürdü. `except EvidenceFieldError: continue`
eklendi; davranış (satır atlanır) değişmedi, ama artık ikinci bir kod yolunu
kapsıyor ve `test_a_public_share_row_written_directly_is_passed_by` listemenin
de cevap verdiğini ölçüyor.

## Dürüstlük şartı: boşalan dallar sessiz bırakılmadı

`UNFILLABLE_FIELDS` boşaldı. Bu, ADR-0009 §2'nin adıyla saydığı **dört dalı**
ölü bırakır ve hiçbiri kırmızı vermez. H2'nin `UNPRODUCIBLE_STATES` tuzağının
birebir tekrarı olduğu için aynı çözümü aldı: mekanizma, **gerçekten
doldurulabilir** bir alan (`test_result`) test süresince kapatılarak sürülür.

Her testin **ilk yarısı** kapatmadan önce aynı yolun izinli olduğunu okur.
Bu yarı olmadan "her şeyi reddeden" bir fonksiyon da geçerdi — sürülen
mutasyonun sessizce yanlış gitme biçimi tam olarak budur.

Aynı disiplin iki yerde daha uygulandı:

- `proof_workspace` **son `PLANNED` kayıttı**. Açılınca
  `test_planned_modules_name_the_package_that_opens_them`'in üç `assert`'i
  hiç çalışmayacaktı. Sözleşme bir fonksiyona çıkarıldı, testte kurulan
  kayıtlarla sürüldü (geçerli bir `planned` kayıt **kabul** ediliyor, dört
  bozuk şekil **reddediliyor**) ve "artık planlanan modül yok" kendi
  adlandırılmış iddiası oldu.
- `test_work_scan_candidates.py`'nin planlı-modül testi kaydı test süresince
  `PLANNED` yapıyor ve önce açık hâlini okuyor. O testin kendi docstring'i
  bu anda ne yapılacağını yazmıştı; yapılan tam olarak odur.

`test_there_are_exactly_four_fields_and_three_decide_publication`'ın
`PUBLICATION_FIELDS == set(EvidenceField) - UNFILLABLE_FIELDS` iddiası da
boşalan kümeyle **yanlış** hâle geliyordu ve onu yeşile döndürmenin yolu
`public_share`'i `PUBLICATION_FIELDS`'e sokmaktı — yani ADR-0004 §4'ün
reddettiği düzenleme. İddia elle yazılı bir oracle'a çevrildi.

## Paket hiçbir yere yazılmaz, ve bu ölçüldü

İki biçim (kanonik JSON + Markdown), `Content-Disposition`, yeni dosya kökü
yok, **zip yok**. Zip-slip yüzeyinin yalnız *açmadan* doğduğu ayrımı kayda
geçti (ADR-0009 §3) ve yine de arşiv üretilmedi: üretmeyerek yüzey hiç
doğmuyor.

Ölçülenler:

- `proof/` ve `routes/proof.py` ağacında `zipfile`/`tarfile`/`shutil`/`gzip`/
  `zlib` importu yok; `symlink`/`write_text`/`mkdir`/`open` adı yok; arşiv ve
  bağlantı biçimli **isim** taşıyan fonksiyon/sınıf yok.
- Paket kurulup iki biçimi üretilip teslim edildikten sonra çalışma alanı
  dizininin **(ad, sha256)** listesi bayt bayt aynı. Paket kendi hash'inin
  girdisi olamıyor.
- Determinizm koşulsuz: belgede kopyanın alındığı anı söyleyen hiçbir alan
  yok, o an `X-Station-Delivered-At` başlığında. Burada bu kanıt dışa
  aktarımındakinden **daha bağlayıcı**: tek kullanımlık onay paket özetine
  bağlı olduğu için değişmemiş paket aynı özeti vermek zorunda.
- `artifact_set_sha256`, `AgentService._artifact_set_digest` ile **birebir
  aynı sayı**. İki yerde hesaplanıyor (agent paketi bu paketi import edemez,
  çünkü bu paket onu import ediyor), bu yüzden anlaşma bir testle sabitlendi.

## Onay: `SendApproval` kalıbı, `ExportConsent` değil

`ExportConsent` istek başına bir boolean'dır ve **tek kullanımlık değildir**;
prompt tek kullanımlık istiyor. Kullanılan kalıp `compose/approvals.py`'nin
`SendApproval`'ıdır ve `SingleUseStore` ile harcanır.

Onay dört şeye bağlı: paket özeti, görev, içerik sürümü, oturum. Ölçülen
reddetmeler: ikinci kullanım, başka oturum, başka görev, değişmiş artifact
(`bundle_changed`), dolmuş TTL, ve — en önemlisi — **reddedilen bir teslim de
token'ı harcar**. Onay reddini atlatarak tekrar denenebilseydi tek
kullanımlık olmazdı.

Rota ayrıca gövdede `acknowledged: Literal[True]` ister. İki bağımsız
reddetme, çünkü bu makineden çıkan bir dosya iki tanesine değer.

## Üretilmeyen iki kayıt

`independent_check` ve `exit_code` `not_implemented` kaldı ve **gerekçesini
söylüyor**. İkisi de politika reddi değil, mimari kapanış: model yolu
ADR-0008 §2 ile, keyfi yürütme ADR-0008 §1 ile kapalı. Planın ölçütü ve
yeniden üretme talimatı **metin olarak** paketleniyor; ölçütün yanında
koşmanın kendi `test_result_state`'i de yazılıyor, yoksa ölçüt tek başına
"geçmiş bir denetim" gibi okunurdu.

Uçtan uca sonuç ölçüldü: söz verilen her çıktıyı üreten bir çalışma bile
görevi `ready_to_publish`'e taşımıyor, çünkü `test_result`'ın üreticisi yok.

## Sınır taramaları: yeni paket hiçbirinin içinde değildi

ADR-0009 §5 bunu merge şartı yaptı ve haklıydı: `proof/` paketi yaratıldığı
gün **hiçbir sınır taramasının** içinde değildi. Genişletilenler:

| Tarama | Sabit | Nereye |
|---|---|---|
| durum yazıcısı | `STATE_WRITER_DIRS` | `+proof` |
| bütçe alanı | `BUDGET_SCANNED_DIRS` | `+proof` |
| dinamik yükleme, giden yüzey, kasa/signer | `REGISTRY_SCANNED_DIRS` (eski `PACKAGE_F_DIRS`) | `+proof` |
| yasak ifade | yeni `test_proof_language.py` | paketin her string literal'i + rota |
| yürütme/arşiv/bağlantı/yazma/zamanlayıcı/secret | yeni `test_proof_boundary.py` | paket + rota |

Sabitin **adı** da içeriğiyle değişti: H3 paketini listeleyen `PACKAGE_F_DIRS`
kendi kapsamı hakkında yanlış konuşan bir yorum olurdu.

Her genişletme iki yarıyla sürüldü: taramanın gerçekten `proof/` dosyalarını
**açtığı** ölçüldü (yanlış bir dizin adı temiz sonuç verir, genişletilmiş bir
kuralın hiçbir şeyi genişletmemesinin yolu budur), ve geçici bir ağaca ekilen
ihlalin **raporlandığı** ölçüldü.

## Kabul geçişin girdisidir

`user_acceptance` Paket F'ten beri tanımlıydı ve hiçbir yüzeyden
doldurulamıyordu; `agent_workspace`'in yedinci gereksinimi tam olarak bunu
bekliyordu ve H3 onu kapattı. Kabul rotası:

- `verified=True`'yu **yalnız** bir insanın isteğinden üretir;
- kişinin **gördüğü paketin özetine** bağlanır (`bundle_changed` aksi hâlde);
- **hiçbir durumu taşımaz** — kabul öncesi ve sonrası görev durumunun aynı
  olduğu ölçülüyor. Kabulü geçişin yan etkisi yapmak SI-222'yi kırardı.

## Aşama 8 → 9

Beş giriş noktası ve pinli sabit atomik olarak taşındı: `cli/__main__.py`,
`launcher.py`, `routes/api.py`, `apps/station-web/e2e/harness/serve.py`,
`tests/conftest.py` ve `test_module_registry.py`'nin `CURRENT_SCHEMA_STAGE`.

**Yeni migration yok.** Kabul mevcut `task_evidence_outcome` sütunlarına,
onay yalnız süreç belleğine yazılıyor; `CURRENT_MIGRATION_HEAD` `0009`'da
kaldı ve `test_proof_boundary.py::test_no_new_migration_was_added_by_this_package`
bunu ayrıca söylüyor.

## Dosya adı uyarısı (Paket G dersi)

Yeni modül adları `.gitignore` ile çakışmayacak şekilde seçildi
(`proof/{__init__,language,bundle,approvals,service}.py`, `routes/proof.py`;
`credentials.*`, `secrets.*`, `*.key`, `build/`, `dist/`, `out/`, `env/`
kurallarının hiçbiriyle çakışmıyor) ve dosyalar **git'e eklendi**.
`tests/security/test_tracked_sources.py` koşuldu ve geçtiği görüldü.

## Mutasyon kaydı

Aşağıdaki her satır **ürün kaynağı fiilen düzenlenerek, tam suite koşularak
ve dosya geri yüklenerek** ölçüldü. Sayılar tahmin değil, koşu çıktısıdır.

| Kaynağa uygulanan mutasyon | Ölçülen sonuç |
|---|---|
| `EvidenceRef.__post_init__`'in **kanıt kaydı kimliği şekli** kontrolü kapatıldı | **3 kırmızı**: `test_a_public_share_reference_needs_an_evidence_record_identity`, `::test_the_service_refuses_a_public_share_pointer_with_no_row_behind_it`, `::test_a_public_share_row_written_directly_is_passed_by` — üçüncüsü, elle düzenlenmiş bir satırın artık yakalanmamış bir hataya dönüştüğünü gösteriyor |
| `record_evidence`'ın **satır varlığı** kontrolü kapatıldı | **1 kırmızı**: `::test_the_service_refuses_a_public_share_pointer_with_no_row_behind_it` — şekli doğru, uydurulmuş kimlik geçiyor |
| `tasks/gate.py`'nin `UNFILLABLE_FIELDS` dalı kapatıldı | **1 kırmızı**: `::test_the_gate_still_reports_a_closed_field_as_not_implemented` |
| `tasks/service.py`'nin `UNFILLABLE_FIELDS` atlaması kapatıldı | **1 kırmızı**: `::test_the_row_reader_still_skips_a_closed_fields_columns` |
| `modules/completion.py`'nin `UNFILLABLE_FIELDS` dalı kapatıldı | **1 kırmızı**: `::test_a_requirement_bound_to_a_closed_field_is_never_counted_as_passed` |
| `EvidenceRef.__post_init__`'in `UNFILLABLE_FIELDS` reddi kapatıldı | **2 kırmızı**: `::test_a_reference_for_a_closed_field_cannot_be_constructed`, `::test_the_service_refuses_to_record_a_closed_field` |
| `build_document`'ın `assert_product_language` çağrısı silindi | **1 kırmızı**: `test_proof_language.py::test_turning_the_guard_into_a_no_op_lets_a_bundle_carry_an_over_claim` |
| `safe_text`'in `neutralise` adımı silindi | **2 kırmızı**: `::test_the_neutralising_step_runs_before_the_guard_and_not_after`, `::test_turning_the_neutraliser_off_lets_a_users_words_refuse_the_product` |
| `deliver_share`'in **paket digest'i** karşılaştırması kapatıldı | **2 kırmızı**: `test_proof_bundle.py::test_an_approval_falls_when_the_artifact_set_changes`, `::test_a_refused_delivery_still_spends_the_approval` |
| `record_acceptance`'ın **paket digest'i** karşılaştırması kapatıldı | **2 kırmızı**: `::test_an_acceptance_for_a_bundle_that_has_since_changed_is_refused`, `test_proof_http.py::test_an_acceptance_for_a_stale_bundle_is_a_conflict` |
| `record_public_share` `verified=True`'yu **koşulsuz** yazdı | **1 kırmızı**: `::test_a_send_whose_outcome_is_unknown_is_recorded_but_not_verified` |
| `proof_workspace` kaydı `PLANNED`'a geri alındı | **3 kırmızı**: `test_module_registry.py::test_no_module_is_registered_as_planned_any_more`, `::test_the_registry_satisfies_the_planned_module_contract`, `test_work_scan_candidates.py::test_a_planned_module_produces_a_capability_that_says_the_code_is_absent` |
| `launcher.py` veritabanını eski aşamada (`stage=8`) açtı | **1 kırmızı**: `test_module_registry.py::test_every_entry_point_names_the_same_release_stage` |

Ekili ihlaller — hepsi `station_api/proof/` içine konan tek bir dosyayla,
ölçüldükten sonra silindi. Üçünde `test_tracked_sources.py`'nin iki testi de
kırmızıya dönüyor, çünkü ekilen dosya git'te yok; bu **beklenen** ve o
kontrolün de çalıştığının ayrı bir kanıtı — aşağıdaki sayılar onları da
içeriyor.

| Ekilen ihlal | Ölçülen sonuç |
|---|---|
| `proof/` içine `row.state = 'ready_to_publish'` yazan bir metot | **3 kırmızı**: `test_task_states.py::test_only_the_transition_method_writes_a_task_state` + iki `test_tracked_sources` |
| `proof/` içine `estimated_budget = 10` | **3 kırmızı**: `test_task_evidence.py::test_the_task_layer_opens_no_budget_field` + iki `test_tracked_sources` |
| `proof/` içine `import httpx`, `import subprocess` ve `from station_api.vault.service import ...` | **9 kırmızı**: `test_proof_boundary.py`'nin dört testi (giden yüzey, secret sınırı, yürütme, ve "gerçek import'lar rahat bırakılıyor" muafiyeti), `test_module_registry.py`'nin iki registry taraması, `test_write_gate.py::test_httpx_is_imported_only_by_the_reviewed_clients` ve iki `test_tracked_sources` |
| `proof/` içine yasak ifade taşıyan bir string literal | **3 kırmızı**: `test_proof_language.py::test_no_string_literal_in_the_proof_package_carries_a_forbidden_phrase` + iki `test_tracked_sources` |

**On altı mutasyonun on altısı en az bir testi öldürdü.** Sıfır öldüren guard
yok.

## Frontend: bölüm açılmadı, bayat tel derleyiciye bağlandı

`sections.ts`'e **dokunulmadı** ve dokuz bölümün dokuzu `ready: true` kaldı
(ADR-0009 §9). Proof Workspace `Kanitlar`'a, kabul ve arşivlenmiş-gönderim
işareti `Gorevler`'e girdi.

**Backend'in bıraktığı bayatlık kapatıldı ve bir daha sessizce
bayatlayamaz.** `types.ts`'te `public_share_available` `false` olarak
tiplenmişti; backend artık `true` gönderiyor. Alan `true`'ya sabitlenmedi,
**`boolean`'a genişletildi** — alanın ne taşıyabileceği sunucunun kararıdır.
Ölçüldü: `false`'u geri koymak artık iki fixture'da **derleme hatası**
(`TS2322`). Önceden sessiz bir yalandı.

Dürüstlük yüzeyleri ekranda ve her biri kendi `test-id`'siyle: hash'in ne
kanıtladığı (ilk digest'in **üstünde**), `independent_check`/`exit_code`/
`test_result` `not_implemented` + gerekçe ve **tik yok**, eksikler
puanlanmadan adlandırılıyor, onayın tek kullanımlık ve digest'e bağlı
olduğu **düğmeye basılmadan önce**, reddedilen teslimin de token'ı
harcadığı, kabulün **hiçbir durumu taşımadığı** (öncesi ve sonrası birlikte
gösteriliyor), arşivlenmiş ≠ doğrulanmış ayrımı, ve `ready_to_publish`'in
HTTP'den hâlâ erişilemez olduğu — iki bölümde birden.

**Bir test yanlış sebeple geçiyordu.** Çift etkinleştirme testi guard'ı
değil, başarı sonrası sıfırlamayı sürüyordu; POST'u uçuşta tutan bir stub'la
yeniden yazıldı. Ajan ayrıca `busy` guard'ı ile düğmenin `isDisabled`'ının
**gereksiz** olduğunu ölçtü: biri kaldırılınca davranış doğru kalıyor, ikisi
birden kaldırılınca test kırmızı. DOM'dan erişilemeyen yarısı için zorlama
bir test **uydurmadı**.

HeroUI kümesi **11'de kaldı**; MCP bağlıydı ve `list_components` ile
doğrulandı (v3.2.4, 71 bileşen), yalnız incelenmiş kümedeki bileşenler
kullanıldı. Yeni npm bağımlılığı yok.

## Kapılar (birleşik ağaç, orkestratör koşusu)

| Kapı | Sonuç |
|---|---|
| pytest | **2114 geçti** (1992 → 2105 → inceleme sonrası 2114) |
| Vitest | **315 geçti** (289 → 315) |
| Playwright (e2e) | **74 geçti** (65 → 74) |
| ruff (iki koşu) / mypy strict | geçti / 0 hata |
| eslint / build | geçti / geçti |

## Bağımsız inceleme sonucu

Temiz bağlamlı bir reviewer subagent koşuldu: **31 backend + 5 frontend
mutasyon, 6 ekili ihlal, 13 uçtan uca prob.** Dört mutasyon hayatta kaldı ve
**sekiz bulgunun hepsi kapatıldı.** Bu **insan güvenlik incelemesi
değildir**; ADR-0001 §5'in kalan riski yerinde duruyor.

### P1-1: `UNFILLABLE_FIELDS`'in dört değil **beş** okuyucusu vardı

Beşincisi `tasks/views.py` — telin kendisi. Sabit bir `True`'ya çevirmek
1770 testin **hiçbirini** kırmıyordu, yani "tel ile kural ayrışamaz" diyen
iki test sabit bir literal'e karşı geçiyordu. ADR-0009 §2 "hiçbir boşalan
dal sessiz bırakılmaz"ı bir merge şartı yapmıştı, ama **envanterin kendisi
eksik olduğu için şart kendi hedefini ıskaladı.** Beşincisi artık diğer
dördüyle aynı disiplinle sürülüyor (izinli hâl önce, sonra kapatma):
0 → **1 kırmızı**. ADR-0009 §2'nin tablosu, `modules/fields.py`'nin "dört
dal" cümlesi ve SI-301 **beşe** düzeltildi; iki testin fazla iddia eden
docstring'i **iddiaları korunarak** gerçeğe indirildi.

### P1-2: `safe_text`'in sweep→neutralise **sırası** sabitlenmemişti

Sırayı ters çevirmek 0 test kırıyordu, ama mutant **eşdeğer değil** ve fark
ölçüldü: `fold()` sıfır-genişlikli karakteri **siler**, `sweep_untrusted`
**boşlukla değiştirir**. Yasak bir ifadenin iki kelimesi arasına konan bir
U+200B ham metinde `neutralise`'a görünmez, sweep'ten sonra birebir yasak
ifade olur ve `routes/proof.py` yalnız `(ProofError, TaskError)` yakaladığı
için **yakalanmayan 500** üretir. Tam olarak IMP-420'nin "bir klavye ürünün
ne söyleyeceğine karar veremez" kuralı. Davranışsal test (önce
`neutralise(hostile) == hostile` öncülü doğrulanıyor) + `neutralise`'ın
argümanının bir `sweep_untrusted(...)` çağrısı olduğunu sabitleyen AST
testi: 0 → **2 kırmızı**.

### P2-3: "üç gereksiz olmayan denetim" — esas iddia doğru, **mekanizmanın
adı yanlıştı**

İncelemeci elle yazılmış bir dizeyle "paylaşıldı" **diyemedi** — esas iddia
ayakta. Ama fiilen reddeden `EvidenceService.get`, hiçbir belgenin anmadığı
bir dördüncü denetim; şekil denetimini pydantic'in `min_length=32`'si,
satır-varlık denetimini `evidence.get` gölgeliyor. H2'nin
containment-reparse'ı-gölgeliyor kalıbının aynısı.

**Düzeltme ajanı incelemeciyi burada ölçerek düzeltti:** önerilen "sonuç
okumasını taşı" seçeneği **ucuz değil, yapısal olarak imkânsız** —
`record.write_outcome`, `verified`'ın **girdisi**, dolayısıyla ondan sonraya
konan her denetim o yolda tanım gereği erişilemez. Mekanizma olduğu gibi
bırakılıp **doğru adlandırıldı**: dört katman, hangisinin ateşlediği, ve
gölgelenen ikisinin "`ProofService`'i atlayan çağıranlar için derinlik
savunması" olduğu. Ayrıca ölçüldü ki gölgelenen iki denetim **kendi
düzeylerinde zaten sürülüyordu**; yeni bir test ikisinin **ayrımını**
(`evidence_field_refused` vs `evidence_record_missing`) tek yerde sabitliyor.

### P2-4: rotadaki `acknowledged` denetimi erişilemez ölü koddu

`Literal[True]` olduğu için handler yalnız `True` ile çalışabiliyordu, ama
docstring "iki bağımsız ret" diyordu (evidence export'ta model `bool`
olduğu için orada ikileme **gerçek**). Ajan modeli genişletmek yerine **ölü
dalı kaldırmayı** seçti — genişletmek reddi şemadan handler'a **geciktirir**
ve mevcut bir testi 422'den 400'e **zayıflatmayı** gerektirirdi. Anotasyon
artık tek savunma olduğu için kendi testine kavuştu (`Literal[True]` **ve**
zorunluluk, artı export'un `bool`'uyla karşıtlık): **2 kırmızı**.

### P2-5, P3-6, P3-7, P3-8

TTL sabiti ikizinin yaptığı gibi sabitlendi (0 → 1 kırmızı). Paylaşım onayı
deposu hiçbir şey atmıyordu — 50 hazırlık, TTL geçildikten sonra 5 tane
daha → **55**; `DraftStore` kalıbı `SingleUseStore`'un kendisine uygulandı
(compose ve bootstrap da kazandı), ölçüm artık **5**, ve tavan ayrı bir
testle sürülüyor. Workspace'teki gerçek bir junction kanıt okumasını 500'e
çeviriyordu; `ProofService.build` `AgentError`'ı çevirerek dört rotayı birden
kapattı ve **gerçek bir NTFS junction** ile sürüldü (bu makinede
`isjunction: True` doğrulandı, sessiz skip yok). Panel yorumunun "iki okuma"
iddiası bire indirildi.

**Ajan incelemeciyi ikinci kez düzeltti:** `routes/agent.py` bir bulgu
değildi — `WorkspaceError`, `AgentError`'ın alt sınıfı ve rota zaten
`(TaskError, AgentError)` yakalıyor, yani orası **hep** belirtilen 400'ü
döndürüyordu. Yeni test bunu da ölçüyor.

### İncelemecinin doğruladıkları

2105 pytest (iki kez tam koşu), 315 Vitest, ruff/mypy/eslint/build temiz,
`PUBLICATION_FIELDS` = 3, `UNFILLABLE_FIELDS` boş,
`OUTBOUND_CLIENT_MODULES` = 5, proof ağacında zip/arşiv/dosya-yazma fiili
yok, yeni dosya kökü yok, yeni migration yok, bağımlılık/lockfile
değişmedi, HeroUI **öncesinde ve sonrasında** 11, `sections.ts` dokunulmamış
ve 9/9 `ready`, aşama 9 beş giriş noktasında, dört dalın her biri **izinli
hâl önce okunarak** sürülüyor, planlanan-modül sözleşmesi testin kendi
kurduğu kayıtlar üzerinde sürülüyor, yazarın 12 yeniden koşulabilir
mutasyon satırının **hepsi aynı kırmızı sayısıyla** üretildi, çift
etkinleştirme testi isteği gerçekten uçuşta tutuyor, `ready_to_publish`
HTTP'den erişilemez (422) ve onu öneren bir düğme yok.

**Sızıntı bulunamadı.** Arşivlenmiş gönderimi olan bir görevden kurulan
9715 baytlık paket, iki biçimde de: mutlak yol yok, `data_dir` yok, `C:\`
yok, ham istek gövdesi yok, imza yok, DID yok, oturum kimliği yok. Hata
gövdeleri: `/api/proof/../../etc/passwd` → 404, bilinmeyen görev → 404.

**Onay yarış-güvenli:** tek token'la 8 eşzamanlı teslim → tam olarak **1
`ok`, 7 `approval_invalid`**.

### İncelemecinin ölçmedikleri (kendi beyanı)

Playwright suite'i **koşulmadı** (statik olarak sayıldı); hiçbir tarayıcı,
görsel veya manuel QA yapılmadı; H3 diff'i dışındaki paketler (vault,
compose, opencode, audit zinciri) incelenmedi; DPAPI/Windows ACL davranışı
incelenmedi; tek 8-iş parçacıklı token yarışı dışında eşzamanlılık
ölçülmedi. Kapılar ve e2e orkestratör tarafından ayrıca koşuldu.

### Bu raporda düzeltilen iki yanlış

Girişi `apps/station-web/src/**`'in hiç değiştirilmediğini söylüyordu, oysa
aynı raporda dolu bir frontend bölümü vardı (ölçüm: 8 dosya, +2590/−7).
`docs/task-modules.md`'nin "`verified` çağırandan alınmaz" cümlesi
**koşulsuz** yazılmıştı ve `TaskService` yolunda yanlıştı; bugün o çağrıyı
açan hiçbir rota olmadığı için bir delik değil bir belge kusuruydu, ama
koşulsuz kalması onu deliğe çevirirdi.

## Ölçülmeyenler (dürüst kapsam)

- **İnsan gözü değmedi**; görsel/manuel QA Paket J'ye ertelenmiş kalan
  risktir (ADR-0001 m.4).
- **`proof.spec.ts` her rotayı mock'luyor**, yani yalnız **tarayıcı yarısını**
  kanıtlıyor: onayın gerçekten tek kullanımlık olduğu, gerçekten digest'e
  bağlı olduğu, sunucuda gerçekten harcandığı, paketin deterministliği ve
  `artifact_set_sha256`'nın agent'ın digest'iyle eşleştiği hakkında **hiçbir
  şey söylemiyor**. Bunlar Python suite'inde ve spec'in başlığında kapsam
  dışı olarak yazılı.
- **A11y/CSP/klavye döngüleri canlı backend'e karşı koşuyor**, ama panel
  orada hiçbir görev bulamıyor — yani o döngüler **boş durumu** sürüyor,
  dolu durumu değil.
- **İnsan güvenlik incelemesi yapılmadı** (ADR-0001 §5, ertelenmiş kalan
  risk).
- **Gerçek gönderim, gerçek harcama, gerçek anahtar/DID/seed yok.** Hiçbir dış
  servise istek gönderilmedi; testlerdeki kanıt kayıtları TEST-ONLY
  fixture'lardır ve arşive doğrudan yazılır.
- **Bu sürümde HTTP'den `ready_to_publish`'e geçilemiyor.**
  `TaskUserTransitionName` onu taşımaz ve ADR-0009 kapsamında değildir; bu
  kapatılmış bir karar değil, **açık bir boşluktur** ve
  [`../proof-workspace.md`](../proof-workspace.md) §10'da yazılıdır.
