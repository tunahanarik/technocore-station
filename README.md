# Technocore Station

Kullanıcıya ait bir Ed25519 `did:key` kimliğini güvenli biçimde yöneten,
Technocore'a gönderilecek içeriğin canonical biçimini resmî kurallara göre
üreten, yalnızca açık kullanıcı onayıyla imzalayıp gönderen ve sunucunun
geçici kayıtlarını yerelde yeniden doğrulanabilir biçimde saklayan
**local-first Windows uygulaması**.

> Technocore imzayı doğrular; Station canonical metni, alınan kaydı ve
> kaynağı doğrular.

**Durum: Aşama 3 — Salt okunur Technocore tamamlandı.** Kimlik, recovery ve
protokol uygunluk motoru çalışıyor; Station artık resmî kaynakları **yalnız
okuyarak** protokol sürüklenmesini tespit ediyor. Mesaj yazma, imzalama ve
Evidence özellikleri **henüz yoktur** — gönderim yolu Aşama 4'te açılır.

Uygunluk ile güncellik ayrı şeylerdir: uygunluk self-test'i bu yapının
**pinlenmiş referans commit** ile aynı davrandığını gösterir; salt okunur
denetim ise **canlı sunucunun** hâlâ o protokolü yayımladığını gösterir. İkisi
de geçmeden dış yazma kapısı açılmaz. Güncel durum:
[`PROJECT_STATUS.md`](PROJECT_STATUS.md).

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
| [`docs/security-invariants.md`](docs/security-invariants.md) | Test edilebilir değişmezler (SI-01…SI-56) |
| [`docs/evidence-model.md`](docs/evidence-model.md) | Dört seviyeli kanıt modeli |
| [`docs/identity-lifecycle.md`](docs/identity-lifecycle.md) | Kimlik durum makinesi ve akışlar |
| [`docs/recovery-format-v1.md`](docs/recovery-format-v1.md) | `.tcrec` biçimi ve AAD sözleşmesi |
| [`docs/threat-model.md`](docs/threat-model.md) | Savunulan ve **savunulmayan** tehditler |
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

## Çalıştırma

```bash
npm --prefix apps/station-web run build
```

```bash
uv run --project apps/station-api python -m station_api
```

Launcher `127.0.0.1:0` adresine bind eder, işletim sisteminden **efemer** bir
port alır, bellekte **tek kullanımlık 30 saniyelik** bir açılış token'ı üretir
ve tarayıcıyı açar. Token loglanmaz. Tarayıcı `/session/<token>` adresini bir
kez kullanır, `HttpOnly` + `SameSite=Strict` cookie alır ve temiz `/` adresine
yönlenir.

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
`httpx` (gerçek loopback istemcisi), `pynacl`, `ruff`, `mypy`.

| Paket | Lisans | Gerekçe |
|---|---|---|
| `cryptography` | Apache-2.0 / BSD | Ed25519 imzalama ve doğrulama; recovery için AEAD (Aşama 2) |
| `argon2-cffi` | MIT | Recovery ve kasa parolası KDF'i (Argon2id) (Aşama 2) |
| `pynacl` | Apache-2.0 | **Yalnız test.** AC-05 için bağımsız bir Ed25519 uygulaması (libsodium): imzayı üreten kütüphanenin kendi çıktısını doğrulaması kanıt sayılmaz. Production import grafiğine girmediği testle doğrulanır. |

Künye §11.2 gereği başka kripto kütüphanesi gerekçesiz eklenmez.

### Frontend (MIT)

| Paket | Gerekçe |
|---|---|
| `react`, `react-dom` | v19 — ADR-005 |
| `@heroui/react`, `@heroui/styles` | HeroUI **v3**, yalnız ücretsiz bileşenler. v2 ve NextUI yasak (INV-07) |
| `tailwindcss`, `@tailwindcss/vite` | HeroUI v3'ün zorunlu koşulu (Tailwind v4) |
| `vite`, `@vitejs/plugin-react` | Build ve dev proxy |
| `typescript`, `typescript-eslint`, `eslint`, `eslint-plugin-react-hooks` | Strict tipler; ESLint tarayıcı depolamasını **kural düzeyinde** yasaklar |
| `vitest`, `jsdom`, `@testing-library/*` | Unit ve smoke testleri |

Uzak font, CDN veya harici UI varlığı **yoktur**.

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
