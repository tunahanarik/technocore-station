# ADR-0012 — Model yolu açılıyor: sözleşme ölçülerek doğrulandı (6 Eylül 2026)

Durum: **kabul edildi** · Bağlam: bağımsız inceleme (`58b5423`) §3.1 ve
kullanıcının "ilk talepteki eksik ürün akışlarını tamamla" talimatı

Bu ADR **ADR-0005 §1.2 ve ADR-0008 §2'nin dayandığı olguyu geçersiz kılar**
ve model yolunu açar. Hiçbir güvenlik değişmezini gevşetmez.

## 0. Ne değişti: varsayım değil, ölçüm

ADR-0005 §1.2 şöyle diyordu: *tool-call wire formatı yayımlanmamıştır.*
ADR-0008 §2 bu olguya dayanarak model lane'ini kapattı ve
`tool_calls_supported: Literal[False]` yazdı. O tarihte **doğru bir
karardı**: doğrulanamayan bir sözleşmeyi uydurmamak, bu projenin en çok
tekrarlanan ilkesiydi.

**Sözleşme artık doğrulanmıştır.** Kullanıcı kendi OpenCode Go anahtarını
verdi ve kullanılmasını açıkça yetkilendirdi. Canlı ölçüm:

```
GET  https://opencode.ai/zen/go/v1/models              -> 200
     Kimliksiz de 200; anahtarli istek OpenAI sekilli liste dondurdu.

POST https://opencode.ai/zen/go/v1/chat/completions    -> 200
     Authorization: Bearer <anahtar>                   -> CALISIYOR (metered uc)
     Istek:  {"model":"glm-5.3-flash","max_tokens":150,
              "messages":[{"role":"user","content":"..."}],
              "tools":[{"type":"function","function":{
                 "name":"write_workspace_file",
                 "parameters":{JSON Schema}}}],
              "tool_choice":"auto"}
     Yanit:  finish_reason = "tool_calls"
             message.tool_calls[0].function.name      = "write_workspace_file"
             message.tool_calls[0].function.arguments = "{\"body\":\"hello\",\"name\":\"notes.txt\"}"
             usage = {prompt_tokens:184, completion_tokens:46, total_tokens:230,
                      completion_tokens_details:{reasoning_tokens:26}}
             cost  = "0"
```

**`reasoning_tokens` ayrica olculdu ve onemli:** 46 cikis token'inin **26'si
muhakemeye** gitti. Yani bu saglayicinin modelleri cikis butcesinin buyuk
kismini arac cagrisina gelmeden harcayabiliyor — nitekim canli bir kosuda
1024 token'lik varsayilan tavan tam olarak boyle tukendi ve model kesildi
(`finish_reason: "length"`). Tavan bu yuzden bir **maliyet** kontrolu degil,
bir **kesilme** ayaridir.

Üç şey **ölçüldü**, çıkarılmadı: (a) `Authorization: Bearer` metered uçta
kabul ediliyor; (b) protokol OpenAI `chat/completions` şeklinde; (c) model
**kayıtlı aracımızı doğru adla ve doğru argümanlarla** çağırdı.

İki ayrıntı kayda değer: `arguments` bir **JSON dizesidir**, nesne değil —
ayrıştırılması gerekir. Ve yanıt bir `reasoning_content` alanı taşır.

## 1. `reasoning_content` saklanmaz

H2 ve ADR-0009 §6 "modelin muhakemesi veya ham provider payload'ı için sütun
yok" kuralını koydu. Sağlayıcının böyle bir alan **gönderiyor** olması bu
kuralı değiştirmez: alan **okunur, kullanılmaz, saklanmaz, gösterilmez,
loglanmaz**.

**Bunu neyin sabitlediği düzeltildi (bağımsız inceleme).** İlk yazımda bu
bölüm "bunu bir test sabitler" diyordu ve iki yerde birden yanlıştı.

*Birincisi, kodun kendisi.* `parse_plan_response` içinde alanı sözlükten
`pop` eden bir döngü vardı ve yorumu bu döngüyü **koruma** diye adlandırıyordu.
Değildi: döngü no-op'a çevrildiğinde hiçbir test kırmızı olmadı — çünkü her
üye sözlükten **adıyla**, bir izin listesinden alınıyor, sözlük hiç
kopyalanmıyor ve `PlanProposal`'ın değerin düşebileceği bir alanı yok. Silinince
kimsenin fark etmediği bir kontrol, okuyanı asıl korumadan (tipten) uzaklaştırır.
Döngü **kaldırıldı** ve yerine korumanın ne olduğu yazıldı.

*İkincisi, "gösterilmez" yarısı tutmuyordu.* Sağlayıcı hatası kullanıcıya
gösterilirken yanıt gövdesinden **sınırlı bir alıntı** cümleye ekleniyor
(`planner._failed(..., quote=True)`, `adapters._with_excerpt`), ve `error`
üyesi taşıyan bir `200` gövdesi **bütünüyle** alıntılanıyor — `reasoning_content`
dahil. Kimlik bilgisi redaksiyonu bu alıntıya uygulanıyordu, muhakeme alanı
uygulanmıyordu.

**Karar:** deny-list, tüketildiği yere taşındı —
`opencode/client.py::DISCARDED_MESSAGE_FIELDS`, kimlik bilgisi redaksiyonuyla
**aynı fonksiyonda** (`_excerpt`) uygulanıyor. Alıntının teşhis değeri korunur:
sağlayıcının kendi hata metni kalır, yalnız muhakeme üyeleri çıkarılır.
Ayrıştırılamayan bir gövde (örneğin bayt tavanında ortasından kesilmiş uzun bir
muhakeme değeri) bu alanlardan birini **adıyla anıyorsa** alıntı bütünüyle
düşürülür — `evidence/language.py`'nin nötrleştirme kesin olmadığında yaptığının
aynısı.

Şunu sabitleyen testler: `test_model_planner.py::test_the_reasoning_field_is_dropped_rather_than_carried`
(tip düzeyi), `::test_a_quoted_provider_error_body_carries_no_reasoning` ve
`::test_an_unreadable_body_that_names_a_reasoning_field_is_not_quoted`
(gösterim yolu), `test_agent_boundary.py::test_no_agent_table_can_hold_a_model_reasoning_trace`
(şema).

## 2. Model plan **önerir**, çalıştırmaz

Açılan yol şudur ve her adımı mevcut savunmadan geçer:

1. Görev içeriği + **kapalı araç registry'sinin şeması** modele verilir.
2. Model `tool_calls` döndürür.
3. Her `function.name` **registry'de aranır**; kayıtsızsa gösterilebilir
   ret (mevcut `tool_unknown` yolu). **Model kendine araç ekleyemez.**
4. `arguments` ayrıştırılır ve **mevcut tipli parametre doğrulamasından**
   geçer; uymayan reddedilir. `path`/`url` parametresi **yoktur** — araca
   adres verilemez, bu değişmez korunur.
5. Sonuç bir **plan önerisi**dir. Bugünkü **dört onaylı akışın aynısından**
   geçer; onaysız çalışmaz. **Model plana kendi onayını veremez.**
6. Araç sonucu `role:"tool"` mesajıyla modele döner; döngü **tavanla**
   sınırlı ve **durdurulabilir**.

Böylece "model çıktısı doğrudan yürütülmez" kuralı, ADR-0008'de olduğu gibi
**yapısal** kalır — ama artık "model çıktısı diye bir şey yok" diyerek değil,
çıktıyı kapalı bir registry'den geçirerek.

## 3. Bütçe: yeni birim ölçülebilir olmalı

ADR-0008 §4 token ve para birimini **gerekçesiyle** reddetmişti ve
`refused_units` olarak yayımlamıştı. Sağlayıcı artık `usage` ve `cost`
gönderiyor.

**Karar:** yeni tavan birimi **model çağrısı sayısı**dır (`max_model_calls`)
— sayılabilir, deterministik ve bizim tarafımızda. `usage` ve `cost`
**kaydedilir** (sağlayıcı ne dediyse o, uydurulmadan) fakat **tavan olarak
kullanılmaz**: ikisi de sağlayıcının beyanıdır, bizim ölçümümüz değil.
Bu ayrım telde görünür kalır.

## 4. Giden yüzey beşte kalır

Yeni bir HTTP istemcisi **açılmaz**; mevcut `opencode/client.py` kullanılır.
`OUTBOUND_CLIENT_MODULES` **beştedir ve beşte kalır**.

## 5. Testler sahte sağlayıcıya karşı koşar

Tüm otomatik testler **mock transport** kullanır. Anahtar koda, teste,
belgeye, loga veya PR'a **yazılmaz**. Bu ADR'deki ölçüm tek seferlik bir
sözleşme doğrulamasıdır ve `cost: "0"` döndürmüştür.

Anahtar bu oturumun dökümüne girdiği için **döndürülmesi önerilir**;
kullanıcı zaten öyle planladığını söyledi.

## 6. Geriye dönük olarak ADR-0005 ve ADR-0008 ne olur

**Silinmezler ve yanlış sayılmazlar.** İkisi de yazıldıkları anda
doğrulanabilir olanı doğru anlatıyordu; kapattıkları şey bir yetenek değil,
**doğrulanmamış bir varsayıma dayanarak yetenek açma** hakkıydı. Bu ADR
onların koşulunu karşılar: sözleşme artık doğrulanmıştır, o yüzden yol
açılabilir.

`opencode/registry.py`'nin `tool_calls_supported` alanı ve ilgili düzyazı
**ölçülen gerçeğe** göre güncellenir ve **neyin ölçüldüğü** yazılır.

## 7. Değişmeyenler

Keyfi kod/shell yürütmesi **kapalı kalır** (ADR-0008 §1) — bu ADR onu
açmaz. Gerçek Technocore write yok; lobby hedef değil. `0.0.0.0` bind yok,
CORS yok, TLS doğrulaması kapatılamaz. Kullanıcı onayı olmadan hiçbir plan
çalışmaz. İnsan güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5).
