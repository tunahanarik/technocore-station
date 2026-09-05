# Kanıt Çalışma Alanı (Paket H3)

Kapsam kararları:
[`ADR-0009`](decisions/0009-paket-h3-kapsam-kararlari-2026-09-05.md).
Bu belge **ne yapıldığını ve neyin bilerek yapılmadığını** anlatır.

## 0. Yetki nereden geliyor

Künyede "Proof Workspace" **yoktur**: aşama tablosu 7'de (Packaging) biter ve
"Proof Verifier & Archive" §19.1'de Proje 1 olarak durur. H3'ün yetkisi
künyeden değil, **ADR-0001'in kapsam ekinden ve promptun §14'ünden** gelir.
Bu fark ADR-0009 §0'da kayda geçmiştir ve burada tekrarlanır: künye bu işi
ileri bir projeye koymuştu, kapsam eki onu bu projeye çekmiştir.

## 1. "Kanıt" kelimesi ne demek değildir

Bu bölümün adı `Kanit`, ve bir okuyucunun bunu *kanıtlandı* diye okuma hakkı
vardır. Ürün bu okumayı **açıkça reddeder** ve reddetme cümlesi hem ekranda
hem pakette yazılıdır (ADR-0009 §11):

> Bir SHA-256 özeti yalnızca dosyanın bayt bakımından aynı kaldığını
> tanımlar. İçeriğin ne kadar doğru, eksiksiz veya yararlı olduğu hakkında
> hiçbir şey söylemez; özetler eşit diye çıktı kabul edilmiş sayılmaz.

Cümle `station_api/proof/language.py` içindedir, iki biçimin ikisine de
yazılır ve **kendi yasak-ifade listesinden geçer** — kendi izinli ifadesini
reddeden bir guard, uğruna guard'ın düzenlendiği guard'dır.

## 2. Paket hiçbir yere yazılmaz

Deponun hâkim kalıbı `downloads.py`'de yazılıdır: *Station dosyayı
kullanıcının seçtiği bir yola yazmak yerine tarayıcıya teslim eder.* Kanıt
paketi aynı yolu izler:

- iki biçim (kanonik JSON + Markdown), kapalı küme, `Content-Disposition`;
- **yeni dosya kökü yok**, `mkdir` yok, `write_text` yok — bir sınır testi
  paketteki tüm dosya yazma fiillerini adıyla reddeder;
- **zip üretilmez.** Zip-slip yüzeyi yalnız *açmadan* doğar, üretmeden değil
  — bu ayrım kayda geçiyor — fakat zip hiçbir davranış kazandırmıyor ve
  üretmeyerek yüzey hiç doğmuyor.

Paket `workspace/v1/<task_id>` içine **konulamaz**: kümenin özeti o dizindeki
her dosyayı kapsar, yani paket kendi hash'inin girdisi olurdu. Bir test
paketin kurulması, iki biçimin üretilmesi ve teslim edilmesi boyunca dizin
listesinin **bayt bayt aynı** kaldığını ölçer.

**Determinizm koşulsuzdur.** Belgede paketin ne zaman hazırlandığını söyleyen
hiçbir alan yoktur; o an `X-Station-Delivered-At` başlığıyla, gövdenin
*yanında* gider. Bu burada kanıt dışa aktarımındakinden daha da bağlayıcıdır:
tek kullanımlık onay paket özetine bağlıdır, yani değişmemiş bir paket aynı
özeti vermek **zorundadır**, yoksa her onay üretildiği anda düşerdi.

## 3. Onay: tek kullanımlık, paket özetine bağlı

Prompt "ayrı **tek kullanımlık** onay" istiyor. `ExportConsent` istek başına
bir boolean'dır ve tek kullanımlık **değildir**, bu yüzden kullanılmadı.
Kullanılan kalıp `compose/approvals.py`'nin `SendApproval` kalıbıdır
(ADR-0009 §4). Onay dört şeye bağlıdır:

| Bağ | Ne zaman düşer |
|---|---|
| paket özeti | bir artifact değişirse özet değişir, onay eşleşmez |
| görev | bir onay başka bir görevin paketini teslim edemez |
| içerik sürümü | görev başka içeriğe bağlandıysa eski kanıt eşleşmez |
| oturum | onayı veren tarayıcı oturumu bitmişse düşer |

Onay `SingleUseStore` ile harcanır ve **her sonuçta** silinir: reddedilen bir
teslim de token'ı harcar, yoksa paket tekrar eşleşene kadar denenebilirdi.
TTL 180 saniyedir ve `SEND_TOKEN_TTL_SECONDS`'tan **ayrı yazılmıştır** —
tesadüfen eşit olan iki pencere tek pencere değildir. 180 sayısı artık
`test_proof_bundle.py::test_the_share_approval_ttl_is_the_documented_three_minutes`
tarafından **sabitlenmiştir**; H3 boyunca sabitlenmemişti ve bir düşman
inceleme onu 86400'e çekip hiçbir testi kırmadan geçti, çünkü dosyadaki her
kullanım sahte bir saatte `TTL + 1`'e gidiyordu — göreli bir kontrol, mutlak
bir kararı korumaz.

**Terk edilen onaylar bellekten de düşer.** Bu cümlenin ikinci yarısı
birincisinden yenidir. `SingleUseStore.consume` yalnız kendisine verilen
token'a ulaşır, yani terk edilmiş bir onay tam olarak hiçbir kod yolunun
silmediği kayıttır; `purge_expired` vardı ve ürün kodunda **hiçbir yerden**
çağrılmıyordu, kapasite tavanı da yoktu. Ölçüm: 50 hazırlık → 50 bekleyen;
saat TTL'i geçtikten sonra 5 hazırlık daha → **55**, hiçbiri
harcanabilir değil. Çözüm `compose/approvals.py`'nin `DraftStore`'unun
zaten uyguladığı kalıptır ve oradan alındı — her `issue` **önce süresi
dolanları temizler**, sonra `MAX_PENDING_TOKENS` (64) tavanını uygular ve
tavana varılmışsa **en eskisini** düşürür, çünkü kullanıcı en yenisinin
önündedir. Aynı düzeltme composer'ın gönderim onaylarını ve bootstrap
handoff'unu da kapsar; hepsi aynı depodur.

## 4. Üretilmeyen iki kayıt, gerekçesiyle

| Alan | Durum | Gerekçe |
|---|---|---|
| `independent_check` | `not_implemented` | Modelin **kendi önerisi üçüncü taraf değildir**: planı öneren tarafın çıktısını bağımsız kontrol diye sunmak ADR-0009 §6'nın reddettiği yalandır |
| `exit_code` | `not_implemented` | Keyfi yürütme kapalı (ADR-0008 §1): koşacak bir denetim yok, sayı **uydurulmaz** |

**Bu tablo H4'te değişti ve iki satırı düzeltildi.**

`test_result` **bu tablodan çıktı.** H3'te "H2'den devralınır" diye
yazılıydı; H4 `station_api/agent/acceptance.py`'yi (yedinci kapalı registry)
ekledi ve alan artık **gerçekten üretiliyor**: makinece denetlenebilir kabul
koşulu taşıyan bir plan gerçek bir verdict alır. Yalnız **cümle** taşıyan bir
plan hâlâ `not_implemented` raporlar — bu bir eksiklik değil, o planın hak
ettiği cevaptır.

`independent_check`'in **gerekçesi** değişti, **durumu** değişmedi. Eskiden
"model yolu kapalı (ADR-0008 §2)" yazıyordu; ADR-0012 o yolu açtı, yani
öncül ortadan kalktı. Alan yine de yerinde duruyor, çünkü öncül zaten asıl
sebep değildi: asıl sebep ikinci yarıydı ve yolun açılması onu
**keskinleştirdi**. Planı öneren model, o planı koşan çalışmanın üçüncü
tarafı değildir; ortada hâlâ ikinci bir görüş yok, yalnızca ikinci bir görüş
diye etiketlenmeye daha müsait bir şey var.

İkisi de **politika reddi değil, mimari kapanıştır** — lobby selamı bu ürünün
sürdürmeyi seçtiği bir politikayla reddedilir, bunlar gerçek izolasyonu olan
ileri bir paketin yeniden açabileceği kararlarla kapalıdır. İkisini aynı
şekilde raporlamak bu farkı kaybederdi, ki ayrı listenin bütün sebebi budur.

Planın `test_condition`'ı ve yeniden üretme talimatı pakete **metin olarak**
girer. Ölçütü sonuçsuz taşımak "geçmiş bir denetim" gibi okunacağı için
ölçütün yanında koşmanın kendi `test_result_state`'i de yazılır.

## 5. Eksikler adıyla listelenir

Eksik olan hiçbir şey sayıya, yüzdeye veya tek bir rozete indirgenmez. Liste
dört ayrı kaynaktan kurulur, çünkü dört farklı sorunun dört farklı çözümü
vardır:

- `evidence.<alan>` — kapıda geçmemiş bir kanıt alanı;
- `requirement.<anahtar>` — modül kaydının karşılanmamış bir gereksinimi;
- `run.<id>` / `run.none` — `completed` ile bitmemiş veya hiç olmayan çalışma;
- `artifact.<ad>` — planın söz verip üretilmemiş çıktısı.

Bir test JSON gövdesinde `score`, `percent`, `completeness`, `grade` ve
`rating` kelimelerinin **bulunmadığını** ölçer.

## 6. Kabul geçişin girdisidir, çıktısı değil

`user_acceptance` Paket F'ten beri tanımlıydı ve **hiçbir yüzeyden
doldurulamıyordu**; `agent_workspace`'in yedinci gereksinimi (`stage: H3`)
tam olarak bunu bekliyordu. H3 ayrı bir kabul rotası açtı:

- `verified=True` **yalnız** bu yoldan doğar ve bu yol yalnız bir kişinin
  yaptığı HTTP isteğinden ulaşılabilir;
- kabul, kişinin **gördüğü paketin özetine** bağlanır; paket o arada
  değiştiyse istek `bundle_changed` ile reddedilir;
- rota **hiçbir durumu taşımaz**. Kabulü geçişin yan etkisi yapmak
  `ready_to_publish`'in "kanıttan türer, istenemez" özelliğini kırardı
  (SI-222) ve bir test durumun kabul öncesi ile sonrası aynı olduğunu ölçer.

## 7. Dördüncü alan: `public_share`

Paket F'te bu alan **temsil edilemezdi**. H3 onu doldurulabilir yaptı
(ADR-0009 §1). Elle yazılmış bir dizeyle "paylaşıldı" denemez — bu ölçüldü —
fakat **bunu yapan mekanizmanın adı** bu belgede yanlış yazılmıştı. Doğrusu:

Dört katman vardır ve **ürün yolunda hepsi ateşlenmez**:

1. **`ProofPublicShareRequest.evidence_id` (`min_length=32`)** — HTTP şekil
   kapısı. `"paylasildi"` gönderen bir çağıran modelden **422** alır ve
   handler'a hiç ulaşmaz.
2. **`EvidenceService.get` — burada fiilen reddeden denetim.** Kaydın
   `write_outcome` değeri `verified`'ın **girdisidir**, yani satır her şeyden
   önce okunmak zorundadır. Arşivlenmiş bir gönderimi adlandırmayan her
   işaretçi — şekli ne olursa olsun — burada `evidence_record_missing` ile
   durur. `"0"*32` ve `"paylasildi"` bu yüzden **aynı** gerekçeyi alır.
3. **`TaskService.record_evidence`'ın satır-varlık denetimi** — bu yola
   ancak var olan bir satırla ulaşılır, dolayısıyla burada yalnız onaylayabilir.
   `ProofService`'i **atlayan** çağıranlar için derinlik savunmasıdır;
   `record_evidence` public'tir ve bu sütunları yazan tek fonksiyondur.
4. **`EvidenceRef.__post_init__`'in şekil denetimi** — aynı şekilde: buraya
   geldiğinde kimlik zaten arşivin birincil anahtarından dönmüştür. Elinde
   veritabanı olmayan her `EvidenceRef` kurucusunu o kapsar.

Yani 3 ve 4 birbirinden ve 2'den bağımsız üç ret değil, **2'nin gölgelediği
iki derinlik savunmasıdır**. İkisi de kendi seviyelerinde ayrıca sürülür
(`test_task_evidence.py`'nin iki testi ve
`test_proof_bundle.py::test_the_two_shadowed_public_share_refusals_are_driven_where_they_fire`),
çünkü yalnız bir başkasının arkasında çalışan bir savunma, kimsenin
çalıştığını görmediği savunmadır.

`verified` her durumda arşivdeki kaydın kendi `write_outcome` değerinden
türer: `outcome_unknown` dönmüş bir gönderim **kaydedilir fakat doğrulanmış
sayılmaz** — sunucunun mesajı saklamış olabileceği, saklamamış da olabileceği
durum (ADR-0002 §3).

Alan `PUBLICATION_FIELDS`'e girmedi: yayımlamadan da bir görev tamamlanabilir.

**Paylaşım onayı ile onaylama iki ayrı rettir; onaylama tek kattadır.**
`share` rotası hem tek kullanımlık onayı harcar hem gövdede `acknowledged`
ister — bunlar gerçekten iki bağımsız rettir. Fakat `acknowledged`'ın
**kendisi** bir kez denetlenir: `ProofShareRequest.acknowledged`
`Literal[True]`'dur ve varsayılanı yoktur, yani eksik gövde de `false` gövde
de handler çalışmadan **422**'dir. Handler'ın tepesinde duran ikinci bir
`if body.acknowledged is not True` dalı, kendisini "iki bağımsız retten
ikincisi" diye tanıtıyordu; `Literal[True]` tek değer kabul ettiği için o dal
**alınamazdı** ve bir düşman inceleme onu silip hiçbir testi kırmadan geçti.
Dal kaldırıldı, model genişletilmedi — `bool`'a genişletmek reddi şemadan
handler'a **geciktirmek** olurdu — ve annotation'ın kendisi artık
`test_proof_http.py::test_the_acknowledgement_is_enforced_by_the_annotation_and_only_there`
ile sabitlenmiştir. Kanıt dışa aktarımı (`EvidenceExportRequest.acknowledged:
bool`) gerçekten çift katlıdır; şekli kopyalarken tipi kopyalamamak, yalnız
bir docstring cümlesi olan bir savunma üretmişti.

## 7b. Çalışma alanındaki bir reparse point: 500 değil, söylenmiş bir ret

`ProofService.build` çalışma alanını `AgentService.workspace_files` üzerinden
okur ve o da reparse point yürüyüşünü yapar. `workspace/v1/<task_id>` üzerine
gerçek bir NTFS junction kurulduğunda (`mklink /J`, yönetici hakkı istemez)
yükselen `WorkspaceError`, `routes/proof.py`'nin **yakalamadığı** bir
istisnaydı — rota yalnız `(ProofError, TaskError)` yakalıyor — ve
`GET /api/proof/{id}` **500** dönüyordu. Genel hata sözleşmesi gövdeyi
redakte ettiği için hiçbir şey sızmıyordu; kaybolan şey **cümleydi**. Çalışma
alanı katmanı neyin yanlış olduğunu tam olarak biliyordu ve rota onun yerine
"bir hata oluştu" diyordu — hem de bütün konusu "bu makine neyi ortaya
koyabilir, neyi koyamaz" olan bir ekranda.

`build` artık `AgentError`'ı (`WorkspaceError` onun alt sınıfıdır) `ProofError`'a
çevirir ve rota onu kendi gerekçesiyle **400** olarak döndürür. Gerçek bir
junction ile sürülür (`test_proof_http.py::test_a_reparse_point_in_the_workspace_is_a_stated_refusal_not_a_500`);
junction kuramayan bir makinede predikat aynı gerçek yol üzerinde zorlanır,
**sessiz skip yoktur**.

`routes/agent.py`'nin çalışma alanı okuması bu kusuru **paylaşmıyordu**:
`read_runs` zaten `(TaskError, AgentError)` yakalıyor ve `WorkspaceError` bir
`AgentError`'dır. İnceleme onu da kusurlu bildirmişti; aynı test bunu
ölçerek reddediyor.

## 8. Sınır: yeni paket hiçbir taramanın içinde değildi

ADR-0009 §5 bunu **merge şartı** olarak yazdı, çünkü depo aynı hatayı üst üste
iki pakette yaptı: SI-213 `modules` + `tasks` tarıyordu, H2 yürütücüyü
`agent`'a yazdı ve tarama onu görmedi. Yeni `proof/` paketi de aynı şekilde
**hiçbir sınır taramasının içinde değildi**.

Genişletilenler ve hepsi ekili bir ihlalle sürülmüştür:

| Tarama | Nereye |
|---|---|
| durum yazıcısı (`THE_ONLY_STATE_WRITER`) | `STATE_WRITER_DIRS` → `+proof` |
| bütçe alanı yasağı | `BUDGET_SCANNED_DIRS` → `+proof` |
| registry sınır taramaları (dinamik yükleme, giden yüzey, kasa/signer) | `REGISTRY_SCANNED_DIRS` → `+proof` |
| yasak ifade taraması | yeni `test_proof_language.py`, paketin **her string literal'i** + rota dosyası |
| yürütme/arşiv/bağlantı/zamanlayıcı/secret sınırı | yeni `test_proof_boundary.py` |

En kötü hâl somuttu: `proof/` içinde `row.state` yazan bir metot
`THE_ONLY_STATE_WRITER` iddiasını **sessizce** delerdi, ve kabulden sonra
görevi `ready_to_publish`'e taşıyan bir metot tam olarak birinin yazacağı
metottur.

## 9. Değişmeyenler

- `OUTBOUND_CLIENT_MODULES` **beşte kaldı**. Dış paylaşım mevcut
  `technocore/write_client.py` + `compose/` zinciriyle gider; bu paket
  tarayıcıya dosya teslim eder ve başka hiçbir şey yapmaz.
- Yeni migration **yok**; `CURRENT_MIGRATION_HEAD` `0009`'da kaldı. Kabul
  mevcut `task_evidence_outcome` sütunlarına, onay ise yalnız süreç
  belleğine yazılır.
- Yeni bölüm açılmadı. Proof Workspace `Kanitlar` bölümüne girer;
  `sections.ts`'e dokunulmadı ve dokuz bölümün dokuzu `ready: true` kaldı.
- `lobby` ve `meta` `DENIED_ROOMS`'ta; gerçek yazma, gerçek harcama, gerçek
  anahtar/DID/seed yok. İnsan güvenlik incelemesi ertelenmiş kalan risktir
  (ADR-0001 §5).

## 10. HTTP'den istenemeyen şey — ve H4'te kapanan boşluk

`ready_to_publish` **hâlâ HTTP'den istenemez**: `TaskUserTransitionName` onu
taşımaz (SI-222) ve H3 bunu değiştirmedi, çünkü ADR-0009 §8 kabulün geçişin
**girdisi** olmasını şart koşuyor ve geçişi kabulün yan etkisi yapmayı
yasaklıyor.

Bu bölüm burada bitiyordu ve şöyle diyordu: *"üç yayım alanı doğrulanmış olsa
bile görevi `ready_to_publish`'e taşıyan bir kullanıcı rotası yoktur. Bu,
kapatılmış bir karar değil **açık bir boşluktur**."* **Boşluk H4'te
kapandı** ve bu paragraf onunla birlikte güncellendi.

`POST /api/tasks/{id}/publish-readiness` o rotadır ve **ayrı** bir rota
olması kasıtlıdır — geçiş literaline yeni bir değer eklemek değil. SI-222'nin
kuralı "bu duruma ulaşılamaz" değil, "bu durum **kanıttan türer ve
istenemez**" idi; ikisi farklı cümlelerdir ve kapatılan yalnızca birincisiydi:

* `TaskUserTransitionName` `ready_to_publish` **taşımıyor**, yani bu üründe
  hiçbir istek durumu **adlandıramıyor**;
* `TaskPublishReadinessRequest` gövdesinde **hedef alanı yok**, yani
  adlandıracak alan da yok (hedef adı taşıyan gövde 422);
* rota bir şey **istemiyor**, üç alanı **yeniden okuyor**; üçü de
  doğrulanmamışsa `evidence_incomplete` ile reddediyor ve eksikleri
  **adıyla** söylüyor;
* geçişi yine `TaskService.transition` yazıyor — bu üründe bir görev durumunu
  yazan tek fonksiyon odur, yani bu rota ikinci bir yazıcı değil.

SI-342 bunu sabitler; SI-222 gevşetilmedi, korundu.
