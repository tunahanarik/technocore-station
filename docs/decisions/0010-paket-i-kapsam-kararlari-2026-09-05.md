# ADR-0010 — Paket I kapsam kararları (5 Eylül 2026)

Durum: **kabul edildi** · Bağlam: künye Aşama 7 (Packaging),
`docs/execution-plan.md` Paket I

Keşif on iki karar boşluğu çıkardı ve **paketlemeyi bugün imkânsız kılan bir
blokeri ölçtü**. ADR-0001…0009 gibi bu da bağlayıcıdır ve hiçbir güvenlik
değişmezini gevşetmez.

## 0. Kurulum sözleşmesi zaten yazılı

ADR-0008 §1 ürünün sözleşmesini kabul edilmiş bir kararda tanımlamıştı:
Station **`%LOCALAPPDATA%`'ya kurulan, admin istemeyen, loopback-only bir
masaüstü uygulamasıdır**. Aynı ADR'nin üçüncü maddesi de bu paketi
bağlıyor: **CI'da veya temiz bir makinede doğrulanamayan bir yol kabul
edilmez.**

`docs/execution-plan.md` Paket I'dan dört şey istiyor: ADR'li paketleyici
seçimi, izole doğrulama, SHA-256, **unsigned uyarısı**. Yani plan imzasız
gönderimi zaten öngörmüş; istediği imza değil, **imzasızlığın dürüstçe
söylenmesi**.

## 1. BLOKER: `REPO_ROOT` bugün yalnız editable kurulum sayesinde çalışıyor

`app.py`'nin `REPO_ROOT = Path(__file__).resolve().parents[4]` satırı repo
düzenine bağlı. Ölçüldü: `.venv/Lib/site-packages` içinde
`_editable_impl_station_api.pth` var; **wheel'den kurulunca `parents[4]`
`.venv`'in üstüne düşer**, `apps/station-web/dist` orada yoktur ve uygulama
**sessizce 503 "Arayuz derlenmemis" servis eder**. PyInstaller altında
`__file__` `_MEIxxxx`'e düşer.

Aynı sorun `db/migrations_runner.py`'nin `MIGRATIONS_DIR`'inde: Alembic
`env.py` ve `versions/*.py`'yi **dosya olarak** okur.

**Karar:** yol çözümü `importlib.resources` ile paket verisinden, donmuş
dalda `sys._MEIPASS`'ten yapılır. **Yolu ortam değişkeninden okumak
reddedilir** — `LOOPBACK_HOST`'un bilinçle ortamdan okunmama gerekçesiyle
aynı: paketlenmiş SPA'yı başka bir dizine yöneltmek, CSP `'self'` altında
çalışan keyfi JS'i servis etmenin yoludur.

**Ek şart:** paketlenmiş bir çalıştırma "build yok" 503'ünü **asla
üretmemelidir** ve bunu bir test doğrulamalıdır, yoksa kırılma sessiz kalır.

## 2. Paketleyici: PyInstaller **onedir**, ZIP olarak

`%LOCALAPPDATA%\Programs\TechnocoreStation\` altına açılan bir ZIP;
installer yok.

**Uyum:** admin gerektirmez · `%LOCALAPPDATA%` · loopback-only'i
değiştirmez · `windows-latest`'te uçtan uca doğrulanabilir · `%TEMP%`'e
yazmaz · vendor dizinini taşımaz (AC-19).

**Eleme gerekçeleri, ölçümle:**
- **MSIX** — imza zorunlu; sertifika **yok** (`signtool` yok, Windows Kits
  yok, `Cert:\CurrentUser\My`'de kod imzalama sertifikası yok, kullanıcı
  admin değil). Eleniyor.
- **Tauri** — ADR-019 "daha sonra" diyor; Rust toolchain + WebView2 en
  yüksek maliyet.
- **PyInstaller onefile** — her çalıştırmada `%TEMP%\_MEIxxxx`'e açar.
  Bugün ürün `%TEMP%`'e **hiç** yazmıyor (tek `tempfile` kullanımı
  `dir=target.parent` ile veri dizininin içinde), yani onefile **doğru olan
  bir özelliği bozar**.
- **uv + `.bat`** — son kullanıcıya uv ve ağ dayatır; ADR-0008 §1'in
  "kullanıcı kurulumu ürünün garantisi değildir" mantığı uv'ye de uygulanır.
- **Inno Setup** — ZIP yeterliyken ayrı bir dış araç.

## 3. Sınır taramaları paketleme ağacını kapsar — **merge şartı**

ADR-0009 §5'in aynısı, aynı gerekçeyle, ve keşif iki somut delik ölçtü:

- **`test_bind.py`'nin `0.0.0.0` taraması yalnız `apps/station-api/src`
  altındaki `.py` dosyalarını okuyor.** Bir `.spec`, `.iss`, `.bat` veya
  `.ps1` içindeki wildcard bind **görünmez**.
- **`subprocess`/`exec` yasağı yalnız `agent/` ve `proof/` ağaçlarında.**
  Bir installer veya güncelleme yolu `subprocess` getirirse
  `arbitrary_execution_supported: Literal[False]` ve `execution_unavailable`
  gerekçesi ürün genelinde **yalancı koruma** olur ve hiçbir test bunu
  görmez.

Ayrıca `test_tracked_sources.py`'nin `SHIPPED_TREES` ve `SOURCE_SUFFIXES`
kümeleri genişletilmelidir: `.gitignore` bugün `dist/`, `build/`, `out/`
taşıyor — **PyInstaller'ın varsayılan çıktı dizin adları**. Bir
`packaging/build/helper.py` sessizce yok sayılır ve CI'da
`ModuleNotFoundError` olarak patlar; Paket G'de `credentials.py`'nin başına
gelenin **birebir tekrarı** olur.

Her genişletme H3'ün ikili kalıbıyla sürülür: taramanın yeni dosyaları
gerçekten **açtığı** ve ekili bir ihlalin **raporlandığı**, ayrı ayrı.

## 4. Gönderilen frontend denetlenir — en yüksek vacuity riski

`test_frontend_bundle.py` **deponun** `dist`'ini okuyor. Paketleme SPA'yı
bundle'ın içine kopyalarsa, bu testler **gönderilmeyen** bir artefaktı
denetlemeye devam eder ve gerçekten gönderilen baytlar hiçbir kontrole
girmez. **Test kırmızıya dönmez, sadece bakmayı bırakır** — bu deponun
ADR-0004'ten beri tekrar tekrar yakaladığı kalıp.

**Karar:** paketlenen SPA'nın `dist` ile **bayt-birebir aynı** olduğu
ölçülür. Tek bir iddia mevcut altı denetimi gönderilen artefakta taşır ve
tek satırda kırılır. Depo zaten bayt-birebir doğrulama kalıbına sahip.

## 5. Kaldırma veri dizinine dokunmaz

Kaldırma bugün **hiçbir belgede tanımlı değil**. Ölçüldü: `%LOCALAPPDATA%\
TechnocoreStation` silinirse seed, audit zinciri anahtarı, kanıt kayıtları
ve workspace **birlikte gider** ve `.tcrec` yoksa geri dönüş yoktur. DPAPI
zarfı kullanıcı hesabına bağlı, **yola bağlı değil**, yani taşımak kimliği
bozmaz — silmek bozar.

**Karar:** kaldırma yalnız program dizinini siler; veri dizinine
**dokunmaz**, ve bu hem kaldırma çıktısında hem kılavuzda açıkça yazılır.
Geri döndürülemez kayıp bir tıklamaya bağlanmaz (ADR-014 ve künye §13.7 ile
tutarlı). Kullanıcı gerçekten temizlemek isterse elle siler; yolu Paket J'nin
kılavuzuna yazılır.

**Installer veri dizinini oluşturmaz.** `ensure_data_dir` bugün ACL
uygulamıyor (vault, audit, credential ve workspace uyguluyor); dizin başka
bir yerde önceden oluşturulursa veritabanı **kalıtılmış izinlerle** doğar.

## 6. Kurulum kökü sürümsüz; yükseltme ve geri dönüş test edilir

Bugün test edilenler yalnız idempotence ve boş DB'ler. **Test edilmeyenler**
(`downgrade`, `unknown revision`, ileri uyumluluk aramaları boş döndü):

1. `0007` şemalı **gerçek veri taşıyan** bir DB'nin `0009`'a yükseltilip
   satırlarını koruduğu,
2. **daha yeni** bir DB'yi açan eski kodun **anlaşılır biçimde** reddettiği
   (sessiz bozulma değil).

İkisi de bu pakette yazılır. **Sürümlü kurulum kökü + `current` bağlantısı
reddedilir**: sembolik bağlantı/junction, H2'nin reparse-point savunmasının
tam olarak reddettiği şeydir.

## 7. Konsol görünür kalır

Bugün log yalnız `StreamHandler`. `--noconsole` bir exe'de stderr **hiçbir
yere** gitmez ve başlangıç hataları sessizce kaybolur; telafi için eklenen
bir dosya log'u ise redaksiyon zincirinin dışına düşme riski taşır.

**Karar:** konsol bu sürümde görünür kalır. Loopback-only bir araç için
konsol bir kusur değil, hem kapanış mekanizması hem teşhis yüzeyidir ve
**hiçbir yeni secret yüzeyi açmaz**. Dosya log'u kanıtı olmadan eklenmez.

## 8. Tek örnek koruması eklenir

Ne tek-örnek koruması ne kapanış handler'ı var; çift tıklama iki prosesi
aynı SQLite ve aynı `audit/v1/chain-head.json` üzerine koyar. **Yarışın
gerçekten bozup bozmadığı ölçülmedi** ve ölçülmeden "sorun yok" yazılamaz
(ADR-0005 §2 kalıbı: yokluk söylenir, uydurulmaz).

**Karar:** veri dizininde `O_CREAT|O_EXCL` kilit dosyası — deponun zaten
kullandığı kalıp, `ctypes` gerekmez. İkinci örneğin mevcut sekmeyi açması
bir IPC kanalı demektir ve loopback-only sözleşmeyi karmaşıklaştırır;
reddedilir.

## 9. İmzasızlık nasıl söylenir

1. Artefaktın SHA-256'sı build çıktısında ve doğrulama raporunda yayımlanır;
   `station_api/digests.py` yeniden kullanılır, yeni bir hash yardımcısı
   yazılmaz.
2. **H3'ün hash cümlesi aynen taşınır** (ADR-0009 §11): *hash yalnız dosya
   bütünlüğünü tanımlar; içeriğin doğru veya yararlı olduğunu kanıtlamaz.*
   Ve ek olarak: **imzasız bir artefaktta hash, onu kimin ürettiğini de
   kanıtlamaz** — çünkü hash'in kendisi aynı kanaldan gelir.
3. SmartScreen davranışı beklenen ve normal olarak tanımlanır.
   **"SmartScreen'i kapatın" yazılmaz.**

## 10. CI'da dördüncü iş

`runs-on: windows-latest` — bu, künyenin istediği **temiz Windows
profilidir**. Mevcut disiplinle (tam SHA pin, cache yok, secret yok):
build → SHA-256 → **`PATH`'ten uv ve Node çıkarılarak** artefaktı çalıştır →
`127.0.0.1:<efemer>`'e bind ettiğini doğrula → `/api/app/status`'ün doğru
aşamayı verdiğini doğrula → `%LOCALAPPDATA%` dışına yazmadığını doğrula →
temiz kapanış.

**İmzalama doğrulanamaz** (secret yok, sertifika yok) ve bu böyle yazılır.

## 11. Aşama numarası `9 → 10`

Beş giriş noktası (`cli/__main__.py`, `launcher.py`, `routes/api.py`,
`e2e/harness/serve.py`, `tests/conftest.py`) ve pinli `CURRENT_SCHEMA_STAGE`
**atomik** olarak. Paket I'nın şemaya dokunması gerekmiyor, dolayısıyla
`CURRENT_MIGRATION_HEAD` **`0009`'da kalır**.

## 12. Yeni SI numaraları ve değişmeyenler

En yüksek numara **SI-313**; Paket I'nın değişmezleri **SI-314**'ten başlar.
Adaylar: paketlenen SPA `dist` ile bayt-birebir aynıdır · paketlenen
artefakt `%TEMP%`'e açılmaz · paketleme ağacında `0.0.0.0` yoktur ·
paketleme ağacında `subprocess`/`exec` yoktur · paketlenmiş çalıştırma
"build yok" 503'ünü üretemez · artefakt `%LOCALAPPDATA%` dışına yazmaz.

**Değişmeyenler:** `OUTBOUND_CLIENT_MODULES` beşte kalır — bir "güncelleme
kontrolü" **altıncı giden yüzey** açar ve bu pakette açılmaz. `0.0.0.0`
bind, CORS ve `verify=False` yasakları aynen. Gerçek yazma, gerçek harcama,
gerçek anahtar/DID/seed yok. İnsan güvenlik incelemesi ertelenmiş kalan
risktir (ADR-0001 §5).
