# ADR-0002 — Paket D kapsam kararları (3 Eylül 2026)

Durum: **kabul edildi** · Bağlam: uçtan uca prompt §8 (Composer & Participation)

Paket D öncesi salt-okuma keşfi, depoda **cevabı olmayan** üç karar boşluğu
ve dört küçük belirsizlik çıkardı. Kararlar burada kayıt altına alınır;
uygulama bunlara bağlıdır. ADR-0001 gibi bu da künyeye üstündür (çelişkide
ek geçerlidir), fakat **hiçbir güvenlik değişmezini gevşetmez**.

## 1. İmzalı note lane'i Paket D kapsamı DIŞINDADIR

Pinli protokol (`vendor/technocore-reference`, pin `7707cb63`) imzalı note
yazmayı yalnız iki namespace'te kabul ediyor. `openapi.json` note lane'inin
`sig` açıklaması birebir:

> "Only the `room-owners` and `room-allow` namespaces take a signed write;
> every other one is world-writable and refuses it."

`manifest.py` aynı kararı gerekçelendiriyor: notlar tasarım gereği
world-writable; istisna yalnız bir oda sahibinin yabancının
değiştiremeyeceği bir allow-list yayımlayabilmesi için var.

Künye §14.2 ve §20.3'ün istediği **DID profile note'u** ise
`/kv/did-<xx>/<...>` konvansiyonunda, yani **imzasız** lane'de yayımlanıyor.

**Karar:** Paket D yalnız **mesaj lane'ini** (`POST /r/{room}`) uygular.
Note gönderme yolu yazılmaz.

**Gerekçe:** (a) İstenen namespace'lerde imzalı note kabul edilmiyor.
(b) İmzasız bir note yazması **imza kanıtı üretemez** — onu "gönderildi"
rozetiyle sunmak, künyenin ve `docs/evidence-model.md`'nin yasakladığı
kanıt-seviyesi karıştırmasının ta kendisi olurdu. (c) `room-owners` /
`room-allow` yazması oda sahipliği demektir; Proje 0 kapsamında değildir.

Sonuç: note nonce'unun sunucu-yazımlı, oda başına paylaşılan sayaç olması
ve CAS 409 yarışları (keşif boşluğu 9.2) bu turda **konu dışıdır**.
`canonical_note`/`sweep_note_value` kodu conformance testleriyle
korunmaya devam eder; ölü kod değildir, yalnız gönderim yolu yoktur.
UI, note gönderiminin neden yok olduğunu dürüstçe yazar.

## 2. Taslak → imza onayı → gönderim onayı zinciri

Prompt "ham metin → swept diff → canonical + hedef → açık imzalama onayı →
**ayrı** tek kullanımlık gönderim onayı" istiyor. Canonical string nonce'u
içerdiği için nonce, canonical'dan önce ayrılmak zorundadır.

**Karar — üç adım, üç ayrı istek:**

| Adım | İstek | Sunucu ne yapar |
|---|---|---|
| 1 | `POST /api/compose/draft` `{room, text}` | Sweep eder; swept metni, görünmez-karakter diff bayrağını, etkin limitleri ve `draft_digest`'i döner. **Nonce ayırmaz, imzalamaz.** |
| 2 | `POST /api/compose/sign` `{draft_id, draft_digest}` | Write gate'i **yeniden** koşar; nonce'u transaction içinde ayırır; canonical'ı kurar; seed'i kısa süre açıp imzalar ve sıfırlar; tek kullanımlık `send_token` üretir. Canonical metni, nonce'u, imzayı ve son kullanma anını döner. |
| 3 | `POST /api/compose/send` `{send_token}` | Gate'i **yeniden** koşar; token'ı harcar; gövdeyi POST eder. |

- `draft_digest`, kullanıcıya gösterilen swept metin + hedef oda üzerinden
  hesaplanır. Metin veya hedef değişirse digest değişir ve adım 2 reddeder
  — **eski onay yeni içeriği imzalayamaz**.
- `send_token` şunlara bağlanır: canonical bayt digest'i, hedef oda,
  ayrılan nonce, imzalayan DID ve **imza anındaki manifest verdict kimliği**.
  Gönderim anında verdict değişmişse token geçersizdir (stale verdict).
- **TTL = 180 saniye**, tek kullanımlık. Gerekçe: oturum bootstrap token'ı
  30 saniyedir ama o makineler arasıdır; burada bir insanın canonical metni
  okuyup karar vermesi gerekir. 3 dakika okumaya yeter, unutulmuş bir
  onayın saatlerce ateşlenebilir kalmasına yetmez.
- Token harcanması ile gönderim aynı transaction'da başlar; çift tıklama
  ikinci kez harcayamaz.

## 3. Gönderim sonucu üç durumludur; kör tekrar YOKTUR

`outcome_unknown` terimi depoda yoktu. Pinli `llms.txt` sorunu adlandırıyor:

> "A fetch failure is therefore not evidence that a write failed."

**Karar:**

| Sonuç | Koşul |
|---|---|
| `accepted` | 2xx |
| `refused` | **yazmadığı kanıtlanan** yanıtlar: 400, 403, 413, 422 |
| `outcome_unknown` | timeout, bağlantı hatası, bozuk yanıt, 429, 5xx — sunucu yazmış olabilir |

- **Hiçbir durumda otomatik tekrar yoktur** (salt-okuma istemcisinin 3
  denemeli politikası yazma yoluna taşınmaz).
- Ayrılan nonce **her üç durumda da harcanmış sayılır** ve asla yeniden
  kullanılmaz. `outcome_unknown` sonrası yeni gönderim yeni nonce ve
  **yeni onay** ister.
- `outcome_unknown`'dan çıkış, odayı okuyarak uzlaştırmayı gerektirir; oda
  okuma yolu bu pakette **açılmaz** (kaynak registry'si kapalı kalır).
  Bu yüzden durum kullanıcıya olduğu gibi gösterilir ve uzlaştırma sonraki
  bir pakete bırakılır. Bunu "gönderildi" veya "başarısız" diye sunmak
  yasaktır.
- 422 (duplicate filter) kullanıcıya "aynı metin yakın zamanda yazılmış"
  olarak açıklanır; **retryable değildir** — aynı baytları yeniden yollamak
  tekrar reddedilir.

## 4. Küçük kararlar

1. **Hedef oda.** Bu turda hiçbir gerçek gönderim yapılmaz; testler fixture
   odası kullanır. Lobby hiçbir testte hedef olamaz (INV-05) ve üründe de
   **açıkça reddedilir**. Oda adı çalışma anında manifest'in `room_classes`
   konvansiyonuna göre doğrulanır; tahmin edilmez.

   **Sonradan eklenen sıkılaştırma (kabul edildi):** `meta` odası da
   `lobby` ile birlikte reddedilir. Pinli referans ikisini birlikte
   `UNOWNABLE_ROOMS = ("lobby", "meta")` olarak sayar; oradaki kural
   sahiplenilebilirlik hakkındadır, yazılabilirlik hakkında değil — yani
   bu **Station'ın kendi kararıdır**, protokolden türetilmiş bir zorunluluk
   değildir. Gerekçe: ikisi de paylaşılan ön kapı odalarıdır ve otomatik
   bir agent'ın ilk yazmasının gürültü olma ihtimali orada en yüksektir.
   Gevşetmek isteyen, bunu bilerek yapsın.
2. **Leading zero yasak.** Sunucu nonce'u int olarak karşılaştırır
   (`store.py`), imza ise string üzerindedir: `"007"` ile `"7"` aynı sayı
   ama farklı imzadır. Station **asla** başında sıfır olan nonce üretmez;
   bu bir testle sabitlenir.
3. **AC-14 Paket D'de değildir.** `docs/evidence-model.md` AC-14'ü Aşama
   5'e koyuyor; `PROJECT_STATUS.md` yanlışlıkla Aşama 4 diyordu. Paket D
   **AC-13 ve AC-16**'yı karşılar; AC-14 (gönderim sonrası exact export
   satırı ve generation) Paket E'dedir. Künye yol haritasının "AC-15"
   maddesi Aşama 3'te zaten karşılanmıştır.
4. **Test emniyet ağı.** Bugün hiçbir mekanizma, `MockTransport` enjekte
   etmeyi unutan yeni bir testin `technocore.chat`'e çıkmasını
   engellemiyor. Paket D, giden gerçek HTTP taşıyıcısını test oturumunda
   **autouse** olarak devre dışı bırakan bir fixture ekler; unutulan mock
   sessizce ağa çıkmak yerine gürültüyle kırılır.

## 5. Değişmeyenler

Bu ADR hiçbir güvenlik değişmezini gevşetmez. SI-83 ("bütün ön koşullar
geçse bile yazma yolu yoktur") Paket D ile **bilinçli olarak** yerini
"yazma yolu yalnız kullanıcı onaylı, gate açık ve nonce ayrılmışken
çalışır"a bırakır; bu değişiklik `docs/security-invariants.md` içinde
görünür şekilde kayda geçer, sessizce silinmez. Gerçek servise yazma bu
turda yapılmaz; insan güvenlik incelemesi ertelenmiş kalan risktir
(ADR-0001 §5).
