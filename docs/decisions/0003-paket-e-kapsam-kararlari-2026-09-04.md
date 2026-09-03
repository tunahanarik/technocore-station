# ADR-0003 — Paket E kapsam kararları (4 Eylül 2026)

Durum: **kabul edildi** · Bağlam: uçtan uca prompt §9 (Evidence & Audit), AC-14

Paket E öncesi salt-okuma keşfi sekiz karar boşluğu çıkardı; ikisi mimariyi
doğrudan etkiliyor. Kararlar burada kayıt altına alınır ve uygulama bunlara
bağlıdır. ADR-0001/0002 gibi bu da künyeye üstündür (çelişkide ek geçerli),
fakat **hiçbir güvenlik değişmezini gevşetmez**.

## 1. Resmî export okuma yolu — ÜÇÜNCÜ kapalı registry

Pinli `openapi.json` gerçekten bir export yüzeyi yayımlıyor:
`GET /r/{room}/export`, `application/x-ndjson`, `X-Room-Generation` header'ı.
Açıklaması birebir:

> "The stored file, snapshotted at open and truncated to the last complete
> line: one record per line, bytes exactly as written, never re-serialized —
> so a signed record re-verifies from its exported line alone… **No query
> parameters.**"

ADR-0002 §3 oda okuma yolunu bilinçli kapalı bırakmış ve uzlaştırmayı
"sonraki bir paket"e ertelemişti. **O paket budur.**

**Karar:** `/r/{room}/export` `SOURCES` registry'sine **eklenmez**. Üçüncü
bir kapalı registry açılır:

| Registry | Kabiliyet |
|---|---|
| `technocore/sources.py` | Belge okuma — altı sabit belge, oda yok |
| `technocore/write_targets.py` | Açık yazma — mesaj lane'i |
| `technocore/evidence_targets.py` | **Kanıt okuma** — yalnız `/r/{room}/export` |

**Gerekçe:** SI-152'nin ilkesi "public read ile explicit write ayrı kapalı
registry taşır"dır; kanıt okuma üçüncü bir kabiliyettir ve **şekli
farklıdır** (oda parametreli, belge listesi değil). `SOURCES`'ın küme
eşitliği testi ve `"/r/" not in source.path` iddiası **aynen korunur** —
altı belge altı kalır. Yeni registry kendi testini alır: şablonu tam olarak
`/r/{room}/export` olan tek bir hedef, başka hiçbir şey.

İstemci tarafı: `technocore/evidence_client.py`. `OUTBOUND_CLIENT_MODULES`
iki'den **üçe** bilinçli genişletilir; başka hiçbir modülün `httpx` import
edemeyeceği iddiası (SI-73) korunur. Salt-okuma istemcisinin
`fetch(self, source)` imzası **değişmez** — oda adı `OfficialSource`'a
sığmaz. Kanıt istemcisi kendi `export(room)` imzasını taşır ve oda adını
yazma yolunun kullandığı **aynı** oda politikasından geçirir
(`DENIED_ROOMS` dahil).

`docs/read-only-technocore.md`'nin "`/r/*` bu aşamada kapsam dışıdır"
cümlesi sessizce silinmez; hangi aşamada ve neden değiştiği yazılır.

## 2. Bayt-exact ile sınırlı okuma arasındaki gerilim

Export'ta sunucu tarafı sınırlama **yok** ("No query parameters", `Range`
desteği belgede geçmiyor) ve ring 10 MiB'a kadar çıkabilir
(`limits.room_ring_bytes = 10485760`). Mevcut `_read_capped` tüm gövdeyi
belleğe alıyor, yani Evidence için kullanılamaz.

**Karar:** Tek istek, **akış üstünde satır satır tarama**. Yeni bir akış
okuyucu yazılır ve şunları tutar:

- kendi satırımızın **ham baytları** (byte offset + uzunluk ile),
- sınırlı bir çevre penceresi (satır sayısı **ve** bayt olarak sınırlı),
- bütün akışın yürüyen SHA-256'sı,
- `X-Room-Generation` değeri.

Cap **12 MiB** (10 MiB ring + başlık payı). Bütün public ring
arşivlenmez — yalnız yukarıdaki dört şey saklanır.

**Satırı bulmak için satır bazında minimal parse yapılır, fakat kanıt
olarak ham baytlar saklanır.** Promptun yasağı "exact'i parse edip yeniden
serialize ederek ÜRETMEK"tir; konum tespiti için okumak değil. Yeniden
serialize edilmiş hiçbir bayt kanıt olarak saklanmaz.

İki istekli alternatif (`?format=json&since=` ile konum tespiti, sonra
export) **reddedildi**: JSON görünümü yeniden serialize edilmiştir, yani
gerçeğin kaynağı olamaz; ayrıca iki rate-limit birimi harcar.

## 3. Kanıt durumları "doğrulandı"ya indirgenemez

**Karar:** Yakalama sonucu ayrı ayrı adlandırılır ve hiçbiri tek yeşil
rozete indirgenmez:

| Durum | Anlamı |
|---|---|
| `line_captured` | Kendi satırımız bulundu, ham baytları ve offset'i saklandı |
| `line_not_found` | Cap içinde bulunamadı — **hiçbir şey kanıtlamaz**, ring unutmuş olabilir |
| `generation_changed` | Generation imza anındakinden farklı — kayıt **karşılaştırılamaz** |
| `stream_truncated` | Cap'e dayandı, tarama tamamlanamadı |
| `parse_problem` | Satır yapısı okunamadı — okunamayan ≠ değişmiş (IMP-238 emsali) |
| `fetch_failed` | Okuma isteği başarısız |

Son beşi **"doğrulandı" değildir**. Gönderilmiş ama kanıtı eksik işlem
görülebilir ve **yalnız okuma** yeniden denenebilir; yazma asla yeniden
denenmez.

## 4. `outcome_unknown` uzlaştırması

Export okuma açıldığı için uzlaştırma teknik olarak mümkün hale gelir.

**Karar:** Yakalama **yalnız kullanıcı isteğiyle** çalışır (otomatik değil)
ve `accepted` ile `outcome_unknown` kayıtlarının ikisi için de
denenebilir. Fakat:

- Satırın bulunması **Seviye 2 sunucu gözlemidir**, "gönderildi
  kanıtı" değil.
- Satırın bulunmaması **hiçbir şey kanıtlamaz** — ring unutur.
  `outcome_unknown` `not_sent`'e **asla** dönüştürülmez.
- Hiçbir koşulda yazma tekrarı önerilmez. `ComposerPanel`'in "Station
  sizin adınıza tahmin yürütmez" duruşu korunur; eklenen şey yalnızca
  **salt-okuma** bir yakalama eylemidir.

`reconciliation_required` alanının anlamı netleşir: "kanıt yakalama
denenebilir", "yeniden gönder" değil.

## 5. Audit zinciri ve truncation'ın dürüst sunumu

`prev_mac → mac` zinciri ortadan satır silmeyi ve yeniden sıralamayı
tespit eder; **sonun kesilmesini tespit etmez** — güvenilen bir baş
olmadan.

**Karar:** Zincir başı (son MAC + satır sayısı) **ayrı bir DPAPI zarfında**
tutulur ve append ile aynı transaction sınırında güncellenir. Bu, **bu
Windows kullanıcısı olarak çalışmayan** bir saldırganın truncation'ını
tespit eder.

**Fakat:** aynı Windows kullanıcısı olarak çalışan bir saldırgan hem
zinciri hem başı yeniden hesaplayabilir. Bu yüzden truncation tespiti
**garanti olarak sunulmaz**. İzinli tek ifade `evidence-model.md` §4'teki
"çevrimdışı değişikliğe karşı tespit edici"dir; "değişmez kayıt",
"sunucu kanıtı", "güvenilir zaman kanıtı" yasak ifadeler listesinde kalır
ve yeni bir test truncation hakkında aşırı iddiayı da yasaklar.

## 6. Audit HMAC anahtarı — mevcut kasa kodu YENİDEN KULLANILAMAZ

`DpapiVault` kimliğe bağlıdır: `identity_id` 32-hex dayatır, dosya adı ve
dizin sabittir, envelope ve iç AAD kimlik id'sini taşır, `store()` asla
üzerine yazmaz (rotasyon engeli).

**Karar:** Audit anahtarı için ayrı bir zarf yazılır ve **yalnız şunlar**
yeniden kullanılır: `dpapi.protect/unprotect` (generic), `windows_acl.
restrict_to_current_user` (herhangi bir dosya), `strict_json`'un canonical
JSON ve strict parse yüzeyi, ve `_atomic_write`'ın **kalıbı** (temp → ACL →
`os.replace` → ACL, fsync ile). Anahtarın kendisi hiçbir tabloya girmez;
tabloda yalnız yol, oluşturma zamanı ve fingerprint tutulur
(`secret_metadata` deseni).

Audit satırının canonical formu `strict_json.canonical_json_bytes` ile
üretilir — zaten bayt-bayt pinli.

## 7. Retention: kanıt ve zincir budanmaz

`snapshot.py`'nin `RETAINED_CHECKS = 50` budaması Evidence için
**yanlıştır** ve HMAC zinciriyle çelişir: ortadan satır silmek zinciri
kırar.

**Karar:** Audit zinciri **ayrı, yalnız-ekleme** bir tablodur ve asla
budanmaz. Evidence kayıtları da otomatik budanmaz — bir kanıt kaydı
kullanıcının onayı olmadan kaybolmaz. Silme yalnız açık kullanıcı
eylemiyle olur ve **kendisi bir audit olayıdır**. Büyüme sınırı kullanımdır
(gönderim başına bir satır); bu bilinen ve kabul edilen bir takas olarak
kaydedilir.

## 8. Secret-pattern taraması — fail-closed, allow-list önce

Künye §16.1 tarama istiyor; böyle bir tarayıcı **yok**. `redact()` registry
tabanlıdır (16+ karakter tam eşleşme) ve şekil sezgiseli içermez.

**Karar:** Muhafazakâr bir tarayıcı yazılır ve **yazmayı reddeder**
(sessizce redakte etmez — kanıtın ham baytlarını redakte etmek onu bozar).
Sıra kritiktir: **önce bilinen-public şekiller allow-list'i**, sonra red
kuralları.

- Allow-list: 86 karakterlik imza, `did:key:z` önekli DID, 1-19 haneli
  nonce. Bunlar public protokol değerleridir ve **asla** gizli sayılmaz.
- Red kuralları: kayıtlı gizli değerler (registry), 64-hex koşular,
  seed uzunluğunda (43 karakter) base64url koşuları.
- False positive → **reddet ve bildir**, sessizce geçme.

## 9. Export dosyası — recovery kalıbı, kullanıcı yolu YOK

**Karar:** Export, recovery ile aynı kalıpla teslim edilir: HTTP yanıtı +
`Content-Disposition` + tarayıcı indirmesi. Sunucu kullanıcının seçtiği bir
yola **yazmaz** ve sabit bir export dizinine de yazmaz.

**Gerekçe:** Bu, path traversal / symlink / reparse point / overwrite
sorularını **hiç doğurmaz** — depoda bu savunmalardan tek satır emsal
olmadığı için sıfırdan yazmak en riskli seçenek olurdu. Ayrıca same-origin
duruşunu (INV-02/03) bozmaz.

**Fakat bir boşluk kapatılır:** bugün `Content-Disposition` filename'i ham
f-string ile kuruluyor ve sanitizasyon yardımcısı yok (bugün güvenli, çünkü
tek değişken parça base58 bir DID kuyruğu). Export adı oda adı veya etiket
taşıyacağı için bir filename sanitizer'ı **ve testi** yazılır: tırnak, CRLF,
`;`, `../`, RTL override, non-ASCII.

Export içeriği deterministiktir (aynı girdi → aynı bayt), sırdan
arındırılmıştır ve Markdown/HTML/link enjeksiyonu etkisizleştirilir —
`safe_display` bidi ve kontrol karakterlerini temizler ama `<`, `[`, `](`,
backtick, `|` karakterlerini escape **etmez**; Markdown export'u için ayrı
bir escaper yazılır.

## 10. Bağlantı anahtarı ve küçük kararlar

1. **Evidence ↔ rezervasyon bağı:** `evidence_record.reservation_id` →
   `message_nonce_reservation.id` yabancı anahtarı (CASCADE **yok**).
   `reservation_id` public bir uuid'dir, capability değildir; bu yüzden
   `SendResult`/`ComposeSendResponse` genişletilip yanıtta dönebilir.
2. **Künye §24.1 çelişkisi:** "Lobby mesajı ve DID note Evidence olarak
   saklanır" ifadesi INV-05 ve ADR-0002 §4.1 (`DENIED_ROOMS = {lobby,
   meta}`) ile çelişir. **ADR-0002 lehine kapatılır**: lobby hedef değildir,
   dolayısıyla lobby kanıtı da üretilmez. Note lane'i ADR-0002 §1 gereği
   kapsam dışıdır, dolayısıyla DID note kanıtı da yoktur.
3. **`evidence-model.md` başlığı** ("HENÜZ UYGULANMADI") ve
   `read-only-technocore.md`'nin `/r/*` cümlesi güncellenir; ikisi de
   bugünkü gerçeği yansıtmıyor.
4. **Migration `0005`** (`down_revision = "0004"`), tek head korunur.
5. **`pages.test.tsx::shows an empty state that names the package that
   will fill it`** Paket E boş durumu değiştirdiğinde **kasten** kırılır;
   güncellenmesi bir düzeltmedir, gevşetme değildir.

## 11. Değişmeyenler

Bu ADR hiçbir güvenlik değişmezini gevşetmez. SI-152 (ayrı kapalı
registry'ler) **korunur ve üçüncü bir registry ile genişletilir**; SI-73
(httpx yalnız incelenmiş istemcilerde) üçüncü modülle görünür şekilde
genişletilir. SI-149/150/151 (üç sonuç, tekrar yasağı, nonce harcanması)
aynen geçerlidir ve Evidence bunları tek yeşil rozete indiremez. Gerçek
servise yazma bu turda da yapılmaz; export okuması testlerde mock taşıyıcı
ile koşar. İnsan güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5).
