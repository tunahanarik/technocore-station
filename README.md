# Technocore Station

Kullanıcıya ait bir Ed25519 `did:key` kimliğini güvenli biçimde yöneten,
Technocore'a gönderilecek içeriğin canonical biçimini resmî kurallara göre
üreten, yalnızca açık kullanıcı onayıyla imzalayıp gönderen ve sunucunun
geçici kayıtlarını yerelde yeniden doğrulanabilir biçimde saklayan
**local-first Windows uygulaması**.

> Technocore imzayı doğrular; Station canonical metni, alınan kaydı ve
> kaynağı doğrular.

**Durum: `CODE_COMPLETE_USER_ACCEPTANCE_PENDING`.** Kod tamamdır ve
arayüzün dokuz bölümünün dokuzu da açıktır: kimlik ve recovery, salt okunur
kaynak denetimi, besteci (canonical biçim, imza ve tek kullanımlık gönderim
onayı), kanıt defteri ve audit zinciri, iş taraması, görev yüzeyi ve agent
çalışma ortamı, aktivite kaydı, kanıt çalışma alanı ve OpenCode bağlantısı.
**Bekleyen şey kullanıcı kabulüdür** ve o kabul kullanıcının kendi işidir:
[`docs/kullanici-kabul-listesi.md`](docs/kullanici-kabul-listesi.md).

Aynı ölçüde önemli olan, ürünün **yapmadıklarıdır**: bu depoda hiçbir gerçek
Technocore write **hiç** yapılmadı, keyfi kod ve kabuk yürütmesi **kapalıdır**,
yayımlanmış bir artefakt **yoktur** ve insan güvenlik incelemesi **ertelenmiş
bir kalan risktir** (ADR-0001 §5). Her bölümün kendi sınırı
[`docs/kullanim-kilavuzu.md`](docs/kullanim-kilavuzu.md) içinde yazılıdır.

Bu paragraf bir madde **eksiltti**: eskiden "model çağrısı **yoktur**" da
diyordu ve o cümle artık doğru değil. Sözleşme
[ADR-0012](docs/decisions/0012-model-yolu-sozlesme-dogrulamasi-2026-09-06.md)
ile hesap sahibinin kendi anahtarıyla **ölçüldü** ve model yolu açıldı: model
bir plan **önerebilir**. Öneri yine kapalı araç registry'sinden geçer, model
kendine araç ekleyemez, kendi planını başlatamaz ve kendi planına onay
veremez. Otomatik testlerin hiçbiri gerçek bir sağlayıcıya çıkmaz —
hepsi `httpx.MockTransport` kullanır.

Bu paragrafta bilerek aşama numarası yoktur: sayı taşımayan bir metin
bayatlamaz. Aşama sayımı ve ayrıntılı durum tek kaynaktadır —
[`PROJECT_STATUS.md`](PROJECT_STATUS.md).

Uygunluk ile güncellik ayrı şeylerdir: uygunluk self-test'i bu yapının
**pinlenmiş referans commit** ile aynı davrandığını gösterir; salt okunur
denetim ise **canlı sunucunun** hâlâ o protokolü yayımladığını gösterir. İkisi
de geçmeden dış yazma kapısı açılmaz.

Ürün bir wallet, token claim uygulaması, airdrop puanlayıcısı, otomatik mesaj
botu veya kimlik sağlayıcısı **değildir**.

---

## Belgeler

| Belge | İçerik |
|---|---|
| [`Technocore-Station-Proje-Kunyesi.md`](Technocore-Station-Proje-Kunyesi.md) | **Ana karar kaynağı** — ürün, kapsam, mimari, kabul kriterleri |
| [`PROJECT_STATUS.md`](PROJECT_STATUS.md) | Aşama durumu, test sonuçları, riskler |
| [`AGENTS.md`](AGENTS.md) / [`CLAUDE.md`](CLAUDE.md) | Coding agent değişmezleri |
| [`SECURITY.md`](SECURITY.md) | Güvenlik duruşu ve **kalan riskler** |
| [`docs/architecture.md`](docs/architecture.md) | Mimari ve paket sınırları |
| [`docs/protocol-contract.md`](docs/protocol-contract.md) | Canonical/sweep/imza sözleşmesi |
| [`docs/conformance.md`](docs/conformance.md) | Uygunluk motoru, self-test, CLI (Aşama 2B) |
| [`docs/read-only-technocore.md`](docs/read-only-technocore.md) | Salt okunur istemci, kaynak registry'si ve drift modeli (Aşama 3) |
| [`docs/security-invariants.md`](docs/security-invariants.md) | Test edilebilir değişmezler — numaralandırılmış SI satırları; sayı burada tekrarlanmaz, tek kaynak belgenin kendisidir |
| [`docs/evidence-model.md`](docs/evidence-model.md) | Dört seviyeli kanıt modeli |
| [`docs/identity-lifecycle.md`](docs/identity-lifecycle.md) | Kimlik durum makinesi ve akışlar |
| [`docs/recovery-format-v1.md`](docs/recovery-format-v1.md) | `.tcrec` biçimi ve AAD sözleşmesi |
| [`docs/threat-model.md`](docs/threat-model.md) | Savunulan ve **savunulmayan** tehditler |
| [`docs/task-modules.md`](docs/task-modules.md) | Görev/proje modülü temeli, durum makinesi ve dört ayrık alan |
| [`docs/work-scan.md`](docs/work-scan.md) | İş taraması: salt okunur okuma yüzeyi ve sekiz öğeli aday |
| [`docs/agent-runtime.md`](docs/agent-runtime.md) | Agent çalışma ortamı, araç registry'si, bütçe ve Activity Desk |
| [`docs/proof-workspace.md`](docs/proof-workspace.md) | Kanıt çalışma alanı, tek kullanımlık paylaşım onayı |
| [`docs/opencode-connection.md`](docs/opencode-connection.md) | OpenCode Go bağlantısı, sağlayıcı anahtarı ve model kataloğu |
| [`docs/execution-plan.md`](docs/execution-plan.md) | Paket paket yürütme planı |
| [`docs/ui-action-map.md`](docs/ui-action-map.md) | Her UI eyleminin çağırdığı rota ve hata davranışı |
| [`docs/browser-qa.md`](docs/browser-qa.md) | Tarayıcı testleri: ne test edilir, ne **edilmez** |
| [`docs/packaging.md`](docs/packaging.md) | Windows paketleme, kurulum/kaldırma, SHA-256 ve **imzasızlık** |
| [`docs/kullanim-kilavuzu.md`](docs/kullanim-kilavuzu.md) | **Kullanım kılavuzu** — dokuz bölüm, kurulum, recovery zorunluluğu, kaldırma |
| [`docs/kullanici-kabul-listesi.md`](docs/kullanici-kabul-listesi.md) | **Kullanıcı kabul listesi** — otomatik testlerin ölçemediği maddeler |
| [`docs/verification/`](docs/verification/) | Paket paket doğrulama raporları; **sayıların tek kaynağı** |
| [`docs/decisions/README.md`](docs/decisions/README.md) | ADR indeksi |

---

## Gereksinimler

| Araç | Sürüm |
|---|---|
| Windows | 10 / 11 |
| Python | 3.12 (`uv` otomatik kurar) |
| [uv](https://docs.astral.sh/uv/) | 0.11+ |
| Node.js | 22+ |

## Kurulum

```bash
uv python install 3.12
```

```bash
uv sync --project apps/station-api
```

```bash
npm --prefix apps/station-web install
```

## Paketlenmiş kurulum (Windows)

Son kullanıcı için hedeflenen biçim bir **ZIP**'tir:
`%LOCALAPPDATA%\Programs\TechnocoreStation\` altına açılır, yönetici hakkı
istemez, yalnız loopback dinler. Ayrıntı, kaldırma talimatı ve SHA-256
doğrulaması: [`docs/packaging.md`](docs/packaging.md).

**Bugün yayımlanmış bir artefakt yoktur.** Paketleyici **PyInstaller**'dır ve
artık bu deponun **kilitli bir geliştirme bağımlılığıdır**
(`apps/station-api/pyproject.toml` `dev` grubunda `pyinstaller==6.16.0`,
`apps/station-api/uv.lock` içinde kilitli — lisans ve gerekçe aşağıdaki
bağımlılık tablosundadır). Çalışma zamanı bağımlılık yüzeyine girmez:
yalnız build zamanı çalışır.

Yani `uv sync --project apps/station-api` yapmış bir makinede ön koşulların
üçü de sağlanmıştır. Build betiği bunu kendisi raporlar:

```bash
uv run --project apps/station-api python packaging/build_bundle.py --check
```

```
[OK  ] spec: ...\packaging\station.spec
[OK  ] frontend-build: ...\apps\station-web\dist
[OK  ] pyinstaller: PyInstaller 6.16.0
```

Arayüz derlenmemişse ikinci satır `[EKSIK]` olur ve betik **2** ile çıkar;
hiçbir şey üretmez.

Kaldırma **yalnız program dizinini** siler. Veri dizini
(`%LOCALAPPDATA%\TechnocoreStation\`) **elle bile olsa dikkatle** silinir:
içinde seed'in DPAPI zarfı, denetim zincirinin anahtarı ve kanıt kayıtları
vardır ve `.tcrec` recovery dosyanız yoksa geri dönüş yoktur.

Artefakt **imzasızdır**. Windows SmartScreen imzasız bir indirmeyi uyarır; bu
beklenen davranıştır. Yayımlanan SHA-256 yalnız dosya bütünlüğünü tanımlar —
içeriğin doğru olduğunu, ve imzasız olduğu için **kimin ürettiğini** de
kanıtlamaz.

## Çalıştırma (kaynaktan)

```bash
npm --prefix apps/station-web run build
```

```bash
uv run --project apps/station-api python -m station_api
```

Launcher önce veri dizini için **tek örnek kilidini** alır (ikinci bir kopya
aynı veritabanını ve aynı denetim zincirini açmaz; ret, silinecek dosyanın
yolunu söyler), sonra `127.0.0.1:0` adresine bind eder, işletim sisteminden
**efemer** bir port alır, bellekte **tek kullanımlık 30 saniyelik** bir açılış
token'ı üretir ve tarayıcıyı açar. Token loglanmaz. Tarayıcı `/session/<token>` adresini bir
kez kullanır, `HttpOnly` + `SameSite=Strict` cookie alır ve temiz `/` adresine
yönlenir.

İlk açılış, kimlik ve recovery zorunluluğu, dokuz bölümün her biri ve
kaldırma: [`docs/kullanim-kilavuzu.md`](docs/kullanim-kilavuzu.md).

### Development

İki terminal gerekir. Backend sabit bir port kullanır ki Vite proxy hedefi
bilinsin (IMP-109):

```bash
set STATION_DEV=1 && uv run --project apps/station-api python -m station_api
```

```bash
npm --prefix apps/station-web run dev
```

`STATION_DEV` **varsayılan olarak kapalıdır ve fail-closed'dur**: yalnız
`1`, `true`, `yes` veya `on` değerleri açar. Production build dev origin'i
**kabul etmez**.

## Mevcut resmî seed'i içe aktarma (yalnız yerel CLI)

Web arayüzünde raw seed alanı **yoktur**. Import yalnız kendi terminalinizde
yapılır; seed ve parola komut satırı argümanı değildir, parolalar `getpass`
ile alınır.

```bash
uv run --project apps/station-api python -m station_api.cli import-seed --file C:\yol\seed.txt
```

Kabul edilen tek biçim: **64 hex karakter** (bare, veya `sign.py keygen`
çıktısındaki `seed: <hex>` satırı). Paroladan seed türetme **desteklenmez**.
Kaynak dosya değiştirilmez veya silinmez.

## Geliştirme komutları

Lint — üç ağacın tamamı, tek komut:

```bash
uv run --project apps/station-api ruff check apps/station-api/src packages/technocore-conform/src tests
```

> **Ruff yapılandırması nereden geliyor?** Ruff, yapılandırmayı çalışma
> dizininden değil **denetlenen dosyadan yukarı yürüyerek** bulur.
> `apps/station-api` ve `packages/technocore-conform` kendi `[tool.ruff]`
> bloklarını taşır; `tests/` hiçbirini taşımıyordu ve bu yüzden ruff'ın
> **varsayılan** kural setiyle denetleniyordu — projenin benimsediği setten
> büyük ölçüde ayrık bir set. Sonuç, benimsenmemiş stil kuralları raporlarken
> (`TRY004`, `FLY002`) burada gerçekten zorunlu olan `S` kurallarını hiç
> çalıştırmamaktı; en açık belirti, gerçek yapılandırmada gerekli olan
> `# noqa: S603` satırlarının "kullanılmayan noqa" diye işaretlenmesiydi.
> Aşama 3.1'de kök dizine [`ruff.toml`](ruff.toml) eklendi ve `tests/` de
> aynı kural setine bağlandı. Bulgular bastırılarak veya dosyalar dışlanarak
> değil, düzeltilerek kapatıldı.
>
> [`AGENTS.md`](AGENTS.md) §4'teki `uv run --directory apps/station-api ruff
> check .` komutu hâlâ geçerlidir, fakat yalnız `apps/station-api` ağacını
> kapsar. Yukarıdaki komut üçünü birden kapsar.

```bash
uv run --project apps/station-api mypy --config-file apps/station-api/pyproject.toml
```

```bash
uv run --project apps/station-api pytest tests
```

```bash
npm --prefix apps/station-web run lint
```

```bash
npm --prefix apps/station-web run test
```

---

## Bağımlılıklar ve gerekçeleri

Bağımlılıklar minimumda tutulur. Her doğrudan bağımlılığın gerekçesi:

### Backend (MIT / BSD / Apache-2.0)

| Paket | Lisans | Gerekçe |
|---|---|---|
| `fastapi` | MIT | Yerel HTTP çekirdeği; Pydantic response modelleriyle secret alanı sızmasını şemada engeller (ADR-006) |
| `uvicorn` | BSD-3 | Hazır bir socket üzerinde tek worker çalıştırabilen ASGI sunucusu — efemer port modelinin ön koşulu |
| `sqlalchemy` | MIT | Tek kullanıcılık SQLite erişimi; `connect` event'i WAL ve foreign-keys PRAGMA'larını her bağlantıda garanti eder (ADR-007) |
| `alembic` | MIT | Deterministik ve idempotent migration zinciri; version tablosu `schema_migrations` olarak adlandırılır |
| `pydantic` | MIT | Response şeması sınırı; `extra="forbid"` ile beklenmeyen alan eklenemez |
| `technocore-conform` | MIT (yerel) | Protokol uygunluk paketi — platformdan bağımsız sınır (ADR-018) |
| `httpx` | BSD-3 | **Aşama 3.** Salt okunur Technocore istemcisi; faz bazlı timeout, redirect kapatma ve streaming (decompress edilmiş bayt üzerinde boyut sınırı) doğrudan desteklenir. Tek giden istek yolunda bunları elle yazmak yerine kütüphaneden almak tercih edildi. |

**Test ve geliştirme:** `pytest`, `hypothesis` (sweep property testleri),
`httpx` (gerçek loopback istemcisi), `pynacl`, `ruff`, `mypy`, `pyinstaller`.

| Paket | Lisans | Gerekçe |
|---|---|---|
| `cryptography` | Apache-2.0 / BSD | Ed25519 imzalama ve doğrulama; recovery için AEAD (Aşama 2) |
| `argon2-cffi` | MIT | Recovery ve kasa parolası KDF'i (Argon2id) (Aşama 2) |
| `pynacl` | Apache-2.0 | **Yalnız test.** AC-05 için bağımsız bir Ed25519 uygulaması (libsodium): imzayı üreten kütüphanenin kendi çıktısını doğrulaması kanıt sayılmaz. Production import grafiğine girmediği testle doğrulanır. |

Künye §11.2 gereği başka kripto kütüphanesi gerekçesiz eklenmez.

### Paketleme (yalnız build zamanı)

| Paket | Lisans | Gerekçe |
|---|---|---|
| `pyinstaller` **6.16.0** | **GPL-2.0-or-later WITH Bootloader-exception** (kurulu paketten okundu: `pyinstaller-6.16.0.dist-info/licenses/COPYING.txt` ve `METADATA`) | **Yalnız build zamanı.** Windows paketini üretir (ADR-0010 §2). Alternatifler ölçülerek elendi: **MSIX** imza zorunlu ve bu makinede kod imzalama sertifikası yok; **`onefile`** her çalıştırmada `%TEMP%\_MEIxxxx`'e açar ve ürünün bugün `%TEMP%`'e hiç yazmama özelliğini bozar; **uv + `.bat`** son kullanıcıya uv ve ağ dayatır; **Tauri** Rust toolchain + WebView2 ister ve ADR-019 ertelemiştir. **Artefaktın çalışma zamanı bağımlılık yüzeyini değiştirmez:** paketleyicinin kendisi bundle'a girmez. Gönderilen exe'de PyInstaller'ın **yalnız** derlenmiş bootloader'ı, `PyInstaller/loader` modülleri (`pyiboot01_bootstrap`, `pyimod01_archive`, `pyimod02_importers`) ve dört run-time hook'u bulunur (bir tane daha `pyinstaller-hooks-contrib`'den gelir); her üç kategori de exe'nin baytlarında ölçüldü. Okunan lisans metni bunu açıkça karşılar: *Bootloader Exception*, derlenmiş bootloader'ı ve ilgili dosyaları başka programlarla birleştirip **o dosyaların kullanımından doğan hiçbir kısıt olmadan** dağıtma izni verir (GPL kısıtları yalnız bu dosyaların **değiştirilmesi** ve birleşik çalıştırılabilire **bağlanmadan** dağıtılması için sürer); run-time hook'lar ise `COPYING.txt`'de ayrıca **Apache-2.0** olarak lisanslanmıştır. Dolayısıyla paketlenen çıktının lisansı etkilenmez ve **kendi kodumuz MIT kalır**. Sürüm `uv.lock` disiplinine uygun olarak **tam pinlidir** (`==`, aralık değil): bir paketleyicinin ürettiği baytlar artefaktın parçasıdır. |

Geçişli olarak `altgraph` (MIT), `pefile` (MIT), `pywin32-ctypes` (BSD-3),
`setuptools` (MIT) ve `pyinstaller-hooks-contrib` (Apache-2.0 / GPL-2.0)
gelir; hepsi aynı şekilde yalnız build zamanı çalışır.

### Frontend (MIT)

| Paket | Gerekçe |
|---|---|
| `react`, `react-dom` | v19 — ADR-005 |
| `@heroui/react`, `@heroui/styles` | HeroUI **v3**, yalnız ücretsiz bileşenler. v2 ve NextUI yasak (INV-07) |
| `tailwindcss`, `@tailwindcss/vite` | HeroUI v3'ün zorunlu koşulu (Tailwind v4) |
| `vite`, `@vitejs/plugin-react` | Build ve dev proxy |
| `typescript`, `typescript-eslint`, `eslint`, `eslint-plugin-react-hooks` | Strict tipler; ESLint tarayıcı depolamasını **kural düzeyinde** yasaklar |
| `vitest`, `jsdom`, `@testing-library/*` | Unit ve smoke testleri |
| `@playwright/test` **1.62.1** (Apache-2.0) | **Yalnız test.** Tarayıcı QA'sı (ADR-0006). jsdom'da **kanıtlanamayan** şeyleri kanıtlar: gerçek odak sırası ve focus trap, gerçek klavye gezinmesi, `URL.createObjectURL` ile indirme yolu ve gerçek `Content-Disposition` gidiş-dönüşü, ve en önemlisi **gerçek CSP başlıkları altında React Aria inline-style hash'i** (risk A1-R1) — jsdom CSP uygulamaz, bu yüzden o riski hiçbir Vitest testi göremezdi. Sürüm `^` olmadan tam pinlidir; indirilen tarayıcı da bu pinden gelir (Chromium **151.0.7922.34**, Playwright revizyon **1234**). Yalnız Chromium kurulur: ürün Windows-only bir yerel uygulamadır (ADR-008, risk A1-R6) ve Firefox + WebKit indirmek hedeflenmeyen iki motor için ~300 MB ve iki motor kadar kararsızlık eklerdi. Production bundle'ına girmez. |

Uzak font, CDN veya harici UI varlığı **yoktur**.

Tarayıcı testleri nasıl çalışır, ne test edilir ve ne **edilmez**:
[`docs/browser-qa.md`](docs/browser-qa.md).

---

## Lisans

- **Kendi kodumuz: MIT** — [`LICENSE`](LICENSE)
- **`vendor/technocore-reference/`: Apache-2.0**, Copyright 2026 FLOP Labs

`vendor/technocore-reference/` dizini
[`flop-labs/technocore-chat`](https://github.com/flop-labs/technocore-chat)
projesinin **pinlenmiş ve değiştirilmemiş** bir kopyasıdır
(commit `7707cb63ebf638e8ef0cf59d1364818b9fef7d24`). Yalnız **test oracle'ı**
olarak kullanılır; uygulama runtime paketine girmez ve Apache-2.0 satırları
MIT kodumuza kopyalanmaz.

Sekiz dosya vendor'lanmıştır. `scripts/sign.py` ve `src/store.py` Aşama 2B'nin
imza ve sweep oracle'ıdır; `src/manifest.py` (+ import ettiği `src/didkey.py`,
`src/config.py` ve sürümü taşıyan `pyproject.toml`) Aşama 3.1'de protokol
projeksiyonunun referans belgelerini **üretmek** için eklendi. Belgeler elle
yazılmaz: `tests/conformance/test_manifest_oracle.py` onları yeniden üretip
bayt bayt karşılaştırır.

Tam lisans haritası: [`NOTICE`](NOTICE).
Provenans ve hash'ler: [`vendor/technocore-reference/PROVENANCE.md`](vendor/technocore-reference/PROVENANCE.md).

---

## Güvenlik özeti

Yalnız `127.0.0.1` + efemer port · CORS yok · exact-Host kontrolü (yanlış Host
**421**) · tek kullanımlık 30 saniyelik açılış token'ı · `HttpOnly` +
`SameSite=Strict` cookie · memory-only CSRF · katı CSP · telemetri yok.

Ürünün **savunmadığı** durumlar ve kanıt dilinin sınırları
[`SECURITY.md`](SECURITY.md) §7 ve
[`docs/evidence-model.md`](docs/evidence-model.md) içinde açıkça yazılıdır.

**Bu depoya gerçek seed, private key veya recovery dosyası koymayın.**
