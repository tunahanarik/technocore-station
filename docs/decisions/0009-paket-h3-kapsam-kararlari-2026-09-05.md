# ADR-0009 — Paket H3 kapsam kararları (5 Eylül 2026)

Durum: **kabul edildi** · Bağlam: uçtan uca prompt §14 (Proof Workspace,
kanıt paketi, dış paylaşım onayı)

Keşif on bir karar boşluğu çıkardı. ADR-0001…0008 gibi bu da bağlayıcıdır
ve **hiçbir güvenlik değişmezini gevşetmez**.

## 0. Yetki nereden geliyor — künye H3'ü tanımıyor

**Künyede "Proof Workspace" yoktur.** Aşama tablosu 7'de (Packaging) biter
ve "Proof Verifier & Archive" §19.1'de **Proje 1 (gelecek proje)** olarak
durur. H3'ün yetkisi künyeden değil, **ADR-0001'in kapsam ekinden ve
promptun §14'ünden** gelir.

Bu açıkça yazılıyor, çünkü "künyeyle çelişen ADR yazılmaz" kuralı
geçerlidir ve H3 künyeyi **çelişmiyor, genişletiyor**: künye bu işi ileri
bir projeye koymuş, kapsam eki onu bu projeye çekmiştir. Fark budur ve
kaydedilmiştir.

## 1. `public_share` doldurulabilir olur — ama yalnız gerçek bir gönderim sonrası

Bugün dört ayrı katman `public_share`'i kapatıyor: `EvidenceRef` **nesne
olarak kurulamıyor**, servis `evidence_field_refused` veriyor,
`_refs_from_row` sütunları **okumadan** atlıyor, `gate.evaluate` koşulsuz
`NOT_IMPLEMENTED` döndürüyor, ve tel `Literal[False]` taşıyor.

**Karar:** alan doldurulabilir olur, **fakat** `EvidenceRef`'in yapıcısı
`public_share` için `ref_id`'nin **gerçek bir evidence kaydı kimliği**
olmasını şart koşar. Yani "paylaşıldı" iddiası her zaman gerçekten olmuş
bir Technocore gönderimine dayanır; elle yazılan bir dize kabul edilmez.

**`PUBLICATION_FIELDS` üçte kalır.** `public_share`'i oraya sokmak
"yayımlamadan hiçbir görev bitemez" demektir ve ADR-0004 §4 bunu açıkça
reddetti. `test_public_share_does_not_block_a_finished_task`'in **gerekçesi
korunur**.

## 2. Dürüstlük şartı: boşalacak **beş** dal sessiz bırakılamaz

`UNFILLABLE_FIELDS` boşalınca **beş kod dalı ölü kalır** ve hiçbiri kırmızı
vermez:

| Yer | Dal |
|---|---|
| `tasks/gate.py` | `if field in UNFILLABLE_FIELDS:` |
| `tasks/service.py` | `if field in UNFILLABLE_FIELDS: continue` |
| `modules/completion.py` | `or requirement.evidence in UNFILLABLE_FIELDS` |
| `modules/fields.py` | `EvidenceRef.__post_init__` reddi |
| `tasks/views.py` | `public_share_available=... not in UNFILLABLE_FIELDS` |

**Bu ADR ilk hâlinde yalnız dördünü sayıyordu ve beşincisi tam da sessiz
kalan oldu.** Bağımsız inceleme ölçtü: `tasks/views.py`'yi sabit bir
`True`'ya çevirmek 1770 testin **hiçbirini** kırmıyordu, yani "tel ile kural
ayrışamaz" diyen iki test sabit bir literal'e karşı geçiyordu. Envanterin
kendisi eksik olduğu için merge şartı kendi hedefini ıskalamıştı; beşincisi
diğer dördüyle aynı disiplinle sürülür.

Bu, H2'nin `UNPRODUCIBLE_STATES` tuzağının **birebir tekrarıdır** ve aynı
çözümü alır: mekanizma, test süresince **geçici olarak kapatılmış** bir
alanla sürülür. Boş bir küme üzerinde dönen bir döngü hiçbir şey kanıtlamaz.

**Ayrıca `test_planned_modules_name_the_package_that_opens_them`**
(`test_module_registry.py:377`): `proof_workspace` **son `PLANNED`
kayıttır**. Açılınca `if record.state is ModuleState.PLANNED:` dalı hiç
çalışmaz ve üç `assert` sessizce ölür. `HIDDEN_SECTIONS` ile aynı şekil,
aynı çözüm: ya "artık planlanan modül yok" kendi adlandırılmış iddiasına
çevrilir, ya mekanizma sürülür.

## 3. Kanıt paketi hiçbir yere yazılmaz

Deponun hâkim kalıbı `downloads.py`'de yazılı: *Station dosyayı kullanıcının
seçtiği bir yola yazmak yerine tarayıcıya teslim eder; bu karar path
traversal'ı, symlink'i, reparse point'i ve üzerine yazma sorularını üründen
tamamen kaldırır.*

**Karar:** proof paketi `evidence/export.py` kalıbını izler — iki biçim
(canonical JSON + Markdown), kapalı küme, `Content-Disposition` ile
tarayıcıya. **Yeni bir dosya kökü açılmaz.**

`workspace/v1/<task_id>` içine **konulamaz**: `_artifact_set_digest`
dizindeki her dosyayı özetliyor, yani paket kendi hash'inin girdisi olurdu.

**Zip üretilmez.** Zip-slip yüzeyi yalnız **açmadan** doğar, üretmeden
değil — bu ayrım burada kayda geçiyor — fakat zip hiçbir davranış
kazandırmıyor ve `test_the_module_has_no_archive_or_link_creating_helper`
ada bakan bir testtir. Üretmeyerek yüzey hiç doğmaz.

## 4. Onay `SendApproval` kalıbıdır, `ExportConsent` değil

Prompt "ayrı **tek kullanımlık** onay" istiyor. `ExportConsent` istek başına
bir boolean'dır ve **tek kullanımlık değildir**.

**Karar:** `compose/approvals.py`'nin `SendApproval` kalıbı kullanılır —
içerik digest'ine, oturuma ve TTL'e bağlı, tek kullanımlık. Onay **paket
digest'ine** bağlanır: artifact değişirse hash değişir, eski onay düşer.
Prompt §14'ün "artifact değişirse hash, test ve eski onay ilişkisi yeniden
değerlendirilir" maddesi böylece **yapısal** olur.

## 5. Kod yeri ve tarama genişletmesi — bağlayıcı madde

Kod yeni bir `station_api/proof/` paketine girer. **Bu paket bugünkü sınır
taramalarının hiçbirine girmez** ve genişletilmezse H2'nin `PACKAGE_F_DIRS`
dersi birebir tekrarlanır. En kötü hâli: `proof/` içinde duruma yazan bir
metot `THE_ONLY_STATE_WRITER` iddiasını **sessizce** delerdi.

Genişletilecekler, adıyla ve **merge şartı olarak**:

- `test_task_states` durum yazıcısı taraması (bugün `modules`, `tasks`,
  `agent`),
- `test_task_evidence`'in bütçe alanı yasağı taraması (`BUDGET_SCANNED_DIRS`
  orada yaşar; bu ADR ilk hâlinde onu `test_module_registry`'ye atfediyordu),
- `test_agent_boundary`'nin yürütme/zamanlayıcı/giden/secret sınırı
  taramasının bir aynası,
- yeni bir `test_proof_language.py` (SI-280 kalıbı, paketin **her string
  literal'i**).

## 6. "Bağımsız kontrol" alanı `not_implemented` kalır

Prompt: *"Bağımsız kontrolün kim tarafından/hangi araçla yapıldığı; yalnız
ikinci model görüşüyse insan onayı gibi gösterilmemesi"* ve *"aynı run'ın
kendi ürettiği çıktıyı üçüncü taraf onayı gibi sunma."*

Model lane'i **kapalıdır** (ADR-0008 §2), yani bu sürümde ikinci model
görüşü diye bir şey **yoktur**. Alan `not_implemented` olur ve gerekçesini
söyler. Bu bir **politika reddi değil, mimari kapanıştır** —
`run_test_result_recorded`'ın `POLICY_REFUSED` **olmama** gerekçesi birebir
geçerlidir.

## 7. Gerçek exit code üretilemez ve üretiliyormuş gibi yapılmaz

Prompt §14 "gerçek exit code" istiyor. ADR-0008 §1 keyfi yürütmeyi kapattı;
`test_result_state` `Literal["not_implemented"]`.

**Karar:** H3 exit code **üretmez** ve alan `not_implemented` kalır. Plan
`test_condition`'ı ve yeniden üretme talimatı **metin olarak** paketlenir.
ADR-0008 §1'i ters çevirmek kullanıcı kararıdır ve bu pakette alınmaz.

## 8. `user_acceptance` kendi rotasını alır

`record_evidence`'ın **hiçbir HTTP rotası yok**; `user_acceptance` bugün
hiçbir yüzeyden doldurulamıyor. `agent_workspace`'in yedinci gereksinimi
(`user_accepted_the_run_output`, stage `H3`) tam olarak bunu bekliyor — yani
H3, `proof_workspace`'i açarken `agent_workspace`'in gereksinimini de
kapatır.

**Karar:** ayrı bir kabul rotası açılır. `verified=True` **yalnız insan
eyleminden** doğar. Kabul, geçişin **girdisidir, çıktısı değil** — geçişin
yan etkisi yapmak `ready_to_publish`'in "kanıttan türer, istenemez"
özelliğini (SI-222) kırardı.

## 9. Bölüm açılmaz

Dokuz bölümün dokuzu `ready: true`. Proof Workspace **`Kanitlar`** bölümüne
girer (promptun hedef navigasyonu da orayı gösteriyor); `sections.ts`'e
**dokunulmaz**. Bu açıkça yazılıyor ki bir sonraki paket "H3 bölüm açmadı,
unutuldu" diye okumasın.

`HIDDEN_SECTIONS` türetmesi **sağlamdır** ve bölüm eklenmediği için
kırılmaz.

## 10. Aşama numarası `8 → 9`

Beş giriş noktası (`cli/__main__.py`, `launcher.py`, `routes/api.py`,
`e2e/harness/serve.py`, `tests/conftest.py`) ve pinli `CURRENT_SCHEMA_STAGE`
**atomik** olarak. Migration eklenirse `CURRENT_MIGRATION_HEAD` `0009 →
0010`. SI-232/SI-262 beşinin de aynı sayıyı taşımasını şart koşuyor.

## 11. Değişmeyenler

`OUTBOUND_CLIENT_MODULES` **beşte kalır** — dış paylaşım mevcut
`technocore/write_client.py` + `compose/` zinciriyle gider, altıncı yüzey
açılmaz. Kibble claim/result sözleşmesi **doğrulanmamıştır** (ADR-0007) ve
çalışıyormuş gibi bir düğme konmaz. `lobby` ve `meta` `DENIED_ROOMS`'ta
kalır. Gerçek yazma, gerçek harcama, gerçek anahtar/DID/seed yok. Zincir
budanmaz. İnsan güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5).

**Hash'in ne kanıtladığı yazılır:** *hash yalnız dosya bütünlüğünü tanımlar;
içeriğin doğru veya yararlı olduğunu kanıtlamaz.* "Proof" kelimesi UI'da
"kanıtlandı" diye okunmamalıdır.
