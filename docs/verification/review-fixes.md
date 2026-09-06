# 58b5423 incelemesi — düzeltme turu

5 Eylül 2026. Taban: `58b542310758cc2c95f735dd2bbde2808f2d658f`.
Yerel HEAD ve GitHub main eşleşti; başlangıç çalışma ağacı temizdi.
GitHub #10–#21 birleşmiş; #18 model yürütmesini kapatmış,
#19 yalnız kanıt envanteri teslim etmiş. #19 Copilot incelemesi kota nedeniyle
yapılamamış; bu kayıt onay değildir. Açık #7 otomasyon PR'ına dokunulmadı.

## Yetki ve sıra

Ekli ilk prompt tarihsel ürün gereksinimidir; bu turun güncel talebi uygulanır.
Önce F1–F5, sonra model ve teslim akışı. PR açılması yetkilidir, merge yasaktır.
Son kullanıcı mesajı canlı model ve mevcut DID ile ayrı operasyonu yetkilendirir.
Otomatik testler yine yalnız geçici veri ve sahte transport kullanır.
Anahtar bu belgeye, kaynak koduna veya PR'a yazılmaz. Manuel tarayıcı ve görsel
kabul kullanıcıya aittir.

## Yeniden üretim ve değişen davranış

| Bulgu | Düzeltme öncesi kanıt | Değişiklik |
|---|---|---|
| F1 | Yeni dosya sonrası devam `artifact_missing`; güncellemede eski dosya `FileNotFoundError` | Geç kalan güncelleme önceki UTF-8 baytlarını geri getirir; açık devam geri alınmış adımı tekrar çalıştırır |
| F2 | Start ve resume yanıtları beklerken aynı ekranda Durdur disabled | Durdurma ayrı istek/durumla aynı run'a ulaşır; eski stop yanıtı yeni bitişi ezmez |
| F3 | B çıktısı sonrasında A kabulü `passed` | Yeni çalışma eski kanıt geçerliliğini düşürür; kabul/test/çıktı referansları kararlı plan+run+dosya özetine bağlanır |
| F4 | Yeni servis listeler fakat resume `run_not_paused` | Açık kullanıcı devamında kesilen çalışma uzlaştırılır; uygulanması belirsiz adım tekrar edilmez |
| F5 | `{}`, null veya eksik status başarılı kabul edilir; gövde timeout'u `malformed` | AppStatus iç içe alanları API sınırında doğrulanır; timeout ayrı sınıflanır; bölüm render hatası gezinmeyi düşürmez |

İlk backend regresyon koşusu: **4 failed**. İlk frontend regresyon koşusu:
**6 failed, 53 passed**. Bunlar Windows üzerinde gerçek ürün servisleri ve
jsdom bileşenleriyle ölçüldü; raporun Linux ölçümü kopyalanmadı.
İlk düzeltilmiş runtime koşusu **31 passed**, genişletilmiş runtime/proof/task
koşusu **120 passed**. İlk bütün frontend koşusu **321 passed**.

İlk tam backend koşusu **5 failed, 2213 passed**: eski paket/dist farkı,
yeni kaynakların henüz Git index'ine alınmaması ve yeni Callable parametresini
tanımayan durum-üretici test yardımcısı. Başarısızlıklar atlanmadı.
Test yardımcısına iki revision okuyucusu eklenerek yeni public metot da
sınandı; assertion kaldırılmadı. Paket yeniden üretilir ve kapılar tekrar koşulur.

Yeni çalışma zamanı bağımlılığı yok. Şema migration başı `0009` korunur;
çıktı sürümü bağları mevcut `app_metadata` içinde yalnız hash olarak tutulur.
Geçmiş kabul referansları silinmez, güncel geçerlilikleri ayrı değerlendirilir.

## Devam eden zorunlu iş

Model çağrısı, doğrulanmış kabul koşulları ve gerçek dosya teslimi henüz bu
ilk düzeltme grubunun yeteneği değildir; sonraki PR grubunda tamamlanacaktır.
F5 doğrulayıcısı bu grupta AppStatus'a uygulanır; diğer bölümler render
boundary ile korunur. Canlı doğrulama ve kullanıcı kabulü henüz yapılmadı.

---

# Küme 11 — modelin okuyamadığı istek, ve ön yüzün reddettiği sonuçlar

6 Eylül 2026. Dal: `codex/review-regressions`. Bu bölümdeki her sayı bu
makinede koşuldu; hiçbiri başka bir rapordan kopyalanmadı.

## İş 1 — model, cevaplaması istenen mesajı okuyamıyordu

### Kırmızı (düzeltmeden önce)

```
uv run --directory apps/station-api pytest ../../tests/security/test_work_scan_http.py \
  -p no:warnings -k "carries_the_request_text"
```

```
>       assert names, "the suggested task's workspace holds no file at all"
E       AssertionError: the suggested task's workspace holds no file at all
E       assert []
1 failed, 41 deselected
```

Ölçülen zincir: `workscan/service.py::suggest` adayın baytlarını
`candidate_content` ile üretip `content_sha256`'ya hash'liyor ve baytları
atıyordu. `TaskRecord`'da içerik sütunu yok. Modele giden brief
(`planner/service.py::_task_brief`) bu yüzden yalnız başlık (≤120 karakter),
modül, sürüm kimliği, içerik özeti ve çalışma alanı envanteri taşıyordu —
`_task_brief`'in kendi docstring'i durumu zaten yazıyordu.

### Düzeltme

Veritabanına içerik sütunu **eklenmedi**. `suggest` isteği görevin kendi
çalışma alanına yazar; model onu mevcut `read_workspace_file` aracıyla okur.

| Karar | Gerekçe |
|---|---|
| Dosya adı `oda-istegi.md` | Sabit ve tahmin edilebilir: oda içeriğinden türetilmiş bir ad saldırgan-seçimli olurdu ve `safe_name` reddedince tuhaf bir oda adı başarısız öneriye dönerdi. Model adı brief'te bir kez duyar ve tahmin edebilir. `safe_name`'den değişmeden geçtiği bir testle sürülür (M2). |
| Caveat `authority.py::REQUEST_CONTENT_CAVEAT` | `TOPIC_CAVEAT`/`MEASURED_CAVEAT` ile aynı kalıp ve aynı ayrım, farkı okuyucusunun bir kişi değil bir model olması. İki yarımı ayrı söyler: **kim yazdı** (doğrulanmamış yabancı) ve **ne olarak işlenir** (VERİ; talimat, izin, kural, yetki değil). Yalnız birincisini söylemek "öyleyse buna göre davran"ı çıkarıma bırakırdı. |
| Güvenilmeyen bölüm **dosyanın sonuna kadar** | Çitin kapanış işareti oda mesajının içerebileceği bir dizedir. Kapanış işareti olmayan bir bölge erken kapatılamaz, yani hiçbir bayt dizilimi saldırgan metnini "Station'ın kendi cümleleri" yarısına geri sokamaz. Sahte işaret + sahte başlık taşıyan bir mesajla sürülür (M4). |
| Caveat hem dosyada hem brief'te | Brief dosya hiç açılmadığında geçerlidir; dosya brief uzun bir oturumda yukarı kaydığında geçerlidir. |

**Yazma başarısız olursa: görev yine açılır, ret yanıtta taşınır.** Satır ve
ilk durum geçişi dosyadan önce yazılır (çalışma alanı görev kimliğiyle
adreslenir), ve bu üründe görev satırını geri alma yolu yoktur — durum
makinesi bir denetim izidir. Exception fırlatmak, gerçek bir görev
`suggested` dururken çağırana "kaydedilemedi" demek olurdu. Yanıt bu yüzden
`request_file` (ad veya `""`) ve `request_file_detail` (her iki yönde de dolu
bir cümle, çalışma alanının kendi `reason` kodu ile) taşır; `WorkScanPanel`
ikisini de gösterir. `content_sha256`/`source_version_id` **etkilenmez** ve
bu, çalışma alanı olan ve olmayan iki build'in aynı adayı aynı özete
bağladığı bir testle sürülür (M11).

`OSError` de yakalanır (dolu disk, reddedilen ACL): yalnız `strerror`
taşınır, `filename` taşınmaz — bir makine yolu yanıt gövdesine yazılmaz.

### Yeşil

```
uv run --directory apps/station-api pytest ../../tests/security/test_work_scan_http.py \
  -p no:warnings -q
...................................................                      [100%]   (51 passed)
```

## İş 2 — ön yüz `truncated`/`inconclusive` yanıtlarını düşürüyordu

### Kırmızı (düzeltmeden önce)

```
npm --prefix apps/station-web run test -- --run src/api/client.test.ts -t "outcome vocabulary"
```

```
× accepts a truncated outcome rather than refusing the document
  → promise rejected "ApiError: malformed_response" instead of resolving
× accepts a inconclusive outcome rather than refusing the document
  → promise rejected "ApiError: malformed_response" instead of resolving
✓ still refuses an outcome nobody defined
2 failed | 1 passed
```

`response-validation.ts` ve `types.ts` beş üye sayıyordu; backend yediye
çıkmıştı. Kesilmeyi bildiren her yanıt sınırda `malformed` oluyordu — yani
kesilme düzeltmesinin kaldırdığı aşırı-iddia bir katman dışarı taşınmıştı.

### Düzeltme

Doğrulayıcı ve mirror yedi üyeyi sayar. `TasksPanel` iki yeni durumu
backend'in kendi cümlelerinden okunan sözcüklerle etiketler:

- `truncated` → "Yanit cikti tavaninda kesildi; oturum acik kaldi", ton
  `problem`. `finished`'ın tonu (`inactive`, "durum: etkin degil") kapanmış
  bir oturumun görüntüsüdür ve bu dal onu ödünç alamaz — insanları yeniden
  denemeden gönderen tam olarak buydu. Not alanı: "Bu bir bitis degildir…
  yeniden isteyebilirsiniz; her istek bir tur harcar."
- `inconclusive` → "Arac cagrisi gelmedi; nedeni okunamadi, oturum
  kapatilmadi". Sebep sağlayıcının kendi yazımıyla `detail` içinde kalır;
  not alanı "Station anlamini uydurmaz" der.

Kaynak cümleler `planner/service.py::TRUNCATED_DETAIL`,
`_inconclusive_detail` ve `docs/model-planning.md` §5'ten okundu.

### Yeşil

```
npm --prefix apps/station-web run test
Test Files  13 passed (13)     Tests  432 passed (432)
```

## Mutasyon

Her yeni guard bir mutasyonla sürüldü; mutasyon uygulanır, hedef test koşulur,
kaynak geri yazılır.

| # | Mutasyon | Yakalayan test | Sonuç |
|---|---|---|---|
| M1 | `suggest` dosyayı yazmaz (asıl kusur geri getirilir) | `..._carries_the_request_text_where_a_model_can_read_it` | yakalandı |
| M2 | Dosya adı `oda istegi.md` (izin listesini geçmez) | `..._name_survives_the_workspace_allow_list` | yakalandı |
| M3 | `REQUEST_CONTENT_CAVEAT` dosyadan çıkarılır | `..._says_the_room_half_is_data...` | yakalandı |
| M4 | Alıntıdan **sonra** bir Station cümlesi eklenir | `..._room_text_is_last_and_has_no_closing_marker_to_forge` | yakalandı |
| M5 | `WorkspaceError` yeniden fırlatılır | `..._refused_write_does_not_discard_the_task...` | yakalandı |
| M6 | `except OSError` dalı kaldırılır | `..._operating_system_failure_does_not_escape...` | yakalandı |
| M7 | Çalışma alanı yokken cümle boşalır | `..._no_workspace_root_says_so...` | yakalandı |
| M8 | Sekiz ögeden biri dosyadan düşer | `..._carries_the_eight_elements...` | yakalandı |
| M9 | Brief dosyayı adlandırmaz | `..._brief_names_the_request_file_and_calls_it_data` | yakalandı |
| M10 | Brief dosyayı envanterden bağımsız vaat eder | `..._brief_promises_no_request_file_when_there_is_none` | yakalandı |
| M11 | Dosya gövdesi görevin bağlandığı içeriğe katılır | `..._content_digest_and_the_source_version_did_not_move` | yakalandı |
| M12 | Route `request_file` alanını boşaltır | `..._writes_the_file_and_still_contacts_nobody` | yakalandı |
| M13 | Doğrulayıcı `truncated`'ı düşürür | `accepts a truncated outcome` | yakalandı |
| M14 | Doğrulayıcı `inconclusive`'i düşürür | `accepts a inconclusive outcome` | yakalandı |
| M15 | `outcome` kapalı sözlük olmaktan çıkar (`str`) | `still refuses an outcome nobody defined` | yakalandı |
| M16 | `truncated` "oturum bitti" diye etiketlenir | `says a truncated turn was cut off` | yakalandı |
| M17 | `truncated` kapanmış oturumun tonunu ödünç alır | `says a truncated turn was cut off` | yakalandı |
| M18 | Açıklama notu hiç render edilmez | `carries an unreadable ending` | yakalandı |
| M20 | Öneri doğrulayıcısı `request_file`'ı istemez | `refuses a suggestion with no ...` | yakalandı |
| M21 | Tarama paneli okunabilirlik cümlesini göstermez | `opens a chosen candidate as a local suggested task` | yakalandı |

**20/20 yakalandı.** İlk turda M11 ve M15 hayatta kalmıştı ve ikisi de testin
değil mutasyonun sorunuydu: M11 önceden var olan `candidate_content`'i
mutasyona uğratıyordu ve test beklenen özeti aynı mutasyona uğramış
fonksiyondan hesapladığı için totolojikti; M15'in mutasyonu `shape`'e
bilinmeyen bir anahtar ekleyip her belgeyi `malformed` yapıyordu, yani testi
yanlış yönden geçiriyordu. M11'in testi artık iki bağımsız iddia taşır
(özet adaydan hesaplanır **ve** çalışma alanı olan/olmayan iki build aynı
`source_version_id`'yi üretir); M15'in mutasyonu doğru mutasyonla
değiştirildi.

## Ölçülmeyenler

- Gerçek bir sağlayıcıya istek yapılmadı; her model turu `httpx.MockTransport`
  üzerinden koştu ve kimlik bilgisi sentetik `TEST-ONLY` sabitidir.
- Gerçek bir Technocore odası okunmadı; tüm oda belgeleri sahtedir.
- Playwright e2e koşulmadı (bu turun kapıları arasında değil); e2e fixture'ları
  öneri yanıtını taklit etmiyor, bu yüzden yeni alanlar oradan geçmiyor.
- Gerçek bir NTFS junction planlanmadı: reparse dalı `WorkspaceError`
  enjekte edilerek sürüldü. Junction'ın kendisi
  `test_agent_workspace.py`'nin mevcut kapsamındadır.
- Tam backend suite bu turda koşulmadı (istenmedi); koşulan alt küme ve
  komşu sınır testleri aşağıdadır.
