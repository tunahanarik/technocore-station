# ADR-0013 — Model çağrısı tavanı göreve yazılır (6 Eylül 2026)

Durum: **kabul edildi** · Bağlam: `ed39521`'in açık riski, `PROJECT_STATUS.md`
"Açık kalan iki not" · Değiştirdiği karar yok; **ADR-0012 §3'ü uygulanabilir
kılar**

Bu ADR hiçbir güvenlik değişmezini gevşetmez ve yeni bir yetenek açmaz. Tek
yaptığı, ADR-0012 §3'ün seçtiği bütçe biriminin **gerçekten bir tavan**
olmasını sağlamaktır.

## 0. Kusur: tek harcama kontrolümüzü bir düğme sıfırlıyordu

ADR-0012 §3 bütçe birimini bilerek seçti: **model çağrısı sayısı**. Token ve
para birimi sağlayıcının beyanıdır, bizim ölçümümüz değildir, ve karşı tarafın
bildirdiği bir sayıyla ifade edilen tavan karşı tarafın koyduğu tavandır. Bu
yüzden `usage` ve `cost` **kaydedilir** ama tavan olarak okunmaz. Geriye kalan
tek sayı — Station'ın kendi yaptığı istek sayısı — bütçenin **tamamıdır**.

O sayı bir satırda değil, bellekteki oturum nesnesinin bir alanındaydı
(`_Session.model_calls`). `ModelPlannerService.forget` — ekrandaki "Oturumu
unut ve baştan başla" düğmesi — o nesneyi düşürüyordu. Yani:

| Kapı | Eski davranış |
|---|---|
| "Oturumu unut" düğmesi | Sayaç sıfırlanır. **Basıldığı kadar**, ölçülü uca karşı. |
| Uygulamayı yeniden başlatma | Sayaç sıfırlanır. Aynı sonuç, biraz daha sürtünmeyle. |

Dört yer bunun tersini söylüyordu ve **dördü de yanlıştı**:
`TasksPanel.tsx`'in "tavan sifirlanmaz" cümlesi, o cümleyi sabitleyen
`TasksPanel.test.tsx` iddiası, `routes/planner.py::forget_session`'ın
"tavanın etrafından dolaşmanın yolu değildir" düzyazısı, ve — en keskini —
adı `test_forgetting_a_session_does_not_forget_the_spend` olup gövdesinde
`state.model_calls_used == 0` iddia eden test. Adı doğruyu, gövdesi tersini
söyleyen bir test, `grep` ile bakan herkese **kapsam** gibi görünür.

## 1. Karar: sayaç göreve aittir ve kalıcıdır

**Model çağrısı sayacı görev başına tutulur ve diske yazılır.**

Yeni tablo: `model_call_ledger` (migration `0011`, yalnız ekleme).

```
task_id           PK, task_record.id'ye FK, ON DELETE CASCADE
model_calls_used  tamsayı, yalnız artar
first_call_at     ilk sayılan turun anı
last_call_at      son sayılan turun anı
```

Erişim: `station_api/agent/model_calls.py::ModelCallCounter`, `AgentService`
üzerinden (`agent.model_calls`), `activity` özelliğinin aynısı gibi.

**Yeniden başlatma da aynı kusurdur.** Soruldu ve cevabı evettir: kullanıcının
zaten sahip olduğu bir kapı, uygulamayı kapatıp açmaktır, ve süreç belleğinde
duran bir tavan o kapıdan geçilir. Bu yüzden karar "unutmaya dayanıklı" değil,
**kalıcı**dır. Konuşma ise kalıcı **değildir** ve olmamalıdır: SI-224 bir
yeniden başlatmanın hiçbir şeyi sürdürmediğini söyler, saklanmış bir konuşma
tam da birinin sürdüreceği şeydir ve ADR-0008 §6 model çıktısına bu şemada yer
olmadığını söyler. İki olgunun ömrü baştan beri farklıydı; tek evleri vardı.

## 2. Neden bu ev, öteki üçü değil

| Aday | Neden değil |
|---|---|
| `task_record`'a sütun | SI-225 görev katmanının bütçe alanı açmadığını söyler ve `test_the_task_layer_opens_no_budget_field` bunu o tablonun sütunlarını **okuyarak** tutar. Oraya yazmak kuralı koda uydurmak olurdu. |
| `activity_event` satırlarını saymak | Her sayılan tur zaten bir `model_called` satırı yazıyor, yani bedava görünüyor. Ama o tablonun bir saklama politikası (`RETAINED_EVENTS = 500`) ve **kullanıcının çağırdığı bir silme** işlemi var. "Tavanı temizlemek için günlüğünü temizle" — `forget`'in kusurunun daha düzenli bir kapıdan hâli. |
| `budget.py` | O modül **tavanın kendisidir**: donmuş sabit, I/O yok, ve `CEILING`'in tam bir kez atandığını isteyen bir AST taraması var. Sınır ile sayaç farklı şeylerdir ve ayrı dosyalarda kalırlar. |

## 3. Kararın bedeli — açıkça

1. **Tavanı dolan bir görevin turu geri gelmez.** Sıfırlama rotası, metodu
   veya aracı **yoktur** ve bilerek yoktur: bir sıfırlama, `forget`'in başka
   bir adla geri gelmesidir. Kullanıcının yolu yeni bir görev açmaktır
   (tablo `task_id` ile anahtarlandığı için kendi tavanıyla başlar) ya da
   kaydedilmiş bir planı elle sürdürmektir.
2. **Bir şema değişikliği ve bir migration.** Yalnız ekleme; hiçbir mevcut
   tablo, sütun veya satır kimliği değişmez. **Backfill yoktur ve dürüst
   olmazdı:** turları hiç kaydedilmemiş bir göreve sayı uydurmak, tahminden
   yapılmış bir tavan olurdu.
3. **Görev silinirse satır da gider** (`ON DELETE CASCADE`). Var olmayan bir
   görevin tavanı yoktur; bu, hâlâ var olan bir görevin sayacını kaybetmesinin
   yolu değildir.
4. **Turun ne zaman sayıldığı değişmedi.** Sağlayıcı yanıtı ayrıştırıldıktan
   sonra, eskiden bellekteki sayacın arttığı yerde. Bu tur bir plan üretsin
   veya üretmesin sayılır; sağlayıcı hiç cevap vermediyse sayılmaz. Bu ADR
   **nerede yazıldığını** değiştirir, **neyin sayıldığını** değil.

## 4. Ürünün cümleleri düzeltildi

Dördü de artık doğru:

- `TasksPanel.tsx`: "tavan sifirlanmaz" **kaldı** (artık doğru) ve yanına
  yeniden başlatma yarısı eklendi — bir tavanı yeniden başlatmanın silmesi ile
  silmemesi **farklı vaatlerdir** ve kullanıcı hangisine sahip olduğunu bilmeye
  hak sahibidir.
- `TasksPanel.test.tsx`: cümle iddiası korundu ama artık iddianın **tek**
  dayanağı değil; yanına bu katmana ait olan iddia kondu (ekran sunucunun
  sayısını gösterir, kendi sıfırını uydurmaz) ve iddiayı gerçekten tutan
  Python testleri adıyla yazıldı.
- `routes/planner.py::forget_session`: düzyazı, cümlenin **yazıldığında yanlış
  olduğunu** ve neyin doğru kıldığını söylüyor. Yanıt cümlesi de artık harcanan
  tur sayısının durduğunu söylüyor.
- `test_forgetting_a_session_does_not_forget_the_spend`: **silinmedi,
  düzeltildi.** Adı baştan beri doğruydu; değişen iddiadır. Yerine geçen iddia
  daha fazlasını sabitliyor: harcama duruyor **ve** konuşma gerçekten düşüyor
  (bekleyen çalışma boşalıyor) **ve** kayıtlı çalışma yerinde.

## 5. Muhafızlar: davranış ve sözdizimi ağacı

Davranış testleri bugünkü kodun kapılarını sürer; yapısal testler yarın
açılabilecek kapıyı kapatır.

| Test | Ne sabitler |
|---|---|
| `::test_forget_cannot_be_clicked_for_a_second_ceiling` | Tavan dolduktan sonra üç kez "unut" + tur iste; hiçbiri ölçülü uca istek göndermez (sayan taraf **transport recorder**'dır) |
| `::test_the_ceiling_survives_a_restart_of_the_process` | Aynı motora ikinci bir `ModelPlannerService` — yeniden başlatmanın ta kendisi — sıfır istek gönderir |
| `::test_the_ceiling_is_counted_per_task_and_not_across_them` | Kalıcı sayaç ürün geneli bir sayaca **dönüşmedi** |
| `::test_nothing_lowers_the_model_call_counter` | `station_api` ağacının tamamında `model_calls_used`'a **tek** yazı vardır ve o `record_call`'dur (düz, annotate, artırmalı ve `setattr` yazımları) |
| `::test_the_ledger_row_is_never_deleted_and_reaches_only_two_modules` | **Mutasyonla bulundu:** satırı silmek de sayacı düşürür ve yalnız niteliği izleyen bir tarama bunu görmez. `model_calls.py` hiçbir şey silmez ve `ModelCallLedger` tam iki modülde anılır |
| `::test_the_only_counter_write_is_an_increment` | Tek yazının **toplama** olduğu; "tek yazıcı" o yazıcı sıfır atıyorsa hiçbir şey değildir |
| `test_agent_boundary.py::test_migration_0011_added_one_table_and_touched_nothing_else` | Tablonun **şekli**: `task_id` birincil anahtar (yani görev başına), sayı dışında okunacak bir izin alanı yok, eski tablolar yerinde |

## 6. Değişmeyenler

`OUTBOUND_CLIENT_MODULES` **beştedir**. Yeni bir giden yüzey, yeni bir
zamanlayıcı, yeni bir araç yoktur; araç registry'sinde tavanı veya sayacı okuyan
ya da yazan bir araç yoktur ve registry derleme zamanı bir tuple literalidir.
`CEILING` hâlâ tek yerde, donmuş ve yazılamaz. Token ve para birimi hâlâ tavan
değildir (ADR-0012 §3). Model hâlâ plan **önerir**, çalıştırmaz. Testlerin
hiçbiri gerçek sağlayıcıya istek yapmaz; hepsi mock transport sürer.
