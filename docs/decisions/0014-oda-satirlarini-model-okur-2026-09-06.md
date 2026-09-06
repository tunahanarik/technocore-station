# ADR-0014 — Oda satırlarını model okur; kalıp listesi kaldırılır (6 Eylül 2026)

Durum: **kabul edildi** · Bağlam: kullanıcının kendi odalarında yaptığı ölçüm
(sıfır aday) ve verdiği karar · **ADR-0007 §2'nin dayandığı olguyu geçersiz
kılar**, ADR-0012 ve ADR-0013'ün açtığı yolu ikinci bir tüketiciye taşır.

Bu ADR bir **ürün vaadini** değiştirir: İş Tara ekranı bugüne kadar
*"anlamsal çıkarım yoktur"* diyordu ve bu cümle bu karardan sonra **yanlış**
olacaktır. Hiçbir güvenlik değişmezini gevşetmez; yasak kaydı, reddedilen
odalar, gerçek gönderim yasağı ve yürütme yasağı olduğu gibi kalır.

## 0. Ölçüm: kalıp listesi hiçbir şey görmedi

Kullanıcı kendi odalarında gerçek bir tarama koştu. Sonuç:

```
gpu_mempool         · 50 satir okundu · 0 aday · 0 reddedilen
technocore          · 50 satir okundu · 0 aday · 4 reddedilen
technocore-genesis  · 50 satir okundu · 0 aday · 18 reddedilen
```

Sebep tek bir cümleyle söylenebilir: `candidates.py::SIGNALS` işi **birebir
ifade eşleşmesiyle** tanıyordu — dört sinyalde toplam **29 marker**
("yardim eden", "help wanted", "hata veriyor", "please review", "belge yok"
…). Bu 29 dizeden birini içermeyen bir satır **hiçbir şey** üretmiyordu: ne
aday, ne ret. Ekranda görünen tek şey boşluktu.

Ölçümün ikinci yarısı daha keskindir. Aynı dosyada
`PROHIBITED_MARKERS[wallet_or_payment]` **tek başına 34 marker** taşıyor,
yani **reddeden süzgeç kabul eden süzgeçten geniş**. Kullanıcının odalarında
bir şeye eşleşen hemen her satır, bir cüzdan reddine eşleşti (4 + 18 = 22
ret, 0 aday). Ürün, işi tanımayan ama reddetmeyi iyi bilen bir tarayıcıydı.

Kullanıcıya üç yol sunuldu — markerları genişletmek, modele okutmak, cüzdan
reddini gevşetmek. **Kullanıcı açıkça modele okutmayı seçti** ve reddi
gevşetmeyi **seçmedi**. Bu ADR o kararı kaydeder.

## 1. Karar: kalıp listesi kalkar, şablonlar kalır

`SignalId`'nin dört üyesi (`help_wanted`, `defect_report`, `review_request`,
`documentation_gap`) **kalır**. `Signal` kaydının `benefit`, `deliverable`,
`success_condition`, `test_method`, `permissions`, `risks` ve `effort_band`
alanları **birebir kalır**. Kalkan tek şey `Signal.markers` — yani eşleşme.

**Neden şablonlar kalıyor.** Bu alanlar bir adayın *neye söz verdiğini*
söyleyen ürünün kendi cümleleridir: başarı koşulu, nasıl test edileceği,
hangi iznin gerektiği, hangi riskin taşındığı. Modelin bunları yazması,
"model sınıflandırır" ile "model kabul ölçütünü yazar" arasındaki farktır ve
ikincisi çok daha büyük bir iddiadır: `planner/service.py::_condition_sentence`
zaten aynı ayrımı yapıyor ve model önerisiyle kaydedilen bir planın kabul
koşulunu **modele yazdırmıyor** ("bir ölçütü öneren tarafın da yazması bir
ölçüt değildir"). Aynı gerekçe burada da geçerlidir, hatta daha güçlüdür:
buradaki metin bir yabancının odaya yazdığı satır hakkındadır.

Sonuç: modelin ürettiği tek şey **iki tipli değerdir** — hangi satır ve dört
şekilden hangisi. Serbest metin **kabul edilmez**; modelin döndürdüğü
argümanlarda metin taşıyan bir parametre **yoktur**. Bir adayın taşıdığı her
dize hâlâ ya ham kaynak alanından ya sabit şablondan gelir; üçüncü kaynak
hâlâ yoktur. ADR-0007 §2'nin *"deterministik çıkarımda uydurulacak alan
yoktur"* cümlesinin koruduğu şey böylece korunur — kaybolan yalnız
"deterministik" sözcüğüdür.

`derivation` alanı bu yüzden vardır ve şimdi işini yapar:
`rule_based_pattern_match` yerine `model_read_line_classification` yazar, yani
eski bir adayla yeni bir aday **adıyla** ayrılır.

## 2. Yol: satırlar veridir, cevap kapalı registry'den döner

Bir tarama artık şu adımlardan geçer ve her adım mevcut savunmadan geçer:

1. **Oda okunur** (değişmedi): `resolve_room_target` → `RoomScanTarget` →
   `parse_room_messages`. `DENIED_ROOMS`, oda kalıbı, istenen-oda kuralı,
   süpürme ve tavanlar aynen.
2. **Yasak kaydı çalışır** (değişmedi ve **modelden önce**): bir satır
   `prohibited_shape` ile eşleşiyorsa yerel olarak reddedilir, gerekçesiyle
   gösterilir **ve modele hiç gönderilmez**. Sıralama yapısaldır; etrafından
   dolaşan kod yolu yoktur.
3. **Kalan satırlar modele okutulur.** Satırlar numaralandırılmış, süpürülmüş
   ve sınırlanmış bir **veri bloğu** olarak gider (§3).
4. **Model `tool_calls` döndürür.** Her `function.name` **derleme zamanı
   registry'sinde aranır** (`workreader/protocol.py::READING_TOOLS`);
   kayıtsızsa **tur bütünüyle reddedilir**. Argümanlar tipli doğrulamadan
   geçer; uymayan tur bütünüyle reddedilir. Bu, `planner/service.py`'nin
   plan turu için yaptığının aynısıdır ve regex ile ayrıştırılmış serbest
   metin **kabul edilmez**.
5. **Verdict aday üretimine bir girdidir**, bir atlama yolu değil.
   `derive_from_room` verdict'i alır, ama yasak kontrolünü, `(room, seq)`
   kimliğini, sekiz zorunlu öğeyi, `assert_no_forbidden_claim` denetimini ve
   `neutralise` çağrılarını **aynen** uygular. Modelin işaret ettiği satır
   yasaklıysa aday **üretilmez**.
6. **Hiçbir şey çalışmaz.** Sonuç bir aday listesidir; göreve çevirmek
   kullanıcının eylemidir ve görev `suggested` doğar (ADR-0007 §7).

### Registry neyi kabul eder

Dört araç, `SignalId` ile birebir:
`report_help_wanted`, `report_defect_report`, `report_review_request`,
`report_documentation_gap`. Şekli **araç adı** taşır, bir argüman değil —
böylece şekil seçimi de ad araması olur.

Her aracın **tek** parametresi vardır: `lines`, virgülle ayrılmış satır
numaraları (`^[0-9]+(,[0-9]+)*$`, en çok bir tur dolusu giriş, her biri o
turda gönderilen aralıkta). Parametre listesinde `path`, `url`, `room`,
`file`, `tool`, `recipient` **yoktur ve olamaz**: registry derleme zamanı bir
tuple literal'idir ve bir test parametre adlarını bu yasak listeye karşı
tarar. Model bir oda adı, bir adres, bir dosya, bir araç veya bir alıcı
**adlandıramaz**; adlandırsa da taşıyacağı alan yoktur.

Metin taşıyan bir parametre olmadığı için "modelin yazdığı cümle" diye bir
şey ürünün hiçbir yüzeyinde yoktur.

## 3. Yabancı metnin kapsanması

Bu, bu projedeki en riskli değişikliktir ve tasarımın çoğu buradadır. Odadan
okunan her satır **bir yabancının yazdığı doğrulanmamış girdidir**
(`authority.py`, seviye 3 = `community`). Model çağrısı bu metni bir modele
verir; yani bugüne kadar yalnızca ekrana çıkan bir metin artık bir muhakemeye
giriyor.

Beş katman, ve hiçbiri tek başına yeterli sayılmaz:

1. **Rol ayrımı.** Kurallar `system` mesajındadır; oda satırları **yalnız**
   `user` mesajının veri bölümündedir. Oda metninden üretilmiş bir `system`
   veya `assistant` mesajı **yoktur** ve üretilemez: mesaj kurucusu odadan
   gelen metni tek bir rolde, tek bir bölümde toplar.
2. **Kapsayıcı.** Satırlar `<<<ODA-SATIRLARI` … blok işaretleri arasında,
   **numaralandırılmış** ve **tek satıra indirilmiş** olarak gider. Satır
   içindeki her satırsonu ve her taşıyıcı karakter süpürülür
   (`sweep_untrusted`), böylece bir satır kendi kapsayıcısını kapatıp yeni
   bir "talimat bölümü" açamaz. Kapanış işareti satırın taşıyabileceği bir
   dize olduğu için **kapanış işaretine güvenilmez**: blok dosyanın/mesajın
   sonuna kadar sürer ve bloktan sonra hiçbir kural cümlesi gelmez
   (`workscan/request_file.py`'nin aynı kararı).
3. **Caveat, bloğun başında.** `authority.py::REQUEST_CONTENT_CAVEAT`'in
   kardeşi olan `READING_CONTENT_CAVEAT` bloğun hemen üstündedir: metni kim
   yazdı (doğrulanmamış bir yabancı) ve ne olarak işlenir (**veri**; talimat,
   izin, kural veya yetki değil).
4. **Cevabın şekli.** En önemli katman budur ve prompt'ta değil **tipte**dir:
   modelin döndürebileceği tek şey `(araç adı, satır numaraları)`. "Bunu acil
   olarak işaretle", "kuralları yok say", "şu aracı çağır" diyen bir satır
   modelin cevabını en fazla **yanlış bir sınıflandırmaya** çevirebilir — ve
   yanlış bir sınıflandırma bile yasak kaydından, sekiz öğeden ve
   kullanıcının onayından geçmek zorundadır. Prompt injection'ın burada
   ulaşabileceği en uç sonuç, kullanıcının okuyup reddedeceği fazladan bir
   adaydır.
5. **Kapsam dışı numara turu düşürür.** Model o turda gönderilmemiş bir satır
   numarası döndürürse tur **bütünüyle** reddedilir ve turdaki her satır
   gerekçesiyle gösterilir. Yalnız o numarayı atmak değil: gönderilmemiş bir
   satır hakkında konuşan bir turun öteki cevapları da bir şeyin kanıtı
   değildir — `planner/service.py`'nin "öneri bütünüyle ya da hiç" kuralı,
   aynen. Aynı satırı iki şekle koyan tur da düşer, çünkü birini seçmek bu
   lane'in yapmamak üzere kurulduğu serbest yargının kendisidir.

## 4. Harcama: turlar sayılır ve tavan tarama başınadır

Tarama artık **para harcıyor**. ADR-0012 §3 ve ADR-0013'ün birimi aynen
geçerlidir: birim **model çağrısı sayısı**dır; `usage` ve `cost` kaydedilir,
**tavan olarak okunmaz**.

**Sayaç.** `agent/model_calls.py::ScanModelCallCounter` — `ModelCallCounter`
ile aynı modülde, aynı kuralla: `used()` okur, `record_call()` **yalnızca
bir artırır**, `reset`/`clear`/setter **yoktur**. Bir AST taraması
`scan_model_calls_used` alanına tek yazının o metotta olduğunu ve o yazının
bir **toplama** olduğunu tutar (`test_nothing_lowers_the_model_call_counter`
kalıbı).

**Tavan.** `budget.CEILING.max_model_calls` (8) — yeni bir sabit yoktur ve
`budget.py` değişmemiştir. Kontrol, planlama yolununkiyle **aynı saf
fonksiyondur**: her turdan önce `budget.check(RunUsage(tool_calls=0,
model_calls=<bu taramada harcanan>, elapsed_seconds=0))`. Tavan dolduğunda
kalan odalar/satırlar `reading_ceiling` gerekçesiyle **gösterilir**,
sessizce düşürülmez.

**Satır sayısı tur sayısını çarpamaz.** Bir tur en çok
`MAX_LINES_PER_TURN` satır taşır ve bir odanın satırları bu boyutta parçalara
bölünür; bütün taramanın tur sayısı yine de tavanla sınırlıdır. İki yüz
satırlık bir oda **iki yüz tur** değil, en çok tavanın izin verdiği kadar tur
harcar.

### Sayaç neden diske yazılmıyor — ve bunun bedeli

ADR-0013 sayacı satıra taşıdı, çünkü oradaki kusur **doldurulabilir bir
sayaçtı**: sayı uzun ömürlü bir öznenin (bir görevin) bellekteki oturum
nesnesindeydi ve "Oturumu unut" düğmesi o nesneyi düşürüyordu.

Bir taramanın böyle bir öznesi **yoktur**. Bir tarama tek bir eşzamanlı
istektir: içinde basılacak bir düğme, sürdürülecek bir oturum ve yeniden
başlatılacak bir süreç yoktur. Taze bir tarama kimliğiyle anahtarlanmış bir
satır, bir sonraki taramada bellekteki sayacın yenilendiği gibi yenilenirdi —
yani **hiçbir şeyi değiştirmezdi**. ADR-0012 §1'in kaldırdığı şey tam olarak
budur: *silindiğinde hiçbir testin kırmızı olmadığı bir denetim, okuyanı asıl
korumadan uzaklaştırır.* Bu yüzden burada satır yoktur ve olmamasının
gerekçesi yazılıdır.

**Bedeli açıkça:** ikinci bir tarama kendi tavanıyla başlar. Bu, ADR-0013
§3.1'in "yeni bir görev kendi tavanıyla başlar" cümlesinin aynısıdır ve aynı
şekilde bir kullanıcı eylemi gerektirir. Tekrar tarama tekrar para harcar;
bunu sınırlayan şey tavan değil, **kullanıcının bilerek bastığı düğmedir** —
ve bu yüzden maliyet düğmenin yanında yazılıdır (§6).

## 5. Sağlayıcı kullanıcı hakkında bir bilgi kaynağına dönüşmez

Gönderilen istek **yalnızca** şunları taşır:

- sabit `system` metni (kurallar ve dört şeklin adları);
- okunan satırların numaralandırılmış, süpürülmüş, sınırlanmış metni;
- kapalı registry'nin JSON Schema projeksiyonu.

Gönderilmeyenler, adıyla: DID, seed, private key, mnemonic, recovery
dosyası, kasadan hiçbir şey, kullanıcının kimliği, görev geçmişi, çalışma
alanı dosyaları, kanıt kayıtları, oturum çerezi, `content_sha256`,
`source_version_id`. Oda **adı** da gönderilmez — model satırları sınıflandırır,
onların nerede yazıldığını bilmesi gerekmez ve bilmemesi bir odanın adının
sağlayıcıya çıkmamasıdır. Bir test istek gövdesini bu listeye karşı tarar.

Muhakeme (`reasoning_content`) ADR-0012 §1'in kuralıyla: **okunur bile
değildir, saklanmaz, gösterilmez**. Bu yolun döndürdüğü tipte
(`ReadingResult`) modelin metnini taşıyacak bir alan yoktur ve
`PlanProposal.text` bu yolda **hiç okunmaz**.

## 6. Kullanıcıya ne söylenir

Üç cümle, üçü de her `status` okumasında yanıt gövdesindedir — bir tasarım
belgesine gömülmez:

1. **Dürüstlük cümlesi değişti.** `DERIVATION_HONESTY_SENTENCE` artık
   *"anlamsal çıkarım yoktur"* demez; adayların bir dil modeli tarafından
   okunarak çıkarıldığını, modelin yanılabileceğini ve kabul etmeden önce
   alıntının okunması gerektiğini söyler.
2. **Maliyet cümlesi eklendi.** `MODEL_READING_COST_SENTENCE`: bir taramanın
   model çağrısı harcadığını, bir turun en çok kaç satır taşıdığını ve bir
   taramanın en çok kaç tur harcayabileceğini **sayıyla** söyler. Tarama
   düğmesinin yanındadır, yani **harcanmadan önce** okunur.
3. **Yasak cümlesi kaldı.** `PROHIBITION_HONESTY_SENTENCE` değişmedi: yasaklar
   hâlâ kalıp eşleşmesiyle reddedilir ve listede olmayan bir sözcükle
   istenen bir ödeme işi hâlâ aday üretebilir. Kullanıcı reddi gevşetmeyi
   seçmediği için bu cümle olduğu gibi durur.

Ayrıca her adayın `risks` listesindeki `_RISK_NO_SEMANTICS` cümlesi
değiştirildi: artık "kalıp eşleşmesiyle çıkarıldı" değil, "bir dil modeli
okuyarak sınıflandırdı; model yanılabilir" der.

## 7. Paket sınırı: `workscan` hâlâ modele erişmez

`tests/security/test_work_scan_candidates.py::test_the_package_calls_no_model_and_imports_no_completion_path`
`station_api/workscan` ağacında `station_api.opencode` importunu yasaklar. Bu
test **değişmedi ve değişmiyor**, çünkü söylediği şey hâlâ doğrudur ve doğru
kalması iyidir: tarama paketi ayrıştırır, süpürür, yasakları uygular ve aday
kurar; **model çağrısını yapmaz**.

Model yolu yeni bir pakettedir: `station_api/workreader/`. Bu, ADR-0013
§2'nin kalıbıdır — kural koda uydurulmaz, yeni olgu kendi evine taşınır
(`budget.py` tavandır, `model_calls.py` sayaçtır, ikisi ayrı dosyadadır).
`workreader` `opencode.service`, `opencode.planner` ve `opencode.errors`
dışında bir giden yüzeye dokunmaz; `opencode.client`, `httpx`, `socket` ve
`ssl` importu yasaktır ve bir test bunu sözdizim ağacından tutar
(`test_planner_boundary.py`'nin aynısı).

`WorkScanService` modeli bir **protokolle** alır (`LineReader`), yani tarama
paketi somut sınıfı bile bilmez; bağlama `app.py`'de yapılır. Reader yoksa
tarama çalışır ve her satır `model_unavailable` gerekçesiyle reddedilir —
sessiz bir boş liste yerine adıyla bir ret.

## 8. `OUTBOUND_CLIENT_MODULES` beşte kalır

Yeni HTTP istemcisi yoktur. `workreader` mevcut `OpenCodeService.propose_plan`
metodunu **olduğu gibi** kullanır: aynı kimlik bilgisi kasası, aynı redaksiyon
penceresi, aynı tek-deneme kuralı, aynı host allow-list'i, aynı TLS politikası.

## 9. Değişmeyenler

Yasak kaydı (`PROHIBITED_MARKERS`, `PROHIBITION_DETAIL`) **kalır ve
uygulanır**; cüzdan/ödeme/hak talebi işleri hâlâ reddedilir ve kullanıcı bunu
biliyor. `DENIED_ROOMS` okumada da geçerlidir; lobby hiçbir yolda hedef
değildir. Zamanlayıcı, arka plan görevi ve `wait` yoktur; tarama yalnız açık
kullanıcı eylemiyle çalışır. Keyfi kod/shell yürütmesi kapalıdır. Gerçek
Technocore write yoktur. `0.0.0.0` bind yok, CORS yok, TLS doğrulaması
kapatılamaz. Bütün testler mock transport sürer; hiçbiri gerçek sağlayıcıya
veya Technocore'a istek yapmaz. İnsan güvenlik incelemesi ertelenmiş kalan
risktir (ADR-0001 §5).

## 10. Geriye dönük olarak ADR-0007 §2 ne olur

**Silinmez ve yanlış sayılmaz.** Yazıldığı gün doğruydu: o tarihte model
çağıracak bir kod yolu yoktu, sözleşme doğrulanmamıştı ve bir model çağrısı
hiçbir testte doğrulanamazdı. Kapattığı şey bir yetenek değil,
**doğrulanmamış bir varsayıma dayanarak yetenek açma** hakkıydı — ADR-0012'nin
ADR-0005/0008 için yazdığı cümlenin aynısı. Koşulu ADR-0012 karşıladı;
ölçülen sonuç (sıfır aday) da ADR-0007 §2'nin kendi bedel cümlesinin
("bir odadaki her fırsat görülmez") ne kadar pahalı olduğunu ölçtü. Bu ADR o
bedeli ödemeyi bırakır.

ADR-0007 §2'nin ikinci gerekçesi — **kimlik kararlılığı** — hâlâ geçerlidir
ve korunmuştur: aday kimliği `(room, seq)` üzerinden üretilir, model
çıktısından değil. Aynı satır aynı kimliği alır. `candidate_content` da
yalnız ham kaynak alanları ve sabit şablonlar üzerinden hesaplanır, yani
`source_version_id` model çıktısına bağlı değildir ve turdan tura değişmez.
