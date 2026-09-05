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
tesadüfen eşit olan iki pencere tek pencere değildir.

## 4. Üretilmeyen iki kayıt, gerekçesiyle

| Alan | Durum | Gerekçe |
|---|---|---|
| `independent_check` | `not_implemented` | Model yolu kapalı (ADR-0008 §2): ikinci bir görüş **yoktur** ve aynı koşmanın kendi çıktısı üçüncü taraf onayı gibi sunulmaz |
| `exit_code` | `not_implemented` | Keyfi yürütme kapalı (ADR-0008 §1): koşacak bir denetim yok, sayı **uydurulmaz** |
| `test_result` | `not_implemented` | Aynı sebep; H2'den devralınır |

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

Paket F'te bu alan **temsil edilemezdi**. H3 onu doldurulabilir yaptı ve
koşulu üç ayrı katmanda tuttu (ADR-0009 §1):

1. `EvidenceRef` yapıcısı `ref_id`'nin **şeklini** denetler (32 küçük harf
   hex — `uuid4().hex`'in ürettiği tek şekil). Elle yazılmış bir cümle burada
   durur, "çağıran hatırlarsa" değil.
2. `TaskService.record_evidence` **satırın gerçekten var olduğunu** denetler.
   Şekli doğru, uydurulmuş bir kimlik burada durur.
3. `ProofService` arşivdeki kaydın kendi `write_outcome` değerini okur ve
   `verified`'ı ondan türetir. `outcome_unknown` dönmüş bir gönderim
   **kaydedilir fakat doğrulanmış sayılmaz** — sunucunun mesajı saklamış
   olabileceği, saklamamış da olabileceği durum (ADR-0002 §3).

Alan `PUBLICATION_FIELDS`'e girmedi: yayımlamadan da bir görev tamamlanabilir.

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

## 10. Bu sürümde HTTP'den ulaşılamayan şey

`ready_to_publish` **hâlâ HTTP'den istenemez**: `TaskUserTransitionName` onu
taşımaz (SI-222) ve H3 bunu değiştirmedi, çünkü ADR-0009 §8 kabulün geçişin
**girdisi** olmasını şart koşuyor ve geçişi kabulün yan etkisi yapmayı
yasaklıyor. Sonuç: üç yayım alanı doğrulanmış olsa bile görevi
`ready_to_publish`'e taşıyan bir kullanıcı rotası yoktur. Bu, kapatılmış bir
karar değil **açık bir boşluktur** ve burada yazılıdır; onu kapatmak
`TaskUserTransitionName`'i genişletmek demektir ve o ADR-0009'un kapsamında
değildir.
