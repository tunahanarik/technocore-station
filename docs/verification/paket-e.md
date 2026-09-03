# Paket E doğrulama raporu — Evidence & Audit

Tarih: 2026-09-04 · Taban: `d0efd3679ae124f1b6cea3c5465a9593376a0830` (Paket D merge'ü)

Kapsam kararları: [`ADR-0003`](../decisions/0003-paket-e-kapsam-kararlari-2026-09-04.md).
Bu paket **AC-14**'ü karşılar.

## En büyük kısıt: sunucu tarafı sınırlama yok

Pinli `openapi.json` bir export yüzeyi yayımlıyor — `GET /r/{room}/export`,
`application/x-ndjson`, `X-Room-Generation` header'ı — ve açıklaması birebir:

> "…one record per line, bytes exactly as written, never re-serialized — so a
> signed record re-verifies from its exported line alone… **No query
> parameters.**"

`Range`, `since`, `limit`, `offset` **yok**; ring `limits.room_ring_bytes`
ile 10 MiB'a kadar çıkabiliyor. Yani promptun istediği "sınırlı okuma"
tamamen istemci tarafında yapılmak zorunda. Mevcut `_read_capped` tüm
gövdeyi belleğe aldığı için kullanılamadı.

**Çözüm:** yeni bir akış tarayıcı. `iter_bytes` üzerinde satır satır, cap
**12 MiB** (10 MiB ring + başlık payı). Tutulanlar: kendi satırımızın **ham
baytları** + offset + uzunluk; satır sayısı (her yandan 2) **ve** bayt
(satır başına 4 KiB) olarak sınırlı çevre penceresi; bütün akışın yürüyen
SHA-256'sı; `X-Room-Generation`. Kendi satırımız ve kuyruk penceresi
alındıktan sonra **tamponlama durur** — hash ve satır sayımı devam eder,
yani tepe bellek gövde boyutundan bağımsızdır. 256 KiB'ı aşan satırlar
tamponlanmadan düşülür.

Nonce **keyfi hassasiyetli `int`** olarak karşılaştırılır: 19 hane 2^53'ü
aşar ve pinli belge bunu açıkça uyarıyor ("a float-rounded nonce fails good
signatures"); `2^53+1` ile `2^53` ayırt edilir.

Satırı bulmak için satır bazında minimal parse yapılır, **kanıt olarak ham
baytlar saklanır**. Yeniden serialize edilmiş hiçbir bayt kanıt değildir.

## Üçüncü kapalı registry

`/r/{room}/export` `SOURCES`'a **eklenmedi**; `technocore/evidence_targets.py`
açıldı. Böylece altı belgelik registry'nin küme eşitliği testi ve
`"/r/" not in source.path` iddiası **aynen geçiyor**. Salt-okuma
istemcisinin `fetch(self, source)` imzası değişmedi. Kanıt istemcisi kendi
`export(room)` imzasını taşıyor ve oda adı yazma yolunun **aynı**
politikasından geçiyor — reddedilen bir oda (`lobby`, `meta`) **sıfır**
giden istek üretir. `OUTBOUND_CLIENT_MODULES` iki'den üçe, yazılı
gerekçeyle genişletildi; başka hiçbir modülün `httpx` import edemeyeceği
iddiası korundu.

## Altı kanıt durumu

| Durum | Anlamı |
|---|---|
| `line_captured` | Kendi satırımız bulundu — **yalnızca Seviye 2 sunucu gözlemi** |
| `line_not_found` | **Hiçbir şey kanıtlamaz**; ring unutur |
| `generation_changed` | Kayıt **karşılaştırılamaz**; bulunmuş bir satıra bile üstün gelir |
| `stream_truncated` | Cap'e dayandı — okunamama durumu |
| `parse_problem` | Okunamayan ≠ değişmiş (IMP-238 emsali) |
| `fetch_failed` | Okuma tamamlanamadı |

Öncelik sırası: fetch hatası > generation değişimi > bulundu > truncated >
parse sorunu > bulunamadı. `may_retry_write` **her durumda `False`**;
`line_not_found` bir `outcome_unknown` gönderimini asla `not_sent`'e
çevirmez. UI'da altı durumun her biri ayrı başlık, ton ve paragraf alır ve
istisnasız hepsinin ardından aynı cümle gelir: *"Yakalama yalnız okur.
Okuma dilediğiniz kadar yeniden denenebilir; gönderim hiçbir durumda ve
hiçbir yolla yeniden denenmez."* Yeniden deneme butonunun etiketi
"(yalnız okur)" taşır — çıplak bir "Yeniden dene" burada "tekrar gönder"
diye okunurdu. Bir test, altı durumun hepsinde yüzeydeki **her** buton
etiketini `/gonder/` için tarar.

## Audit zinciri ve truncation dürüstlüğü

`prev_mac → mac` HMAC-SHA256, `strict_json.canonical_json_bytes` üzerinde;
yalnız-ekleme, asla budanmaz, `UNIQUE(seq)`. Zincir **başı** (son MAC +
satır sayısı) ayrı bir DPAPI zarfında, append ile aynı transaction
sınırında yazılır.

**Uygulama sırasında gerçek bir hata yakalandı:** SQLite
`DateTime(timezone=True)` kolonlarını **naive** döndürüyor; MAC'e ham
`isoformat()` girseydi **her zincir ilk doğrulamada bozuk okunacaktı**.
`canonical_timestamp` ile kapatıldı (IMP-314).

Truncation **garanti olarak sunulmuyor ve bu iddia edilmiyor, gösteriliyor**:
`test_a_truncation_is_invisible_when_the_head_goes_with_it` aynı-kullanıcı
saldırısını fiilen uyguluyor (MAC'leri yeniden hesaplayıp başı yeniden
yazıyor) ve zincirin `intact` döndüğünü iddia ediyor. Yarıda kalan bir
yazma "kurcalama" değil, "yarıda kalmış yazma" olarak raporlanıyor. İzinli
tek ifade **"çevrimdışı değişikliğe karşı tespit edici"**; yasak ifadeler
listesine "değiştirilemez/kurcalanamaz kayıt" da eklendi. UI backend'in
`claim` alanını **birebir** gösteriyor, kendi iddiasını üretmiyor — iki
yüzey birbirinden sapamaz.

## Secret taraması — allow-list önce, fail-closed

Token tabanlı. **Önce** bilinen-public şekiller: 86 karakterlik canonical
imza, `did:key:z…`, 1-19 haneli nonce (kalıplar `technocore_conform`'dan
sabitlendi). **Sonra** red: kayıtlı gizli değerler, 64-hex koşular, 43
karakterlik base64url koşuları. SHA-256 digest'leri bilinçli olarak
allow-list'e **alınmadı** — o muafiyet, gerçek bir seed'in giyebileceği
kılık olurdu. Bir eşleşme kanıt yazmasını **reddeder** (asla redakte
etmez — ham kanıt baytlarını redakte etmek onu bozar), red kendisi bir
audit olayıdır ve ikisi de sorunlu değeri yankılamaz.

## Export

JSON (`canonical_json_bytes`) + Markdown (sabit bölümler), **bayt bayt
deterministik**. Onay yapısal: `acknowledged` varsayılansız
(`Literal[True]`), eksikse handler çalışmadan **422**; ayrıca handler'da
ikinci kontrol; UI'da onay kutusu işaretlenmeden butonlar `isDisabled` ve
devre dışı butona tıklama `fetch`'e **sıfır** kez ulaşıyor (testli).
`safe_display` markup escape etmediği için ayrı bir Markdown escaper
yazıldı; her metakarakterin escape edildiği ve hiçbir şeyin sessizce
düşmediği konumsal olarak iddia ediliyor.

Teslim recovery kalıbıyla: HTTP yanıtı + `Content-Disposition` + tarayıcı
indirmesi. **Sunucu hiçbir yola dosya yazmıyor**, dolayısıyla path
traversal / symlink / reparse point / overwrite soruları hiç doğmuyor.
Bir boşluk da kapandı: `downloads.py` dosya adlarını allow-list'ten yeniden
kuruyor (tırnak, CRLF, `;`, `../`, RTL override, non-ASCII, boş/nokta) ve
recovery indirmesi de artık aynı yardımcıyı kullanıyor — eski ham f-string
gitti. İstemci tarafında indirme adı sabit; sunucunun `Content-Disposition`'ı
bilinçli olarak parse edilmiyor.

Ayrıca `SignedWriteClient` artık gövdeyi kendisi serialize edip ham bayt
gönderiyor, böylece **arşivlenen request baytları gönderilen baytlarla
aynı** (IMP-323).

## Testler ve kapılar (birleşik ağaç, orkestratör koşusu)

| Kapı | Sonuç |
|---|---|
| pytest | **1179 geçti** (1049 → 1179) |
| Vitest | **206 geçti** (155 → 206) |
| ruff (iki koşu) | geçti |
| mypy strict | `mypy src` **76 dosya** / `mypy --config-file` (CI) **78 dosya** — ikisi de 0 hata |
| eslint / build (tsc+vite) | geçti / geçti |
| `git diff --check` | 0 |

Backend 130, frontend 51 yeni test. Promptun zorunlu listesi karşılandı:
yakalanan satır uyuşmazlığı, doğrulanmayan imza, sahte timestamp,
generation farkı, DB rollback, HMAC tamper (eksik orta satır, değiştirilmiş
veri, yeniden sıralama, sonun kesilmesi), truncated export, içe alınan
tehlikeli metin, secret canary, export onay zorunluluğu.

Yasak ifade testi **genişletildi**: dört ham alt dizeden altı ifadeye ve
backend tarzı katlamaya (küçük harf + NFKD diakritik soyma + `ı`→`i`);
ayrıca izinli zincir cümlesinin **var olduğu** da iddia ediliyor.
`pages.test.tsx::shows an empty state that names the package that will fill
it` ADR-0003 §10.5 gereği **kasten** kırıldı ve gerçeğe göre güncellendi.

Yeni HeroUI bileşeni **kullanılmadı** — küme 11'de kaldı. `Table` liyakat
gerekçesiyle reddedildi (her satır dört seviye satırı, bir yakalama
paragrafı ve koşullu bir uyarı taşıyor; hiçbiri hücreye sığmaz), dolayısıyla
A1-R1 (CSP inline-style hash) riski yeniden açılmadı ve yeni tarayıcı-QA
borcu eklenmedi.

## Aşama numarası tutarsızlığı (orkestratör düzeltmesi)

API kendini `stage=4` diye tanıtırken launcher kurulum kaydına `stage=3`
yazıyordu — aynı kurulum kime sorduğunuza göre iki farklı aşama söylüyordu.
İkisi de **5** oldu. `write_available_from_stage` bilinçli olarak **4**
kaldı: yazma gerçekten 4'te açıldı ve ikisini eşitlemek ya kanıt işini
geriye tarihlendirir ya da yazmanın bir sürüm sonra geldiğini iddia ederdi.

## Bilinçli ertelenenler ve kalan riskler

1. **Gerçek servise hâlâ hiçbir istek gönderilmedi.** Export okuması dahil
   her şey mock taşıyıcıya karşı koştu; autouse ağ kesici altında.
2. **Aynı Windows kullanıcısı saldırganı bütün zinciri yenebilir** —
   belgelenmiş, testle gösterilmiş, aksi iddia edilmemiş.
3. **Baş/DB atomikliği bir sınırdır, iki fazlı commit değil**: bir çökme
   başı bir halka geride bırakır ve bu "yarıda kalmış yazma" olarak
   raporlanır, kurcalama olarak değil.
4. **Seviye 4 (haricî anchor) tasarım gereği yok** — `null`.
5. **DPAPI yoksa kanıt katmanı `None`**: gönderim çalışır ve
   `evidence_recorded=false` raporlar.
6. **Sayfalama yok**; kayıtlar budanmadığı için uzun ömürlü bir kurulum
   uzun bir liste render eder.
7. **Bir gönderim, iki yüzey, iki ömür**: composer sonuç alanı yeniden
   yüklemede kayboluyor, defter kalıyor.
8. **Tarayıcı QA yok** (ADR-0001 m.4): blob/anchor indirme yolu,
   `URL.createObjectURL` ve gerçek `Content-Disposition` gidiş-dönüşü
   yalnız jsdom'da; 90 sn'lik yakalama deadline'ı gerçek yavaş akışa karşı
   ölçülmedi, backend'in faz bütçesinden akıl yürütüldü.

## Bağımsız inceleme sonucu

(PR üzerinde doldurulacak — temiz bağlamlı reviewer subagent koşulacak; bu
insan güvenlik incelemesi değildir, ADR-0001 §5 kalan risk.)

## Sınırlar

Gerçek DID/kasa/recovery okunmadı; Technocore'a hiçbir istek gönderilmedi;
lobby hiçbir testte hedef olmadı; yeni npm/Python bağımlılığı yok; pin
(`7707cb63`) ve beklenen sürüm değişmedi; tag/release/deploy yok; PR #7'ye
dokunulmadı.
