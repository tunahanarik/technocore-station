# Windows paketleme

> Kapsam kararları:
> [`ADR-0010`](decisions/0010-paket-i-kapsam-kararlari-2026-09-05.md) ·
> Kurulum sözleşmesi: [`ADR-0008 §1`](decisions/0008-paket-h2-kapsam-kararlari-2026-09-05.md) ·
> Doğrulama: [`verification/paket-i.md`](verification/paket-i.md)

Station **`%LOCALAPPDATA%`'ya kurulan, admin istemeyen, yalnız loopback
dinleyen bir masaüstü uygulamasıdır.** Paketleme bu sözleşmeyi değiştirmez;
onu taşınabilir hâle getirir.

## Paketleme zorunlu değildir

**Ürünün birincil çalışma biçimi tarayıcıdır ve öyle kalır.** Station bir
FastAPI sunucusu olarak `127.0.0.1`'de efemer bir porta bağlanır, SPA'yı
kendisi servis eder ve kullanıcının varsayılan tarayıcısını açar. Depodan
`uv run --project apps/station-api python -m station_api` ile çalıştırmak
**tam ve desteklenen bir yoldur**.

Bu paketin ürettiği ZIP, aynı uygulamayı **`uv` ve Node kurmadan**
başlatabilmek için bir kolaylıktır — bir ön koşul değil. Bu ayrım iki şeyi
değiştirir:

- **İmzasızlığın kalan riski küçülür.** SmartScreen uyarısı yalnız ZIP'i
  tercih eden kullanıcıyı ilgilendirir; depodan çalıştıran hiç görmez.
- **Paketleme kırılırsa ürün kırılmaz.** Dördüncü CI işi kırmızıya dönerse
  kaybedilen şey kolaylıktır, çalışabilirlik değil.

Buna karşılık, bu paketin **paketlemeye özgü olmayan** düzeltmeleri her iki
yolu da ilgilendirir ve tutulur: yol çözümünün editable olmayan kurulumlarda
sessizce 503 vermesi, `subprocess`/`exec` yasağının ürün geneline taşınması,
`0.0.0.0` taramasının genişlemesi, gerçek veri taşıyan migration yükseltme
testleri, tek örnek kilidi ve **Ctrl+C/Ctrl+Break kapanışı** — sonuncusu
depodan çalıştırmada da aynı şekilde bozuktu.

---

## 1. Bugünün durumu — ölçülmüş özet

**Artefakt üretildi ve çalıştırıldı.** PyInstaller artık bu deponun
**kilitli bir geliştirme bağımlılığıdır**: `apps/station-api/pyproject.toml`
`dev` grubunda `pyinstaller==6.16.0`, `apps/station-api/uv.lock` içinde
kilitli. Yani `uv sync --locked` onu diğer her şeyle aynı yoldan kurar ve
CI'daki paketleme işi artık **kilitsiz kurulum yapmaz** — bu, o işi merge
kapısı yapan tek engelin kalkması demektir (§10).

**Paketleyicinin kendisi artefaktın içine girmez.** Yalnız build zamanı
çalışır. Gönderilen exe'de PyInstaller kaynaklı olarak **bulunanlar**
ölçüldü (exe'nin baytlarında arandı): derlenmiş bootloader,
`PyInstaller/loader` modülleri (`pyiboot01_bootstrap`, `pyimod01_archive`,
`pyimod02_importers`) ve run-time hook'lar. Ürünün **çalışma zamanı
bağımlılık yüzeyi değişmedi**: `pyproject.toml`'un `dependencies` listesine
hiçbir şey eklenmedi. Lisans (kurulu paketten okundu; SPDX:
`GPL-2.0-or-later WITH Bootloader-exception`) ve tam gerekçe `README.md`
bağımlılık tablosundadır; gönderilen bundle'ın lisans haritası
[`NOTICE`](../NOTICE) sonundadır.

### Ölçülen artefakt

Sürüm `0.1.0`, `windows-latest` değil bir **geliştirme makinesinde**
(Windows 11 Pro 10.0.26200, CPython 3.12, PyInstaller 6.16.0) üretildi:

| Ölçüm | Değer |
|---|---|
| Arşiv | `TechnocoreStation-0.1.0-windows-x64.zip` |
| Arşiv boyutu | **26 126 723 bayt** (24,92 MiB) |
| Arşiv SHA-256 | `7deebffda8bdf0a6f7cc82b785c461703444770237b5e16d4d5583ec6508a5f0` |
| `TechnocoreStation.exe` boyutu | **12 263 074 bayt** |
| `TechnocoreStation.exe` SHA-256 | `5121b7194494d77e45fcac2a975dec1c51ad0a22f3d694c193fef54bfc33454e` |
| Açılmış bundle | **152 dosya**, 38 dizin, **50 778 509 bayt** (48,43 MiB) |

Bu değerler **bu makinede üretilen bu yapıya** aittir. **Yeniden
üretilebilirlik ölçülmedi**: bundle bir kez üretildi, ikinci bir yapının aynı
özeti verip vermeyeceği denenmedi. PyInstaller bit-bit yeniden
üretilebilirlik **garanti etmez**, dolayısıyla başka bir makinede üretilen
bir yapının aynı özeti vermesi beklenmemelidir ve burada iddia edilmiyor.
Özet, elinizdeki dosyanın kendisiyle karşılaştırılmak içindir.

## 2. Biçim: PyInstaller `onedir`, ZIP olarak (ADR-0010 §2)

`%LOCALAPPDATA%\Programs\TechnocoreStation\` altına açılan bir ZIP.
Installer yok, kayıt defteri yazımı yok, servis yok, zamanlanmış görev yok,
UAC istemi yok.

Elenen seçenekler ve **ölçülmüş** gerekçeleri ADR-0010 §2'dedir. İkisi kodun
şeklini belirlediği için burada da tekrarlanır:

- **`onefile` reddedildi.** Her çalıştırmada `%TEMP%\_MEIxxxx`'e açar. Ürün
  bugün `%TEMP%`'e **hiç** yazmıyor, yani `onefile` doğru olan bir özelliği
  bozar. `station.spec` bu yüzden `COLLECT` ile biter ve
  `test_the_spec_is_onedir_and_not_onefile` bunu sabitler.
- **Konsol görünür kalır (ADR-0010 §7).** Donmuş bir `--noconsole` derlemede
  `stderr`'in gideceği hiçbir yer yoktur; bu pakette eklenen her ret —
  tutulmuş veri dizini, daha yeni bir veritabanı, arayüzsüz bir paket —
  `stderr`'e yazılır. Telafi için dosya log'u eklemek redaksiyon zincirinin
  dışına çıkma riskidir ve **kanıtsız eklenmez**.

## 3. Nasıl üretilir

```bash
npm --prefix apps/station-web run build
uv run --project apps/station-api python packaging/build_bundle.py
```

Çıktılar **yalnız** `packaging/artifacts/` altındadır:

| Yol | Nedir |
|---|---|
| `packaging/artifacts/bundle/TechnocoreStation/` | `onedir` paketi |
| `packaging/artifacts/work/` | PyInstaller ara dosyaları |
| `packaging/artifacts/TechnocoreStation-<sürüm>-windows-x64.zip` | dağıtılan arşiv |

`dist/` veya `build/` **kullanılmaz**, ve bu bir stil tercihi değildir:
`.gitignore` bu iki adı Aşama 1'den beri **derinlikten bağımsız** olarak
yok sayar. PyInstaller'ın varsayılanlarını kabul etmek, `packaging/build`'i
kaynak taramasından muaf tutmak demekti; ADR-0010 §3 o muafiyetin yuttuğu
dosyayı adıyla söylüyor: `packaging/build/helper.py` — bir makinede var, CI'da
`ModuleNotFoundError`. Paket G'de `credentials.py`'nin başına gelenin
birebir aynısı. `/packaging/artifacts/` tek, dar ve **çapalanmış** bir kural
olarak eklendi; muafiyet dokümante edilmedi, **kaldırıldı**.

## 4. Kurulum ve kaldırma

**Kurulum.** Arşivi `%LOCALAPPDATA%\Programs\TechnocoreStation\` altına açın
ve `TechnocoreStation.exe`'yi çalıştırın. Yönetici hakkı gerekmez.

**Kaldırma (ADR-0010 §5).** Yalnız program dizinini silin:

```
%LOCALAPPDATA%\Programs\TechnocoreStation\
```

**Veri dizinine dokunulmaz:**

```
%LOCALAPPDATA%\TechnocoreStation\
```

Bu dizinde seed'in DPAPI zarfı, denetim zincirinin anahtarı, kanıt kayıtları
ve çalışma alanı vardır. Silinirse `.tcrec` recovery dosyanız yoksa **geri
dönüş yoktur**. DPAPI zarfı Windows kullanıcı hesabınıza bağlıdır, **yola
bağlı değildir**: dizini taşımak kimliği bozmaz, silmek bozar. Gerçekten
temizlemek istiyorsanız elle silersiniz; geri döndürülemez bir kayıp tek bir
tıklamaya bağlanmaz.

Kurulum veri dizinini **oluşturmaz**. `ensure_data_dir` bugün ACL
uygulamıyor (kasa, denetim, credential ve workspace uyguluyor); dizin başka
bir yerde önceden oluşturulursa veritabanı kalıtılmış izinlerle doğardı.

## 5. Tek örnek koruması (ADR-0010 §8)

Veri dizininde `station.lock`, `O_CREAT | O_EXCL` ile açılır. İkinci bir
kopya aynı SQLite dosyasını ve aynı `audit/v1/chain-head.json`'ı açmaz; ret
çıkış kodu **4** ve silinecek dosyanın tam yolunu taşıyan bir cümledir.

İki şey bilinçle **yapılmadı**:

- **IPC yok.** İkinci kopyanın mevcut sekmeyi açması ikinci bir yerel
  dinleyici veya adlandırılmış boru demektir; sözleşme tek loopback
  dinleyicidir.
- **Canlılık yoklaması yok.** `os.kill(pid, 0)` Windows CPython'da
  `OpenProcess` + `TerminateProcess` olarak uygulanır, yani sinyal `0`
  sorulan süreci **sonlandırırdı**. Bu yüzden bayat kilit tahminle
  temizlenmez; silinecek yol söylenir.

**Kilit ne zaman kalır — ölçüldü.** Uygulama gerçekten paketlenip
çalıştırıldı ve üç şekilde durduruldu. Tablo **kapanış turundan sonraki**
hâldir; bulunan iki kusur ve nasıl kapandığı hemen altındadır.

| Durdurma | Uvicorn kapanışı | `station.lock` | Çıkış kodu | Konsol |
|---|---|---|---|---|
| **Ctrl+C** (belgelenen yol) | temiz | **silindi** | **0** | çöküş metni yok |
| **Ctrl+Break** | temiz | **silindi** | **0** | çöküş metni yok |
| Zorla sonlandırma (`TerminateProcess`) | yok | **kaldı** | öldürenin verdiği | — |

### Ne bulundu ve nasıl kapandı

İlk ölçümde ilk iki satır şöyleydi: Ctrl+C **çıkış kodu 1** ve konsolda
`KeyboardInterrupt` ile PyInstaller'ın `Failed to execute script` satırı;
Ctrl+Break **çıkış kodu 3**, `finally` hiç çalışmadan, `station.lock`
**kalarak**. İkisinin de tek bir nedeni vardı ve tek bir yerde durur:

`uvicorn.Server.capture_signals`, yakaladığı sinyali zarif kapanıştan sonra
**kendisinden önce kurulu olan handler'ı geri koyup** `signal.raise_signal`
ile yeniden yükseltir. Yani `Server.run` çağrısını çevreleyen handler,
temiz bir kapanışın **nasıl göründüğüne** karar verir. Varsayılanlar iki kötü
son veriyordu: `SIGINT` `default_int_handler`'a döner ve `KeyboardInterrupt`
yükseltir — `main()`'in `return 0`'ına hiç varılmaz; `SIGBREAK` `SIG_DFL`'e
döner ve Windows CRT varsayılanı süreci **yığın çözülmeden** bitirir, bu
yüzden kilidi bırakan `finally` hiç çalışmaz.

Çözüm `launcher.absorbing_shutdown_signals()`: `Server.run` çağrısının
**etrafına** kurulan, `SIGINT`/`SIGTERM`/`SIGBREAK` için hiçbir şey yapmayan
bir handler. uvicorn geri koyduğunda bu handler'ı geri koyar, yeniden
yükseltilen sinyal hiçbir şey yapmaz, `main()` `return 0`'a ulaşır ve
`finally: lock.release()` her iki tuşta da çalışır. Pencere **dar**dır:
yalnız sunucunun koştuğu süre boyunca kuruludur, çünkü tüm süreç boyunca
sinyal yutmak yavaş bir migration'ı kesilemez yapardı. Gerçek bir çökme
**hâlâ çökmedir** — `except` yalnız `KeyboardInterrupt` yakalar, `Exception`
değil.

**Ölçüm, kaynakta değil artefaktta.** Kusur öncesi ve sonrası hâller aynı
düzenekle, yeniden üretilmiş `.exe` üzerinde ölçüldü
([`verification/paket-i.md`](verification/paket-i.md) §13.3). Üçüncü satır da
tahmin değil: `TerminateProcess` ile ölçüldü, `finally` çalışmaz ve kilit
kalır. Bu durum için ret mesajı silinecek yolu zaten söyler; ADR-0010 §8'in
"canlılık yoklaması yok" kararı **değişmedi**.

## 6. Yükseltme ve geri dönüş (ADR-0010 §6)

Kurulum kökü **sürümsüzdür** ve bir `current` bağlantısı **yoktur**:
sembolik bağlantı/junction, H2'nin reparse-point savunmasının tam olarak
reddettiği şeydir. Yükseltme yerinde yapılır — arşivi aynı dizine açın.

- **Eski şemadan yükseltme.** `0007` şemalı, **satır taşıyan** bir
  veritabanı `0009`'a yükselir ve satırlarını korur
  (`test_an_upgrade_from_an_older_release_keeps_the_rows_it_found`).
- **Daha yeni bir veritabanı.** Tanımadığı bir revizyonla işaretlenmiş bir
  dosyayı açan eski kod `SchemaAheadError` ile **durur** ve verinin
  değiştirilmediğini söyler. Bu kontrol olmadan hata Alembic'in `upgrade`
  içinden gelen `Can't locate revision`'ıydı: bir çökme, ama üzerine
  hareket edilebilecek bir cümle değil.

Downgrade **yoktur**. Eski bir sürüme dönmek isterseniz veri dizininin
yedeğini alıp eski sürümü kurun; şemayı geri almanın desteklenen bir yolu
yoktur ve olduğu iddia edilmez.

## 7. Yol çözümü (ADR-0010 §1)

`station_api/resources.py` üç durumu ayırır:

| Durum | Arayüz | Migration ağacı |
|---|---|---|
| Donmuş (PyInstaller) | `sys._MEIPASS/station_web` — yoksa **hata** | `sys._MEIPASS/station_api/db/migrations` — yoksa **hata** |
| Depo çalışma kopyası | `apps/station-web/dist` (yoksa 503 "derlenmemiş" sayfası) | paket içindeki ağaç |
| Yalnız wheel | yok (`None`) | paket içindeki ağaç |

**Yol ortam değişkeninden okunmaz.** Gerekçe `LOOPBACK_HOST`'unkiyle
aynıdır: paketlenmiş SPA'yı başka bir dizine yöneltmek, CSP `'self'` altında
çalışan keyfi JS'i bu origin'den servis etmenin yoludur.
`test_no_path_in_the_resolver_is_read_from_the_environment` hem modülde
ortam okuyucu bulunmadığını hem de makul isimleri ayarlamanın sonucu
değiştirmediğini ölçer.

**Paketlenmiş bir çalıştırma "Arayuz derlenmemis" 503'ünü üretemez.** İki ayrı
ret vardır — çözücü olmayan bir dizini **adlandırmayı** reddeder, `_mount_spa`
onu **bağlamayı** reddeder — çünkü biri değiştirildiğinde diğeri hâlâ
ateşlemelidir.

## 8. Gönderilen arayüz denetlenir (ADR-0010 §4)

`test_frontend_bundle.py`'nin altı denetimi `apps/station-web/dist`'i okur.
Paketlenen kopya o dizinden farklı olsaydı, bu altı denetim **kırmızıya
dönmeden** gönderilmeyen bir artefaktı denetlemeye devam ederdi.

İki iddia bunu kapatır:

1. `test_the_packaging_spec_ships_the_audited_dist_and_nothing_else` —
   spec'in kopyaladığı **kaynak** `apps/station-web/dist`'tir ve hedefi
   `station_api.resources.BUNDLED_WEB_DIR`'dir.
2. `test_the_shipped_spa_is_byte_for_byte_the_audited_dist` — paket
   üretilmişse gönderilen kopya `dist` ile **bayt-birebir** aynıdır; paket
   yoksa bunu söyler ve **paket var ama SPA'sı beklenen yerde değilse
   başarısız olur**.

Karşılaştırmanın kendisi ayrıca sürülür: tek baytı değişmiş bir kopyada
**hangi dosyanın** değiştiği isimle raporlanır.

## 9. SHA-256 ve imzasızlık (ADR-0010 §9)

Build çıktısı arşivin SHA-256'sını yayımlar. Değer
`station_api.digests.file_digest` ile hesaplanır — bu ürünün diğer bütün
digest'leri alan-ayrılmış ve uzunluk-önekli olduğu hâlde bu biri **düz
SHA-256**'dır, çünkü kullanıcının `Get-FileHash -Algorithm SHA256` ile
doğrulayabilmesi gerekir. Yalnız bu depoda doğrulanabilen bir yayın özeti
yayın özeti değildir.

```powershell
Get-FileHash -Algorithm SHA256 .\TechnocoreStation-0.1.0-windows-x64.zip
```

Bu depoda üretilen yapının ölçülen değerleri (§1'deki tabloyla aynı):

```
7deebffda8bdf0a6f7cc82b785c461703444770237b5e16d4d5583ec6508a5f0  TechnocoreStation-0.1.0-windows-x64.zip
5121b7194494d77e45fcac2a975dec1c51ad0a22f3d694c193fef54bfc33454e  TechnocoreStation.exe
```

> Bu özet **yalnızca dosya bütünlüğünü** tanımlar: içeriğin doğru veya
> yararlı olduğunu kanıtlamaz. Artefakt **imzasızdır**, bu yüzden özet onu
> **kimin ürettiğini de kanıtlamaz** — özetin kendisi dosyayla aynı kanaldan
> gelir.

**SmartScreen.** İmzasız bir indirme için Windows SmartScreen uyarı
gösterecektir. Bu **beklenen ve normal** davranıştır. Bu belge SmartScreen'i
kapatmanızı istemez ve istemeyecektir.

**İmzalama neden yok:** bu makinede kod imzalama sertifikası yok (`signtool`
yok, Windows Kits yok, `Cert:\CurrentUser\My`'de sertifika yok, kullanıcı
admin değil) ve CI'da secret yok. `docs/execution-plan.md` Paket I zaten
imza değil, **imzasızlığın dürüstçe söylenmesini** istiyordu.

## 10. CI (ADR-0010 §10)

`.github/workflows/packaging.yml`, `windows-latest` üzerinde: derle →
SHA-256 → **`PATH`'ten uv ve Node çıkarılarak** artefaktı çalıştır →
`127.0.0.1` ve efemer port doğrula → `/api/health` → korumalı rotanın 401
verdiğini doğrula → `%TEMP%`'e `_MEI*` açılmadığını doğrula → veri dizininin
dışına yazmadığını doğrula.

**Bu iş artık dördüncü merge kapısıdır.** Tetikleyicisi `quality.yml`'ninkiyle
aynı: `pull_request` (hedef `main`) + `push` (`main`), üstüne elle çalıştırma
için `workflow_dispatch`. Kapı olamamasının tek nedeni kaydedilmişti —
PyInstaller `uv.lock` içinde yoktu ve bir işin kilitsiz kurulum yapması
gerekiyordu. PyInstaller artık kilitli `dev` bağımlılığıdır, `uv sync
--locked` onu kuruyor ve **`uv pip install` adımı silindi**; yerine
paketleyicinin sürümünü yazdıran bir doğrulama adımı kondu.

`quality.yml`'ye dördüncü **iş** olarak değil, ayrı bir workflow olarak
duruyor: bu iş donmuş bir ikiliyi derleyip **çalıştırır** (40 dakikaya kadar)
ve başarısızlığı "bundle bozuk" diye okunmalıdır, "backend kapıları
başarısız" diye değil. Tetikleyici, izinler, tam SHA pin ve cache politikası
`quality.yml` ile birebir aynıdır.

**Bu workflow hiç koşturulmadı.** Yerelde GitHub Actions yok; YAML bir
ayrıştırıcıyla doğrulandı (tetikleyiciler, `permissions: contents: read`,
`concurrency`, tek iş `bundle`, 11 adım, üç action'ın da `quality.yml` ile
aynı tam SHA'lara pinli olduğu). İçindeki PowerShell **çalıştırılmadı**; ilk
kez CI'da koşacak. Aynı doğrulamaların yerel karşılığı elle yapıldı ve
sonuçları [`verification/paket-i.md`](verification/paket-i.md) §13'te.

**Doğrulanamayanlar, iddia edilmeden:**

- `/api/app/status`'ün aşama numarası. O rota oturum ister, oturum da
  launcher'ın tarayıcıda açtığı ve **bilinçle loglamadığı** tek kullanımlık
  bağlantıyı ister (SI-07). CI için yazdırmak canlı bir token'ı herkese açık
  bir log'a koymak olurdu. Aşama numarası bunun yerine süreç içinde
  `test_module_registry.py` ile doğrulanır.
- İmzalama. Sertifika ve secret yok.

## 11. Değişmeyenler

`OUTBOUND_CLIENT_MODULES` **beşte** kalır. Bir "güncelleme kontrolü"
**altıncı giden yüzey** açardı ve bu pakette açılmadı: paket kendini
güncellemez, sürüm sorgulamaz ve hiçbir uzak adrese bakmaz. `0.0.0.0` bind,
CORS ve `verify=False` yasakları aynen; artık `.spec`, `.ps1`, `.bat`,
`.iss` ve CI workflow dosyaları da `0.0.0.0` taramasının içindedir
(ADR-0010 §3).
