# Paket J doğrulama raporu — teslim, temizlik ve kılavuz

Tarih: 2026-09-05 · Kapsam kararları:
[`ADR-0011`](../decisions/0011-paket-j-kapsam-kararlari-2026-09-05.md)

**Bu, projenin son paketidir ve tek sayı kaynağıdır.** ADR-0011 §1 gereği
test sayıları başka hiçbir belgede tekrarlanmaz.

## Bu paket yeni yetenek getirmedi

Yeni rota yok, yeni bağımlılık yok, yeni HeroUI bileşeni yok, yeni migration
yok. Getirdiği tek kod, belgelerin kendisini denetleyen bir testtir. İşi,
**on bir paketin ürettiği ürünü doğru anlatmaktı** — ve keşif, belgelerin
ürünün gerisinde kaldığı on bir yeri ölçtü.

## Neden bayatladı: `-qq` tuzağı

Bu paketin en açıklayıcı bulgusu bir kusur değil, **kusurların nasıl fark
edilmediğidir**.

`pytest.ini` zaten `addopts = -q` veriyor. `AGENTS.md` ve `CLAUDE.md`'nin
aşama sonu kapı komutu bir `-q` daha ekliyordu, yani efektif **`-qq`** — ve
`-qq` **özet satırını bastırır**. Ölçüldü:

| Komut | Son satır |
|---|---|
| `pytest tests/security/test_bind.py -q` (efektif `-qq`) | *(özet yok)* |
| `pytest tests/security/test_bind.py` | `18 passed, 1 warning in 2.71s` |

Yani kapıyı yerelde koşan hiç kimse "N passed" satırını görmüyordu. CI `-q`
eklemediği için sayıyı görüyordu — belgelerdeki sayıların sessizce
bayatlamasının mekanizması tam olarak buydu. Fazladan `-q` iki dosyadan da
düşürüldü.

## Beş değişmez `AGENTS.md` INV-06'yı ihlal ediyordu

`docs/security-invariants.md` §9'un başlığı *"Aşama 2+ değişmezleri (bugün
kod yolu yok)"* idi ve altındaki SI-49, SI-50, SI-51, SI-52, SI-55 **bugün
canlıydı**: seed DPAPI zarfında, restore-test kapısı `write_gate.py`'de,
onay zinciri `compose/approvals.py`'de. INV-06 "her satır bir testle
eşleşir" der; bu beşi **test göstermeden** listede duruyordu.

Tablo kaldırıldı, satırlar ilgili bölümlere **gerçek test adlarıyla**
taşındı. Ölçüm sırasında **altıncı** aynı kusur çıktı: SI-38'in Test sütunu
"Aşama 2" yazıyordu.

**Kapatılamayan bir boşluk dürüstçe kaydedildi:** SI-50'nin *üretim* yarısı.
`identity/service.py::generate_seed` `secrets.token_bytes` kullanıyor ama
**bunu iddia eden bir test yok**; yalnız içe aktarma yolu kapsanmış. Belgeye
açık boşluk olarak yazıldı, üstü örtülmedi.

## Bayat test referansları ve onları kalıcı kapatan test

Dört bozuk referans ölçüldü: SI-211 ve SI-277 **var olmayan** test adları
veriyordu; SI-243'ün jokeri yedinci yüzeyi hiç tutmuyordu; ve dördüncüsü
SI-105'in çıplak `::test_*` jokeriydi. SI-277'nin **beklenen metni de**
bayattı (`RUNNING`/`PAUSED` "üretilemez" diyordu; `UNPRODUCIBLE_STATES` H2'den
beri boş).

Bu depoda bayat referans **dört kez** bulundu, o yüzden elle düzeltmek
yetmedi: `tests/security/test_security_invariants_doc.py` eklendi. **329
satır / 924 referans** ayrıştırıyor, nitelikli `dosya.py::ad` referansını **o
dosyaya** karşı, çıplak `::ad` referansını tüm suite'e karşı çözüyor, **her
türlü jokeri reddediyor**, ve vitest dosya adlarını denetliyor. İki
guard-the-guard testi ayrıştırıcının boşa düşmesini engelliyor.

**Mutasyon: 7/7** — her bozuk referans biçimi geri konup öldürüldüğü
ölçüldü, ayrıca atıf yanlış dosyaya taşındığında, atıf yapılan test yeniden
adlandırıldığında ve tüm satır kimlikleri değiştirildiğinde (ayrıştırıcı
hiçbir şey eşleştiremediğinde) de kırmızı.

## Üç aşama numaralandırması hizalandı

Kod `10 → 11`'e **atomik** taşındı (altı yer; `CURRENT_MIGRATION_HEAD`
`0009`'da kaldı). `PROJECT_STATUS.md` başlıklarına kod aşaması eki, **git'ten
okunarak** kondu — ve ayrışmanın nerede başladığı böylece görünür oldu:
**H1 kendine "Aşama 8" dedi ama kodun sayısını taşımadı** (F=6, G=7, **H1=7**,
H2=8, H3=9, I=10, J=11). Tarihsel raporlar yeniden yazılmadı.

## Ölü yüzey: ikiz argümanı ölçüldü ve çürüdü

Yedi `__all__` adı, bir property ve bir TS export'u ölü olarak işaretlenmişti.
`AUTHORITY_DETAIL` ve `SOURCE_DETAIL` için "`STATE_DETAIL` gibi meşru olabilir"
denmişti; **ölçüldü ve yanlış çıktı**: `STATE_DETAIL`'in canlı bir tüketici
zinciri (`views.detail_for_state` → `service` → `states.refuse`) ve her durumu
kapsadığını iddia eden bir testi var; diğer ikisinin **ne tüketicisi ne testi**
var. Yedisi de silindi. `OFFICIAL_SEED_HEX_LENGTH` ise iki regex'teki `{64}`'ün
üçüncü kopyasıydı — bir kapı değil, bir sürüklenme yeri.

**`WorkScanRingDrop` silinmedi**: belgelenmiş, bilinçli bir boşluk ve silmek
"alan ve gösterim birlikte gelmeli" kararını kaybettirirdi.

## Kılavuz yalan söylemiyor

`docs/kullanim-kilavuzu.md` ve `docs/kullanici-kabul-listesi.md` yazıldı.
ADR-0011 §5'in **sekiz yasak cümlesinin hiçbiri** geçmiyor; yerlerine ürünün
ne yapmadığı yazıldı: *"hiçbir gerçek write hiç yapılmadı"*, *"bu sürüm kod
çalıştıramaz"*, *"bugün yayımlanmış artefakt yoktur, indirme bağlantısı
veremem"*, *"SHA-256 bir doğrulama yordamı olarak sunulmaz"*.

Kılavuz ajanı her iddiayı **ilgili dosyayı okuyarak** doğruladı: altı kapı
`write_gate.py`'den tek tek sayıldı, beş dialog `IdentityDialogs.tsx`'ten,
sekiz araç ve tavanlar `agent-runtime.md`'den, `lobby`+`meta` reddi
`write_targets.py`'den.

Kabul listesinde **gerçek gönderim harf sırasını bilerek bozup en sona**
kondu, sekiz ön koşulu tek tek sayılıyor ve **onay kutusu olmadığı belgede
açıkça yazıyor** — aksi hâlde "kullanıcı açıkça 'başlayalım' demeden gerçek
gönderim yapılmaz" koruması erirdi. İstenmeyecek dört madde de gerekçesiyle
listelendi: imza yok ki doğrulansın, iki derleme aynı hash'i vermiyor,
h1→h3 atlaması bilinen ve düzeltilemez, DPAPI hesaba bağlı olduğu için
başka-profil denemesi tek yönlü.

## Kılavuz iki bayat yüzey daha buldu

Kendi alanı dışındaydı, **düzeltmeye kalkışmadan bildirdi** ve temizlik
tarafı ölçerek kapattı:

`SettingsHelpPage.tsx` hâlâ "kullanim kilavuzu Paket J'de eklenecek"
diyordu. Metin düzeltildi ve testinin iddiası **silinmek yerine ters
çevrildi**: artık kılavuz adlarını **şart koşuyor** ve "Paket J"/"eklenecek"
ifadelerini **yasaklıyor**, yani her iki yönde sürüklenme kırmızı.

`docs/identity-lifecycle.md` §5'in write-gate tablosu iki kapı için "Aşama 4
/ `not_implemented`" diyordu; `write_gate.py`'nin altı `GateCheck`'i tek tek
okundu — aşamalar **2 / 2B / 3** ve `evaluate` bugün **hiç**
`NOT_IMPLEMENTED` üretmiyor. Aynı dosyada **ikinci** bayat satır da bulundu:
parola isteminin "(Aşama 4'te) imzalama" için olduğu yazıyordu; imzalama
Paket D'de indi.

## Ölçüm sırasında yaşananlar

**Bayt-birebir testi doğru şekilde kırmızıya döndü.** Temizlik ajanının
frontend değişikliği, Paket I'dan kalan bundle'ı bayatlattı ve
`test_the_shipped_spa_is_byte_for_byte_the_audited_dist` bunu yakaladı —
yani o test tasarlandığı işi yapıyor. Bundle yeniden derlendi.

**Ajan kendi verdiği zararı bulup onardı:** `sed -i` CRLF checkout'unda dokuz
dosyanın satır sonlarını bozdu; `git diff` uyarılarından fark edilip geri
yüklendi ve `git diff` artık sıfır uyarı veriyor.

## Kapılar (son head, orkestratör koşusu)

| Kapı | Sonuç |
|---|---|
| pytest | **2212 geçti** |
| Vitest | **315 geçti** |
| Playwright (e2e) | **74 geçti** |
| ruff (iki koşu) / mypy strict | geçti / 133 dosya 0 hata |
| eslint / build | geçti / geçti |
| `git diff --check` | 0 |

**Sessizce atlanan test yok:** `skipped`/`xfailed`/`xpassed` **sıfır**,
toplanan ile koşan **aynı**, ve platform `skipif`'leri Windows'ta
tetiklenmiyor. Paket J altı test ekledi, **hiçbirini silmedi**.

## Kalan riskler — proje düzeyinde

1. **İnsan güvenlik incelemesi yok.** On bir paketin hepsinde ertelenmiş
   kalan risk (ADR-0001 §5). Bu paket onu **kapatmaz, görünür kılar** —
   `SECURITY.md` §7'ye de yazıldı.
2. **Gerçek Technocore write hiç yapılmadı.** Lobby hiçbir testte hedef
   olmadı.
3. **Gerçek LLM çağrısı hiç yapılmadı**, hiçbir ücretli çağrı yok; OpenCode
   `Authorization: Bearer` varsayımı **resmî belgede doğrulanmadı**.
4. **Kibble claim/result sözleşmesi doğrulanmadı** (ADR-0007).
5. **`ready_to_publish` HTTP'den erişilemiyor** — kapatılmış bir karar değil,
   **açık bir boşluk**.
6. **İmza yok**, ve **yeniden üretilebilirlik yok** (ölçüldü: iki derleme
   farklı özet).
7. **Tarayıcı QA otomatik**; manuel/görsel kabul kullanıcının işidir ve
   `docs/kullanici-kabul-listesi.md` onu maddeleştirir.
8. **SI-50'nin üretim yarısı testsiz** (yukarıda).
9. **e2e ağacı lint edilmiyor** — `eslint.config.js` bir depo hook'u
   tarafından yazmaya kapalı; bir ölü export'u fiilen bu üretti. Kabul
   listesine gerekçesiyle girdi.

## Sınırlar

Bu pakette hiçbir dış servise istek gönderilmedi; hiçbir şey kurulmadı;
gerçek DID/kasa/recovery/API anahtarı okunmadı; kullanıcının veri dizinine
dokunulmadı; lobby hedef olmadı; yeni bağımlılık yok; pin (`7707cb63`) ve
beklenen sürüm değişmedi; tag/release/deploy yok.

## Proje durumu

**`CODE_COMPLETE_USER_ACCEPTANCE_PENDING`** — kod tamam, **kullanıcı kabulü
bekliyor**, ve o kabul kullanıcının kendi işidir.
