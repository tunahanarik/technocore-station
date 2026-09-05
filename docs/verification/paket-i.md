# Paket I doğrulama raporu — Windows paketleme

Tarih: 2026-09-05 · Kapsam kararları:
[`ADR-0010`](../decisions/0010-paket-i-kapsam-kararlari-2026-09-05.md) ·
Uygulama ayrıntısı: [`../packaging.md`](../packaging.md).

## Önce kapsam: paketleme **zorunlu değil, kolaylık**

Kullanıcı bu paket bitmek üzereyken kapsamı netleştirdi: *"windows uygulaması
olarak paketlememize gerek yok aslında tarayıcıda çalışan bir uygulama olarak
da kalabilir."* Sorulduğunda kararı bize bıraktı, biz de **yapılmış ve yeşil
olan işi tuttuk** — atmanın maliyeti var, tutmanın yok.

Fakat bu, kalan riskin ağırlığını gerçekten değiştiriyor ve burada kayda
geçiyor: **ürünün birincil yolu tarayıcı ve depodan çalıştırmadır.**
Paketlenmiş ZIP, aynı uygulamayı `uv` ve Node kurmadan başlatmak için bir
kolaylıktır. Dolayısıyla imzasızlık ve SmartScreen uyarısı **yalnız ZIP'i
tercih edeni** ilgilendirir; depodan çalıştıran kullanıcı onları hiç görmez.

Bu paketin **paketlemeye özgü olmayan** düzeltmeleri ise her iki yolu da
ilgilendirir: yol çözümü, sınır taramalarının genişlemesi, migration
yükseltme testleri, tek örnek kilidi ve kapanış davranışı — Ctrl+C'nin
çıkış kodu 1 ile ve traceback basarak bitmesi **depodan çalıştırmada da**
aynen oluyordu.

## Artefakt üretildi ve çalıştırıldı

Bu raporun ilk sürümü "artefakt üretilmedi" diye açılıyordu ve nedeni
PyInstaller'ın bu deponun bağımlılığı olmamasıydı. **O karar alındı.**
PyInstaller `apps/station-api/pyproject.toml`'un `dev` grubuna
`pyinstaller==6.16.0` olarak, tam pinle eklendi ve `apps/station-api/uv.lock`
güncellendi. Üretim bağımlılığı **değildir** ve **artefaktın içine girmez**:
yalnız build zamanı çalışır, dolayısıyla ürünün çalışma zamanı bağımlılık
yüzeyi değişmedi.

Sonuç: bu turda **bir `.zip`, bir `.exe` ve bir `onedir` dizini üretildi**,
artefakt **çalıştırıldı** ve önceki sürümün §12'sinde adıyla listelenen
ölçülemeyenlerin çoğu artık ölçüldü. Ölçülemeyen ne kaldıysa §12'de.

**Kapanış turu (5 Eylül 2026, ikinci geçiş).** İlk çalıştırmada üç kusur
ölçülmüştü — Ctrl+C'nin çöküş gibi görünmesi, Ctrl+Break'in bayat kilit
bırakması ve sınır taramasının dosya sayısının build durumuna bağlı olması.
**Üçü de kapatıldı**; ne bulunduğu ve nasıl kapandığı §13.3 ve §13.5'te
**silinmeden** duruyor, ölçümler artefakt yeniden üretilip yeniden
çalıştırılarak alındı.

### Lisans — okunan metin

İddia hafızadan veya webden değil, **kurulu paketten** okundu:

* `apps/station-api/.venv/Lib/site-packages/pyinstaller-6.16.0.dist-info/METADATA`
  → `License: GPLv2-or-later with a special exception which allows to use
  PyInstaller to build and distribute non-free programs (including
  commercial ones)`
* aynı dizinde `licenses/COPYING.txt` (636 satır) → SPDX kimliği
  **`GPL-2.0-or-later WITH Bootloader-exception`**

İstisna maddesinin **tam metni** ("Bootloader Exception"): GPL'in verdiği
izinlere **ek olarak**, yazarlar derlenmiş bootloader'ı ve ilgili dosyaları
başka programlarla birleştirmek (link/embed) ve **o dosyaların kullanımından
doğan hiçbir kısıt olmadan** bu birleşimleri dağıtmak için sınırsız izin
verir. GPL kısıtları başka açılardan sürer: örneğin bu dosyaların
**değiştirilmesi** ve birleşik bir çalıştırılabilire **bağlanmadan**
dağıtılması. "Bootloader and Related Files" aynı dosyada `./bootloader/` ve
`./PyInstaller/loader` olarak **tanımlanmıştır**. Run-time hook'lar
(`./PyInstaller/hooks/rthooks`) aynı dosyada ayrıca **Apache-2.0** olarak
lisanslanmıştır.

Bunun paketlenmiş çıktıya etkisi, **ölçülerek** yazıldı: üretilen exe'nin
baytları arandı ve içinde `pyiboot01_bootstrap`, `pyimod01_archive`,
`pyimod02_importers` (yani `PyInstaller/loader`), `pyi_rth_inspect` ve
`pyi_rth_setuptools` (yani rthook'lar) ile `pyi_rth_cryptography_openssl`
(`pyinstaller-hooks-contrib`, Apache-2.0) bulundu. Yani artefakt **gerçekten
PyInstaller kaynaklı dosyalar taşıyor** — ve okuduğum metin tam olarak bu
üç kategoriyi karşılıyor. **Kendi kodumuzun lisansı etkilenmez: MIT kalır.**
Gönderilen bundle'ın lisans haritası [`../../NOTICE`](../../NOTICE) sonuna
yazıldı.

---

## 1. Bloker: `REPO_ROOT` (ADR-0010 §1)

`app.py`'nin `Path(__file__).resolve().parents[4]` satırı dokuz pakettir
**yalnız editable kurulum sayesinde** çalışıyordu. Ölçüm:
`.venv/Lib/site-packages` içinde `_editable_impl_station_api.pth` var, yani
`parents[4]` gerçekten depo kökü. Wheel'den kurulunca `.venv`'in üstüne
düşer, `apps/station-web/dist` orada olmaz ve uygulama **sessizce 503
"Arayuz derlenmemis"** servis eder. O sayfaya bakan **hiçbir test yoktu** —
sessizliğin nedeni budur.

Çözüm `station_api/resources.py`: `importlib.resources` ve donmuş dalda
`sys._MEIPASS`. Ortam değişkeni **reddedildi** ve reddedildiği ölçülüyor
(modülde `os.environ`/`getenv`/`import os` yok, ve üç makul değişken adını
ayarlamak sonucu değiştirmiyor).

Ölçülen davranış:

| Durum | Arayüz | Migration ağacı |
|---|---|---|
| Donmuş, SPA var | `_MEIPASS/station_web` | `_MEIPASS/station_api/db/migrations`, Alembic `script_location` odur |
| Donmuş, SPA yok | **`PackagedLayoutError`** (503 **değil**) | **`PackagedLayoutError`** |
| Depo kopyası, `dist` yok | 503 sayfası + `npm ... run build` komutu | paket içindeki ağaç |

Üçüncü satır bilinçle korundu: o sayfa yalnız **bir** durumda doğrudur ve o
durum bir geliştiricinin henüz `npm run build` çalıştırmamış olmasıdır.

**İki katman, çünkü biri düzenlenebilir.** Çözücü olmayan bir dizini
adlandırmayı reddeder; `_mount_spa` açıkça verilen boş bir dizini bağlamayı
reddeder. Mutasyon tablosunda ikisi de **ayrı ayrı** öldürüyor.

## 2. Sınır taramaları (ADR-0010 §3) — iki delik, iki ölçüm

**Delik 1 — `0.0.0.0` taraması.** Eski hâli `apps/station-api/src` altındaki
`.py` dosyalarıydı. `packaging/station.spec`'e ekilen bir `0.0.0.0` **hiçbir
testi kırmıyordu**. Tarama artık **beş** ağaç ve on beş uzantı okuyor
(`len(test_bind.SCANNED_TREES) == 5`, `.github/workflows` beşincisi); ekili ihlal `.spec`, `.ps1`, `.bat`, `.iss` ve
`.yml` için **ayrı ayrı** sürülüyor, ve taramanın `.py` dışında gerçekten
dosya açtığı sayılıyor.

**Delik 2 — yürütme yasağı.** `subprocess`/`exec` yasağı yalnız `agent/` ve
`proof/` ağaçlarındaydı. `packaging/build_bundle.py`'ye ekilen bir
`import subprocess` **hiçbir testi kırmıyordu**, oysa
`arbitrary_execution_supported: Literal[False]` ürün geneli hakkında bir
iddiadır. Yasak artık ürün geneli.

Bu yüzden **build betiği `subprocess` kullanmıyor**: PyInstaller kendi Python
API'sinden (`PyInstaller.__main__.run`) sürülüyor.

**`ctypes` muafiyeti iki dosyadır ve sürülüyor.** `vault/dpapi.py` ve
`vault/windows_acl.py` Win32'yi `ctypes` ile çağırır ve süreç yaratmaz;
üçüncü bir modülün `ctypes` import etmesi mutasyon tablosunda kırmızı
veriyor. `importlib` bu listeye **konmadı**: ADR-0010 §1 çözümü tam olarak
`importlib.resources`'tır ve `technocore_conform.selftest` pinli vektörlerini
Aşama 2B'den beri öyle okur.

**`SHIPPED_TREES` / `SOURCE_SUFFIXES`.** `packaging/` eklendi, sekiz uzantı
eklendi. Asıl karar burada `GENERATED_NAMES`'e **`build` ve `out`
eklenmemesidir**: ADR-0010 §3'ün adını verdiği kaza
(`packaging/build/helper.py` — bir makinede var, CI'da `ModuleNotFoundError`)
tam olarak o eklemeyle görünmez olurdu. Bunun yerine build çıktısı
`packaging/artifacts/` altına alındı ve `.gitignore`'a **çapalanmış** tek bir
kural eklendi; muafiyet dokümante edilmedi, kaldırıldı. Test `git
check-ignore` ile `packaging/build/helper.py`'nin gerçekten yok sayıldığını,
ve taramanın onu **muaf tutmadığını** ayrı ayrı ölçüyor.

## 3. Gönderilen SPA (ADR-0010 §4)

`test_frontend_bundle.py`'nin altı denetimi `dist`'i okumaya devam ediyor.
Tek bir iddia onları gönderilen artefakta taşıyor, ve o iddianın kendisi
sürülüyor: tek baytı değişmiş bir kopyada **hangi dosyanın** değiştiği isimle
raporlanıyor, silinen bir dosya da yakalanıyor.

**Bu turda bayt karşılaştırması ilk kez gerçek bir pakete karşı koştu.**
`packaging/artifacts/bundle/TechnocoreStation/_internal/station_web/` üç dosya
taşıyor (`index.html`, `assets/index-j_o5mxO6.css`, `assets/index-D3ufUUGq.js`)
ve üçünün de SHA-256'sı `apps/station-web/dist` ile **birebir eşit** çıktı.

İddianın bu turda gerçekten iş gördüğü ayrıca sürüldü: gönderilen
`index.html`'in **son baytı** satır sonundan boşluğa çevrildi, test kırmızıya
döndü ve farkı **isimle** raporladı —
`index.html: 768bcc88... != 0968f28b...` — sonra dosya geri yüklendi ve test
yeniden yeşile döndü. İlk mutasyon denemesi kayda geçiyor çünkü **mutasyon
değildi**: son bayt zaten satır sonuydu, dosya değişmedi ve test haklı olarak
geçti. "Test mutasyonu öldürmedi" ile "ortada mutasyon yoktu" ayrımı bu
raporun konusudur.

Kanıtlanan şey dar ve önemli: `test_frontend_bundle.py`'nin altı denetimi
artık **gönderilen** baytların denetimidir. Gönderilen kopya `dist`'ten bir
bayt saparsa altı denetim sessizce ilgisiz bir dizine bakmaya başlamaz; tek
satırda kırılır.

## 4. Paketleyici (ADR-0010 §2, §7)

`packaging/station.spec`: `onedir` (`COLLECT` + `exclude_binaries=True`),
`console=True`, `codesign_identity=None`, `nacl` hariç tutulmuş (SI-63 ürün
import grafiğinde PyNaCl istemez), datas olarak SPA + migration ağacı +
pinli conformance vektörleri.

`packaging/build_bundle.py` ölçülen çıktı — üç ön koşul da sağlanıyor:

```
[OK  ] spec: ...\packaging\station.spec
[OK  ] frontend-build: ...\apps\station-web\dist
[OK  ] pyinstaller: PyInstaller 6.16.0
exit=0
```

Refüs yolu bu makinede artık tetiklenmiyor, ve bunu ölçen test
(`test_the_build_script_never_claims_an_artefact_it_did_not_produce`) iki
dallı yazılmıştı: `--check` sıfır dönerse çıktıda `EKSIK` **bulunmadığını**
doğrulayıp durur, dönmezse refüsü sürer. Bu tur dalı değiştirdi; test bu
yüzden sessizce vakum testine dönüşmedi.

## 5. Yükseltme ve geri dönüş (ADR-0010 §6)

İki test yazıldı, ikisi de daha önce hiç yoktu:

1. `0007` şemasına **gerçek satır** yazılıyor (kimlik, görev, metadata),
   `0009`'a yükseltiliyor, satırlar **değer değer** karşılaştırılıyor.
   Öncesinde bu depodaki her migration testi **boş** veritabanı üzerindeydi.
2. Tanımadığı bir revizyonla işaretli bir veritabanını açan kod
   `SchemaAheadError` ile duruyor. Bu bir **ürün değişikliğidir**:
   `run_migrations` artık `guard_against_a_newer_schema` çağırıyor. Öncesi
   Alembic'in `upgrade` içinden gelen `Can't locate revision`'ıydı — bir
   çökme, ama üzerine hareket edilebilir bir cümle değil. Mesaj verinin
   **değiştirilmediğini** ve **silinmediğini** söylüyor (ADR-0010 §5 ile
   tutarlı), ve damganın el değmediği testte doğrulanıyor.

Sürümlü kurulum kökü ve `current` bağlantısı **reddedildi**: junction, H2'nin
reparse-point savunmasının reddettiği şeydir.

## 6. Tek örnek (ADR-0010 §8)

`station_api/single_instance.py`, `O_CREAT | O_EXCL`, veri dizininde.
Launcher kilidi **veritabanını açmadan önce** alıyor (sıra testte
sabitlendi — sonra alsaydı kapatmak istediği pencere açık kalırdı) ve
`finally` ile bırakıyor.

`os.kill(pid, 0)` ile canlılık yoklaması **yapılmadı** ve nedeni koda
yazıldı: Windows CPython'da `os.kill` `OpenProcess` + `TerminateProcess`
olarak uygulanır, yani sinyal `0` sorulan süreci **sonlandırırdı**. Bayat
kilit bu yüzden tahminle temizlenmiyor; silinecek dosyanın tam yolu
söyleniyor.

**Ölçülmeyen:** iki sürecin aynı SQLite ve aynı `chain-head.json` üzerinde
yarışmasının **gerçekten** bozup bozmadığı. ADR-0010 §8 bunu zaten
ölçülmemiş olarak kaydediyor; koruma "yarış ölçüldü" diye değil, kaybedilecek
şey bir denetim zinciri olduğu için var.

## 7. İmzasızlık (ADR-0010 §9)

`digests.py`'ye `file_digest` eklendi — **düz** SHA-256, çünkü kullanıcının
`Get-FileHash` ile doğrulayabilmesi gerekir. Bu, modülün kendi iki kuralına
(alan ayrımı, uzunluk öneki) bilinçli bir istisnadır ve gerekçesi docstring'e
yazıldı; test değerin `hashlib.sha256(bayt)` ile birebir eşit ve
alan-ayrılmış digest'e **eşit olmadığını** ölçüyor. İkinci bir hash
yardımcısı yazılmadı.

Cümle H3'ten aynen taşındı, imzasızlığa özgü yarısı eklendi, ve
**"SmartScreen'i kapatın" hiçbir yerde yazmıyor** — testte de aranıyor.

## 8. CI (ADR-0010 §10) — artık dördüncü kapı

`.github/workflows/packaging.yml`: `windows-latest`, tam SHA pin, cache yok,
secret yok; derle → SHA-256 → `PATH`'ten uv/Node/Python çıkar → artefaktı
çalıştır → `127.0.0.1` + efemer port → `/api/health` → korumalı rota **401**
→ `%TEMP%`'te `_MEI*` yok → veri dizinine yazıldı.

**Bu artık bir merge kapısıdır.** Tetikleyici `workflow_dispatch`'ten
`quality.yml`'ninkine çevrildi: `pull_request` (hedef `main`) + `push`
(`main`), üstüne elle koşturma için `workflow_dispatch` korundu. Kapı
olamamasının kaydedilmiş tek nedeni ortadan kalktı — PyInstaller `uv.lock`
içinde ve `uv sync --locked` onu kuruyor. `uv pip install "pyinstaller==6.16.0"`
adımı **silindi**; yerine paketleyicinin sürümünü yazdıran bir adım kondu, ki
artefaktı kimsenin pinlemediği bir şey derlerse bu görünsün.

`quality.yml`'ye dördüncü **iş** olarak taşınmadı, ayrı workflow olarak
bırakıldı: bu iş donmuş bir ikiliyi derleyip **çalıştırır** ve başarısızlığı
"bundle bozuk" diye okunmalıdır, "backend kapıları başarısız" diye değil.
Tetikleyici, `permissions`, pin ve cache politikası birebir aynıdır.

**Workflow koşturulmadı** ve koşturulamaz: yerelde GitHub Actions yok. YAML
bir ayrıştırıcıyla doğrulandı — `on` = `{pull_request: {branches: [main]},
push: {branches: [main]}, workflow_dispatch: None}`, `permissions:
{contents: read}`, `concurrency: packaging-${{ github.ref }}`, tek iş
`bundle`, `runs-on: windows-latest`, `timeout-minutes: 40`, **11 adım**, üç
action da `quality.yml` ile **aynı tam SHA'lara** pinli, dosyada hiç
`secrets.` geçmiyor. İçindeki PowerShell **çalıştırılmadı**; ilk kez CI'da
koşacak. Aynı kontrollerin yerel karşılığı elle yapıldı: §13.

Yeni bir sınır: workflow header'ı artık "temiz kapanış" iddia **etmiyor**.
İş süreci `Stop-Process -Force` ile öldürüyor, yani ölçtüğü şey bayat kilidin
kaldığıdır; graceful kapanış §13'te elle ölçüldü ve **kusurlu çıktı**.

`/api/app/status`'ün aşama numarası CI'da hâlâ **doğrulanamıyor**: rota oturum
ister, oturum tek kullanımlık bağlantıyı ister, o bağlantı bilinçle
loglanmaz (SI-07). Aşama numarası süreç içinde
`test_module_registry.py::test_every_entry_point_names_the_same_release_stage`
ile doğrulanıyor.

## 9. Aşama numarası (ADR-0010 §11)

`9 → 10`, beş giriş noktası ve `CURRENT_SCHEMA_STAGE` atomik olarak:
`cli/__main__.py`, `launcher.py`, `routes/api.py`,
`apps/station-web/e2e/harness/serve.py`, `tests/conftest.py`.
`CURRENT_MIGRATION_HEAD` **`0009`'da kaldı** — Paket I şemaya dokunmadı.

## 10. Değişmeyenler

`OUTBOUND_CLIENT_MODULES` **beşte**. Güncelleme kontrolü **eklenmedi**: paket
kendini güncellemez, sürüm sorgulamaz, hiçbir uzak adrese bakmaz. `0.0.0.0`,
CORS ve `verify=False` yasakları aynen ve artık daha geniş kapsamda. Gerçek
yazma, gerçek harcama, gerçek anahtar/DID/seed yok. Vendor pin
`7707cb63ebf638e8ef0cf59d1364818b9fef7d24` değişmedi.

## 11. Mutasyon tablosu

Yirmi mutasyon, yirmisi de en az bir testi öldürdü. Tam tablo:
[`../security-invariants.md`](../security-invariants.md) §9l.

İki satır özellikle: `.spec`'e ekilen `0.0.0.0` ve `build_bundle.py`'ye
ekilen `import subprocess` — **ikisi de bu paketten önce sıfır kırmızı
verirdi**. ADR-0010 §3'ün ölçtüğü iki delik tam olarak bunlar.

**Yirmi birinci mutasyon bu turda eklendi ve tabloda değil, §3'te**: o tur
tablodaki mutasyonlar sentetik dizinler üzerinde koşuyordu, bu ise
**gerçekten gönderilen** dosyanın baytı üzerinde koştu. Yirmi satırın hiçbiri
o zaman mümkün değildi, çünkü gönderilecek bir dosya yoktu.

**Bağımsız inceleme turu.** Dışarıdan bir düşman inceleme yirmi iki mutasyon
daha yaptı ve **beşi sıfır kırmızı** verdi. Beşi de kapatıldı ve her biri
"önce 0 kırmızı / sonra n kırmızı" olarak yeniden ölçüldü;
[`../security-invariants.md`](../security-invariants.md) §9l'nin üçüncü
mutasyon tablosu satır satır taşıyor. Bu turda **bir bulgu ölçülerek
reddedildi**: incelemenin F6 için önerdiği düzeltmenin kendisi totolojikti
(döngü, denetlediği listeyle birlikte küçülüyor) ve önerildiği gibi
yazıldığında mutasyon **yine 0 kırmızı** verdi; guard bunun yerine ikiye
bölündü ve kırmızıyı **depodan türetilen** yarı veriyor.

## 12. Ölçülmeyenler — adıyla

Önceki sürümün altı maddesinden **üçü ölçüldü** (§13). Geriye kalanlar:

1. **`packaging.yml` bu makinede bir iş olarak koşturulmadı.** GitHub
   Actions yok. Bağımsız inceleme turunda yapılabilen ölçüldü ve fazlası
   değil: YAML ayrıştırıldı, iki `pwsh` bloğu PowerShell'in **kendi
   ayrıştırıcısıyla** (`[Parser]::ParseInput`) hatasız çözüldü, `PATH`
   stripleme bölümü gerçek bir kabukta **birebir çalıştırıldı**, ve
   build'den sonra eklenen pytest adımının komutu yerelde **aynen** koşuldu
   (bundle diskteyken 77 test yeşil; gönderilen SPA'nın bir baytı
   çevrildiğinde **kırmızı**). Adımların **sırası** ve runner davranışı hâlâ
   ölçülmedi.
2. **Temiz Windows profili artık ölçülüyor — ve eski hâli yanlıştı.**
   Artefakt yine uv/Node/Python `PATH`'te **iken** çalıştırıldı, yani bundle'ın
   kendi kendine yeterliliği bu makinede **ölçülmedi**. Ölçülen şey
   workflow'un striplemesidir: eski regex filtresi (`uv|node|nodejs|npm|
   hostedtoolcache|Python`) gerçek bir Windows 11 kabuğunda `uv`'yi
   (`\.local\bin` altında) ve `python`'ı (`WindowsApps` App Execution Alias)
   **kaldırmıyordu** ve adımda bunu söyleyecek hiçbir iddia yoktu. Stripleme
   çözünürlük sürücülü hâle getirildi (aracı çöz, çözdüğü dizini `PATH`'ten
   at, tekrar çöz) ve arkasına `uv`/`python`/`node`'un artık **çözülmediğini**
   söyleyen bir iddia kondu; ikisi birlikte bu makinede çalıştırıldı ve
   `clean profile: ...` satırını bastı.
3. **İmzalama doğrulanamaz.** Sertifika yok, secret yok. Artefakt imzasız.
4. **Çift örnek yarışının gerçek etkisi** ölçülmedi (§6). Kilit ölçüldü,
   yarışın kendisi değil.
5. **Kaldırma akışı elle denenmedi.** Artefakt hiçbir yere **kurulmadı**:
   `%LOCALAPPDATA%` altındaki `Programs/TechnocoreStation` bu turda
   **oluşmadı** (kontrol edildi, yok). Kullanıcının veri dizini
   `%LOCALAPPDATA%` altındaki `TechnocoreStation` **hiç değişmedi** — dört
   dosyanın adı, boyutu ve mtime'ı çalıştırmadan önce ve sonra
   karşılaştırıldı, **birebir aynı**. Artefakt geçici bir `STATION_DATA_DIR`
   ile çalıştırıldı ve o dizin ölçümden sonra silindi.
6. **Tarayıcı QA (Playwright)** bu turda koşturulmadı.
7. **Yeniden üretilebilirlik ölçüldü ve olumsuz çıktı.** Artık "denenmedi"
   değil: aynı kaynaktan arka arkaya alınan iki yapının exe boyutu aynı,
   **SHA-256'sı farklı** çıktı. PyInstaller çıktısı bit-bit yeniden
   üretilebilir **değildir** ve öyle olduğu iddia edilmiyor; yayımlanan özet
   elinizdeki dosyayla karşılaştırılmak içindir.
8. Gerçek DID/seed/private key/recovery/`.tcrec`/API anahtarı **okunmadı,
   istenmedi, yazılmadı**. Gerçek Technocore'a hiçbir istek gitmedi.
   `git commit`/`push`/PR/tag/release **yapılmadı**.

## 13. Artefaktın kendisi — üretildi, ölçüldü, çalıştırıldı

### 13.1 Üretim ve ölçüm

Windows 11 Pro 10.0.26200, CPython 3.12, PyInstaller 6.16.0, `onedir`.
Özetler `station_api.digests.file_digest` ile (düz SHA-256, ADR-0010 §9).

Üç yapı üretildi. **Aşağıdaki ilk iki tablo tarihsel kayıttır ve artık
gönderilen artefakta ait değildir**; `Get-FileHash` ile karşılaştırılacak
değerler bu bölümün **sonundaki** tablodadır. Kayıt silinmiyor, çünkü hangi
değişikliğin özeti neden değiştirdiği bu üçlünün kendisinde okunuyor.

İlk üretim (kusur öncesi kod) — **geçersiz**:

| Ölçüm | Değer |
|---|---|
| Arşiv | `TechnocoreStation-0.1.0-windows-x64.zip` |
| Arşiv boyutu | 26 126 723 bayt (24,92 MiB) |
| Arşiv SHA-256 | `7deebffda8bdf0a6f7cc82b785c461703444770237b5e16d4d5583ec6508a5f0` |
| exe boyutu | 12 263 074 bayt |
| exe SHA-256 | `5121b7194494d77e45fcac2a975dec1c51ad0a22f3d694c193fef54bfc33454e` |
| Açılmış bundle | **152 dosya**, 38 dizin, 50 778 509 bayt (48,43 MiB) |

Birinci kapanış turunda yeniden üretilen artefakt (`launcher.py` değiştiği
için özetler zorunlu olarak farklıydı) — **bu da geçersiz**, çünkü aşağıdaki
sızıntı düzeltmesi artefaktı bir kez daha değiştirdi:

| Ölçüm | Değer |
|---|---|
| Arşiv boyutu | 26 128 503 bayt (24,92 MiB) |
| Arşiv SHA-256 | `ebc799ed3d7fbe7129e9e77609b4993b0009f780c0b2c8e65feed928428b183e` |
| exe boyutu | 12 264 773 bayt |
| exe SHA-256 | `52cb519111aaf4a77ea995716992dd8a65ee3f3478790d23518deec52ab232c5` |
| Açılmış bundle | **152 dosya**, 38 dizin, 50 780 208 bayt (48,43 MiB) |

Bağımsız incelemeden sonra üçüncü kez üretildi. Bu tur artefaktın **içeriğini**
değiştirdi: `station.spec` migration ve vektör ağaçlarını dizin olarak
kopyalıyordu, `__pycache__` dâhil. Bir `.pyc`'nin `co_filename`'i derlendiği
mutlak yolu taşır, dolayısıyla **gönderilen ZIP'in 152 dosyasından 11'i
üretildiği makinenin kullanıcı adını ve ev dizini yolunu içeriyordu**
(`db/migrations/__pycache__/env`, `versions/__pycache__/0001…0009`,
`technocore_conform/vectors/__pycache__/__init__`). exe ve PYZ temizdi;
dağıtılan tek şey ZIP. `launcher.py` de değişti (kilit artık tüm başlatmayı
sarıyor), bu yüzden özetler zaten farklı olacaktı.

**Gönderilen artefakt aşağıdaki tablodur. Yayımlanan tek kaynak budur.** `docs/packaging.md` ve `PROJECT_STATUS.md`
bu tabloyu tekrarlamaz, buraya referans verir — inceleme, üç yerde
yayımlanan özetlerin artefaktla eşleşmediğini ölçtü ve eşleşmeyen bir özet
kullanıcının ya vazgeçmesine ya da özeti umursamamayı öğrenmesine yol açar.

<a id="olculen-artefakt"></a>

| Ölçüm | Değer |
|---|---|
| Arşiv | `TechnocoreStation-0.1.0-windows-x64.zip` |
| Arşiv boyutu | **26 103 236 bayt** (24,89 MiB) |
| Arşiv SHA-256 | `cdd454e5082fd926dde737b347767b7a4294a92a66baac26d91adb68a9dc457b` |
| `TechnocoreStation.exe` boyutu | **12 264 811 bayt** |
| `TechnocoreStation.exe` SHA-256 | `13564d018191d109f53711f39f48dda940d1da2f4d9b330a25ac0fb7d6c8f0f4` |
| Açılmış bundle | **141 dosya**, 35 dizin, **50 727 517 bayt** (48,38 MiB) |
| ZIP içinde `__pycache__`/`.pyc` | **0** (önce 11) |
| ZIP içinde kullanıcı adı / ev dizini yolu geçen dosya | **0** (önce 11) |

Dosya sayısı 152'den 141'e, dizin sayısı 38'den 35'e düştü: kaybolanlar
yalnız üç `__pycache__` dizini ve içlerindeki 11 `.pyc`. Kaynak içerik
eksilmedi — 11 migration dosyası (`env.py`, `script.py.mako`, dokuz
`versions/*.py`) ve iki vektör dosyası (`__init__.py`,
`conformance-v1.json`) yerinde. Bu tarama artık bir test:
`test_the_shipped_archive_names_no_developer_and_no_home_directory`, ve
paketleme workflow'u onu build'den **sonra** koşuyor.

**Yeniden üretilebilirlik yine ölçülmedi ve yine iddia edilmiyor.** Aynı
kaynaktan arka arkaya alınan iki yapının exe özeti farklı çıktı (boyut aynı,
özet farklı), yani PyInstaller çıktısı bit-bit tekrarlanabilir değildir.
Yayımlanan özet, **elinizdeki dosyanın kendisiyle** karşılaştırılmak
içindir.

**Yeniden üretilen artefakt çalıştırıldı** (geçici `STATION_DATA_DIR`;
kullanıcının veri dizinine dokunulmadı): efemer port 59631, `/api/health`
**200**, `/api/app/status` oturumsuz **401**, `GET /` **200** ve gövdede
"derlenmemis" dizesi **yok**, `%TEMP%`'te `_MEI*` **yok**, yazılan her dosya
veri dizininin içinde (`station.sqlite3` + `-wal`/`-shm`, `station.lock`,
`audit/v1/chain-head.json`, `audit/v1/chain-material.json`). Veritabanının
oluşması, Alembic'in `env.py`'yi bundle'dan **`.pyc` olmadan** okuyabildiğini
gösterir — bu turun asıl riski oydu.

exe'nin `onedir`'de 12 MB olması beklenen davranıştır: `exclude_binaries=True`
ikilileri `COLLECT`'e bırakır, saf Python modülleri ise PYZ olarak exe'ye
eklenir.

### 13.2 Çalıştırma — gözlenenler

Geçici bir `STATION_DATA_DIR` ile, kullanıcının gerçek veri dizinine
dokunmadan.

| Gözlem | Sonuç |
|---|---|
| Dinlenen adres(ler) | yalnız `127.0.0.1` (`netstat -ano`, süreç PID'ine göre) |
| Port | efemer (`> 1024`; ölçülen koşularda 59919 / 62688 / 64086) |
| `GET /api/health` | **200** |
| `GET /api/app/status` (oturumsuz) | **401** |
| `GET /` | **200**, gövde `apps/station-web/dist/index.html` ile **bayt-birebir** |
| "Arayuz derlenmemis" 503'ü | **üretilmedi** (gövdede o dize yok) |
| `%TEMP%` içinde `_MEI*` | **yok** — çalışırken de, çıkıştan sonra da (`onedir`'in bütün anlamı) |
| Yazılan dosyalar | hepsi `STATION_DATA_DIR` altında: `station.sqlite3` (+`-wal`, `-shm`), `station.lock`, `audit/v1/chain-head.json`, `audit/v1/chain-material.json` |
| Kullanıcının veri dizini | **dokunulmadı** (4 dosyanın adı/boyutu/mtime'ı önce–sonra aynı) |
| Program dizini | **oluşmadı** |

`GET /`'in gövdesinin `dist/index.html` ile bayt-birebir çıkması, ADR-0010
§1'in "paketlenmiş bir çalıştırma 'build yok' 503'ünü **asla** üretmemelidir"
şartının statik değil, **çalışan süreç üzerinde** ölçülmüş hâlidir.

### 13.3 İki kusur — bulundu, ölçüldü, kapatıldı

Aşağıdaki iki kusur **ilk çalıştırmada** ölçüldü. Kayıt silinmiyor: ne
bulunduğu, nasıl ölçüldüğü ve nasıl kapandığı birlikte duruyor.

**Kusur 1 — temiz kapanış bir çöküş gibi görünüyordu.** Ctrl+C ile
durdurulan artefakt uvicorn'u düzgün kapatıyor ve `finally: lock.release()`
çalışıyordu, fakat süreç **çıkış kodu 1** ile ve konsola şunları yazarak
bitiyordu:

```
KeyboardInterrupt
[PYI-9728:ERROR] Failed to execute script '__main__' due to unhandled exception!
```

**Kusur 2 — Ctrl+Break bayat kilit bırakıyordu.** Aynı yeniden yükseltme,
`SIGBREAK`'in CRT varsayılanı süreci yığın çözülmeden bitirdiği için
`finally`'yi **atlıyordu**: çıkış kodu **3**, `station.lock` **kalıyordu** —
ve o kilit yüzünden uygulama bir daha açılmıyordu.

**Nedeni.** Tek bir mekanizma: `uvicorn.Server.capture_signals` yakaladığı
sinyali zarif kapanıştan sonra, **kendisinden önce kurulu handler'ı geri
koyarak** `signal.raise_signal` ile yeniden yükseltir. Dolayısıyla
`Server.run`'ı çevreleyen handler, temiz bir kapanışın nasıl bittiğine karar
verir; varsayılanlar `KeyboardInterrupt` (SIGINT) ve `abort()` (SIGBREAK)
idi.

**Kapanış.** `launcher.absorbing_shutdown_signals()` — `Server.run`'ın
**etrafına** kurulan ve `SIGINT`/`SIGTERM`/`SIGBREAK` için hiçbir şey
yapmayan bir handler; uvicorn geri koyduğunda geri konan handler budur,
yeniden yükseltilen sinyal hiçbir etki yaratmaz, `main()` `return 0`'a
varır. Pencere dardır (yalnız sunucu koşarken), böylece yavaş bir migration
hâlâ Ctrl+C ile kesilebilir. `except` yalnız `KeyboardInterrupt` yakalar:
gerçek bir çökme hâlâ yayılır, hâlâ basılır, hâlâ sıfırdan farklı çıkar.
Ayrıntı: [`../packaging.md`](../packaging.md) §5, değişmez **SI-326**.

#### Ölçüm — aynı düzenek, iki artefakt

Kusur öncesi kodla ve kusur sonrası kodla **ayrı ayrı** `.exe` üretildi ve
her ikisi de geçici bir `STATION_DATA_DIR` ile çalıştırıldı. Kullanıcının
`%LOCALAPPDATA%\TechnocoreStation` dizinine dokunulmadı.

| Artefakt | Tuş | Çıkış kodu | `station.lock` (çıkıştan sonra) | Konsol |
|---|---|---|---|---|
| kusur öncesi | Ctrl+C | **1** | silindi | `KeyboardInterrupt` + `[PYI-13744:ERROR] Failed to execute script '__main__' due to unhandled exception!` |
| kusur öncesi | Ctrl+Break | **3** | **kaldı** | `Shutting down` … `Finished server process`, sonra sessizce ölüm |
| **kapanış sonrası** | Ctrl+C | **0** | **silindi** | `Shutting down` / `Waiting for application shutdown.` / `Application shutdown complete.` / `Finished server process [19824]` — çöküş metni **yok** |
| **kapanış sonrası** | Ctrl+Break | **0** | **silindi** | aynı; çöküş metni **yok** |

Kapanış sonrası artefakt ayrıca **aynı veri dizininde** Ctrl+Break'ten sonra
yeniden başlatıldı: **başladı**, "zaten calisiyor" reddi **çıkmadı**. Kusurun
kullanıcıya dokunan yüzü buydu ve ölçülen şey odur.

Üçüncü durdurma yolu (`TerminateProcess`) **değişmedi ve değiştirilmedi**:
`finally` çalışmaz, kilit kalır, ret mesajı silinecek yolu söyler. ADR-0010
§8'in "canlılık yoklaması yok — `os.kill(pid, 0)` Windows'ta süreci
öldürür" kararı **yerinde duruyor**; bu turda ona dokunulmadı.

**Ölçüm metodolojisi notu.** İlk turda olduğu gibi bu turda da düzenek,
çocuk süreci yaratmadan önce `SetConsoleCtrlHandler(NULL, FALSE)` çağırarak
miras alınan "Ctrl+C yoksay" bayrağını temizliyor; aksi hâlde `CTRL_C_EVENT`
sessizce düşer ve sonuç **yanlış** okunurdu. İkinci bir tuzak da bu turda
ölçüldü: `SetConsoleCtrlHandler(NULL, TRUE)` yalnız Ctrl+C'yi yok saydırır,
**Ctrl+Break'i yok saydırmaz** — ilk denemede ölçüm sürecinin kendisi
Ctrl+Break ile öldü ve rapor üretilemedi. Düzenek her olayı sahiplenen
gerçek bir handler kaydedecek şekilde düzeltildi ve ölçüm tekrarlandı.

**Ölçüm sırasında ortaya çıkan yan gözlem.** Tarayıcı penceresi açılmasın
diye bazı koşularda `BROWSER` ortam değişkeni zararsız bir programa
ayarlandı; `webbrowser` o programı **tek kullanımlık açılış URL'siyle**
çağırdı ve program argümanı kendi hata satırında yankıladı. Bu düzeneğin
kendi yan etkisidir, ürünün değil — üründe URL Windows varsayılan
tarayıcısına gider ve loglanmaz (SI-07). Konsol metninin **birebir** alındığı
koşu `BROWSER` ayarlanmadan yapıldı. Yine de kayda değer: `webbrowser`
`BROWSER` değişkenini onurlandırır, yani ortam değişkenlerini yazabilen biri
açılış URL'sini hangi programın alacağını seçebilir. Böyle bir saldırgan
zaten veri dizinini okuyabilir; **yeni** bir yüzey değildir ve bu turda
değiştirilmedi, ama ölçüldüğü için yazılıyor.

### 13.4 Yan gözlem — dalgalı bir uvicorn/h11 izi

Kapanış sırasında iki koşuda da şu ERROR düştü:

```
WARNING uvicorn.error: Invalid HTTP request received.
... h11._util.LocalProtocolError: can't handle event type Response when
    role=SERVER and state=CLOSED
```

Sunucuyu düşürmüyor ve kapanışı engellemiyor; kapanmış bir bağlantıya 400
yazmaya çalışan uvicorn/h11 yarışıdır. Paket I'nın getirdiği bir şey değil
ve bu turda kök nedeni **kovalanmadı**; not olarak duruyor.

### 13.5 Üçüncü kusur — taramanın dosya sayısı build durumuna bağlıydı

**Ne bulundu.** Bir bundle üretildikten sonra `test_bind.py`'nin joker
tarama kümesi `packaging/` altında **14 dosya** açıyordu; ikisi kaynak
(`build_bundle.py`, `station.spec`), on ikisi artefakt içindeki
**kopyalardı** (migration ağacının `.py`'leri ve conformance vektörlerinin
`.json`'ı). Tarama geçiyordu ve gevşetilmemişti, ama **ne denetlediği**
makineye göre değişiyordu: bir geliştiricide 2, başka birinde 14 dosya. Bu
deponun tanıdık kusurunun tohumu budur — aynı test farklı yerlerde farklı
şeye bakar.

**Kolay çözüm neden alınmadı.** `artifacts`'ı `GENERATED_DIR_NAMES`'e
eklemek her yerdeki her `artifacts` dizinini kör eder; ADR-0010 §3 bu
kalıbı açıkça reddediyor (`.gitignore`'un `dist`/`build`/`out` kuralları
PyInstaller çıktısını yutuyordu ve muafiyet eklemek yerine çıktı dizini
taşınmıştı).

**Nasıl kapandı.** Tarama artık **kaynak** ile **üretilmiş kopya** arasındaki
farkı iki ayrı soruyla görüyor:

1. `ARTIFACT_DIR = packaging/artifacts` — **tam yol**, dizin adı değil. Tek
   bir yeri muaf tutar ve `test_tracked_sources.py`'nin zaten kullandığı
   muafiyetin **aynısıdır**; iki tanım birbirinden ayrılamasın diye testte
   eşitlikleri denetleniyor ve ikisi de `build_bundle.py`'nin gerçekten
   yazdığı yere bağlanıyor.
2. `GENERATED_DIR_NAMES`'ten `build`, `dist` ve `out` **çıkarıldı**. Bunlar
   PyInstaller'ın varsayılan çıktı adlarıdır ve ada göre atlanmaları, kardeş
   taramanın yıllardır reddettiği körlüğün ta kendisiydi. Artık üçünde de
   ekili bir `0.0.0.0` **raporlanıyor**.

**Ölçüldü.** Bir bundle diskteyken tarama `packaging/` altında **2 dosya**
açıyor (`build_bundle.py`, `station.spec`); toplam 149 dosya. Sentetik bir
ağaçta hem kopyaların atlandığı hem de atlanan kopyaların gerçekten
okunabilir uzantılar taşıdığı ayrı ayrı sürüldü, ve `build`/`dist`/`out`
altına ekilen üç ihlalin üçü de yakalandı. Değişmez **SI-327**.

## 13b. CI dördüncü kapıyı ilk kez koştu — ve bir gerçeği ölçtü

`packaging.yml` bu raporun ilk sürümünde **hiç çalışmamıştı**; PR #20'de
**ilk kez koştu ve geçti** (`windows bundle`, 2 dk 2 sn). Dört işin dördü de
yeşil. Runner'da ölçülenler:

- Ön koşul denetimi üç satırı da `[OK]` verdi (spec, frontend build,
  PyInstaller 6.16.0).
- ZIP üretildi ve SHA-256'sı **iki ayrı adımda** yayımlandı; build
  script'inin bastığı özet ile doğrulama adımının `Get-FileHash`'i **aynı**:
  `0028ac02…23dbec`.
- **İmzasızlık cümlesi artefaktın kendi çıktısında basılıyor**, yalnız
  belgede değil: özetin bütünlüğü tanımladığı, **imzasız bir artefaktta onu
  kimin ürettiğini kanıtlamadığı** (özet dosyayla aynı kanaldan geldiği
  için), ve SmartScreen uyarısının **beklenen ve normal** olduğu.
- Artefakt `PATH`'ten uv ve Node çıkarılmış hâlde çalıştırıldı ve
  `STATION_DATA_DIR` altına veritabanını yazdı.

**Kilidin bırakıldığı CI'da bilinçle DENETLENMİYOR** ve gerekçesi
workflow'un içinde yazılı: `Stop-Process -Force` bir **öldürmedir**, kapanış
değil — hiçbir `finally` çalışmaz. Adım bunun yerine kilidin **hayatta
kaldığını** doğruluyor, yani bayat-kilit yönergesinin doğru olduğunu.
Zarif kapanış bir konsol ister ve runner'ın `Start-Process` çocuğunda o yok;
bırakma yolu bu yüzden **süreç içinde** ayrı bir testle sabitleniyor.

### Ölçülen: derlemeler tekrarlanabilir değil ve bu iddia da edilmiyor

CI runner'ın ürettiği ZIP **26 696 239 B / `0028ac02…23dbec`**; yereldeki
derlemenin ölçüleri §13.1'dedir ve **oradaki değerler esastır** (bu bölümün
ilk hâli yerel satırda kusur **öncesi** bir boyutu kusur **sonrası** bir
hash'le eşleştiriyordu — bağımsız inceleme ölçtü ve düzeltildi; bu yüzden
sayı burada tekrarlanmıyor).

İki artefakt **aynı değil** ve olması da beklenmiyor: farklı CPython yama
sürümü (3.12.13 / 3.12.11), farklı makine, farklı yollar. Bu, §12'nin "bit-birebir
tekrarlanabilirlik iddia edilmiyor" satırının **ölçülmüş** karşılığıdır.
Pratik sonucu şudur: **bir özet yalnız onu üreten derlemeyi tanımlar**, ve
imza olmadığı için kullanıcının indirdiği ZIP'i doğrulamasının tek yolu onu
aldığı kanalda yayımlanan özettir — ki bu, imzanın yerini tutmaz.

### Yan gözlem: CI'da tarayıcı açılıyor

İş sonunda runner beş yetim süreç sonlandırdı (`msedge`, `identity_helper`).
Sebep ürünün kendi davranışı: `launcher` açılışta `webbrowser.open` çağırıyor
ve runner'da bunu Edge karşılıyor. Bir kusur değil — headless bir ortamda
beklenen sonuç — fakat CI'nın temizlemesi gereken süreç bırakıyor ve
buraya kayda geçiyor.

## 13c. Bağımsız inceleme sonucu

Temiz bağlamlı bir reviewer subagent koşuldu: **22 mutasyon, beşi sıfır
kırmızı.** On iki bulgunun **hepsi kapatıldı**. Bu **insan güvenlik
incelemesi değildir**; ADR-0001 §5'in kalan riski yerinde duruyor.

### P1-1: ADR'nin adını verdiği kaza hâlâ açıktı

ADR-0010 §3 `dist`/`build`/`out`'u PyInstaller'ın varsayılan çıktı adları
diye sayıp uyarmıştı. Düzeltme `build` ve `out`'u kaldırdı ve **`dist`'i
bıraktı** — oysa `dist` tam da varsayılan distpath. Ölçüldü:
`packaging/dist/helper.py` ekildi, `.gitignore` yuttu, **2184 test yeşil**.
Kardeş tarama bunu düzelttiği için iki liste sessizce ayrışmıştı.
Muafiyetler artık **tam yola** bağlı ve PyInstaller'ın üç varsayılan adı için
parametrize bir prob var: 0 → **3 kırmızı**.

### P1-2: `ctypes` muafiyeti yürütme yasağının tamamını deliyordu

İki dosya yalnız `ctypes`'tan değil, `EXECUTION_IMPORTS`'un **tamamından**
muaftı. İncelemeci `vault/dpapi.py`'ye — DPAPI zarfını açan modüle —
`subprocess.Popen` koydu ve **ruff, mypy ve 2184 test yeşil geçti**.
Muafiyet artık **sembole** bağlı: 0 → **1 kırmızı**.
`EXECUTION_ATTRIBUTES`'a `Popen`, `check_output`, `check_call`, `getoutput`,
`getstatusoutput`, `startfile`, `spawn*`, `exec*`, `posix_spawn` eklendi.
**`run`/`call` bilerek eklenmedi ve bu bir ölçüm:** `uvicorn.Server.run`,
`PyInstaller.__main__.run` ve `proof/bundle.py`'de sekiz meşru `run`
bağlaması var — `compile`'ın gerekçesinin aynısı, kodda yazılı.

### P2-3: kapattığımız kilit kusurunun ikinci yüzü

`finally: lock.release()` yalnız sunucu koşusunu sarıyordu, dolayısıyla
`acquire()` ile o `try` arasındaki her hata **bayat kilit** bırakıyordu —
migration sırasında Ctrl+C dâhil. Yani `absorbing_shutdown_signals`'ın
"yavaş bir migration hâlâ kesilebilir" övüncü, tam o senaryoda §13.3'te
kapattığımız kusuru geri getiriyordu. Ve `PackagedLayoutError` — bu paketin
**var oluş sebebi** olan hata — sonrasında kullanıcıya **yanlış sebep**
söyleniyordu ("zaten çalışıyor"). Kilit artık tüm başlatmayı sarıyor
(**SI-328**): düzeltme öncesi 4 kırmızı, sonrası 0.

### P2-5: gönderilen ZIP makineyi adlandırıyordu

`.pyc` dosyalarının `co_filename`'i mutlak kaynak yolunu taşıyordu:
**11 dosyada** geliştiricinin Windows hesabı adı ve ev dizini. exe ve PYZ
temizdi; sızıntı yalnız `__pycache__` kopyalarındaydı — ve dağıtılan tek şey
o ZIP. Spec artık iki ağacı dosya dosya kopyalıyor, `__pycache__`/`.pyc`
dışarıda (**SI-329**), ve artefaktı tarayan bir test eklendi: eski artefakta
karşı **1 kırmızı, 11 dosyayı adıyla**.

### İki ölçüm incelemeciyi düzeltti

**İncelemecinin önerdiği F6 düzeltmesi totolojikti ve bu ölçüldü.**
`for tree in SCANNED_TREES: assert ...` yazıldı, liste 4'ten 2'ye
indirildi — **yine 0 kırmızı**, çünkü döngü listeyle birlikte küçülüyor.
Guard ikiye bölündü: biri listeyi gezer, öbürü **depoyu** gezer
(`tests/`+`vendor/` dışındaki her `.py` taramanın içinde olmalı, istisnalar
gerekçeli). İkisi de mutasyonla sürüldü: 0 → 1 kırmızı.

**F10'da iddiayı eklemek striplemenin çalışmadığını ortaya çıkardı.**
Gerçek bir Windows 11 kabuğunda eski regex sonrası `uv` (`\.localin`) ve
`python` (`WindowsApps` alias) **hâlâ çözülüyordu** — yani "temiz profil"
iddiası yanlıştı ve ancak iddia edilince ölçülebilir oldu. Stripleme
çözünürlük sürücülü hâle getirildi ve arkasına üç aracın çözülmediği iddiası
kondu.

### Yeniden derlenen artefakt

| Ölçüm | Önce | Sonra |
|---|---|---|
| Açılmış bundle | 152 dosya / 50 780 246 B | **141 dosya / 50 727 517 B** |
| `__pycache__` girdisi | 11 | **0** |
| Ev dizini/kullanıcı adı geçen üye | 11 | **0** |

Arşiv **26 103 236** B, SHA-256 `cdd454e5…dc457b`; exe **12 264 811** B,
SHA-256 `13564d01…c8f0f4`. Kaynak içerik eksilmedi (11 migration + 2 vektör
dosyası yerinde). Çalıştırıldı: port 59631, `/api/health` 200, korumalı rota
401, `GET /` 200 ve "derlenmemiş" dizesi yok, `%TEMP%`'te `_MEI*` yok.

**Ayrıca ölçüldü:** aynı kaynaktan iki yapı **farklı exe SHA-256** verdi.
Yeniden üretilebilirlik yok ve iddia da edilmiyor — artık bu bir ölçüm,
bir varsayım değil.

### İncelemecinin ölçmedikleri (kendi beyanı)

`packaging.yml` bir Actions işi olarak **koşulmadı** (YAML ayrıştırıldı,
`pwsh` blokları PowerShell'in kendi parser'ıyla çözüldü, PATH-strip bölümü
gerçek kabukta çalıştırıldı — ama adım **sırası** ve runner davranışı
ölçülmedi). Yeniden üretilebilirlik, kusur öncesi artefaktın sayıları,
tarayıcı QA, ve Paket I dışındaki paketler incelenmedi.

## 14. Kapılar

Yedisi de yeşil. Kapanış turundan sonra pytest **2184** (kusur turu tabanı
2169, **+15**: on tanesi kapanış davranışı, beşi tarama kaynak/kopya ayrımı),
Vitest **315** (değişmedi).

| Kapı | Sonuç |
|---|---|
| `ruff check .` (station-api) | temiz |
| `ruff check` (üç ağaç) | temiz |
| `mypy --config-file ...` | 133 dosya, sorun yok |
| `pytest ../../tests -q -p no:warnings` | **2184 geçti** |
| `npm run lint` | temiz |
| `npm run test` | **315 geçti** |
| `npm run build` | başarılı |

`packaging/artifacts/` git'e **girmiyor**: `.gitignore`'un çapalanmış
`/packaging/artifacts/` kuralıyla `git check-ignore -v` hem ZIP'i hem exe'yi
yok sayıyor, `git status --porcelain --untracked-files=all packaging/` yalnız
iki kaynak dosyayı gösteriyor, ve `test_tracked_sources.py` bundle varken de
geçiyor. Kapanış turundan sonra **`test_bind.py` de** bundle varken ve
yokken aynı dosya kümesini açıyor (§13.5).
