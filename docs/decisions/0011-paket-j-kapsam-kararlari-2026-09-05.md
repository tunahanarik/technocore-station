# ADR-0011 — Paket J kapsam kararları (5 Eylül 2026)

Durum: **kabul edildi** · Bağlam: `docs/execution-plan.md` Paket J
(bütünleşik inceleme, temizlik, kılavuz)

Bu **son pakettir** ve diğerlerinden farklıdır: yeni yetenek getirmez,
mevcut olanı **doğru anlatır**. Keşif on iki karar boşluğu çıkardı ve
belgelerde on bir ölçülmüş yanlış buldu. ADR-0001…0010 gibi bu da
bağlayıcıdır ve hiçbir güvenlik değişmezini gevşetmez.

## 0. Bu paketin asıl işi: belgelerin ürünle uzlaşması

Keşif tek tek ölçtü. En ağırı şu: **`README.md` deponun ilk gördüğü dosya ve
ürünü yedi paket geride tarif ediyor** — "Durum: Aşama 3 — Salt okunur
Technocore tamamlandı. Mesaj yazma, imzalama ve Evidence özellikleri **henüz
yoktur**." Oysa `compose`, `evidence`, `agent`, `proof`, `opencode` ve
`workscan` rotalarının hepsi var ve dokuz bölümün dokuzu `ready: true`.

`SECURITY.md` de Aşama 3'te donmuş: imza/onay zinciri, audit/HMAC zinciri,
DPAPI'deki provider anahtarı ve ADR-0001 §6'nın istisnası, agent izolasyonu,
tek kullanımlık paylaşım onayı, ve **imzasız artefakt/SmartScreen** —
hiçbiri yok.

## 1. Neden bayatladı: `-qq` tuzağı

Keşif mekanizmayı buldu. `pytest.ini` zaten `addopts = -q` veriyor;
`AGENTS.md` ve `CLAUDE.md`'nin kapı komutu bir `-q` daha ekliyor, yani
efektif **`-qq`** — ve `-qq` **özet satırını bastırır**. Yerelde kapıyı koşan
kimse "2201 passed" satırını görmüyor. CI `-q` eklemediği için sayıyı
görüyor.

**Karar:** kapı komutundan `-q` düşer. Ve **test sayıları hiçbir belgede
tekrarlanmaz** — tek kaynak J'nin doğrulama raporudur. `docs/packaging.md`
bu kalıbı zaten teşhis edip uygulamıştı ("üç ayrı kopya, üçü de eskimişti");
aynı kural sayılara da uygulanır.

## 2. Beş SI satırı `AGENTS.md` INV-06'yı ihlal ediyor

`docs/security-invariants.md` §9'un başlığı *"Aşama 2+ değişmezleri (bugün
kod yolu yok)"* ve altındaki SI-49, SI-50, SI-51, SI-52, SI-55 **bugün
canlı** — seed DPAPI zarfında, restore-test kapısı `write_gate.py`'de, onay
zinciri `compose/approvals.py`'de. INV-06 "her satır bir testle eşleşir"
diyor; bu beşi test göstermeden listede duruyor.

**Karar:** §9 tablosu kaldırılır, satırlar ilgili bölümlere **test
adlarıyla** taşınır. "Uygulandı, bkz. §…" işareti yetmez.

Ayrıca **SI-211 ve SI-277 var olmayan test adları veriyor**, SI-243'ün
jokeri yedinci yüzeyi tutmuyor, ve SI-277'nin beklenen metni de bayat
(`RUNNING`/`PAUSED` "üretilemez" diyor; `UNPRODUCIBLE_STATES` boş).

**Karar:** elle düzeltilir **ve** SI tablosundaki her test adının gerçekten
var olduğunu doğrulayan bir test eklenir. Bayat referans bu depoda **üç kez**
bulundu; ölçen bir test onu kalıcı kapatır.

## 3. Aşama numarası: üç numaralandırma uzlaşır

Bugün üç ayrı sayım var: künye roadmap'i (0–7), `PROJECT_STATUS.md`
anlatısı (…9, 10, 11), ve kodun `CURRENT_SCHEMA_STAGE`'i (…8, 9, 10).
Ayrışma H1'de başladı: paket kendine "Aşama 8" dedi ama kodun sayısını
taşımadı. Bugün ürün `/api/app/status`'ta **10**, `PROJECT_STATUS` **11**
diyor.

**Karar:** kod `10 → 11`'e taşınır (beş giriş noktası + pinli sabit,
**atomik**; `CURRENT_MIGRATION_HEAD` `0009`'da kalır) **ve** `PROJECT_STATUS`
başlıklarına "(kod aşaması N)" eki konarak iki sayım hizalanır. Tarihsel
raporlar **yeniden yazılmaz**.

## 4. `CODE_COMPLETE_USER_ACCEPTANCE_PENDING` nereye yazılır

**Karar:** `PROJECT_STATUS.md`, `docs/execution-state.json` ve `README.md`.

**UI'ya veya `/api/app/status`'a yazılmaz** — yeni bir alan, yeni bir SI ve
yeni bir bayatlama yüzeyi demek olurdu, ve Paket I aşama numarasının CI'da
doğrulanamadığını zaten ölçtü.

**`README.md`'nin durum paragrafına aşama numarası yazılmaz.** O paragraf
yedi pakettir bayat; sayı taşımayan bir metin bir daha bayatlamaz. Durum tek
kaynağa bırakılır.

## 5. Kılavuz: yalnız ürün karşılığı olanı anlatır

`docs/kullanim-kilavuzu.md` yazılır ve **yalnız var olan dokuz bölümü**
anlatır. Recovery zorunluluğu (ADR-014) merkezdedir: `write_gate` altı kapı
sayar ve `recovery_verified` geçmeden hiçbir Technocore write açılmaz.

**Yazılırsa yalan olacak cümleler** — keşif ölçtü, kılavuz bunları
**diyemez**:

| Cümle | Neden yalan |
|---|---|
| "Technocore'a mesaj gönderebilirsiniz" | Hiçbir gerçek write **hiç** yapılmadı; kapı altı koşulun hepsini ister |
| "Bir agent'a görev yaptırabilirsiniz" | Yürütme **kapalı** (ADR-0008 §1) |
| "OpenCode ile model çalıştırabilirsiniz" | Model lane'i kapalı; `Bearer` **doğrulanmamış varsayım** |
| "İndirin ve kurun" | **Yayımlanmış artefakt yok**; kaldırma hiç denenmedi |
| "SHA-256 ile doğrulayın" | Özet yalnız **o derlemeyi** tanımlar; iki derleme farklı hash verdi |
| "Bir görevi yayına alabilirsiniz" | `ready_to_publish`'e HTTP'den geçilemiyor |
| "İş taraması hızlıdır" | 10 oda ≈ **6,8 dakika**, **iptal yok** |
| "Kaldığınız yerden devam edersiniz" | Derin link yok; yenileme Genel Bakış'a döner |

## 6. Kabul listesi: doğrulanabilir olanı ister

`docs/kullanici-kabul-listesi.md` yazılır ve iskeleti **on bir doğrulama
raporunun** "kalan riskler / ölçülmeyenler" bölümlerinden gelir.

**İstenemeyecekler** — çünkü doğrulanamazlar:

- "İmzanın geçerli olduğunu doğrulayın" — artefakt **imzasız**.
- "İki derlemenin aynı hash'i verdiğini doğrulayın" — **ölçüldü, vermiyor**.
- "Başlık hiyerarşisini doğrulayın" — h1→h3 atlaması **bilinen ve kabul
  edilmiş**; kullanıcıdan düzeltemeyeceği bir şeyi onaylaması istenir.
- "Recovery'nizi başka bir profilde deneyin" — DPAPI hesaba bağlı, tek
  yönlü bir denemedir.

**Gerçek gönderim ayrı ve açıkça isteğe bağlı bir son bölümdür**, ön
koşulları tek tek sayılır (recovery üret, restore-test geç, altı kapı yeşil,
**lobby değil**). Onay kutusu hâline getirilmez — "kullanıcı açıkça
'başlayalım' demeden gerçek gönderim yapılmaz" koruması aksi hâlde erir.

## 7. Ölü yüzey: gerekçesiz silinmez, gerekçesiz bırakılmaz

Keşif AST ile ölçtü: `__all__`'da olup hiç import edilmeyen yedi ad, hiç
okunmayan bir property, ve bir ölü TS export'u.

**Karar:** `attachJson` ve `ProofBundle.missing_count` silinir. `__all__`'daki
yedi ad için **her birine gerekçe yazılır ya da silinir** — ikizi kullanılan
sabitler (`AUTHORITY_DETAIL`, `SOURCE_DETAIL`) meşru olabilir.

**`WorkScanRingDrop` silinmez.** Belgelenmiş, bilinçli bir boşluktur; silmek
"alan ve gösterim **birlikte** gelmeli" kararını kaybettirir.

`attachJson`'ın hayatta kalma sebebi de ölçüldü: **e2e ağacı lint
edilmiyor**, çünkü `eslint.config.js` bir depo hook'u tarafından yazmaya
kapalı. Bunu bir agent kaldıramaz; **kabul listesine gerekçesiyle girer**.

## 8. `PROJECT_STATUS.md` düzgün kapanır

2027 satır. İki yapısal kusur ölçüldü: "Sonraki aşama" başlığı Paket I
bölümünün **önünde** duruyor ve gövdesi H3'ün kapanış metni; ve dosyanın
**son sözü bir Aşama 3 beyanı**.

**Karar:** yanlış yerdeki blok kaldırılır, Paket I'nın ardına tek bir Paket J
bölümü konur ve sonunda aranabilir tek satırlık durum damgası yer alır.
Aşama 3 beyanı başlığına "(tarihsel)" eklenerek yerinde bırakılır.

## 9. Diğer temizlik borçları

`architecture.md`'nin migration tablosu (`0001…0007` → `0009`; **14 tablo
sayıyor, 19 var**) ve §6'nın "paketleme yapılmadı" maddesi düzeltilir.
`README.md` ve `AGENTS.md`'nin belge tabloları yedi ve on bir belgeyi
anmıyor. `ui-action-map.md`'nin başlığı H3'ü atlıyor. `NOTICE`'ın lisans
haritası `packaging/` dizinini listelemiyor.
`PROJECT_STATUS.md`'nin "ölçülmeyenler" bloğunun **dört maddesi** artık
yanlış — silinip doğrulama raporuna işaret edilir.

## 10. Tam suite son head'de

Keşif ölçtü: **sessizce atlanan test yok** — `skipped`/`xfailed`/`xpassed`
sıfır, toplanan ile koşan **aynı**, ve platform `skipif`'leri Windows'ta
tetiklenmiyor. Playwright de koşuldu ve **74'ü yeşil** (Paket I onu
"koşturulmadı" diye kaydetmişti; bu düzeltilir).

J, son head'de yedi kapının tamamını koşar ve sayıları **tek yere** yazar.

## 11. Değişmeyenler

Bu paket **yeni yetenek getirmez, yeni bağımlılık eklemez, yeni rota
açmaz**. `OUTBOUND_CLIENT_MODULES` beşte kalır. Gerçek yazma, gerçek
harcama, gerçek anahtar/DID/seed yok; lobby hedef değil.

**İnsan güvenlik incelemesi ertelenmiş kalan risktir** (ADR-0001 §5) ve bu
paket onu **kapatmaz** — görünür kılar. Hedef bitiş durumu
`CODE_COMPLETE_USER_ACCEPTANCE_PENDING`'dir: kod tamam, **kullanıcı kabulü
bekliyor**, ve o kabul kullanıcının kendi işidir.
