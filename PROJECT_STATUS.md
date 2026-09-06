# PROJECT_STATUS

> Ana karar kaynağı: [`Technocore-Station-Proje-Kunyesi.md`](Technocore-Station-Proje-Kunyesi.md)
> Çalışma kuralları: [`AGENTS.md`](AGENTS.md) · [`CLAUDE.md`](CLAUDE.md)
> Son güncelleme: **6 Eylül 2026** (Paket H4 — model plan yolu ve makinece
> denetlenen kabul koşulları; ADR-0012 sözleşmeyi ölçtü, `tool_calls_supported`
> `True` oldu ve `ready_to_publish` kanıttan türeyerek erişilebilir hâle geldi.
> Ardından bir temizlik turu: ölü sabitler kaldırıldı ve model yolu açılınca
> yanlışa düşen cümleler düzeltildi.)
>
> **Proje durumu: REVIEW_FIXES_IN_PROGRESS_CORE_AGENT_INCOMPLETE** — dosyanın sonuna
> bakın.

## Aşama checklist

Bu liste **aşama 7'de bitiyordu** ve son beş aşamayı hiç saymıyordu; üstelik
"Aşama 7 — Packaging" diyordu, oysa aşama 7 OpenCode bağlantısıdır ve
paketleme **aşama 11**'dir. Liste gövdedeki başlıklara göre düzeltildi ve
her satır kendi doğrulama raporuna bağlandı — ayrıntı raporlarda, sayım
burada.

| Aşama | Konu | Paket | Doğrulama raporu |
|---|---|---|---|
| 0 | Spesifikasyon | — | — |
| 1 | Güvenli iskelet | — | — |
| 2 | Identity & Recovery | — | — |
| 2B | Conformance | — | — |
| 3 | Salt okunur Technocore | — | — |
| 3.1 | Protokol projeksiyonu düzeltmesi | B | [`paket-b`](docs/verification/paket-b.md) |
| — | Başlangıç, kapsam eki, tekrarlanabilir CI | A | [`paket-a`](docs/verification/paket-a.md) |
| — | Dashboard kabuğu ve hata sözleşmesi | C | [`paket-c`](docs/verification/paket-c.md) |
| 4 | Composer & Participation | D | [`paket-d`](docs/verification/paket-d.md) |
| 5 | Evidence & Audit | E | [`paket-e`](docs/verification/paket-e.md) |
| 6 | Project Modules (temel; görünür yüzey H1/H2) | F | [`paket-f`](docs/verification/paket-f.md) |
| 7 | OpenCode Go bağlantısı | G | [`paket-g`](docs/verification/paket-g.md) |
| 8 | Work Scan | H1 | [`paket-h1`](docs/verification/paket-h1.md) |
| 9 | Agent çalışma ortamı ve Activity Desk | H2 | [`paket-h2`](docs/verification/paket-h2.md) |
| 10 | Kanıt çalışma alanı | H3 | [`paket-h3`](docs/verification/paket-h3.md) |
| 11 | Windows paketleme — artefakt **üretildi ve çalıştırıldı**; imzasız (ADR-0010 §9) | I | [`paket-i`](docs/verification/paket-i.md) |
| 12 | Bütünleşik inceleme ve temizlik (yeni yetenek yok) | J | [`paket-j`](docs/verification/paket-j.md) |
| — | Model plan yolu ve makinece denetlenen kabul koşulları | H4 | [`paket-h4`](docs/verification/paket-h4.md) |
| — | Bağımsız inceleme düzeltmesi (F1–F5) | — | [`review-fixes`](docs/verification/review-fixes.md) |

Hepsi tamamlandı. **Bekleyen tek şey kullanıcı kabulüdür**
([`kullanici-kabul-listesi.md`](docs/kullanici-kabul-listesi.md)); insan
güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5). PyInstaller
kilitli bir **geliştirme** bağımlılığıdır ve artefaktın içine girmez.

---

## Aşama 0 — Tamamlanan görevler

### Belgeler
- [x] `AGENTS.md` — 9 değişmez kural (INV-01…INV-09) + çalışma kuralları
- [x] `CLAUDE.md` — aynı değişmezler + Claude Code'a özgü notlar
- [x] `PROJECT_STATUS.md` — bu dosya
- [x] `SECURITY.md` — güvenlik duruşu, oturum modeli, **dürüst kalan riskler**
- [x] `docs/architecture.md` — mimari, paket sınırları, middleware zinciri
- [x] `docs/protocol-contract.md` — canonical/sweep/imza sözleşmesi (Aşama 2B+ hedefi)
- [x] `docs/security-invariants.md` — **SI-01…SI-56**, her biri bir teste bağlı
- [x] `docs/evidence-model.md` — dört güven seviyesi + yasak ifadeler
- [x] `docs/decisions/README.md` — ADR indeksi + Aşama 1 kararları (IMP-101…IMP-110)

### Resmî referans pinleme
- [x] Kaynak: `https://github.com/flop-labs/technocore-chat`
- [x] Pinlenmiş commit: **`7707cb63ebf638e8ef0cf59d1364818b9fef7d24`** (2026-08-30T11:04:44Z)
- [x] `vendor/technocore-reference/` — `scripts/sign.py`, `src/store.py`, `LICENSE`, `NOTICE`
- [x] `PROVENANCE.md` — repo URL, commit SHA, alınma tarihi, dosya hash'leri
- [x] `SHA256SUMS` — makine-okunabilir, testle doğrulanıyor
- [x] Dosyalar **değiştirilmedi** (hash testi bunu kanıtlıyor)
- [x] Kök `LICENSE` MIT; kök `NOTICE` lisans haritasında vendor dizini **Apache-2.0**
- [x] Vendor kodu runtime paketine **girmiyor** (AST tabanlı test)

---

## Aşama 1 — Tamamlanan görevler

### Monorepo
- [x] `apps/station-web/`, `apps/station-api/`, `packages/technocore-conform/`
- [x] `tests/{security,integration,conformance}/`, `vendor/`, `docs/`
- [x] `technocore-conform` **yalnız paket sınırı + placeholder** (sweep/DID/imza kodu yok)
- [x] Paket sınırı gerçek: `station-api` → `technocore-conform` path bağımlılığı; ters yön yok

### Güvenli launcher ve oturum
- [x] `127.0.0.1:0` socket bind → işletim sisteminden efemer port
- [x] Aynı socket uvicorn'a veriliyor (tek worker)
- [x] Bellekte 256-bit tek kullanımlık açılış token'ı
- [x] Token **30 saniye** geçerli, ilk kullanımda iptal
- [x] `webbrowser.open(/session/<token>)`; **token loglanmıyor** (`access_log=False` + redaksiyon filtresi)
- [x] `HttpOnly` + `SameSite=Strict` + `Path=/` cookie, ardından temiz `/` redirect (303)
- [x] Session ve token **tamamen process memory**'de

### Aynı-origin güvenliği
- [x] Production'da FastAPI, build edilmiş SPA'yı aynı origin'den servis ediyor
- [x] Vite yalnız `127.0.0.1`; `/api` ve `/session` proxy (`changeOrigin: true`)
- [x] `STATION_DEV` **varsayılan kapalı ve fail-closed** (yalnız `1/true/yes/on` açar)
- [x] **CORS middleware yok** (kaynak taraması + response taraması ile doğrulandı)
- [x] Host tam `127.0.0.1:<port>`; `localhost` ve yabancı Host → **421**
- [x] Yanlış `Origin` → 403; `Sec-Fetch-Site: cross-site` → 403
- [x] `Sec-Fetch-Site: none` yalnız güvenli navigasyonda (launcher sekmesi için)
- [x] CSRF: session'a özel değer, `GET /api/session/bootstrap`, `X-Station-CSRF`, `compare_digest`
- [x] Frontend CSRF'i **yalnız memory**'de tutuyor; localStorage/sessionStorage/IndexedDB **hiç kullanılmıyor** (ESLint kuralı + test)

### Güvenlik başlıkları
- [x] Katı CSP: `default-src 'none'`, `script-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'none'`, `form-action 'none'`
- [x] `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`
- [x] `Permissions-Policy` — 19 tarayıcı yeteneği kapalı
- [x] `Cross-Origin-Opener-Policy` / `Cross-Origin-Resource-Policy: same-origin`
- [x] Session/bootstrap/API yanıtlarında `Cache-Control: no-store`
- [x] Hata yanıtları (401/403/421) da tüm başlıkları taşıyor
- [x] **Google Fonts / CDN / uzaktan varlık yok** (sistem fontları)

### SQLite iskeleti
- [x] Windows veri dizini `%LOCALAPPDATA%\TechnocoreStation\`; testler geçici dizin
- [x] Yalnız altyapı tabloları: **`schema_migrations`** + **`app_metadata`**
- [x] WAL aktif, `foreign_keys` aktif (her bağlantıda, `connect` event'inde)
- [x] Alembic; version tablosu `schema_migrations` olarak adlandırıldı (IMP-102)
- [x] Migration sırası deterministik (tek head, lineer zincir), `upgrade head` idempotent
- [x] Seed/secret sütunu yok; **veritabanı yolu frontend'e dönmüyor**

### HeroUI v3 dashboard kabuğu
- [x] HeroUI **v3.2.4** (MCP'den doğrulanmış ücretsiz bileşenler: Tabs, Card, Chip, Alert, Separator, Button)
- [x] MVP navigasyonu **yalnız üç yüzey**: Identity, Compose & Verify, Evidence & Sources
- [x] Üst sistem durum alanı: Yerel servis / Veritabanı / Oturum güvenliği / Technocore
- [x] Technocore: **"Bağlı değil — Aşama 3"**
- [x] Identity: "Kimlik oluşturulmadı" · Compose: **kilitli** · Evidence: boş durum
- [x] **Sidebar yok, Pro template yok, grafik yok**
- [x] **Secret input / private key alanı yok** (test: 0 input, 0 textarea)
- [x] **Sahte DID gösterilmiyor** (test: `did:key:z` yok)
- [x] Backend portu frontend'de **hardcoded değil** (yalnız göreli URL)
- [x] Haricî link / untrusted içerik render edilmiyor
- [x] Dark/light tema erişilebilir; **durumlar yalnız renkle anlatılmıyor** (glyph + metin + sr-only)

### İlk API yüzeyi
| Method | Yol | Koruma |
|---|---|---|
| GET | `/api/health` | public, minimum bilgi |
| GET | `/session/{token}` | tek kullanımlık token |
| GET | `/api/session/bootstrap` | cookie, `no-store` |
| GET | `/api/app/status` | cookie |

**Oluşturulmadı (bilinçli):** identity, seed/recovery, signing, Technocore write
endpoint'i, gerçek Technocore network client'ı. CSRF probe uygulaması **yalnız
testlerde** kuruluyor (IMP-108). OpenAPI şeması HTTP üzerinden servis edilmiyor
(`openapi_url=None`).

---

## Oluşturulan ana dosyalar

```text
AGENTS.md · CLAUDE.md · PROJECT_STATUS.md · SECURITY.md · README.md
LICENSE (MIT) · NOTICE (lisans haritası) · .gitignore · pytest.ini

docs/architecture.md · protocol-contract.md · security-invariants.md
docs/evidence-model.md · decisions/README.md

vendor/technocore-reference/{PROVENANCE.md, SHA256SUMS, LICENSE, NOTICE,
                             scripts/sign.py, src/store.py}

apps/station-api/pyproject.toml · alembic.ini · uv.lock · README.md
apps/station-api/src/station_api/
    config.py · launcher.py · app.py · __main__.py · schemas.py
    dependencies.py · logging_setup.py · py.typed
    security/{tokens,sessions,middleware}.py
    db/{engine,models,migrations_runner}.py
    db/migrations/{env.py, script.py.mako, versions/0001_initial_schema.py}
    routes/{session,api}.py

packages/technocore-conform/{pyproject.toml, README.md,
    src/technocore_conform/{__init__.py, py.typed}}

apps/station-web/{package.json, vite.config.ts, eslint.config.js, index.html,
                  tsconfig*.json}
apps/station-web/src/
    main.tsx · App.tsx · theme.ts · styles.css · vite-env.d.ts
    api/{client.ts, types.ts}
    components/{AppShell,SystemStatusBar,StatusPill,ThemeToggle,EmptyState}.tsx
    pages/{IdentityPage,ComposeVerifyPage,EvidencePage}.tsx
    test/setup.ts · App.test.tsx · api/client.test.ts · pages/pages.test.tsx

tests/conftest.py
tests/security/{conftest,test_bind,test_session,test_host_origin,test_csrf,
                test_headers,test_logging,test_database,test_no_secret_fields,
                test_frontend_bundle}.py
tests/integration/test_live_server.py
tests/conformance/test_vendor_integrity.py
```

---

## Kullanılan bağımlılık sürümleri

### Backend (Python 3.12.11, uv 0.11.26, `uv.lock` kilitli)
| Paket | Sürüm |
|---|---|
| fastapi | 0.141.1 |
| starlette | 1.6.0 |
| uvicorn | 0.52.4 |
| sqlalchemy | 2.0.52 |
| alembic | 1.19.1 |
| pydantic | 2.13.5 |
| pytest | 9.1.1 |
| hypothesis | 6.167.0 |
| httpx | 0.28.1 |
| ruff | 0.16.5 |
| mypy | 2.3.1 |

### Frontend (Node 22.14.0, npm 11.14.1, `package-lock.json` kilitli)
| Paket | Sürüm |
|---|---|
| react / react-dom | 19.2.8 |
| @heroui/react | **3.2.4** |
| @heroui/styles | **3.2.4** |
| tailwindcss | 4.3.3 |
| @tailwindcss/vite | 4.3.3 |
| vite | 7.3.6 |
| @vitejs/plugin-react | 5.2.0 |
| typescript | 5.9.3 |
| typescript-eslint | 8.68.0 |
| eslint | 9.39.5 |
| vitest | 3.2.7 |
| jsdom | 26.1.0 |
| @testing-library/react | 16.3.3 |
| @testing-library/jest-dom | 6.9.1 |

---

## Çalıştırılan komutlar ve test sonuçları

| Komut | Sonuç |
|---|---|
| `uv python install 3.12` | Python **3.12.11** kuruldu |
| `uv sync --project apps/station-api` | 37 paket, `uv.lock` üretildi |
| `npm --prefix apps/station-web install` | 330 paket |
| `ruff check apps/station-api/src packages/technocore-conform/src tests` | **All checks passed** |
| `mypy --config-file apps/station-api/pyproject.toml` | **Success: no issues found in 23 source files** (strict) |
| `pytest tests` | **121 passed** |
| `npm run lint` | **0 hata** |
| `npx tsc -b` (strict) | **0 hata** |
| `npm run test` | **20 passed** (3 dosya) |
| `npm run build` | **Başarılı** — `index.html` 0.79 kB, CSS 405.45 kB, JS 365.89 kB |
| `npm audit` | **found 0 vulnerabilities** |
| `uv lock --check` | Lock güncel |

### Test dağılımı (toplam **141**)
| Katman | Adet |
|---|---:|
| `tests/security/` | 106 |
| `tests/integration/` | 6 |
| `tests/conformance/` | 9 |
| Frontend (vitest) | 20 |

### Zorunlu 20 güvenlik testi — durum
| # | Gereksinim | Test | Durum |
|---:|---|---|:--:|
| 1 | Yalnız `127.0.0.1` bind | `test_bind.py::test_launcher_binds_only_loopback` | ✅ |
| 2 | Port gerçekten efemer | `test_bind.py::test_port_is_ephemeral` | ✅ |
| 3 | Token tek kullanımlık | `test_session.py::test_bootstrap_token_is_single_use` | ✅ |
| 4 | Token 30 sn sonra geçersiz | `test_session.py::test_bootstrap_token_expires_after_30_seconds` | ✅ |
| 5 | Token loglarda yok | `test_logging.py::test_bootstrap_token_never_appears_in_logs` | ✅ |
| 6 | Cookie'siz korumalı endpoint 401 | `test_session.py::test_protected_endpoint_without_cookie_is_401` | ✅ |
| 7 | `Host: localhost:<port>` reddediliyor | `test_host_origin.py::test_localhost_host_rejected` | ✅ |
| 8 | Yabancı Host 421 | `test_host_origin.py::test_foreign_host_rejected_with_421` | ✅ |
| 9 | Yanlış Origin reddediliyor | `test_host_origin.py::test_foreign_origin_rejected` | ✅ |
| 10 | `Sec-Fetch-Site: cross-site` reddediliyor | `test_host_origin.py::test_cross_site_fetch_metadata_rejected` | ✅ |
| 11 | CSRF başlığı yoksa 403 | `test_csrf.py::test_state_change_without_csrf_header_is_403` | ✅ |
| 12 | Yanlış CSRF 403 | `test_csrf.py::test_state_change_with_wrong_csrf_is_403` | ✅ |
| 13 | CORS response header'ı yok | `test_headers.py::test_no_cors_headers_in_any_response` | ✅ |
| 14 | Production'da dev origin reddediliyor | `test_host_origin.py::test_dev_origin_rejected_in_production_mode` | ✅ |
| 15 | SQLite WAL + foreign keys | `test_database.py::test_wal_journal_mode_enabled` / `test_foreign_keys_enabled` | ✅ |
| 16 | Migration 2. kez hatasız | `test_database.py::test_migrations_are_idempotent` | ✅ |
| 17 | Şemada seed/private/secret/mnemonic yok | `test_no_secret_fields.py::test_openapi_schema_has_no_secret_field_names` | ✅ |
| 18 | Bundle'da hardcoded port yok | `test_frontend_bundle.py::test_no_hardcoded_backend_port_in_bundle` | ✅ |
| 19 | Frontend production build başarılı | `test_frontend_bundle.py::test_production_build_output_exists` | ✅ |
| 20 | HeroUI v2/NextUI bağımlılığı yok | `test_frontend_bundle.py::test_no_heroui_v2_or_nextui_dependency` | ✅ |

**Gerçek Technocore'a network isteği atan test yoktur.**

### Tarayıcı doğrulaması
Uygulama gerçek bir tarayıcıda açıldı; üç yüzey, tema değişimi ve mobil
yerleşim denetlendi. **Konsol temiz** (CSP ihlali ve Permissions-Policy
uyarısı yok). Bu denetim iki gerçek kusuru ortaya çıkardı; ikisi de
düzeltildi:

1. **CSP ihlali.** React Aria çalışma zamanında tek bir inline `<style>`
   *elemanı* enjekte ediyor (`[data-react-aria-pressable] { touch-action: … }`).
   `style-src-attr` yalnız inline `style` **attribute**'unu kapsadığı için bu
   eleman bloklanıyordu ve dokunmatik davranış bozulurdu. `'unsafe-inline'`
   açmak yerine **tam hash** ile izin verildi
   (`REACT_ARIA_PRESSABLE_STYLE_HASH`).
2. **Geçersiz Permissions-Policy özelliği.** `ambient-light-sensor` tarayıcı
   tarafından tanınmıyordu ve uyarı üretiyordu; listeden çıkarıldı.

---

## Açık riskler ve blocker'lar

**Blocker yok.** Resmî kaynağa erişildi, commit pinlendi, tüm testler yeşil.

| ID | Risk | Durum / yanıt |
|---|---|---|
| A1-R1 | **CSP hash kırılganlığı.** HeroUI/React Aria yükseltmesi `REACT_ARIA_PRESSABLE_STYLE_HASH` değerini geçersizleştirebilir. | Fail-closed ve gürültülü: stil bloklanır, konsol yeni hash'i söyler. Yükseltme sonrası tarayıcı denetimi zorunlu. `test_react_aria_inline_stylesheet_is_allowed_by_hash` hash'i pinliyor. |
| A1-R2 | **Development'ta sabit port.** Vite proxy hedefi bilinmek zorunda olduğu için dev'de backend `STATION_DEV_PORT` (8787) kullanıyor. | Production yolu efemer kalıyor ve test ediliyor. `STATION_DEV` fail-closed. |
| A1-R3 | **Cookie'de `Secure` yok.** Loopback HTTP üzerinde tarayıcılar tutarsız davranıyor. | Bilinçli karar (IMP-103). `SECURITY.md` §3'te açıkça yazılı; test bunu doğruluyor. Koruma HttpOnly + SameSite=Strict + exact-Host + CSRF'ten geliyor. |
| A1-R4 | **`style-src-attr 'unsafe-inline'`.** React Aria konumlandırma için gerekli. | Yalnız *attribute* düzeyinde; inline `<style>` elemanı ve tüm script'ler yasak. `script-src 'self'` hiç gevşetilmedi. |
| A1-R5 | **Güvenlik testleri teknik olarak değiştirilebilir.** Bir agent dosyayı düzenleyebilir. | Künye §22 bunu kabul ediyor: test tabanı yardımcı kontrol, **insan review'u zorunlu**. |
| A1-R6 | **Yalnız Windows hedefleniyor.** POSIX yolu sadece test taşınabilirliği için var. | ADR-008 gereği; desteklenen hedef Windows. |
| A1-R7 | Aşama 2B öncesi `technocore-conform` boş. | Bilinçli; Compose & Verify yüzeyi bu yüzden **kilitli**. |

---

## Aşama 2 — Tamamlanan görevler

Dal: `stage-2-identity-recovery` (commit atılmadı).

### DID uygunluğu (AC-01)
- [x] `technocore-conform` içinde seed → public key → `did:key` ve **ters** çözümleme
- [x] Bağımsız uygulama; resmî implementation satırı kopyalanmadı
- [x] **7 TEST-ONLY seed** ile pinlenmiş `scripts/sign.py` oracle'ına karşı
      subprocess diferansiyel testi — hepsi **karakter karakter aynı**
      (all-zero ve all-`0xff` kenar durumları dâhil)
- [x] Public key tam 32 bayt; multibase tam 48 karakter, `z6Mk` başlıklı
- [x] Geçersiz uzunluk, prefix, alfabe dışı karakter ve **canonical olmayan**
      kodlama fail-closed reddedilir
- [x] Sweep/canonical/sign/verify **yazılmadı** (Aşama 2B)

### DPAPI vault
- [x] **Current-user** kapsam; `CRYPTPROTECT_LOCAL_MACHINE` hiç kullanılmaz (testle doğrulandı)
- [x] Kasa `%LOCALAPPDATA%\TechnocoreStation\vault\v1\<identity_id>.vault.json`;
      repo ve OneDrive dışında, sürümlü dizin
- [x] Dosya adı uygulama üretimi 32-hex id'den; yol HTTP girdisinden türetilmez
- [x] **Atomik yazma**: temp dosya → ACL → `os.replace` → ACL; artık `.tmp` kalmaz
- [x] **Windows API ile ACL** (`icacls` yok): `D:P(A;;FA;;;SY)(A;;FA;;;<user-sid>)`;
      geri okunup doğrulanır, uygulanamazsa **fail-closed**
- [x] Sürümlü, strict parse edilen envelope (bilinmeyen alan reddedilir)
- [x] Açılışta DPAPI + AEAD self-test
- [x] Production'da **fake/in-memory vault yok**; non-Windows fail-closed
- [x] Modlar: `dpapi`, `dpapi+passphrase` (varsayılan ve önerilen)

### Recovery `.tcrec` v1
- [x] Argon2id **64 MiB / 3 iterasyon / p=1 / 32 bayt**, ChaCha20-Poly1305
- [x] Dosya başına yeni 16 baytlık salt ve 12 baytlık nonce
- [x] Aynı seed + aynı parola → **byte olarak farklı** dosyalar
- [x] `ciphertext` hariç tüm header alanları **AAD**; byte-exact test vektörü
- [x] Duplicate key, oversize (64 KiB), aşırı/düşük KDF maliyeti, unsupported
      version/algorithm, padding'li ve non-canonical base64url **reddedilir**
- [x] Untrusted KDF parametreleri **türetmeden önce** doğrulanır
- [x] Yanlış parola, ciphertext tamperi ve header tamperi **aynı** dış hata
      sözleşmesini kullanır (zamanlama eşitliği **iddia edilmez**)
- [x] `docs/recovery-format-v1.md` yazıldı

### Akışlar
- [x] Kimlik oluşturma: koruma seçimi, risk onayı, çift parola, tam
      `KİMLİK OLUŞTUR` onay metni; sonuç `recovery_pending`
- [x] Recovery export: ayrı eylem, `attachment` + `no-store`, DB'ye yalnız
      SHA-256 ve KDF metadata
- [x] Restore-test: yalnız şifreli dosya + parola; kasaya dokunmaz;
      başarısızlıkta **hiçbir şey değişmez**; başarıda `ready`
- [x] Temiz profilden kurtarma: inspect → onay → yeni koruma → kurulum
- [x] CLI seed import: yalnız resmî 64-hex biçim, `getpass`, tam onay,
      aktif kimlik varsa ret, kaynak dosya değiştirilmez
- [x] Revoke: tam DID yazımı, kasa silme, "güvenli silme değildir" uyarısı

### Write gate (AC-12)
- [x] Merkezî `WriteGate`; override/env/bypass **yok**
- [x] Kimlik yok / recovery bekliyor / kasa yok / revoked → **kapalı**
- [x] Başarılı restore-test sonrası `identity_ready = true`, fakat
      `allowed = false` — conformance ve manifest `not_implemented`
- [x] Repoda hiçbir Technocore write yolu veya giden HTTP istemcisi yok
      *(Aşama 2 durumu. Aşama 3 tek bir salt-okunur istemci ekledi; write
      yolu hâlâ yok ve bunu bir test doğruluyor.)*

### Veri modeli
- [x] `Identity`, `SecretMetadata`, `RecoveryRecord` (migration `0002`)
- [x] Tek aktif kimlik, nullable UNIQUE `active_slot` ile **şemada** zorlanır
- [x] Hiçbir tabloda seed, private key, parola veya ciphertext yok
- [x] Dosya sistemi/DB hatalarında iki yönlü rollback

### UI
- [x] Identity sekmesi gerçek state machine ile çalışıyor
- [x] Public DID ve fingerprint kopyalanabilir; **seed gösterimi/kopyalaması yok**
- [x] Raw seed textbox'ı yok; parolalar yalnız local state, dialog kapanınca temizlenir
- [x] Compose & Verify **gerçek write gate**'i okuyor ve kilitli kalıyor
- [x] Üç sekme korundu; LLM/Lobby sekmesi eklenmedi

---

## Aşama 2 — Ek bağımlılıklar

| Paket | Sürüm | Gerekçe |
|---|---|---|
| cryptography | 46.0.7 | Ed25519 ve ChaCha20-Poly1305 |
| argon2-cffi | 25.1.0 | Recovery ve vault KDF |
| python-multipart | 0.0.32 | Şifreli `.tcrec` yüklemesi (multipart) |
| @testing-library/user-event | 14.x | Dialog ve klavye akışı testleri |

---

## Aşama 2 — Test sonuçları

| Kapı | Sonuç |
|---|---|
| `ruff check` | **All checks passed** |
| `mypy --strict` | **Success: no issues found in 41 source files** |
| `pytest tests` | **222 passed** |
| ESLint | **0 hata** |
| `tsc -b` | **0 hata** |
| vitest | **28 passed** |
| production build | **başarılı** (JS 437.93 kB, CSS 405.89 kB) |
| `npm audit` | **0 vulnerabilities** |
| `uv lock --check` | güncel |
| vendor SHA256 | **4/4 OK** |
| secret taraması | temiz |
| Windows DPAPI integration | **gerçek DPAPI ile çalıştırıldı ve geçti** |

### Dağılım (toplam **250**)
| Katman | Adet |
|---|---:|
| `tests/security/` | 173 |
| `tests/integration/` | 15 |
| `tests/conformance/` | 34 |
| Frontend (vitest) | 28 |

### Kabul kriteri eşlemesi
| AC | Kriter | Kanıt |
|---|---|---|
| **AC-01** | DID resmî script ile karakter karakter aynı | `test_did_differential.py::test_did_matches_official_reference` (7 seed) |
| **AC-06** | Seed hiçbir response, log veya bundle'da görünmez | `test_seed_leakage.py` (canary seed; HTTP, OpenAPI, SQLite, kasa, log, exception, bundle) |
| **AC-10** | Recovery round-trip temiz profilde aynı DID | `test_identity_flow.py::test_clean_profile_recovers_the_same_did` |
| **AC-11** | Yanlış parola ve kurcalanmış dosya aynı güvenli hata | `test_identity_flow.py::test_wrong_passphrase_and_tamper_share_one_response` |
| **AC-12** | Restore-test olmadan write çalışmaz | `test_write_gate.py` + `test_identity_lifecycle_over_http` |

---

## Aşama 2 — Açık riskler

| ID | Risk | Durum |
|---|---|---|
| A2-R1 | **Farklı Windows hesabında test edilmedi.** Temiz profil testi aynı hesap içinde bağımsız veri kökü kullanır. | Dürüstçe beyan edildi; ikinci hesap testi manuel bir adımdır |
| A2-R2 | Zamanlama eşitliği iddia edilmiyor | Tek dış hata sözleşmesi var; yan kanal kapatılmadı |
| A2-R3 | Python belleği güvenilir sıfırlanamaz | En-iyi-çaba scrub; belgelendi |
| A2-R4 | DPAPI aynı kullanıcı malware'ine karşı mutlak değil | `dpapi+passphrase` azaltır; `threat-model.md` §2.1 |
| A2-R5 | `.tcrec` güvenliği parola gücüne bağlı | UI ve belge açıkça söylüyor |
| A2-R6 | Argon2 64 MiB, HTTP testlerini yavaşlatır | Kabul edildi; production politikası düşürülmedi |

---

## Aşama 2B — Tamamlanan görevler

> Ayrıntılı sözleşme: [`docs/conformance.md`](docs/conformance.md).
> Dal: `stage-2b-conformance`. Bu turda commit/push/PR **yapılmadı**.

### `technocore-conform` protokol yüzeyi

- [x] `sweep.py` — Cc/Cf/Cs/Co/Zl/Zp → tek boşluk, sonra `str.strip()`
- [x] **Collapse yok, normalization yok, case folding yok** (property testli)
- [x] Uzunluk sweep sonrası code point ile ölçülür; mesaj 4096, note 8192
- [x] `SweepPolicy` + ayrı `sweep_message` / `sweep_note_value` yüzeyleri
- [x] `names.py` — `[a-z0-9][a-z0-9_-]{0,47}`, `fullmatch`
- [x] `nonce.py` — `[0-9]{1,19}`, Unicode rakam reddi, **leading zero korunur**
- [x] `canonical.py` — immutable `CanonicalPayload`; `repr` içerik değil uzunluk yazar
- [x] `signature.py` — Ed25519, 64 bayt, 86 karakter unpadded base64url, son karakter `[AQgw]`
- [x] `selftest.py` — fail-closed runtime self-test, digest pinli vektör paketi
- [x] `cli.py` — `sweep` / `canonical` / `verify` / `self-test` / `version`
- [x] `did.py` **korundu**; Aşama 2 DID API'si kırılmadı
- [x] Paket bağımsız build ediliyor (wheel + sdist, `py3-none-any`)
- [x] Tek runtime bağımlılığı `cryptography`; vendor dizini artefaktlara girmiyor

### Oracle ve vektörler

- [x] Sweep oracle'ı pinlenmiş `store.py`'nin **AST'sinden** izole edilip çalıştırılıyor
- [x] İmza oracle'ı pinlenmiş `scripts/sign.py` subprocess'i
- [x] Her iki oracle da kullanılmadan önce vendor SHA-256'larını doğruluyor
- [x] Vektör paketi oracle'dan **türetiliyor**; test her koşuda bayt-eşitliğini doğruluyor
- [x] Vektör seed'leri, `test_seed_leakage.py` canary'sinden **farklı** (canary anlamlı kalıyor)

### Write gate ve API

- [x] `conformance_verified` artık **gerçek** self-test sonucuna bağlı
- [x] `manifest_current` hâlâ `not_implemented` (Aşama 3)
- [x] `WriteGateInput.conformance_verified` varsayılanı `False` — unutan çağıran kapalı kapı alır
- [x] Başarılı self-test kapıyı **açmıyor**; dış yazma yolu yok
- [x] `GET /api/conformance/status` — session korumalı, salt okunur, `no-store`
- [x] Yanıt yalnız public metadata; vektör içeriği ve seed serialize edilmiyor
- [x] Gate ile status endpoint'i **aynı** verdict nesnesini okuyor

### UI

- [x] Üç sekme korundu; genel tasarım değiştirilmedi
- [x] Identity → "Teknik ayrıntılar" altında uygunluk paneli
- [x] `Aşama 2B · Hazır` durumu, 7 capability + vektör sayıları
- [x] Kısa pinlenmiş SHA (`7707cb6`), kısaltılmış bundle digest (`688c6e4dcf14`)
- [x] Python/Unicode sürümleri yalnız "Teknik ayrıntılar" altında
- [x] **Tam digest DOM'a girmiyor** (64-hex kuralı korunuyor)
- [x] Compose & Verify kilitli; textarea/buton yok
- [x] "Uygunluk ile güncellik aynı şey değildir" uyarısı eklendi

---

## Aşama 2B — Test sonuçları

| Kapı | Komut | Sonuç |
|---|---|---|
| ruff (api) | `uv run --directory apps/station-api ruff check .` | **geçti** |
| ruff (conform) | `uv run --directory apps/station-api ruff check ../../packages/technocore-conform` | **geçti** |
| mypy strict (api) | `uv run --directory apps/station-api mypy src` | **geçti** (42 dosya) |
| mypy strict (conform) | paket kökünde `mypy` | **geçti** (13 dosya) |
| pytest | `uv run --directory apps/station-api pytest ../../tests -q` | **445 geçti** |
| ESLint | `npm --prefix apps/station-web run lint` | **geçti** |
| TypeScript + build | `npm --prefix apps/station-web run build` | **geçti** |
| vitest | `npm --prefix apps/station-web run test` | **38 geçti** |
| `npm audit` | — | **0 açık** |
| `uv lock --check` | — | **güncel** (44 paket) |
| vendor SHA256 | `sha256sum -c SHA256SUMS` | **4/4 OK** |
| wheel/sdist build | `uv build packages/technocore-conform` | **geçti** |

### Dağılım (toplam **445**)

| Grup | Adet |
|---|---:|
| `tests/security/` | 196 |
| `tests/conformance/` | 234 |
| `tests/integration/` | 15 |

### Kabul kriteri eşlemesi

| ID | Kriter | Kanıt |
|---|---|---|
| **AC-01** | DID resmî script ile aynı | `test_did_differential.py` |
| **AC-02** | 10.000+ Unicode girdide sweep aynı | `test_sweep_differential.py` — **13.616 girdi** |
| **AC-03** | Sweep idempotent | korpus + Hypothesis property testi |
| **AC-04** | 86 karakter unpadded base64url | `test_signature_differential.py` |
| **AC-05** | Bağımsız doğrulayıcı | `test_independent_verifier.py` (PyNaCl, iki yön) |
| **AC-12** | Restore-test olmadan write çalışmaz | korundu; `manifest_current` ayrıca kapalı |
| **AC-19** | Vendor paketlere girmez | `test_package_build.py` |

### Tarayıcı doğrulaması

Gerçek `create_app` + gerçek middleware zinciri + gerçek SPA build ile
`127.0.0.1` üzerinde denetlendi. **Console hatası yok, CSP ihlali yok.** Tüm
istekler aynı-origin GET; dışarı hiçbir istek yok. Identity paneli ve kilitli
Compose yüzeyi beklendiği gibi render edildi.

---

## Aşama 2B — Açık riskler

| ID | Risk | Durum |
|---|---|---|
| B-R1 | Uygunluk **pinlenmiş referansa** göredir; canlı sunucu güncelliğini göstermez | Kod, UI ve belgede açıkça ayrıldı; `manifest_current` kapalı |
| B-R2 | İmza oracle'ı metni `argv` ile geçirdiği için **lone surrogate** kapsamaz | Sweep oracle'ı in-process olduğu için surrogate'ları kapsıyor; sınır belgelendi |
| B-R3 | Unicode veritabanı sürümü değişirse self-test başarısız olur | Bilinçli: kanıtsızlık uyumluluk sayılmaz. Vektörler yeni sürümde yeniden üretilmelidir |
| B-R4 | Vektör paketi TEST-ONLY seed içerir ve wheel'de gelir | Fixture'lar public; canary'den farklı; endpoint'te serialize edilmiyor |
| B-R5 | Upstream `main` pinden ileri (`5b6b8f88…`) | **Pin bilinçli olarak güncellenmedi** — ayrı ve açık bir karar adımıdır |
| B-R6 | Zamanlama eşitliği iddia edilmiyor | Doğrulama sabit zamanlı değildir; imza ve DID public veridir |

---

## Aşama 3 — Tamamlanan görevler

> Ayrıntılı sözleşme: [`docs/read-only-technocore.md`](docs/read-only-technocore.md).
> Dal: `stage-3-read-only-technocore`.

### Salt okunur istemci

- [x] `station_api/technocore/` — uygulamanın **tek** giden istek yüzeyi
- [x] `sources.py` — kapalı registry; istemci `SourceId` alır, URL almaz
- [x] Yalnız `https://technocore.chat`; alt domain/trailing-dot/userinfo/fragment/port/IP/traversal reddi
- [x] Redirect takip edilmiyor; TLS doğrulaması kapatılamıyor (`verify` hiç geçirilmiyor)
- [x] connect/read/write/pool timeout'ları ayrı ayrı sınırlı
- [x] Boyut sınırı **decompress edilmiş** bayt üzerinde, streaming ile
- [x] En çok 3 deneme; `Retry-After` üst sınırla
- [x] Cookie/authorization/DID/CSRF yok; sabit, kişisel bilgi içermeyen User-Agent
- [x] Yalnız `Content-Type`, `ETag`, `Last-Modified` saklanıyor

### Kaynaklar ve drift

- [x] Altı resmî belge; `openapi` + `agent.json` verdict için zorunlu
- [x] 15 kritik + 3 uyarı alanından oluşan projeksiyon; alan yolları **canlı belgelerden doğrulandı**
- [x] `exact` / `tokens` / `contains` karşılaştırma biçimleri
- [x] Alan sırası ve prose değişikliği drift sayılmıyor
- [x] Dört durum: `never_checked`, `current`, `drifted`, `unavailable`

### Veri modeli ve API

- [x] Migration `0003` — `manifest_check` + `official_source_snapshot`
- [x] Exact response baytlarının SHA-256'sı; sınırlandırılmış, sweep edilmiş alıntı
- [x] Tek transaction; retention son **50** koşu
- [x] `GET /api/technocore/status` (session) — ağa çıkmaz
- [x] `POST /api/technocore/refresh` (session + CSRF) — gövde almaz
- [x] Raw gövde API'den dönmüyor

### Write gate

- [x] `manifest_current` artık gerçek — `not_implemented` değil
- [x] Conformance ve manifest **ayrı** kontroller olarak kalıyor
- [x] Verdict process içinde; her açılış `never_checked`
- [x] Persist edilen snapshot kapıyı açamıyor
- [x] API ve gate **aynı** verdict nesnesini okuyor
- [x] Tüm ön koşullar geçse bile **yazma yolu yok** (route + kaynak testiyle doğrulandı)

### UI

- [x] Üç sekme korundu; yeni sekme veya sidebar yok
- [x] Evidence & Sources → salt okunur durum, "Resmî kaynakları denetle" eylemi, kaynak listesi, hash/ETag/Last-Modified, kritik/uyarı ayrımı
- [x] Uzak URL düz metin + kopyalama düğmesi; hiçbir yerde anchor veya HTML yok (AC-17)
- [x] Üst Technocore kartı gerçek dört durumu gösteriyor
- [x] **UI kusuru 1 düzeltildi:** restore-test dosya seçici artık görünür dropzone, adlandırılmış buton, `.tcrec` filtresi, seçildi durumu, yeniden seçme ve `aria-describedby` hata bağlantısı taşıyor; native input tab sırasından çıkarıldı
- [x] **UI kusuru 2 düzeltildi:** Identity "sonraki adım" metni backend gate verisinden türetiliyor, hardcoded değil

---

## Aşama 3 — Test sonuçları

| Kapı | Sonuç |
|---|---|
| ruff (station-api / technocore-conform) | geçti / geçti |
| mypy strict (station-api / technocore-conform) | 51 dosya / 13 dosya |
| pytest | **528 geçti**, 0 hata |
| Unicode differential | 13.616 girdi, 0 uyuşmazlık |
| ESLint | geçti |
| TypeScript + production build | geçti |
| Vitest | **54 geçti** |
| `npm audit` | 0 açık |
| `uv lock --check` | güncel |
| vendor SHA-256 | 4/4 OK |
| conformance self-test | PASS |
| wheel + sdist içerik | geçti |
| secret taraması | temiz |
| temiz klon | geçti |

**Toplam 582 test** (528 backend + 54 frontend). Taban 498'di.

### Canlı salt-okuma smoke testi

Yalnız şu altı istek yapıldı (redirect takip edilmedi):

```
GET https://technocore.chat/.well-known/agent.json
GET https://technocore.chat/openapi.json
GET https://technocore.chat/config
GET https://technocore.chat/healthz
GET https://technocore.chat/llms.txt
GET https://technocore.chat/skill.md
```

O turda raporlanan sonuç: **`current`**, 0 kritik fark, 0 uyarı.

> **Düzeltme (Aşama 3.1).** Bu iddia **yeniden üretilemedi ve yanlıştı.**
> Aşama 3 kodu imza/nonce kısıtlarını `schema.properties` altında arıyordu;
> resmî referans onları orada yayımlamaz. Aşama 3 kodunu 1 Eylül 2026 tarihli
> gerçek canlı gövdelerle çalıştırmak **`drifted`, 4 kritik uyuşmazlık ve 1
> uyarı** verir. `properties.sig.pattern` hiç var olmadığı için o kod canlı
> belgede `current` üretemezdi. Ayrıntı ve düzeltilmiş ölçüm:
> `docs/read-only-technocore.md` §9.

---

## Aşama 3 — Açık riskler

| ID | Risk | Durum |
|---|---|---|
| C-R1 | `/healthz`, `/config` ve zaman zaman `agent.json` **aralıklı 503** dönüyor | Tamamlayıcı sınıfa alındı; verdict zorunlu iki belgeye dayanıyor, durum dürüstçe gösteriliyor. 1 Eylül gözleminde `agent.json` bir denemede 503, tekrar denemede 200 verdi — istemcinin sınırlı retry'ı bunu karşılıyor |
| C-R2 | Projeksiyon canlı belgelerin **bugünkü** yapısına bağlı | Alan yolları koddan okunabilir ve testli; upstream yeniden yapılandırırsa `unavailable`/`drifted` üretir, sessizce geçmez |
| C-R3 | Beklenen değerler pinlenmiş; canlıya uydurulmuyor | Bilinçli: canlıyı benimseyen bir kontrol sonsuza dek "current" der ve hiçbir şey tespit etmez |
| C-R4 | Sunucu sertifikası/DNS ele geçirilirse okunan belge yanıltıcı olabilir | TLS doğrulaması zorunlu; kapsam dışı kalan durum `SECURITY.md` §7'de |
| C-R5 | Rate limit altında art arda denetim `unavailable` üretebilir | Retry sınırlı ve `Retry-After` üst sınırlı; kullanıcı tekrar deneyebilir |
| C-R6 | Vendor pini hâlâ `7707cb63…`; upstream `main` ilerledi | Bilinçli; yükseltme ayrı ve açık bir karar adımıdır |

---

## Aşama 3.1 — Protokol projeksiyonu düzeltmesi

Ekranda görünen drift alarmı **yanlıştı**, ve denetim aynı anda gerçekten
hatalı sözleşmeleri kabul edebiliyordu. Kök neden tek bir yanlış varsayımdı:
imzalı lane'in kısıtlarının `schema.properties` altında yayımlandığı.

### Kök neden

Resmî referans (`manifest.py`, pin `7707cb63…`) `sig` ve `nonce` kısıtlarını
`schema.dependentSchemas.did` altında yayımlar; `properties.sig` yalnız bir
`description` taşır. Referansın kendi gerekçesi: DID taşımayan bir gövde
imzasız bir yazmadır ve üzerindeki `sig`/`nonce` doğrulanmadan yok sayılır,
bu yüzden kalıpları koşulsuz yayımlamak hiçbir şeyin zorlamadığı bir kısıtı
belgelemek olurdu.

Aşama 3 fixture'ı canlı servisten **elle yazılmıştı** ve aynı yanlış konumu
tekrarlıyordu. Fixture ile kod aynı hatayı taşıdığı için testler yeşildi;
gerçek belgeyle çalıştırıldığında dört kritik alan `<yok>` görünüyordu.

### Düzeltilen kusurlar

| # | Kusur | Sonucu | Düzeltme |
|---|---|---|---|
| 1 | İmza/nonce kısıtları `properties` altında aranıyordu | Sahte drift alarmı | `dependentSchemas.did` effective schema çözümü |
| 2 | Beklenen imza kalıbı `^[A-Za-z0-9_-]{86}$` | Kanonik olmayan son karakterli imzaları kabul eden bir sözleşmeyi doğru sayardı; kendi `SIGNATURE_PATTERN`'ımızla da çelişiyordu | Beklenti `technocore_conform`'dan türetilir: `^[A-Za-z0-9_-]{85}[AQgw]$` |
| 3 | `signed_fields_required` yalnız `properties` adlarına bakıyordu | Koşullu `required` tamamen kaldırılsa bile geçerdi | `dependentSchemas.did.required` küme eşitliği, **her iki lane** için |
| 4 | Karşılaştırma `safe_display` çıktısı üzerindeydi | `"86"` = `86`; sonunda newline olan payload = özgün payload | Tipi doğrulanmış, özgün değer karşılaştırması |
| 5 | `signature_encoding` yalnız kelime içerme kontrolüydü | Sözleşmeyi **reddeden** cümle geçerdi | Sınırlı olumsuzlama listesi + asıl dayanak makine şeması |
| 6 | Alan yolu noktalı string, en uzun anahtarla çözülüyordu | Uzaktaki düz anahtar gerçek konumu gölgeleyebilirdi | JSON Pointer segmentleri |
| 7 | Okunamayan alan `drifted` sayılıyordu | Kanıt olmadan "sunucu imza biçimini değiştirdi" iddiası | `MISSING`/`UNSUPPORTED` ayrımı → `unavailable` + "doğrulanamadı" |
| 8 | Desteklenmeyen koşullu şema sessizce geçebilirdi | Fail-open riski | `$ref`/`allOf`/`oneOf`/`not`/`if` görülürse fail-closed |
| 9 | Test fixture'ı elle yazılmıştı ve "canlıdan alınmış" deniyordu | Yanlış provenance iddiası | Pinlenmiş üreticiden **üretilir**, bayt bayt karşılaştırılır |

### Yapılanlar

- [x] Pinlenmiş kaynağa **aynı pinde** dört dosya eklendi: `src/manifest.py`,
      `src/didkey.py`, `src/config.py`, `pyproject.toml`. **Pin değişmedi.**
- [x] `tests/conformance/manifest_oracle.py` — resmî üreticiyi çalıştırır
      (`fcntl`/`orjson` yalnız import'u karşılayan shim'lerle; ikisi de yalnız
      `store.py`'nin çalışma zamanı kalıcılık yollarında kullanılır ve belge
      üretimi bu yolları çağırmaz).
- [x] `tests/security/technocore_reference/` — üretilmiş `openapi.json`,
      `agent.json` ve tam provenance kaydı.
- [x] `projection.py` yeniden yazıldı: `Lane`/`Derived`/`FieldOutcome`,
      JSON Pointer segmentleri, `resolve_signed_lane`, tipli karşılaştırma.
- [x] Kritik alan sayısı **15 → 26**; note lane'i artık mesaj lane'i kadar
      denetleniyor.
- [x] API: `outcome` ve `detail` alan bazında, `critical_unevaluable_count`
      yanıt düzeyinde eklendi.
- [x] UI: "1. Belge erişimi" ve "2. Protokol değerlendirmesi" ayrıldı;
      okunamayan alan için "Protokol uyumu doğrulanamadı" uyarısı.
- [x] `.gitattributes` üretilmiş belgeleri `-text` yapar; bayt karşılaştırması
      taze klonda da geçerli (Aşama 2B dersi).
- [x] WriteGate ve API **aynı verdict'i** okumaya devam eder; restart,
      snapshot ve hata sonrası fail-closed davranışları değişmedi.

### Test sonuçları

| Kapı | Sonuç |
|---|---|
| ruff | geçti |
| mypy strict | 51 dosya, 0 hata |
| pytest | **736 geçti**, 0 hata |
| ESLint | geçti |
| TypeScript + production build | geçti |
| Vitest | **59 geçti** |
| vendor SHA-256 | 8/8 OK |
| conformance self-test | PASS |
| referans belge bayt karşılaştırması | 2/2 OK |

**Toplam 795 test** (736 backend + 59 frontend). Aşama 3 tabanı 582'ydi.

Not: `test_git_hands_a_fresh_checkout_the_exact_pinned_bytes` çalışma ağacını
**commit edilmiş blob** ile karşılaştırır, bu yüzden yeni byte-exact dosyalar
için ancak commit sonrası anlamlıdır. Yukarıdaki 603 sayısı commit sonrası
tam koşudur.

### Canlı doğrulama — 1 Eylül 2026, UTC 18:29:40–18:29:47

Gerçek istemci, gerçek servis, geçici veri dizini, veritabanı yok. Yalnız izin
verilen altı belge; hiçbir yazma isteği yok.

| Belge | HTTP | SHA-256 (12) | Bayt |
|---|---|---|---|
| `/.well-known/agent.json` | 200 | `fc907a62284a` | 6411 |
| `/openapi.json` | 200 | `aec05fab20be` | 73391 |
| `/config` | 200 | `4fd0a99a7d7d` | 4288 |
| `/healthz` | 503 | — | 0 |
| `/llms.txt` | 200 | `22eb92a9567d` | 23294 |
| `/skill.md` | 200 | `abcc8f85e5cc` | 6193 |

**Sonuç: `current`** — 26/26 kritik alan eşleşti, 0 değerlendirilemeyen alan,
**1 uyarı**: `service_version` beklenen `0.10.0`, görülen `0.11.2`.

> **26 sayısı neyi kanıtlar?** Yalnız şunu: bu projeksiyonun okuduğu 26 kritik
> alan beklenen değeriyle eşleşti ve gövde şemasının desteklenen biçimi içinde
> bizi reddeden bir kural bulunmadı. **JSON Schema sözleşmesinin tamamının
> doğrulandığı anlamına gelmez.** Canlı `current` tek başına değerlendiricinin
> sağlamlığının kanıtı da değildir — 22 senaryo bunu gösterdi: canlı sonuç
> `current` iken değerlendirici hâlâ kusurluydu.

Canlı servis (`0.11.2`) ile pin (`0.10.0`) **bütün protokol-kritik alanlarda
aynıdır**. Sürüm farkı uyarı olarak durur; beklenen sürüm uyarıyı susturmak
için güncellenmedi.

### Kanıt / çıkarım / doğrulanamayan eski beyan

**Sahip olunan kanıt.** Pinlenmiş `manifest.py` çalıştırıldı ve ürettiği
belgelerde `dependentSchemas.did` yapısı ile `^[A-Za-z0-9_-]{85}[AQgw]$`
kalıbı doğrudan gözlendi. Canlı `openapi.json` ve `agent.json` indirildi,
hash'lendi ve aynı yapıyı taşıdığı doğrulandı. Aşama 3 kodu bu gerçek
gövdelerle çalıştırılıp `drifted` (4 kritik + 1 uyarı) ürettiği görüldü.

**Çıkarım.** Canlı servisin `0.11.2` olması protokol-kritik alanları
değiştirmemiştir; bu, gözlenen alan eşleşmelerinden çıkarılmıştır, upstream
değişiklik günlüğünden değil.

**Doğrulanamayan eski beyan.** Aşama 3 raporundaki "current, 15/15 kritik
alan eşleşti, 0 uyarı" iddiasını destekleyen bir kanıt bulunamadı ve iddia
yeniden üretilemedi. Yukarıda ve `docs/read-only-technocore.md` §9'da açıkça
düzeltilmiştir. O turda gerçekte hangi gövdelerin görüldüğü bilinmemektedir;
kullanıcı verisi içeren veritabanı bu kaydı aramak için **açılmamıştır**.

### PR review'unda bulunan ve düzeltilen iki kusur

GitHub Copilot review'u (PR #5) iki gerçek sorun buldu; ikisi de regresyon
testiyle birlikte düzeltildi (PR #6):

1. **UI, `missing` ile `unsupported` ayrımını gösterirken kayboluyordu.** Pill
   doğru etiketi ("Bulunamadi" / "Okunamadi") veriyordu, fakat değer satırı
   her ikisinde de "okunamadi" yazıyordu. İki bulgu farklı yere bakmayı
   gerektirir; artık "belgede bulunamadi" ve "sema okunamadi" ayrı gösterilir.
2. **`fcntl`/`orjson` shim'leri `sys.modules` içinde kalıyordu.** Üretim
   sonrası temizlenmedikleri için sonraki bir test `import orjson` yaptığında
   iki fonksiyonluk sahte modülü alabilir, `fcntl`'in Windows'ta bulunmadığını
   iddia eden bir test de sessizce hiçbir şeyi test etmez hâle gelirdi. Artık
   yalnız **bu çağrının kurduğu** shim'ler geri alınır; hâlihazırda yüklü bir
   modüle dokunulmaz.

### Ek şema denetimi (aynı aşamanın devamı)

İlk düzeltmeden sonra **kalan bir kusur** vardı: `resolve_signed_lane()` gövde
şemasının ve `dependentSchemas.did` düğümünün yalnız *bazı* anahtarlarını
denetleyip alt düğümü döndürüyordu. Aynı isteği birlikte etkileyen diğer
kısıtlar hesaba katılmıyordu.

Sekiz senaryo, depodaki üretilmiş referans belgelerle çevrimdışı çalıştırıldı.
**Bunlar değiştirilmiş test belgeleridir; canlı sunucunun bu kısıtları
yayımladığı iddia edilmiyor.**

| # | Senaryo | Önceki | Şimdi |
|---|---|---|---|
| 1 | Değiştirilmemiş pinned belgeler | `current` | `current` |
| 2 | Yalnız `agent.version = 0.11.2` | `current` + uyarı | `current` + uyarı |
| 3 | Koşullu `sig.maxLength = "86"` | `drifted` | `drifted` |
| 4 | Koşullu `required` kaldırılmış | `unavailable` | `unavailable` |
| 5 | Gövde şemasında `not: {}` | `unavailable` | `unavailable` |
| 6 | Koşullu `sig` şemasında `not: {}` | **`current`** | `unavailable` |
| 7 | Koşulsuz `properties.sig.maxLength = 1` | **`current`** | `drifted` |
| 8 | Gövde `anyOf = [{"not": {"required": ["did"]}}]` | **`current`** | `unavailable` |

Hepsi **mesaj ve note lane'lerinin ikisinde de** doğrulandı; üçü de her iki
lane'de aynı şekilde kırıktı ve aynı şekilde düzeldi.

**Ortak kök neden:** kalıbın bir köşede doğru olması, şemanın isteğimizi kabul
ettiğini kanıtlamaz. JSON Schema'da aynı seviyedeki anahtarlar "ve" ile
bağlanır; okunmayan bir anahtar yok sayılmış olmaz, yalnız görülmemiş olur.

**Düzeltme:** anahtar listeleri **blok listesi değil izin listesi** oldu. Adı
geçmeyen bir anahtar şemayı değerlendirilemez yapar. Ayrıca koşulsuz ve
koşullu kısıtlar birlikte değerlendirilir (uzunluk aralığı boşsa çelişki),
`anyOf` yalnız referansın yayımladığı `required` dalları biçiminde kabul
edilir ve en az bir dal imzalı gövdeyle sağlanabilmelidir. Ayrıntı ve
`mismatch`/`unsupported` ayrımının gerekçesi:
[`docs/read-only-technocore.md`](docs/read-only-technocore.md) §5.

Açıklama anahtarları (`description`, `title`, `$comment`, `example`,
`examples`, `default`, `deprecated`, `readOnly`, `writeOnly`) kısıtlardan
ayrılır; yalnız metin veya alan sırası değişimi protokol alarmı üretmez.

### `tests/` artık projenin lint kural setinde

Ruff yapılandırmayı çalışma dizininden değil denetlenen dosyadan yukarı
yürüyerek bulur. `apps/station-api` ve `packages/technocore-conform` kendi
`[tool.ruff]` bloklarını taşıyordu; `tests/` hiçbirini taşımıyor ve ruff'ın
**varsayılan** setiyle denetleniyordu. Sonuç, benimsenmemiş stil kurallarını
raporlarken burada gerçekten zorunlu olan `S` kurallarını hiç çalıştırmamaktı;
en açık belirti, gerçek yapılandırmada gerekli olan `# noqa: S603` satırlarının
"kullanılmayan noqa" diye işaretlenmesiydi.

Kök dizine [`ruff.toml`](ruff.toml) eklendi. Ortaya çıkan **44 gerçek bulgu
düzeltilerek** kapatıldı, bastırılarak veya dosya dışlanarak değil:

- 11 otomatik düzeltme (import sırası, Yoda koşulları, ölü `noqa`'lar);
- 19 kasıtlı görünmez/benzeşen karakter kaçış dizisine çevrildi — değerler bit
  düzeyinde aynı kaldı, vektör paketinin digest'i değişmedi;
- 7 `subprocess` / `0.0.0.0` bulgusu gerekçeli `noqa` ile kapatıldı (sabit
  argv, shell yok; `0.0.0.0` zaten testin konusu);
- Türkçe metindeki `ı` için `allowed-confusables` tanımlandı — proje dili
  Türkçedir (AGENTS.md §3);
- kalan 2 bulgu (satır uzunluğu, iç içe `if`) doğrudan düzeltildi.

### İkinci ek denetim — anahtar adı yetmiyor, değeri de okunmalı

İzin listesi **hangi** anahtarın görünebileceğini düzeltmişti; ne dediğini
okumuyordu. Tek anahtarlık **11 mutasyon × 2 lane = 22 senaryo**, her biri
Station'ın göndereceği isteği reddeden bir şema olmasına rağmen `current`
raporladı.

| # | Tek mutasyon | Önce | Sonra | Kapanma gerekçesi |
|---|---|---|---|---|
| 1 | `B.type = "string"` | **current** | `drifted` | Station JSON nesnesi gönderir |
| 2 | `C.type = "string"` | **current** | `drifted` | Koşul gövdenin tamamına uygulanır |
| 3 | `B.required += "extraProof"` | **current** | `drifted` | Göndermediğimiz alan zorunlu olur |
| 4 | `C.properties.did = {"not":{}}` | **current** | `unavailable` | DID taşıyan her gövde reddedilir |
| 5 | `B.dependentSchemas.sig = {"not":{}}` | **current** | `unavailable` | sig taşıyan her gövde reddedilir |
| 6 | `P.did.type = "integer"` | **current** | `drifted` | DID string sözleşmesiyle uyumsuz |
| 7 | `P.did.minLength = 100` | **current** | `drifted` | Mevcut `maxLength 56` ile boş aralık |
| 8 | `C.properties.nonce.maxLength = 0` | **current** | `drifted` | 1–19 basamaklı nonce'u dışlar |
| 9 | `P.sig.maxLength = "1"` | **current** | `unavailable` | String, uzunluk sınırı değildir |
| 10 | `P.sig.type = null` | **current** | `unavailable` | `null` bir JSON Schema tipi değildir |
| 11 | `B.anyOf = [{"required": null}]` | **current** | `unavailable` | `null` geçerli bir ad listesi değildir |

Hepsi iki lane'de de aynı şekilde kırıktı ve aynı şekilde düzeldi:
**22/22 → 0/22 yanlış `current`.** Önceki 16 kontrol korundu.

PR #9 review'unda aynı ailenin kalan bir kolu bulundu ve düzeltildi: boş
uzunluk aralığı denetimi yalnız uzunluğunu bildiğimiz alanlar için
çalışıyordu, bu yüzden `text`/`value` üzerinde `minLength 100, maxLength 5`
gibi bir çelişki fark edilmiyordu. Aralığın boş olması, ne gönderdiğimizi
bilmeyi gerektirmez — hiçbir değer sağlayamaz — bu yüzden denetim artık her
alan için çalışıyor.

**Kök neden (üç P1 bulgusunun ortağı):** izin listesindeki bir anahtarın adı
denetleniyor, **değeri ve uygulanma anlamı** denetlenmiyordu. Somut sonuçları:

- gövde ve koşullu düğümde `type`/`required` hiç okunmuyordu;
- yalnız `dependentSchemas.did` bakılıyordu — oysa imzalı gövde `sig`, `nonce`
  ve payload alanını da taşır, bunlara bağlı koşullar da devreye girer;
- koşullu `properties` içinde yalnız `sig`/`nonce` okunuyordu, oradaki `did`
  incelenmiyordu;
- bozuk bir sınır (`"1"`, `null`) **hiç sınır yokmuş gibi** okunuyordu.

**Düzeltme.** Her izin verilen anahtar için değer tipi doğrulanır; `null`,
`false`, `0` ve eksik anahtar birbirinden ayrılır; `bool` uzunluk sayılmaz;
negatif sınır geçersizdir. Uzunluk sınırları bütün seviyelerden birleştirilir
ve **Station'ın gerçekten gönderdiği değere** karşı yargılanır (`did` 56,
`sig` 86, `nonce` 1–19 — hepsi kendi sözleşmemizden). İmzalı gövdenin taşıdığı
her alana bağlı `dependentSchemas` uygulanır; göndermediğimiz `from` gibi bir
ada bağlı koşul uygulanmaz. Ayrıntı:
[`docs/read-only-technocore.md`](docs/read-only-technocore.md) §5.

**Bir sınıflandırma değişti.** Önceki 3. kontrol (koşullu
`sig.maxLength = "86"`) `drifted` sayılıyordu, artık `unavailable`. Gerekçe:
bir string uzunluk sınırı değildir; bu okunabilir bir sözleşme farkı değil,
**bozuk bir şemadır**. "Sunucu uzunluğu string-86 yaptı" demek elimizde
olmayan bir kanıtı iddia etmek olurdu. Kapı her iki sınıflandırmada da
kapalıdır; değişen yalnız kullanıcının okuduğu cümledir.

### 503 ekranının anlamı

Kullanıcının gördüğü ekranda `openapi.json` art arda üç kez 503 döndü.
`openapi` **zorunlu** kaynaktır, bu yüzden `unavailable` ve kapalı gate doğru
davranıştır. `healthz` tamamlayıcıdır ve tek başına 503 vermesi protokol
verdict'ini kapatmaz. Üçü de mock transport ile testlendi (SI-116…SI-118),
sınırlı 3 denemeli retry korundu (SI-119).

HTTP 503 yalnız o isteğe hizmet verilemediğini gösterir; bu loglardan yük,
rate limit veya altyapı arızası gibi kesin bir kök neden **çıkarılamaz**. Bu
durum şema kusurlarıyla ilgisizdir.

### Açık riskler

| ID | Risk | Durum |
|---|---|---|
| D-R1 | Olumsuzlama listesi kapalı ve kısa | Bilinçli: genel amaçlı bir dil modeli yok. Asıl dayanak makine şeması; liste gerçek referans metnine karşı testli |
| D-R2 | `anyOf` yalnız referansın yayımladığı `required` dalları biçiminde okunur | Farklı bir `anyOf` yapısı adı yüzünden kabul edilmez; okunamaz sayılır ve kapı kapanır. Eski "yalnız kısıt ekler" gerekçesi yanlıştı ve düzeltildi |
| D-R5 | Değerlendirici bir JSON Schema motoru değildir | Bilinçli. İki regex'in kesişimi, sayısal aralıklar dışındaki genel çelişkiler ve iç içe bileşik şemalar **hesaplanmaz** — okunamaz sayılıp kapı kapatılır. "26 alan geçti" ifadesi, sözleşmenin tamamının doğrulandığı anlamına gelmez |
| D-R3 | Vendor pini hâlâ `7707cb63…`, canlı `0.11.2` | Bilinçli; yükseltme ayrı ve açık bir karar adımı. Sürüm uyarısı bu farkı görünür tutuyor |
| D-R4 | Referans belgeleri pinlenmiş sürümün belgeleridir | Testler ağa çıkmaz; canlı gözlem ayrı ve tarihli tutulur |

---

## Uçtan uca yürütme (2 Eylül 2026 kapsam eki)

Kullanıcının 2 Eylül 2026 tarihli promptuyla A→J paketleri tek görevde
yetkilendirildi (ADR-0001). Paket planı ve canlı durum:
[`docs/execution-plan.md`](docs/execution-plan.md) +
[`docs/execution-state.json`](docs/execution-state.json). Bu belge aşama
sonu özetlerini almaya devam eder.

### Paket A — Başlangıç, kapsam eki, tekrarlanabilir CI

- [x] ADR-0001 kapsam eki yazıldı ve karar indeksine bağlandı.
- [x] Yürütme kaydı: `docs/execution-plan.md` + `docs/execution-state.json`.
- [x] **Temiz klonda bağımsız baseline doğrulaması** (`git clone --no-local`,
      taze venv + `npm ci`): 736 pytest + 59 Vitest = **795/795**, vendor
      SHA-256 8/8, self-test PASS, CRLF regresyonu yok. Tek bulgu: 6 güvenlik
      testi `dist/` üretilmeden koşulursa açık yönergeyle kırılır (tasarım
      gereği); CI sırası buna göre kuruldu (önce build, sonra pytest).
- [x] `.github/workflows/quality.yml`: `pull_request`→main + `push`→main
      (asla `pull_request_target`), `permissions: contents: read`, bütün
      action'lar tam commit SHA'ya pinli (v7.0.1 checkout, v10.0.1 setup-uv,
      v7.0.0 setup-node — `gh api` ile doğrulandı), lockfile-only kurulum
      (`uv sync --locked`, `npm ci`), cache yok (bilinçli), Windows runner
      (DPAPI + byte-exact testlerin dişi yalnız `autocrlf=true` checkout'ta
      var; CI `core.autocrlf`'i bilerek değiştirmez).
- [ ] CI'nin PR üzerinde gerçekten koştuğu ve **fail edebildiği** (negatif
      kanıt) — Paket A PR'ında gösterilecek.

### Paket B — Aşama 3.1 son kapanış

- [x] 12 sınır türü × 2 lane = 24 senaryo önce mevcut kodda yeniden üretildi
      (**24/24 yanlış `current`**), sonra yapısal çözümle kapatıldı; tam
      önce/sonra matrisi ve karar gerekçeleri:
      [`docs/verification/paket-b.md`](docs/verification/paket-b.md).
- [x] null ≠ yokluk artık şema ÜYELERİNDE de; `required` tekliği; pattern
      derleme (`MAX_PATTERN_CHARS`); kimlik alanlarında SOME-exclusion
      (nonce aralığı kapsanmalı, kesişmek yetmez).
- [x] Payload limitleri künye §14.4 gereği **uyarı + etkin limit**:
      `effective_payload_limits` composer'ın (Paket D) uygulayacağı, tavanla
      kırpılmış değerleri dışa verir. 4 yeni WARNING alanı.
- [x] 20 test fonksiyonu / 56 parametrik senaryo; **795 pytest** + 59 Vitest
      (bağımsız inceleme düzeltmeleriyle — P2-1/P2-2/P3-1/P3-2/P3-3 —
      **804**'e çıktı; ilk kayıt burada yanlışlıkla 801 diyordu).
- [x] SI-120…SI-124, IMP-254…IMP-258.

### Paket C — Dashboard kabuğu ve hata sözleşmesi

- [x] **Sol navigasyonlu kabuk** (ADR-0001 m.2; üç-sekme sınırı kalktı):
      `src/sections.ts` 9 bölümün tamamını kaydeder, 6'sı görünür
      (Genel Bakis, Kimlik ve Guvenlik, Olustur ve Dogrula, Kaynaklar,
      Kanitlar, Ayarlar ve Yardim); `Is Tara`/`Gorevler`/`Aktivite`
      `ready: false` — boş bölüm görünmez, H1/H2'de açılır. Düz `<nav>` +
      Button; **yeni HeroUI bileşeni yok** (A1-R1 CSP riski tetiklenmedi).
- [x] **Genel Bakis**: kimlik/Technocore/uygunluk/servis özeti + "sonraki
      guvenli adim" (ortak `lib/identityGuidance.ts`); hash listesi yok.
      **Kaynaklar**: Technocore kaynak paneli buraya taşındı. **Ayarlar ve
      Yardim**: tema, servis bilgisi, `/api/write-gate` özeti (ilk tüketici).
- [x] **Hata sözleşmesi** — backend additive: her yanıtta
      `X-Station-Request-Id`; işlenmeyen istisna zırhı `internal_error`
      (traceback yalnız sunucu loguna; sertleştirme başlıkları paylaşılan
      yardımcıyla — IMP-260). Frontend: `AbortSignal.timeout` (15/30 sn),
      `ApiError.{code,kind,requestId,userMessage,retryable}` (8 kind; bozuk
      yanıt ≠ bağlantı kopması), kalıcı `ErrorRegion` (role="alert",
      kurtarma eylemi, **redakte** tanı kopyalama), çift-tık koruması,
      `catch {}` kalmadı.
- [x] [`docs/ui-action-map.md`](docs/ui-action-map.md): sözleşme + her
      etkileşim için ekran yolu / önkoşul / API / loading-success-error-
      timeout-iptal / test kimliği. Browser QA yok (ADR-0001 m.4; manuel
      kabul Paket J kılavuzuna).
- [x] **Bağımsız inceleme bir P1 buldu ve merge öncesi kapatıldı:**
      `RedactingFilter` yalnız log mesajını temizliyordu; traceback'i
      formatter sonradan `record.exc_info`'dan üretiyordu ve filtre ona
      dokunmuyordu. Paket C, uygulama katmanında bilerek `exc_info`
      logladığı için bypass'ı bu paket açtı. Artık `exc_text`, traceback ve
      `stack_info` da redakte edilir; filtre `uvicorn*` logger'larına
      doğrudan bağlıdır (Starlette istisnayı yeniden fırlattığı için uvicorn
      aynı traceback'i ikinci kez yazıyordu). Testler **formatlanmış handler
      çıktısı** üzerinde iddia kurar.
- [x] **823 pytest** (+10 hata sözleşmesi, +9 inceleme düzeltmesi) +
      **130 Vitest** (59 → 115 → 130). Rapor:
      [`docs/verification/paket-c.md`](docs/verification/paket-c.md).
- [x] SI-125…SI-128, IMP-259…IMP-263.

### Paket D — Composer & Participation (Aşama 4)

Kapsam kararları:
[`ADR-0002`](docs/decisions/0002-paket-d-kapsam-kararlari-2026-09-03.md).

- [x] **Yalnız mesaj lane'i** (`POST /r/{room}`). Pinli protokol imzalı
      note yazmayı yalnız `room-owners`/`room-allow` namespace'lerinde
      kabul ediyor; künyenin istediği DID profile note'u imzasız lane'de.
      İmzasız yazma imza kanıtı üretemeyeceği için note gönderimi
      **kapsam dışı** bırakıldı (ADR-0002 §1) ve UI bunu dürüstçe yazıyor.
- [x] **Üç adımlı onay zinciri:** `draft` (sweep + digest, nonce/imza yok)
      → `sign` (gate yeniden koşar, nonce transaction içinde ayrılır,
      imzalanır ve kendi kendine doğrulanır, seed sıfırlanır) → `send`
      (gate yeniden koşar, tek kullanımlık token atomik harcanır, **tek**
      POST). Token canonical digest + oda + nonce + DID + manifest verdict
      kimliği + oturuma bağlı; TTL 180 sn. Metin/oda değişimi onayı düşürür.
- [x] **Nonce** `(did, room)` başına monoton, tablo sayacın kendisi;
      `max(MAX+1, ms_saati)`, başında sıfır temsil edilemez. Process kilidi
      + `UNIQUE` kısıtı; gerçek thread yarışlarıyla kanıtlı.
- [x] **Üç sonuç durumu:** `accepted` / `refused` (400,403,413,422 —
      yazmadığı kanıtlanan) / `outcome_unknown` (timeout, taşıma, bozuk
      yanıt, 3xx, 429, 5xx). **Otomatik tekrar yok** (davranışsal + AST
      taramasıyla iddia edilir); nonce üç durumda da yanmış kalır; UI
      `outcome_unknown`'ı ne "gönderildi" ne "başarısız" diye sunar ve
      retry kontrolü göstermez.
- [x] **Vacuous test bulgusu:** `test_no_outbound_write_route_exists_...`
      hiçbir şey denetlemiyordu — FastAPI dahil edilen router'ları `path`
      taşımayan sarmalayıcılara sarıyor, karşılaştırma boş string'ler
      üzerindeydi; üç güvenlik testi boşa koşuyordu. Yollar artık
      özyinelemeli toplanıyor ve her çağıran bilinen bir yolu da iddia
      ediyor.
- [x] **Test emniyet ağı:** autouse fixture gerçek giden taşıyıcıyı devre
      dışı bırakıyor; `MockTransport` unutulursa test gürültüyle kırılıyor.
- [x] **1049 pytest** (823 → 1009 → 1049) + **155 Vitest** (130 → 155).
      Rapor: [`docs/verification/paket-d.md`](docs/verification/paket-d.md).
- [x] SI-83 bilinçli olarak değişti (görünür kayıtla, sessizce silinmedi);
      SI-73 daraltıldı; SI-129…SI-170, IMP-264…IMP-297.
- [x] **PR #13 bağımsız inceleme düzeltmeleri** (P0/P1 yok; yedi P2/P3
      bulgusu kapatıldı, +40 test):
      - yazma yanıtı `client.stream`+`iter_bytes` ile akış üstünde sınırlanır
        ve istenmeyen `Content-Encoding` hiç açılmaz (SI-163, SI-164);
      - iki giden istemcinin `transport` seam'i `httpx.MockTransport`'a
        daraltıldı — `HTTPTransport(verify=False)` enjekte edilemez (SI-165);
      - `signer.py`'nin iddia ettiği üretim-wiring testi gerçekten yazıldı
        (SI-166);
      - kasa parolası imzalama süresince redaksiyon registry'sindedir
        (SI-162);
      - `send`'in her ret yolu rezervasyonu defterde kapatır (SI-167);
      - kilitli sayaç veritabanı `NonceStorageError` → 409 olur, zırhlı 500
        değil (SI-168);
      - `/api/compose/sign` ve `/send` event loop'u tutmaz (SI-169);
      - test ağ kesicisi `socket.socket.connect` katmanını da kapsar ve
        docstring'i gerçeğe indirildi (SI-170).
      `ComposerPanel` parolayı imza hatasında bilinçli olarak state'te tutar;
      kod değiştirilmedi, gerekçe `docs/ui-action-map.md` §5.1'dedir.
- [x] **AC-13 ve AC-16** karşılandı. **AC-14 Paket E'dedir** — aşağıdaki
      "Kabul kriterleri" satırı yanlışlıkla AC-14'ü Aşama 4'e koyuyordu;
      `docs/evidence-model.md` onu Aşama 5'e koyar ve ADR-0002 §4.3 bu
      çelişkiyi Aşama 5 lehine kapatır.

### Paket E — Evidence & Audit (Aşama 5)

Kapsam kararları:
[`ADR-0003`](docs/decisions/0003-paket-e-kapsam-kararlari-2026-09-04.md).

- [x] **Üçüncü kapalı registry.** Pinli `openapi.json` bir export yüzeyi
      yayımlıyor (`GET /r/{room}/export`, bayt-exact NDJSON,
      `X-Room-Generation`), ama açıklaması **"No query parameters"** diyor —
      `Range`/`since`/`limit` yok. Bu yol `SOURCES`'a **eklenmedi**;
      `evidence_targets.py` açıldı, böylece altı belgelik registry'nin küme
      eşitliği ve `/r/` yasağı aynen geçiyor. `OUTBOUND_CLIENT_MODULES`
      iki'den üçe yazılı gerekçeyle genişledi.
- [x] **Akış tarayıcı**, 12 MiB cap: kendi satırımızın **ham baytları** +
      offset, satır ve bayt olarak sınırlı çevre penceresi, akışın yürüyen
      SHA-256'sı. Satır alındıktan sonra tamponlama durur — tepe bellek
      gövde boyutundan **bağımsız** (testle). Nonce keyfi hassasiyetli
      `int` (19 hane 2^53'ü aşar; float'a yuvarlanmış nonce iyi imzaları
      düşürür).
- [x] **Altı kanıt durumu**, hiçbiri tek yeşil rozete indirgenmedi:
      `line_captured` (yalnızca Seviye 2 gözlemi) / `line_not_found`
      (**hiçbir şey kanıtlamaz**) / `generation_changed` (karşılaştırılamaz)
      / `stream_truncated` / `parse_problem` / `fetch_failed`.
      `may_retry_write` her durumda `False`; `line_not_found` bir
      `outcome_unknown`'ı asla `not_sent`'e çevirmez.
- [x] **HMAC zinciri** ayrı DPAPI zarfındaki başıyla; yalnız-ekleme, asla
      budanmaz. Truncation **garanti diye sunulmuyor**: aynı-kullanıcı
      saldırısı testte fiilen uygulanıp zincirin `intact` döndüğü
      gösteriliyor. Uygulama sırasında gerçek bir hata yakalandı — SQLite
      naive datetime döndürdüğü için ham `isoformat()` MAC'e girseydi her
      zincir ilk doğrulamada bozuk okunacaktı (IMP-314).
- [x] **Secret taraması** allow-list önce, sonra red; SHA-256 digest'leri
      bilinçli olarak muaf tutulmadı. Eşleşme kanıt yazmasını **reddeder**,
      redakte etmez. Bağımsız inceleme sonrası allow-list bir *şekil* listesi
      olmaktan çıkıp **çağıranın bildirdiği tam değerler** oldu; red kuralları
      "en az" uzunluğa geçti (IMP-330, IMP-331).
- [x] **Export** JSON + Markdown, **koşulsuz** bayt bayt deterministik
      (`exported_at` gövdeden `X-Station-Exported-At` header'ına taşındı),
      onay yapısal (`acknowledged` varsayılansız → 422). Sunucu **hiçbir yola
      dosya yazmaz**; `downloads.py` dosya adlarını allow-list'ten kurar ve
      recovery indirmesindeki ham f-string boşluğunu da kapatır.
- [x] **Bağımsız incelemenin 18 bulgusu kapatıldı** (F1…F18). En ağırı:
      yasak-ifade denetimi bitmiş dışa aktarım belgesine uygulanıyordu, yani
      bir uzak hata gövdesi ya da kullanıcının kendi mesajı bir kaydı **her
      iki biçimden kalıcı olarak** çıkarabiliyordu — üstelik 500 olarak.
      Denetim artık yalnız **ürünün kendi cümlelerine** uygulanır; içe alınan
      metin veri sayılır ve nötrlenir (IMP-327…IMP-340).
- [x] **1229 pytest** (1049 → 1179 → 1229) + **206 Vitest** (155 → 206). Yeni
      HeroUI bileşeni yok (küme 11'de kaldı, A1-R1 yeniden açılmadı).
      Rapor: [`docs/verification/paket-e.md`](docs/verification/paket-e.md).
- [x] SI-171…SI-209, IMP-298…IMP-340.
- [ ] **ADR-0003 §7'nin silme yarısı ertelendi.** Kanıt kaydını silen bir
      route yoktur ve ölü `EVIDENCE_DELETED` enum girdisi kaldırıldı; erteleme
      IMP-329 ve `docs/evidence-model.md` §4'te görünür şekilde kayıtlıdır.
- [x] **AC-14** karşılandı.
- [x] Aşama numarası tutarsızlığı kapatıldı: API `stage=4`, launcher
      `stage=3` diyordu; ikisi de **5** oldu.
      `write_available_from_stage` bilinçli olarak **4** kaldı.


### Paket F — proje/görev modülü temeli (Aşama 6, kod aşaması 6)

Kapsam kararları:
[`ADR-0004`](docs/decisions/0004-paket-f-kapsam-kararlari-2026-09-04.md).
Uygulanmış hâlin tarifi: [`docs/task-modules.md`](docs/task-modules.md).

Bu bir **temel** paketidir: görünür bir görev yüzeyi açmaz. Görev katmanının
HTTP route'u yoktur ve `work-scan` / `tasks` / `activity` bölümleri
`ready: false` kalır (ADR-0004 §9). `apps/station-web` kaynağına
dokunulmadı.

- [x] **Derleme zamanı registry.** `station_api/modules/` dört kayıt taşır:
      `project_zero` (`available`) ve H1/H2/H3'ün açacağı üç `planned` kayıt.
      **Proje 0 taşınmadı** — kayıt `owners` alanıyla kimlik, recovery,
      conformance, technocore, compose ve evidence modüllerine işaret eder ve
      bir test her adın gerçekten bir dosyaya çözüldüğünü doğrular.
      Diskten plugin/import yükleme yolu **yoktur**; bir test iki paketin
      sözdizim ağacını **dört yazım** için tarar — yasak import, yasak bare ad
      (`runner = __import__`), yasak attribute (`builtins.__import__`) ve
      yasak ad alanı (`sys.modules`, `getattr(builtins, ...)`). `compile`'ın
      yalnız bare adı yasaktır; `re.compile` serbesttir. Taramanın kendisi on
      sentetik atlatmayla test edilir (künye ADR-017 böylece ilk kez gerçekten
      uygulanmış oldu).
- [x] **Çekirdek yeniden kullanıldı, kopyalanmadı.** `station_api/tasks/`
      yalnız yeni koddur; bağımlılığı constructor'dan alır ve `app.py` onu
      mevcut `engine` ile kurar. **Yeni HTTP istemcisi yok**
      (`OUTBOUND_CLIENT_MODULES` üçte kaldı), **ikinci vault/signer yok**,
      **ikinci gate yok**: `tasks/gate.py` `write_gate.evaluate()`'in
      saf-fonksiyon kalıbını izler ve onun `CheckState`'ini **import eder**.
      Üçü de testle sabitlendi.
- [x] **Dokuz durum, açık geçiş tablosu.** `ALLOWED_TRANSITIONS` makineyi
      tek yerde yazar (bundan önce kurallar DB kısıtlarına ve bir alışkanlığa
      dağılmıştı) ve `validate_transition` saf bir fonksiyondur.
      **Dürüstlük şartı karşılandı:** `suggested` (H1 ister), `running` ve
      `paused` (H2 ister) tanımlı kalır fakat **hiçbir kod yolundan
      üretilemez**. Bunu **bir davranış ve bir yapı** testi birlikte sabitler
      (bağımsız inceleme düzeltmesi, aşağıda): yürüyüş `TaskService`'in her
      public metodunu introspection ile sürer, tarama ise `.state`'e yazan tek
      yerin `transition` olduğunu denetler. Beklenen küme testin içinde elle
      yazılıdır, böylece sabiti düzenlemek oracle'ı büyütmez.
- [x] **Dört ayrı alan.** Görev çıktısı / test sonucu / kullanıcı kabulü /
      public paylaşım dört ayrı sütun grubudur (`_ref_id`, `_verified`,
      `_version_id`, `_detail`, `_recorded_at`) — `EvidenceRecord`'un dört
      seviye kalıbı. **Public paylaşım alanı temsil edilemez:**
      `EvidenceRef` onun için kurulamaz, servis reddeder, kapı daima
      `not_implemented` raporlar — ve yayımı **engellemez** (aksi hâlde hiçbir
      görev dışarı paylaşılmadan tamamlanamazdı). `ready_to_publish` gerçek
      kanıttan türer: `verified` varsayılansızdır, doğrulanmamış bir kayıt
      `blocked`'tır ve "bir kaydın varlığı tek başına başarı değildir" cümlesi
      testle kanıtlanır.
- [x] **Deduplication.** `domain_digest(b"technocore-station/task-source/v1",
      source_id, content_sha256)` → `source_version_id`. Kaynak kimliği
      **registry enum'undan** gelir; `StrEnum` her `isinstance(str)`
      kontrolünden geçtiği için çalışma zamanında açık bir enum kontrolü
      yapılır. İçerik değişince kimlik değişir ve **eski kanıt eşleşmez** —
      test aynı kanıtı yeni sürüme sunar ve gerekçeli reddi doğrular.
- [x] **Restart uzlaştırması: okur, yazmaz.** Keşif bulgusu doğrulandı —
      `WriteOutcomeValue.IN_FLIGHT` Paket D'den beri yazılıyor ve hiçbir
      başlangıç hook'u okumuyordu. `tasks/reconciliation.py` tek bir `SELECT`
      yapar. **Sıfır iddiası ölçülerek kanıtlandı:** httpx taşıyıcısı ve
      `socket.connect` sarılıp denemeler sayıldı; hem taramada hem gerçek
      `create_app` çağrısında sayı **0**. Defter bayt bayt aynı kalır, satır
      hâlâ `in_flight`'tır, `resumed_any` **kurucu argümanı olmayan** bir
      property'dir (bağımsız inceleme düzeltmesi).
- [x] **Bütçe YOK ve erteleme görünür.** Bütçe alanı açılmadı;
      `budget_available: Literal[False]` + `budget_detail` ertelemeyi söyler
      (composer'ın `note_lane_available` kalıbı). Bir test görev/registry
      paketlerinde bütçe biçimli sütun veya tanımlayıcı olmadığını, bir
      diğeri de ertelemenin `docs/task-modules.md` §6'da kayıtlı olduğunu
      denetler. **Kalan yarım gereksinim:** harcama bağlamı Paket G'ye,
      bütçe/izin sınırı Paket H2'ye ertelendi.
- [x] **Migration `0007`** (`down_revision="0006"`, tek head), yalnız ekleme:
      `task_record`, `task_evidence_outcome`, `task_state_transition`. Hiçbir
      mevcut tablo adı, sütun veya kayıt kimliği değişmedi. Görev
      tablolarında sütun adı denetimi şema geneli kuraldan daha sıkıdır —
      `key` parçası da yasaktır.
- [x] **Şemalar `schemas.py`'de kaldı** (ADR-0004 §8). `test_no_secret_fields.py`
      `vars(schemas)` tarıyor; modelleri yeni bir modüle koymak üç korumayı
      sessizce kapsam dışı bırakırdı. Onları dolduran saf projeksiyon
      `station_api/tasks/views.py`'dedir, böylece modeller kullanılmadan
      durmaz.
- [x] **`docs/architecture.md` gerçekle uzlaştırıldı** (ADR-0004 §10). Belge
      "Conformance, Technocore istemcisi ve Evidence katmanları henüz
      **yoktur**" diyordu; üçü de merge edilmişti. Durum satırı, paket
      tablosu, mimari diyagramı, tablo listesi ve "bilinçli olarak
      yapılmayanlar" bölümü güncellendi.
- [x] **1331 pytest** (1229 → 1331; **102 yeni test**), üç yeni güvenlik
      dosyası: `test_module_registry.py` (32), `test_task_states.py` (23),
      `test_task_evidence.py` (47). Yeni bağımlılık yok, yeni marker yok,
      yeni HeroUI bileşeni yok, frontend kaynağına dokunulmadı.
- [x] SI-210…SI-232, IMP-341…IMP-365.

#### Bağımsız inceleme düzeltmeleri (PR #15)

Bağımsız bir düşman incelemesi on bir bulgu çıkardı; hepsi kapatıldı ve her
düzeltme **mutasyonla** doğrulandı (bozulan kod, kırılan test):

| Bulgu | Ne yanlıştı | Düzeltme |
|---|---|---|
| F-1 (P1) | "Hiçbir kod yolu üretemez" testi yalnız `transition()` üzerinden arıyordu; incelemenin dört satırlık `start_running` probu hiçbir testi kırmadı | yürüyüş her public metodu introspection ile sürer **ve** `.state`'e yazan tek yerin `transition` olduğunu bir AST testi sabitler |
| F-2 (P2) | Oracle sabitin kendisiydi: `PRODUCIBLE_STATES`'e `RUNNING` eklemek hem reddi kaldırıyor hem beklentiyi büyütüyordu | beklenen küme testte elle yazıldı (`EXPECTED_PRODUCIBLE`); sabit ayrı satırda denetlenir |
| F-3 (P2) | `modules/completion.py`'nin bayat-kanıt dalı hiç test edilmiyordu (`if False` → sıfır kırık) | doğrulanmış ama başka sürüme bağlı referansla dalı doğrudan süren iki test |
| F-4 (P3) | `_refs_from_row` docstring'i "raise eder" diyordu; gerçekte sütunu okumadan atlıyor | cümle gerçeğe indirildi ve davranış testle sabitlendi |
| F-5 (P3) | `resumed_any` sıradan bir alandı; `Literal[False]` yalnız Pydantic modelindeydi ve `views.py` değeri hiç okumuyordu | property'ye çevrildi (kurucu argümanı yok) ve projeksiyon değeri rapordan okur |
| F-6 (P3) | `ref_id` süpürülmüyor ve sınırlanmıyordu; bidi/NUL/406 karakter yanıta kadar ulaşıyordu | süpürülür ve 64'e kesilir; boşa inen işaretçi reddedilir |
| F-7 (P3) | Dinamik yükleme yasağı `builtins.__import__`, `getattr(builtins, ...)` ve `sys.modules`'u yakalamıyordu | tarama dört yazımı arar; on sentetik atlatma ve dört masum yazım testlidir |
| F-8 (P3) | Registry ve test docstring'i "iki" diyordu; sayılan üçtü | üçe düzeltildi |
| F-9 (P3) | `TaskGateStatus(checks=()).ready_to_publish` boş `all()` yüzünden `True` idi | küme eşitliğine çevrildi; boş küme `False` |
| F-10 (P3) | `cli/__main__.py` hâlâ `stage=3` idi | `6`'ya çekildi; bir test üç üretim çağrısının aynı sayıyı taşımasını ister |
| F-11 (P3) | Geçersiz `module_id` çıplak `KeyError` üretiyordu (geçersiz kaynak ise temiz ret) | `ModuleRegistryError` (bir `KeyError`) → `TaskError(reason="module_unknown")` |

**Bu pakette bilinçli olarak yapılmayanlar:** görev HTTP route'u ve görünür
yüzey (H1/H2), öneri üreticisi ve yürütücü, dış paylaşım (H3), bütçe (G/H2),
kanıt silme route'u (ADR-0003 §7'nin ertelenmiş yarısı, IMP-329).
### Paket G — OpenCode Go baglantisi (Asama 7, kod asamasi 7)

Kapsam kararlari:
[`ADR-0005`](docs/decisions/0005-paket-g-kapsam-kararlari-2026-09-04.md).
Tarayici QA: [`ADR-0006`](docs/decisions/0006-tarayici-qa-kapsama-alindi-2026-09-04.md).

- [x] **Sozlesme resmi belgeden dogrulandi** (prompt 11.1 sart kosuyor).
      Dogrulanan: uc protokol yolu, base URL, katalog endpoint'i, kullanim
      limitleri, "Use balance"in konsolda oldugu, veri saklama/egitim
      tablosu, `x-opencode-session` zorunlulugu, `opencode-go/` on ekinin
      provider on eki oldugu. **Dogrulanamayan ve uydurulmayan:** auth
      header'i, uc ailenin govde sekilleri, streaming/tool-call formati,
      hata govdeleri.
- [x] **Streaming ve tool-call YOK** (ADR-0005 §2) - sozlesmesi
      yayimlanmamis; yazmak tahmin olurdu. Tipleri `false` oldugu icin
      sonraki bir duzenleme `true` atayamaz.
- [x] **Auth header'i beyan edilmis, dogrulanmamis varsayim** - tek yerde,
      etiketli ve kullaniciya gorunur.
- [x] **"Baglantiyi denetle" yesil rozet uretemez**: durum kumesinde
      `verified` yok, UI ton haritasinda `ok` girdisi yok. Katalog
      anahtarsiz cevap verdigi icin listeyi cekmek anahtari dogrulamaz.
- [x] **Kendi kendini kapatan hata yakalandi ve duzeltildi:** ilk uygulama
      belgenin protokol ailesini soylemedigini varsayip 34 modelin hepsini
      `unverified` isaretledi ve **hicbir model secilemez** hale geldi -
      yani ozellik promptun yasakladigi "gostermelik API kutusu" durumuna
      dustu. Belge model basina endpoint yayimliyor (27 satir) ve kod
      `grok-4.6`'yi yanlis aileye koymustu. **Sekiz test yanlis iddiayi
      sabitliyordu**; yeniden yazildi ve 27 satir testte bagimsiz olarak
      yeniden bildirildi. SI-256 bu gerilemeyi sabitler.
- [x] **Dorduncu giden istemci** gerekcesiyle acildi; allow-list duz
      kumeden `{dizin: {modul}}` haritasina donustu. SI-71 Technocore
      istemcilerine, SI-48 seed/private key/recovery'ye **daraltildi** -
      ikisi de gevsetilmedi.
- [x] **Credential ayri DPAPI zarfinda**, audit zarfinin sekliyle ve tek
      bilincli farkla: **anahtar uzerine yazilabilir** (kullanici
      degistirebilmeli). Saklanan anahtari geri gosteren endpoint YOK.
      TEST-ONLY canary ile yedi yuzey taraniyor.
- [x] **Butce acilmadi** (ADR-0005 §9): `budget_available: Literal[False]`
      degismedi. "Sinirsiz" denmiyor, bilinmeyen maliyet `unknown`,
      "Use balance" saglayici konsoluna havale ediliyor.
- [x] **Verilen soz bilincli revize edildi**: ekranda tam olarak **bir**
      maskeli alan olabilir ve o provider anahtaridir; seed/private
      key/recovery icin hicbir frontend istisnasi yok. Test daraltilarak
      guclendirildi.
- [x] **Tarayici QA kapsama alindi** (ADR-0006, kullanici talimatiyla
      ADR-0001 §4 tersine cevrildi): Playwright 1.62.1 tam pin, yalniz
      Chromium, `npm audit` 0 acik. **51 e2e testi**, bes ardisik kosuda
      51/51, kararsizlik yok. **A1-R1 sonucu: CSP ihlali YOK** - pinli
      React Aria hash'i gecerli ve test bosa gecemiyor. Dis aga sifir istek
      **olculdu** (negatif kontrol testiyle). CI'a ayri `browser` isi eklendi.
- [x] **1514 pytest** (1331 -> 1514) + **230 Vitest** (206 -> 230) +
      **51 Playwright**. Rapor:
      [`docs/verification/paket-g.md`](docs/verification/paket-g.md).
- [x] SI-233...SI-256, IMP-366...IMP-378. Asama numarasi dort yerde 6 -> 7.
- [ ] **Acik bulgu (sabitlendi, duzeltilmedi):** baslik hiyerarsisi
      h1 -> h3 atliyor (HeroUI `Card.Title` `<h3>` render ediyor).
      Duzeltmek MCP dogrulamasi gerektiriyor (CLAUDE.md kural 7).
- [ ] **Bilinen bosluk:** `e2e/**` lint edilmiyor (eslint config bir depo
      hook'u tarafindan yazmaya kapali); telafi olarak `tsc -b` kapsiyor ve
      bir suite-discipline testi disiplini zorluyor.

### Paket H1 - Work Scan (Asama 8, kod asamasi 7)

Kapsam kararlari:
[`ADR-0007`](docs/decisions/0007-paket-h1-kapsam-kararlari-2026-09-04.md).

- [x] **Kibble'a hicbir istek atilmadi, istemci yazilmadi.** Okuma
      endpoint'leri belgelenmis ama `job` semasi, sayfalama, rate limit,
      kullanim kosullari ve isletmeci **dogrulanamadi**; `/api/board`
      sayfalamasiz ~77 bin kayitla 60 sn'de timeout oldu. Sema bilinmeden
      adapter yazmak alan adi uydurmaktir. `support_unverified` kaydi;
      `adapter_written`/`contacted` turetilmis ozellik ve daima `False`.
      Servisin kendi cumlesi: "Kibble is not FLOP Network and not
      Technocore. It settles nothing."
- [x] **Aday uretimi deterministik**; model cagrisi H2'ye ertelendi.
      Gerekce yalniz harcama yasagi degil: deterministik cikarimda
      uydurulacak alan yoktur. Bedeli kullaniciya **gosteriliyor**.
- [x] **Sekiz oge yapisal olarak zorunlu** — eksik aday insa edilemiyor;
      "tahmin" etiketi dusurulemez; sekizinci ogede **hicbir boolean yok**
      ve UI'da "acik/kapali" rozeti yok.
- [x] **Dorduncu kapali registry + besinci istemci.** `/r/events` kapsam
      disi (sema `parameters: null`). Ilk kez sorgu dizesi gonderiliyor,
      bu yuzden hazir sorgu tasiyan URL reddediliyor; basari olcutu status
      degil **Content-Type**.
- [x] **Polling yok**, bayatlik esigi **uydurulmadi** (olculen an +
      sunucunun kendi 3 sn beyani), ring dususu **ayri** sinyal.
- [x] **Ucuncu otorite seviyesi** (`community`): yollar seviye 1, icerikleri
      seviye 3. `topic` bir onay degil; `did:key` olmayan `from` "kendi
      beyan ettigi takma ad".
- [x] `SUGGESTED` uretilebilir oldu; **`INITIAL_STATE` degismedi**.
      `PUBLIC_ROOM_SCAN` kaynak kimligi eklendi — kullanicinin kendi gorevi
      ile taranmis aday iki katmanda ayrisiyor.
- [x] **1692 pytest** (1555 -> 1692) + **255 Vitest** (233 -> 255) +
      **58 Playwright** (53 -> 58). Yeni HeroUI bileseni yok. Rapor:
      [`docs/verification/paket-h1.md`](docs/verification/paket-h1.md).
- [x] SI-271...SI-281, IMP-386...IMP-402.
- [ ] **Kalan:** ring dususu telde yok (alan uydurulmadi, yoklugu yazili);
      sinyal tablosu kaba ve recall'u olculemiyor; tarama 10 oda icin
      ~6,8 dk surebilir ve iptal kontrolu yok.


#### Paket H1 - PR #17 dusman inceleme turu (5 Eylul 2026)

Bagimsiz bir inceleme yedi bulguyu **ham prob ciktisiyla** kanitladi. Hepsi
kapatildi; her duzeltme testle ve **mutasyon kontroluyle** kanitlandi
(on uc mutasyon, hepsi en az bir testi kirmiziya dondurdu; kayit
[`docs/security-invariants.md`](docs/security-invariants.md) §9i).

- [x] **P1 - Yanit taramanin kapsamini yeniden adlandiramaz.** `room`
      yanittan okunuyor ama hicbir sey onu cozumlenmis hedefle
      karsilastirmiyordu: her oda `{"room": "lobby"}` donunce urun kapsami
      `["lobby"]` diye raporluyor, aday referansina ve fayda cumlesine o adi
      yaziyor, kimligi ondan uretiyordu (iki farkli oda tek adaya cokuyordu).
      `parse_room_messages` artik cozumlenmis odayi **zorunlu** argüman
      olarak aliyor ve uyusmazlikta belgeyi reddediyor; reddetme mesaji
      yanitin sectigi adi **tekrarlamiyor** (INV-05). SI-282, IMP-403.
- [x] **P2-A - Iki mutasyon hayattaydi.** `adapter_written`/`contacted`
      `True` yapilinca **0** test kirmizi donuyordu: rota bu alanlari hic
      gecirmiyor, tel degeri semadaki `Literal[False]` varsayilanindan
      geliyordu. Rota artik kaydin kendi ozelligini okuyor ve `True` bir
      kaydi serilestirmeyi reddediyor; ayrica dogrudan iddia eden bir test
      var. Ayni turda Kibble'in iki Ingilizce cumlesi **tele** tasindi.
      SI-281, IMP-407.
- [x] **P2-B - Alti yasak bicim "yapisal" degil, kalip listesiydi.**
      On dokuz satir listeyi asiyordu (`w a l l e t`, `wal-let`, sifir-genislikli
      karakterler, yumusak tire, Kiril `а` ile `claim`/`cuzdan`, ve listede
      olmayan es anlamlilar). `fold()` bicim karakterlerini siliyor ve benzer
      harfleri esliyor; yasak kapisi ayrica ayraclari atilmis bir samanlikta
      esliyor; es anlamlilar eklendi. **Ve cumle gercege indirildi**: ADR,
      belge ve **kullanicinin gordugu yuzey** artik "kalip eslesmesiyle
      reddedilir" diyor (`prohibition_statement`). SI-283, IMP-406, IMP-408.
- [x] **P2-C - Oda politikasi artik uc katmanda.** `RoomScanTarget` duz bir
      frozen dataclass'ti; elle kurulan bir hedef `/r/lobby`'ye surulebiliyor
      ve URL kontrolunun her maddesini geciyordu. `__post_init__` ve
      `assert_allowed_url` politikayi yeniden uyguluyor. SI-282, IMP-404.
- [x] **P2-D - `ts` alani olmayan bir satir artik taramayi dusurmuyor.**
      Eskiden `CandidateError` servisin oda basina `try`'inin disindan
      firliyor ve on odalik bir tarama HTTP 500 donuyordu — okunmus butun
      odalar cope. Satir basina reddediliyor (`unusable_source`); servis oda
      basina, rota tarama basina (502) yedekliyor ve iki yedek **hata
      enjeksiyonuyla** suruluyor. SI-284, IMP-405.
- [x] **P3'ler.** `WorkCandidate.__post_init__`'in bes zorunlu cumlesi ve
      kimlik kontrolu artik testli (once 0 test kapsiyordu);
      `assert_allowed_query` buyuk/kucuk harf duyarsiz (`WAIT` reddediliyor);
      tekrarlanan `seq` sessizce dusmuyor, `duplicate_sequence` gerekcesiyle
      gosteriliyor; zamanlayici/long-poll statik taramasi
      `routes/workscan.py`'yi de kapsiyor; Kibble alintilarinin nerede
      tasindigina dair belge yanlisi duzeltildi (tel genisletildi).
- [x] **1769 pytest** (1692 -> 1769) + **256 Vitest** (255 -> 256) +
      **58 Playwright**. Yeni HeroUI bileseni yok, yeni bagimlilik yok.
- [x] SI-282...SI-284, IMP-403...IMP-408. SI-273, SI-278, SI-279 ve SI-281
      metinlerindeki yanlis iddialar **duzeltildi**, silinmedi.

### Paket H2 - Agent calisma ortami ve Activity Desk (Asama 9, kod asamasi 8)

Kapsam kararlari: [ADR-0008](docs/decisions/0008-paket-h2-kapsam-kararlari-2026-09-05.md).
Dogrulama raporu: [docs/verification/paket-h2.md](docs/verification/paket-h2.md).

- [x] **Keyfi kod/shell yurutmesi KAPALI.** Olcum yapildi (Docker Desktop
      4.89.0 kurulu ve daemon acik, WSL2 var, Windows Sandbox yok, Hyper-V
      yonetim yuzeyi yok, kullanici local admin degil, optional feature
      durumlari admin gerektigi icin **olculemedi**) ve yurutme yine de
      kapatildi: Docker **kullanicinin kurulumudur, urunun degil**, ve
      konteyner calistiran bir yol CI'da dogrulanamaz. Hicbir sey kurulmadi,
      hicbir konteyner calistirilmadi. Urun kaynaginda `subprocess`/`exec`/
      `eval`/`os.system` **hala yok**.
- [x] **`execution_unavailable` bir durum gerekcesi** ve UI'da olculen
      envanterle gosteriliyor; `not_measured` ile `absent` **ayri** tutuluyor.
      Test sonucu alani `not_implemented` kaldigi icin gorev
      `ready_to_publish`'e **gecemiyor** - calistirilmamis kod test edilmis
      sayilmaz.
- [x] **Model lane'i kapali kaldi.** `tool_calls_supported: Literal[False]`
      degismedi, `post_completion` produksiyonda cagrilmiyor,
      `OUTBOUND_CLIENT_MODULES` **beste kaldi**. Tool-call wire formati hala
      yayimlanmamis (ADR-0005 §1.2).
- [x] **Arac semasi Station'in altinci kapali registry'si**: derleme zamani
      tuple, sekiz arac, tipli parametreler, **`path`/`url` parametresi yok**.
      Durdur/devam bilerek arac degil. Kayitsiz kimlik gosterilebilir bir ret
      donduruyor.
- [x] **Guven siniri:** git, PR, merge, paket kurulumu, ayar duzenleme, izin
      listesi ve plugin registry'de **yok** ve bu **import zamaninda**
      denetleniyor (ekili `git_commit` kaydiyla suruldu). SI-213'un yasagi
      yeni `agent/` paketine **tasindi**.
- [x] **Butce acildi**: arac cagrisi (32), duvar saati (120 sn), eszamanlilik
      `Literal[1]`. Token ve para birimi **gerekcesiyle reddedildi** ve telde
      `refused_units` olarak **yayimlaniyor**. "Agent kendi butcesini
      yukseltemez" uc kilitle yapisal; dort yazimi tarayan AST testi ekili bir
      yaziciyla suruldu. `tasks/` ve `modules/` **hic dokunulmadi**.
- [x] **Workspace savunmasi sifirdan**: ad allow-list'ten yeniden kurulur ve
      yeniden yazilacaksa **reddedilir**; `resolve()` + `is_relative_to`;
      `is_symlink()` **ve** `os.path.isjunction()` ile koke kadar yuruyus;
      tavanlar diskten okunur. **Arsiv acma yolu hic yok.** 15 dusmanca ad,
      iki gorev arasi okuma, yaprakta ve ust dizinde bag - hepsi reddedildi.
- [x] **`RUNNING`/`PAUSED` acildi**; `ALLOWED_TRANSITIONS` ve `INITIAL_STATE`
      **degismedi**; `UNPRODUCIBLE_STATES` bosaldi. Bosalan uc test
      **sessizce birakilmadi** - saf-fonksiyon testi artik mekanizmayi
      suruyor, bos `parametrize` kaldirildi, yanlis adlandirilmis test
      duzeltildi. `STATE_DETAIL`'in yalan olan iki cumlesi duzeltildi.
      `_state_writers` taramasi `agent` paketini de kapsiyor.
- [x] **Activity Desk**: ayri yalniz-ekleme tablo, kendi retention'i (500),
      satirlari zincir halkasi **degil**. Zincire yalniz **bes karar noktasi**
      giriyor. `chain_referenced` append basarili olduktan **sonra** yaziliyor
      ve isaretli satir budanamiyor. Silme bir audit olayi ve sonrasinda
      zincir `INTACT` dogrulaniyor. Modelin muhakemesi/ham payload icin
      **sutun yok**.
- [x] **Frontend**: `Gorevler` ve `Aktivite` birlikte acildi.
      `HIDDEN_SECTIONS` artik elle yazilmis liste degil, `SECTIONS`'tan
      **turetiliyor** ve boslugu kendi adlandirilmis iddiasi olarak
      olculuyor; `never shows a section that is not ready` testinin govdesi
      **degismedi**. On dort eylem, on dort etiket; yuk tasiyan bes olay
      benzersiz **etiket sayisiyla** test ediliyor. Sahte progress yok.
- [x] **Mutasyon gercek bir kusur yakaladi**: `activity._clean` denetimden
      **once** notruyordu ve guard'i sessizce no-op yapiyordu (IMP-420).
      Ayrica guard silme (3 kirmizi), reparse-point yuruyusu silme (2),
      `_assert_plan_intact` silme (1), `safe_name` yeniden adlandirma (17).
- [x] **1992 pytest** (1769 -> 1992) + **289 Vitest** (256 -> 289) +
      **65 Playwright** (58 -> 65). Yeni HeroUI bileseni yok (kume 11'de),
      yeni bagimlilik yok. Asama numarasi bes giris noktasinda `7 -> 8`.
- [x] `docs/task-modules.md`'nin eskiyen uc yuzeyi (modul tablosu iki satir,
      "uretilemeyen uc durum", butce ertelemesi) **kaydedilerek** guncellendi.
      Ayrica `docs/architecture.md` ve `docs/agent-runtime.md`'nin H2 gercegi
      tarafindan yalanlanan bes cumlesi duzeltildi.

#### Paket H2 - PR #18 dusman inceleme turu (5 Eylul 2026)

**53 mutasyon, 42 oldurulen, 11 hayatta kalan.** Hayatta kalan her mutasyon
bir bulguya donustu; **on ucunun hepsi kapatildi.** Ayrintili tablo:
[docs/verification/paket-h2.md](docs/verification/paket-h2.md).

- [x] **P1 - reparse savunmasi KORDU.** Yuruyus **cozulmus** yol uzerinde
      kosuyordu ve `resolve()` bagi zaten erittigi icin hicbir gercek reparse
      point'i goremiyordu. Incelemeci `mklink /J` ile - **admin gerekmeden** -
      olctu: workspace kokunun kendisi junction oldugunda `read_text` icerigi
      donduruyor, `list_files` listeliyor, `ensure_workspace` itiraz
      etmiyordu. Reddi **containment** yapiyordu (`workspace_escape`), o
      yuzden CI'da `assert 'workspace_escape' == 'workspace_reparse_point'`
      dustu. Yuruyus artik cozulmemis yolda ve `<data_dir>/workspace`'te
      duruyor; mutasyon yine 2 kirmizi ama **ikisi de gercek junction diken
      test** (eskiden ikisi de monkeypatch'li dalidi).
- [x] **Duzeltme sirasinda ikinci kusur cikti:** `service._discard` reparse
      yuruyusu olmadan `unlink` cagiriyordu - geciken bir yanitin temizligi
      bag uzerinden silebilirdi. `workspace.remove_file`'a tasindi.
- [x] **P1 - containment denetimini 1974 testin hicbiri oldurmuyordu**
      (`if False:` -> tum suite yesil), cunku onu surdugunu iddia eden test
      katman 1'e takiliyordu. Iki test eklendi (biri `safe_name`'i atlayarak,
      biri root icinde disari bakan **gercek** junction'la); 0 -> 2 kirmizi.
- [x] **P2 - IMP-420'nin duzeltmesi testsizdi.** `neutralise` silindiginde
      tum suite yesildi ve kullanici bir argüman anahtarina yasak ifade
      yazarak urunu 500'e surebiliyordu. 0 -> 2 kirmizi; notrlemenin **yonu**
      (servis evet, activity hayir) AST ile sabitlendi.
- [x] **P2 - `execution_unavailable` uyesi hicbir kod yolundan
      uretilemiyordu** ve bu, ayni diff'in `evidence/audit.py`'ye yazdigi
      "her uye gercek bir kod yolundan kaydedilebilir" kuralini ihlal
      ediyordu. Gercek bir yola baglandi: registry **once** reddediyor, sonra
      ad bir komut gibi okunuyorsa ayri ret. Mutasyon 2 kirmizi.
- [x] **P2 - `.allowed` ve `ARBITRARY_EXECUTION_SUPPORTED` dekoratifti**;
      tel `schemas.py`'de elle sabitlenmisti ve modul sabitiyle bagi yoktu.
      Tureti tersine cevrildi; sabiti degistirmek 0 -> **6 kirmizi**.
- [x] **P2 - registry degismezlik taramasi zayifti**: `_BY_ID[x] = y` ve
      `globals()[...]` yazimini goremiyordu ve yalniz `tools.py`'yi
      okuyordu (docstring'i "anywhere in the package" diyordu). Alti yazim
      bicimi + tum paket; ekili mutatorle suruldu.
- [x] **P2 - "seed taramasi workspace'i otomatik kapsiyor" YANLISTI.**
      `ensure_workspace` o testlerin fixture zincirinde hic cagrilmiyordu,
      yani tarama hicbir workspace dosyasi gormuyordu. Iddia geri cekilmedi,
      **gercek yapildi**: iki tarama artik gercek bir workspace artefakti
      okuyor ve canary ile suruldu.
- [x] **P3'ler:** import zamani cagri yeri korunmuyordu (0 -> 1); `purpose`
      taranmiyordu; retention yorumu kodla celisiyordu (**kod cumleye
      uyduruldu**, cunku zincir buyudukce kuculen bir sinir kimsenin
      sectigi bir sinir degil); `ToolParamType.JSON_TEXT` olu, kaldirildi;
      uc guard'in (faz, `MAX_PLAN_STEPS`, tavan degeri) davranissal testi
      eklendi - tavan artik sabitle karsilastirilmiyor, 32 adim kosulup
      33'uncu reddedilerek suruluyor.
- [x] **Incelemeci de iki yerde yanildi ve bu olcerek gosterildi:**
      `ARBITRARY_EXECUTION_SUPPORTED` zaten `Literal[False]` idi;
      `get_tool`'un dali olu degil (zaten 1 kirmizi veriyor).
      `MAX_NAME_CHARS`'in teshisi de yanlisti - dal erisilebilirmis, ama iki
      dal **ayni gerekceyi** donduruyordu, o yuzden test ayirt edemiyordu;
      kendi gerekcesini aldi ve SI-288'in "asiri uzunluk" kaniti artik
      gercekten uzunluga dair.
- [x] **Bu paketin kendi raporunda iki yanlis iddia duzeltildi:** "`tasks/`
      ve `modules/` hic dokunulmadi" (olcum: 201 ekleme; kastedilen "butce
      alani eklenmedi" dogru ve testle korunuyor) ve `safe_name` mutasyonu
      "17 kirmizi" (olcum: 18).
- [x] **Incelemecinin olcmedikleri** raporda acikca yazildi: Playwright
      kosulmadi, dort kapi kosulmadi, **iceri bakan gercek dosya symlink'i
      olculemedi** (bu makinede `WinError 1314`), migration SQL'i okunmadi.
      Bunlar orkestrator tarafindan ayrica kosuldu.

### Paket H3 - Kanit calisma alani (Asama 10, kod asamasi 9)

Kapsam kararlari: [ADR-0009](docs/decisions/0009-paket-h3-kapsam-kararlari-2026-09-05.md).
Dogrulama raporu: [docs/verification/paket-h3.md](docs/verification/paket-h3.md).
Uygulama ayrintisi: [docs/proof-workspace.md](docs/proof-workspace.md).

- [x] **`public_share` doldurulabilir oldu - kosulu yapisal.** Alan yalniz
      **arsivlenmis bir gonderimin kanit kaydi kimligiyle** isaretlenebilir ve
      bunu birbirinin yerine gecmeyen **uc** kontrol saglar: yapici **sekli**
      (32 kucuk harf hex), servis **satirin varligini**, `ProofService` de
      kaydin **kendi `write_outcome` degerini** denetler. `outcome_unknown`
      donmus bir gonderim kaydediliyor fakat **dogrulanmis sayilmiyor**.
      `PUBLICATION_FIELDS` **ucte kaldi**: yayimlamadan da bir gorev
      tamamlanabilir.
- [x] **Acilan alan bir okuma yolunu kirabilirdi ve kirmadan once yakalandi.**
      Alan kapaliyken `_refs_from_row` sutunlari **okumadan** atliyordu; alani
      acmak o yolu yukselten bir yapiciya cevirdi ve elle duzenlenmis bir
      satir o gorevin **her okumasini** (listeleme dahil) dusururdu.
      `except EvidenceFieldError: continue` eklendi; davranis ayni kaldi, test
      artik ikinci bir kod yolunu kapsiyor.
- [x] **Bosalan dort dal sessiz birakilmadi.** `UNFILLABLE_FIELDS` bosaldi ve
      onu okuyan dort dal (kapi, satir okuyucu, modul tamamlanmasi, yapici)
      olu kalirdi. Mekanizma **gercekten doldurulabilir** bir alan
      (`test_result`) test suresince kapatilarak suruluyor - ve her testin
      **ilk yarisi** kapatmadan once ayni yolun izinli oldugunu okuyor, yoksa
      "her seyi reddeden" bir fonksiyon da gecerdi.
- [x] **Son `PLANNED` kayit acildi ve testi vacuous birakilmadi.**
      `proof_workspace` acilinca planli-modul testinin uc `assert`'i hic
      calismayacakti. Sozlesme bir fonksiyona cikarildi ve testte kurulan
      kayitlarla suruluyor (gecerli bir `planned` kayit **kabul** ediliyor,
      dort bozuk sekil **reddediliyor**); "artik planlanan modul yok" kendi
      adlandirilmis iddiasi oldu. `test_work_scan_candidates.py`'nin ayni
      sekle sahip testi de kaydi test suresince `PLANNED` yaparak suruluyor.
- [x] **Paket hicbir yere yazilmiyor.** Iki bicim (kanonik JSON + Markdown),
      `Content-Disposition`, yeni dosya koku yok, **zip yok**. Pakette
      `zipfile`/`shutil`/`gzip` importu, `symlink`/`write_text`/`mkdir`/`open`
      adi ve arsiv/baglanti bicimli **isim** tasiyan fonksiyon yok. Paket
      kurulup iki bicimi uretilip teslim edildikten sonra calisma alani dizini
      **bayt bayt ayni** - paket kendi hash'inin girdisi olamiyor.
- [x] **Determinizm kosulsuz.** Belgede kopyanin alindigi ani soyleyen alan
      yok; o an `X-Station-Delivered-At` basliginda. Burada bu kanit disa
      aktarimindakinden daha baglayici: tek kullanimlik onay paket ozetine
      bagli. `artifact_set_sha256`, `AgentService._artifact_set_digest` ile
      **birebir ayni sayi** ve anlasma bir testle sabitlendi.
- [x] **Onay `SendApproval` kalibi, `ExportConsent` degil.** Tek kullanimlik,
      TTL'li, ve **paket digest'ine + goreve + icerik surumune + oturuma**
      bagli. **Reddedilen bir teslim de token'i harciyor** - aksi hâlde
      reddi atlatarak tekrar denenebilirdi. Rota ayrica govdede
      `acknowledged: Literal[True]` istiyor.
- [x] **"Bagimsiz kontrol" ve "gercek exit code" `not_implemented` kaldi** ve
      gerekcesini soyluyor: model yolu (ADR-0008 §2) ve keyfi yurutme
      (ADR-0008 §1) kapali. Planin olcutu ve yeniden uretme talimati **metin
      olarak** paketleniyor; olcutun yaninda kosmanin `test_result_state`'i de
      yaziliyor. Soz verilen her ciktiyi ureten bir calisma bile gorevi
      `ready_to_publish`'e tasimiyor.
- [x] **Eksikler adiyla listeleniyor**, skor/yuzde/rozet yok:
      `evidence.*`, `requirement.*`, `run.*`, `artifact.*`. JSON govdesinde
      `score`/`percent`/`completeness`/`grade`/`rating` gecmedigi olculuyor.
- [x] **Kabul gecisin girdisi.** `user_acceptance` icin ayri bir rota acildi;
      `verified=True` yalniz insan eyleminden doguyor, kisinin **gordugu
      paketin ozetine** baglaniyor ve rota **hicbir durumu tasimiyor** -
      kabul oncesi ve sonrasi gorev durumunun ayni oldugu olculuyor (SI-222).
      Bu, `agent_workspace`'in yedinci gereksinimini de kapatti.
- [x] **Yeni paket her sinir taramasinin icine alindi (ADR-0009 §5, merge
      sarti).** `STATE_WRITER_DIRS`, `BUDGET_SCANNED_DIRS` ve
      `REGISTRY_SCANNED_DIRS` (eski `PACKAGE_F_DIRS`) `proof`'u kapsiyor; iki
      yeni dosya (`test_proof_boundary.py`, `test_proof_language.py`) yurutme,
      arsiv, baglanti, dosya yazma, zamanlayici, secret ve yasak ifade
      sinirlarini paketin **her string literal'i** ve rota dosyasi uzerinde
      uyguluyor. Her genisletme iki yariyla suruldu: taramanin gercekten
      `proof/` dosyalarini **actigi** ve ekili ihlalin **raporlandigi**.
- [x] **Asama `8 -> 9`** bes giris noktasi ve pinli sabitle atomik.
      **Yeni migration yok**; `CURRENT_MIGRATION_HEAD` `0009`'da kaldi.
- [x] **`OUTBOUND_CLIENT_MODULES` beste kaldi.** Dis paylasim mevcut
      `compose/` zinciriyle gider; bu paket tarayiciya dosya teslim eder ve
      baska hicbir sey yapmaz. Yeni bagimlilik yok, yeni HeroUI bileseni yok,
      `sections.ts`'e dokunulmadi.
- [x] SI-300...SI-311; SI-213, SI-219, SI-220, SI-225 ve SI-226 metinleri
      **gercek degistigi icin guncellendi**, iddialari zayiflatilmadi.

- [x] **Mutasyon kaydi: on alti mutasyon, on altisi da en az bir testi
      oldurdu.** Sifir olduren guard yok. Tam tablo
      [docs/verification/paket-h3.md](docs/verification/paket-h3.md) ve
      [docs/security-invariants.md](docs/security-invariants.md) §9k'de.
- [x] **Frontend: bolum ACILMADI** (9/9 `ready` kaldi, ADR-0009 §9). Proof
      Workspace `Kanitlar`'a, kabul ve arsivlenmis-gonderim yuzeyi
      `Gorevler`'e girdi. `public_share_available` telde **BAYATTI** (`false`
      tiplenmisken backend `true` gondermeye baslamisti); `true`'ya
      sabitlenmedi, **`boolean`'a genisletildi** - alanin ne tasiyabilecegi
      sunucunun karari - ve `false`'u geri koymak artik **derleme hatasi**
      (iki fixture'da TS2322, olculdu).
- [x] **Bir test YANLIS SEBEPLE geciyordu**: cift etkinlestirme testi guard'i
      degil, basari sonrasi sifirlamayi suruyordu; istegi ucusta tutan bir
      stub'la yeniden yazildi. Ajan `busy` guard'i ile `isDisabled`'in
      gereksiz oldugunu da olctu ve DOM'dan erisilemeyen yari icin **zorlama
      test uydurmadi**.
- [x] **2114 pytest** (1992 -> 2105 -> inceleme sonrasi 2114) + **315
      Vitest** (289'dan) + **74 Playwright** (65'ten). Yeni HeroUI bileseni
      yok (kume 11'de, MCP ile dogrulandi v3.2.4), yeni bagimlilik yok,
      migration yok, asama `8 -> 9`.

#### Paket H3 - PR #19 dusman inceleme turu (5 Eylul 2026)

**31 backend + 5 frontend mutasyon, 6 ekili ihlal, 13 uctan uca prob.** Dort
mutasyon hayatta kaldi; **sekiz bulgunun hepsi kapatildi.** Ayrintili tablo:
[docs/verification/paket-h3.md](docs/verification/paket-h3.md).

- [x] **P1 - `UNFILLABLE_FIELDS`'in DORT DEGIL BES okuyucusu vardi.**
      Besincisi `tasks/views.py` - telin kendisi - ve onu sabit bir `True`'ya
      cevirmek 1770 testin **hicbirini** kirmiyordu, yani "tel ile kural
      ayrisamaz" diyen iki test sabit bir literal'e karsi geciyordu.
      **ADR-0009 §2 bunu bir merge sarti yapmisti ama ENVANTERIN KENDISI
      EKSIK oldugu icin sart kendi hedefini iskaladi.** 0 -> 1 kirmizi;
      ADR tablosu, `modules/fields.py`'nin "dort dal" cumlesi ve SI-301
      **bese** duzeltildi.
- [x] **P1 - `safe_text`'in sweep->neutralise SIRASI sabitlenmemisti.**
      Ters cevirmek 0 test kiriyordu ama mutant **esdeger degil**: `fold()`
      sifir-genislikli karakteri **siler**, `sweep_untrusted` **boslukla
      degistirir**. Yasak bir ifadenin iki kelimesi arasina konan U+200B ham
      metinde gorunmez, sweep'ten sonra birebir yasak ifade olur ve
      **yakalanmayan 500** uretir - tam olarak IMP-420'nin "bir klavye urunun
      ne soyleyecegine karar veremez" kurali. 0 -> 2 kirmizi.
- [x] **P2 - "uc gereksiz olmayan denetim" iddiasinin MEKANIZMASI yanlisti**
      (esas iddia dogru: incelemeci elle yazilmis dizeyle "paylasildi"
      diyemedi). Fiilen reddeden `EvidenceService.get`, hicbir belgenin
      anmadigi bir dorduncu denetim; sekil denetimini pydantic
      `min_length=32`, satir-varlik denetimini `evidence.get` golgeliyor -
      H2'nin containment-reparse kalibinin aynisi. Mekanizma **dogru
      adlandirildi**.
- [x] **DUZELTME AJANI INCELEMECIYI IKI KEZ OLCEREK DUZELTTI:** (1) onerilen
      "sonuc okumasini tasi" secenegi **ucuz degil, yapisal olarak
      imkansiz** - `write_outcome`, `verified`'in GIRDISI, dolayisiyla ondan
      sonraya konan her denetim o yolda tanim geregi erisilemez;
      (2) `routes/agent.py` bir bulgu **degildi** - `WorkspaceError`,
      `AgentError`'in alt sinifi ve rota zaten `(TaskError, AgentError)`
      yakaliyor.
- [x] **P2 - rotadaki `acknowledged` denetimi erisilemez olu koddu** ve
      docstring "iki bagimsiz ret" diyordu. Modeli genisletmek reddi semadan
      handler'a **geciktirir** ve mevcut bir testi 422'den 400'e
      **zayiflatmayi** gerektirirdi; olu dal kaldirildi ve anotasyon tek
      savunma oldugu icin kendi testine kavustu. 2 kirmizi.
- [x] **P2/P3'ler:** TTL sabiti ikizinin yaptigi gibi sabitlendi (0 -> 1);
      paylasim onayi deposu hicbir sey atmiyordu (50 hazirlik + TTL gecisi +
      5 daha -> **55**), `DraftStore` kalibi `SingleUseStore`'un kendisine
      uygulandi (compose ve bootstrap da kazandi) ve olcum **5** oldu, tavan
      ayri testle suruluyor; workspace'teki **gercek bir junction** kanit
      okumasini 500'e ceviriyordu, `ProofService.build` `AgentError`'i
      cevirerek dort rotayi birden kapatti ve gercek NTFS junction ile
      suruldu (sessiz skip yok); panel yorumunun "iki okuma" iddiasi bire
      indirildi. Yeni **SI-312** (sinirli token deposu) ve **SI-313**
      (reparse point -> belirtilen ret).
- [x] **Incelemeci sizinti bulamadi**: 9715 baytlik paket iki bicimde de
      mutlak yol, `data_dir`, `C:\`, ham istek govdesi, imza, DID ve oturum
      kimligi tasimiyor. **Onay yaris-guvenli**: tek token'la 8 eszamanli
      teslim -> tam olarak 1 `ok`, 7 ret.
- [x] **Bu paketin raporunda iki yanlis duzeltildi:** girisi
      `apps/station-web/src/**`'in hic degistirilmedigini soyluyordu (olcum:
      8 dosya, +2590/-7) ve `task-modules.md`'nin "`verified` cagirandan
      alinmaz" cumlesi **kosulsuz** yazilmisti (TaskService yolunda yanlis;
      bugun o cagriyi acan rota olmadigi icin belge kusuruydu, ama kosulsuz
      kalmasi onu delige cevirirdi).
- [x] **Incelemecinin olcmedikleri** raporda acikca yazildi: Playwright
      kosulmadi (statik sayildi), hicbir tarayici/gorsel/manuel QA
      yapilmadi, H3 diff'i disindaki paketler incelenmedi, DPAPI/ACL
      davranisi incelenmedi. Kapilar ve e2e orkestrator tarafindan kosuldu.

**Gercek servise hicbir istek gonderilmedi** ve **hicbir ucretli cagri
yapilmadi** - her sey mock tasiyiciya karsi, iki katmanli ag kesici altinda.

On kosul: kullanici acikca "baslayalim" demeden gercek gonderim yapilmaz.


---

## Aşama 11 / Paket I — Windows paketleme (5 Eylül 2026, kod aşaması 10)

Kapsam kararları: [`docs/decisions/0010-paket-i-kapsam-kararlari-2026-09-05.md`](docs/decisions/0010-paket-i-kapsam-kararlari-2026-09-05.md) ·
Uygulama: [`docs/packaging.md`](docs/packaging.md) ·
Doğrulama: [`docs/verification/paket-i.md`](docs/verification/paket-i.md)

### En önemli satır: **artefakt üretildi, çalıştırıldı ve ölçüldü**

Bu bölümün ilk hâli "artefakt üretilmedi" diyordu; nedeni PyInstaller'ın bu
deponun bağımlılığı olmamasıydı. **O karar alındı ve uygulandı.**

- **PyInstaller `dev` grubuna, tam pinle eklendi:**
  `apps/station-api/pyproject.toml` içinde `pyinstaller==6.16.0`,
  `apps/station-api/uv.lock` güncellendi (`uv lock` + `uv sync --locked`).
  **Üretim bağımlılığı değildir** ve **artefaktın içine girmez** — yalnız
  build zamanı çalışır, ürünün çalışma zamanı bağımlılık yüzeyi
  **değişmedi**.
- **Lisans kurulu paketten okundu**, hafızadan veya webden değil:
  `pyinstaller-6.16.0.dist-info/METADATA` ve `licenses/COPYING.txt` (636
  satır). SPDX: **`GPL-2.0-or-later WITH Bootloader-exception`**. İstisna
  maddesi ("Bootloader Exception") derlenmiş bootloader'ı ve ilgili
  dosyaları başka programlarla birleştirip **o dosyaların kullanımından
  doğan hiçbir kısıt olmadan** dağıtma izni verir; run-time hook'lar ayrıca
  Apache-2.0'dır. Üretilen exe'nin baytlarında `pyiboot01_bootstrap`,
  `pyimod01_archive`, `pyimod02_importers` ve üç rthook **bulundu** — yani
  artefakt gerçekten PyInstaller kaynaklı dosya taşıyor ve okunan metin tam
  olarak bunu karşılıyor. **Kendi kodumuz MIT kalır.** `README.md`
  bağımlılık tablosuna satır, `NOTICE`'a gönderilen bundle'ın lisans
  haritası eklendi.

**Ölçülen artefakt** (Windows 11 Pro 10.0.26200, CPython 3.12, `onedir`):
boyutlar ve SHA-256'lar **burada tekrarlanmaz**, tek kaynak
[`docs/verification/paket-i.md` §13.1](docs/verification/paket-i.md#131-üretim-ve-ölçüm).
Bu dosya bir kopya taşıyordu ve artefakt yeniden üretildiğinde eskidi;
bağımsız inceleme üç ayrı belgede aynı eskimiş özeti ölçtü.

**Artefakt çalıştırıldı** (geçici `STATION_DATA_DIR` ile; kullanıcının veri
dizinine **dokunulmadı**, dört dosyanın adı/boyutu/mtime'ı önce–sonra aynı):
yalnız `127.0.0.1`, efemer port, `/api/health` **200**, korumalı rota
**401**, `GET /` gövdesi `dist/index.html` ile **bayt-birebir** (yani
"Arayuz derlenmemis" 503'ü **üretilmedi**), `%TEMP%`'te `_MEI*` **yok**,
yazılan her dosya veri dizininin **içinde**.

**Bayt-birebir testi ilk kez gerçek bir bundle'a karşı koştu** ve sürüldü:
gönderilen `index.html`'in son baytı değiştirildiğinde test kırmızıya döndü
ve farkı isimle raporladı; dosya geri yüklendi, test yeşile döndü.

### Kapanış turu — üç kusur kapatıldı (5 Eylül 2026, ikinci geçiş)

İlk çalıştırmada ölçülen üç kusurun **üçü de kapatıldı**. Kayıt silinmedi:
ne bulunduğu ve nasıl kapandığı
[`docs/verification/paket-i.md`](docs/verification/paket-i.md) §13.3/§13.5
ve [`docs/packaging.md`](docs/packaging.md) §5'te duruyor. Yeni değişmezler:
**SI-326**, **SI-327**.

1. **Ctrl+C çöküş gibi görünüyordu** (çıkış kodu **1**, konsolda
   `KeyboardInterrupt` + PyInstaller'ın `Failed to execute script` satırı).
   **Kapandı:** `launcher.absorbing_shutdown_signals()`, `uvicorn.Server.run`
   çağrısının **etrafına** kurulan ve uvicorn'un kapanıştan sonra yeniden
   yükselttiği sinyali yutan handler. Yeniden üretilen artefaktla ölçüldü:
   **çıkış kodu 0**, konsolda çöküş metni **yok**, kilit **silindi**.
2. **Ctrl+Break bayat kilit bırakıyordu** (çıkış kodu **3**, `finally`
   çalışmıyor, `station.lock` kalıyor, uygulama bir daha açılmıyor). Aynı
   mekanizma kapattı. Ölçüldü: **çıkış kodu 0**, kilit **silindi**, ve aynı
   veri dizininde **yeniden başlatıldı** — "zaten calisiyor" reddi çıkmadı.
   ADR-0010 §8'in `os.kill(pid, 0)` reddi **yerinde duruyor**; canlılık
   yoklaması eklenmedi.
3. **`test_bind.py`'nin dosya sayısı bundle'ın varlığına bağlıydı** (bundle
   varken `packaging/` altında 14 dosya, 12'si artefakt içindeki kopyalar).
   **Kapandı:** tarama artık kaynağı kopyadan **tam yolla** ayırıyor
   (`packaging/artifacts`, dizin adıyla değil — ADR-0010 §3'ün uyardığı
   körlük eklenmedi) ve `build`/`dist`/`out` **ada göre atlanmayı bıraktı**,
   yani üçüne ekilen bir `0.0.0.0` artık yakalanıyor. Bundle diskteyken
   ölçüldü: `packaging/` **2 dosya**.

**Mutasyon:** on hedefli mutasyonun **onu** öldürüldü; ayrıca kusur öncesi
kodla **ayrı bir `.exe` üretilip** aynı düzenekle çalıştırıldı ve eski
çıkış kodları (`1` ve `3`) yeniden gözlendi — yani ölçüm düzeneğinin kusuru
görebildiği kanıtlandı.

### Bağımsız inceleme turu — on iki bulgu kapatıldı (5 Eylül 2026, üçüncü geçiş)

Dışarıdan bir düşman inceleme **yirmi iki mutasyon** yaptı; **beşi sıfır
kırmızı** verdi. On iki bulgunun tamamı kapatıldı, her biri mutasyonla veya
kırmızı→yeşil geçişiyle sürüldü. Tam tablo:
[`docs/security-invariants.md`](docs/security-invariants.md) §9l üçüncü
mutasyon kaydı. Yeni değişmezler: **SI-328**, **SI-329**.

**Sıfır kırmızı veren beş mutasyon ve kapanışları**

1. **`dist` hâlâ ada göre muaftı** — PyInstaller'ın **varsayılan
   distpath**'i. `packaging/dist/helper.py` ekildi, `.gitignore` yuttu, 2184
   test yeşil kaldı. `dist` iki listeden de çıkarıldı; muafiyetler artık tam
   yol. Ölçüm: **0 → 3 kırmızı**.
2. **`ctypes` allow-list'i her şeyi muaf tutuyordu.** `vault/dpapi.py`'ye
   `import subprocess` + `subprocess.Popen` ekildi; ruff, mypy ve 2184 test
   yeşildi. Muafiyet **sembole** bağlandı; `EXECUTION_ATTRIBUTES`'a `Popen`
   ve on dört süreç başlatan giriş noktası eklendi (`run`/`call`
   eklenmedi — ürün onları meşru olarak çağırıyor, gerekçe kodda ölçümle
   yazılı). Ölçüm: **0 → 1 kırmızı**.
3. **İki tarama ağaçlarını sessizce kaybediyordu.** İncelemenin önerdiği
   düzeltme **totolojikti** ve ölçülerek reddedildi: döngü, denetlediği
   listeyle birlikte küçülüyor. Guard ikiye bölündü — listeyi gezen yarı ve
   **depoyu** gezen yarı. Ölçüm: her iki listede **0 → 1 kırmızı**.
4. **Başlatma sırasındaki her hata bayat kilit bırakıyordu.** `finally`
   yalnız `Server.run`'ı sarıyordu; migration'daki Ctrl+C, soket hatası ve
   `PackagedLayoutError` kilidi geride bırakıyordu — sonuncusu, bu paketin
   var oluş sebebi olan hatanın ardından kullanıcıya **yanlış** sebep
   söylüyordu. `finally` tüm gövdeyi sarıyor; elle `release()` kaldırıldı.
   Ölçüm: yeni testler düzeltme öncesi **4 kırmızı**, sonrası **0**.
5. **Gönderilen ZIP geliştiricinin kullanıcı adını ve ev dizini yolunu
   taşıyordu.** `station.spec` iki Python ağacını `__pycache__` dâhil
   kopyalıyordu; `.pyc`'lerin `co_filename`'i mutlak yol taşır. Ölçüldü: 152
   dosyanın **11'i** sızdırıyordu (exe ve PYZ temizdi). Spec dosya dosya
   kopyalıyor; **artefaktı tarayan bir test eklendi** — depoda böyle bir
   tarama yoktu. Yeniden üretilen artefakt: **141 dosya, 0 sızıntı, 0
   `.pyc`**.

**Diğer yedi bulgu.** Bayt-birebir SPA denetimi CI'da hiç koşmuyordu
(`packaging.yml`'e build **sonrası** pytest adımı eklendi ve komut yerelde
ekili bir baytla sürüldü); yayımlanan SHA-256'lar artefaktla eşleşmiyordu
(üç kopya kaldırıldı, **tek kaynak**
[`docs/verification/paket-i.md` §13.1](docs/verification/paket-i.md#131-üretim-ve-ölçüm));
`README.md` PyInstaller'ı hâlâ "bağımlılık değil" diyordu; doğrulama belgesi
"dört ağaç" diyordu (beş); `packaging.yml`'in `PATH` stripleme adımı ne
strip ettiğini doğrulamıyordu — **ve doğrulama eklenince striplemenin
çalışmadığı ortaya çıktı**, bu yüzden stripleme çözünürlük sürücülü hâle
getirildi; `Get-NetTCPConnection` belirsizliği açık bir `throw` ile kaldırıldı
(cmdlet'in boş sonuçta `CimJobException` fırlattığı **ölçüldü**).

**Kapılar:** 2201 pytest (taban 2184, +17 yeni test), 315 Vitest, ruff ×2,
mypy 133 dosya, eslint, vite build — hepsi yeşil.

### Tamamlanan görevler

- [x] **PyInstaller kilitli bir geliştirme bağımlılığı oldu.** `dev` grubuna
      `pyinstaller==6.16.0` (tam pin, aralık değil), `uv lock` +
      `uv sync --locked`. Alternatifler ADR-0010 §2'de ölçülerek elenmişti.
      Üretim bağımlılığı değildir. `README.md` bağımlılık tablosuna satır
      (ad, sürüm, **kurulu paketten okunan** lisans, gerekçe), `NOTICE`'a
      gönderilen bundle'ın lisans haritası eklendi.
- [x] **Artefakt üretildi, ölçüldü ve çalıştırıldı** (yukarıdaki tablolar).
      Bayt-birebir SPA testi **ilk kez gerçek bir bundle'a karşı** koştu ve
      mutasyonla sürüldü.
- [x] **Paketleme CI işi dördüncü kapı yapıldı.** `packaging.yml` tetikleyicisi
      `pull_request` + `push → main`; kilitsiz kurulum adımı silindi.
      Workflow **koşturulmadı**, YAML yerel olarak ayrıştırıldı.
- [x] **BLOKER kapatıldı (ADR-0010 §1).** `app.py`'nin
      `Path(__file__).resolve().parents[4]` satırı dokuz pakettir yalnız
      editable kurulum sayesinde çalışıyordu; wheel'den kurulunca `.venv`'in
      üstüne düşer ve uygulama **sessizce 503 "Arayuz derlenmemis"** servis
      eder. O sayfaya bakan **hiçbir test yoktu**. Yeni
      `station_api/resources.py` yolu `importlib.resources` ve donmuş dalda
      `sys._MEIPASS` ile çözüyor; **ortam değişkeni reddedildi** ve
      reddedildiği ölçülüyor. Aynı düzeltme `db/migrations_runner.py`'nin
      `MIGRATIONS_DIR`'ine uygulandı (Alembic `env.py`'yi **dosya olarak**
      okur).
- [x] **Paketlenmiş bir çalıştırma "build yok" 503'ünü üretemez.** İki
      bağımsız ret: çözücü olmayan bir dizini **adlandırmayı**, `_mount_spa`
      onu **bağlamayı** reddeder. Mutasyon tablosunda ikisi de ayrı ayrı
      öldürüyor. Depo kopyasında aynı sayfa **korundu** — orada doğru olan
      tek durum odur.
- [x] **`0.0.0.0` taraması genişletildi (ADR-0010 §3).** Eskiden yalnız
      `apps/station-api/src` altındaki `.py`. `packaging/station.spec`'e
      ekilen bir `0.0.0.0` **hiçbir testi kırmıyordu**. Artık dört ağaç, on
      beş uzantı ve `.github/workflows`; ekili ihlal `.spec`/`.ps1`/`.bat`/
      `.iss`/`.yml` için **ayrı ayrı** sürülüyor.
- [x] **Yürütme yasağı ürün geneline çıkarıldı (ADR-0010 §3).** Eskiden
      yalnız `agent/` ve `proof/`. `packaging/build_bundle.py`'ye ekilen bir
      `import subprocess` **hiçbir testi kırmıyordu**, oysa
      `arbitrary_execution_supported: Literal[False]` ürün geneli hakkında
      bir iddia. `ctypes` muafiyeti **iki dosya**, birebir allow-list, ve
      üçüncü bir dosyanın import etmesi kırmızı veriyor. `importlib` bu
      listeye **konmadı** — ADR-0010 §1'in çözümü tam olarak odur.
- [x] **Build betiği `subprocess` kullanmıyor:** PyInstaller kendi Python
      API'sinden sürülüyor.
- [x] **`test_tracked_sources` genişletildi.** `packaging/` ağacı ve sekiz
      uzantı eklendi. Asıl karar `GENERATED_NAMES`'e **`build`/`out`
      eklenmemesidir**: ADR-0010 §3'ün adını verdiği kaza
      (`packaging/build/helper.py`) tam olarak o eklemeyle görünmez olurdu.
      Çıktı `packaging/artifacts/` altına alındı ve `.gitignore`'a
      **çapalanmış** tek bir kural eklendi; muafiyet **kaldırıldı**.
- [x] **Gönderilen SPA bayt-birebir (ADR-0010 §4).** Tek iddia mevcut altı
      denetimi gönderilen artefakta taşıyor; spec'in kopyaladığı kaynak
      `apps/station-web/dist` olarak sabitlendi; karşılaştırma tek baytlık
      farkta **hangi dosya** olduğunu adıyla raporluyor. Paket varken SPA'sı
      beklenen yerde değilse test **kırmızıdır**.
- [x] **Paketleyici (ADR-0010 §2, §7).** `packaging/station.spec`: `onedir`
      (`COLLECT`), `console=True`, `codesign_identity=None`, `nacl` hariç;
      datas olarak SPA + migration ağacı + pinli conformance vektörleri.
      `onefile` reddedildi (her çalıştırmada `%TEMP%`'e açar; ürün bugün
      `%TEMP%`'e hiç yazmıyor).
- [x] **Yükseltme ve geri dönüş (ADR-0010 §6).** İki test, ikisi de daha
      önce yoktu: `0007` şemasına **gerçek satır** yazılıp `0009`'a
      yükseltiliyor ve satırlar değer değer korunuyor; tanınmayan bir
      revizyonla işaretli veritabanı `SchemaAheadError` ile **anlaşılır
      biçimde** reddediliyor. İkincisi bir ürün değişikliğidir:
      `run_migrations` artık `guard_against_a_newer_schema` çağırıyor.
      Sürümlü kurulum kökü ve `current` junction **reddedildi** (H2'nin
      reparse-point savunması).
- [x] **Tek örnek kilidi (ADR-0010 §8).** Veri dizininde `station.lock`,
      `O_CREAT | O_EXCL`. Launcher kilidi **veritabanını açmadan önce**
      alıyor (sıra testte sabit) ve `finally` ile bırakıyor. `os.kill(pid,
      0)` ile canlılık yoklaması **yapılmadı**: Windows CPython'da o çağrı
      `TerminateProcess`'e düşer, yani sinyal `0` sorulan süreci
      sonlandırırdı.
- [x] **SHA-256 ve imzasızlık (ADR-0010 §9).** `digests.py`'ye `file_digest`
      eklendi — modülün kendi iki kuralına **bilinçli istisna**, çünkü değerin
      `Get-FileHash` ile doğrulanabilmesi gerekir; test bunu ölçüyor. İkinci
      hash yardımcısı yazılmadı. **"SmartScreen'i kapatın" hiçbir yerde
      yazmıyor** ve bir test bunu arıyor.
- [x] **Aşama numarası `9 → 10` (ADR-0010 §11).** Beş giriş noktası ve
      `CURRENT_SCHEMA_STAGE` atomik. `CURRENT_MIGRATION_HEAD` **`0009`'da
      kaldı** — bu paket şemaya dokunmadı.
- [x] **Yeni değişmezler SI-314 … SI-325.** SI-02 ve SI-232 **güncellendi,
      silinmedi**: SI-02'nin iddiası aynı, kapsamı büyüdü.
- [x] **Mutasyon tablosu: 20 mutasyon, 20'si de en az bir testi öldürdü.**
      Sıfır öldüren guard yok. İkisi (`.spec`'e `0.0.0.0`,
      `build_bundle.py`'ye `subprocess`) **bu paketten önce sıfır kırmızı
      verirdi** — ADR-0010 §3'ün ölçtüğü iki delik.

### CI (ADR-0010 §10) — artık **dördüncü kapı**

`.github/workflows/packaging.yml`: `windows-latest`, tam SHA pin, cache yok,
secret yok. **Tetikleyici `workflow_dispatch`'ten `quality.yml`'ninkine
çevrildi**: `pull_request` (hedef `main`) + `push` (`main`); elle koşturma
için `workflow_dispatch` da korundu. Kapı olamamasının kaydedilmiş tek nedeni
ortadan kalktı — PyInstaller `uv.lock` içinde ve `uv sync --locked` onu
kuruyor. Kilitsiz `uv pip install` adımı **silindi**; yerine paketleyicinin
sürümünü yazdıran bir doğrulama adımı kondu.

`quality.yml`'ye dördüncü **iş** olarak taşınmadı, ayrı workflow olarak
bırakıldı: bu iş donmuş bir ikiliyi derleyip **çalıştırır** (40 dakikaya
kadar) ve başarısızlığı "bundle bozuk" diye okunmalıdır. Tetikleyici,
`permissions`, pin ve cache politikası `quality.yml` ile birebir aynıdır.

**Workflow koşturulmadı ve koşturulamaz** — yerelde GitHub Actions yok. YAML
yerel bir ayrıştırıcıyla doğrulandı: tetikleyiciler, `permissions:
{contents: read}`, `concurrency`, tek iş `bundle`, `runs-on: windows-latest`,
`timeout-minutes: 40`, **11 adım**, üç action da `quality.yml` ile **aynı tam
SHA'lara** pinli, dosyada hiç `secrets.` geçmiyor. İçindeki PowerShell
**çalıştırılmadı**; **ilk kez CI'da koşacak.**

Workflow header'ı artık "temiz kapanış" iddia **etmiyor**: iş süreci
`Stop-Process -Force` ile öldürüyor, yani ölçtüğü şey bayat kilidin kaldığı
hâldir — ve bu, kapanış turundan sonra da doğrudur, çünkü zorla sonlandırma
`finally`'yi hiç çalıştırmaz. Graceful kapanış yerelde elle ölçüldü; iki
kusur çıktı ve **ikisi de kapatıldı** (yukarıda).

`/api/app/status`'ün aşama numarası CI'da hâlâ doğrulanamıyor: rota oturum
ister, oturum tek kullanımlık bağlantıyı ister, o bağlantı bilinçle
loglanmaz (SI-07). Aşama numarası süreç içinde doğrulanıyor.

### Test sonuçları

| Kapı | Sonuç |
|---|---|
| `uv run --directory apps/station-api ruff check .` | **temiz** |
| `uv run --project apps/station-api ruff check apps/station-api/src packages/technocore-conform/src tests` | **temiz** |
| `uv run --project apps/station-api mypy --config-file apps/station-api/pyproject.toml` | **133 dosya, sorun yok** |
| `uv run --directory apps/station-api pytest ../../tests -q -p no:warnings` | **2184 geçti** (taban 2114, **+70**; kapanış turu **+15**) |
| `npm --prefix apps/station-web run lint` | **temiz** |
| `npm --prefix apps/station-web run test` | **315 geçti** (değişmedi) |
| `npm --prefix apps/station-web run build` | **başarılı** |
| `packaging/build_bundle.py` (kapı değil, elle) | **artefakt üretildi**, üç ön koşul da `[OK]` |

Yeni test dosyası: `tests/security/test_packaging_boundary.py` (kapanış
turundan sonra 50 test). Genişletilen: `test_bind.py` (kapanış turunda +5),
`test_tracked_sources.py`, `test_frontend_bundle.py`, `test_database.py`.

### Bu turda ölçülmeyenler — adıyla

> **Paket J düzeltmesi (ADR-0011 §9, §10).** Bu blok yazıldıktan sonra
> Paket I'nın kendi turu devam etti ve **dört maddesi yanlışa döndü**:
> `packaging.yml` CI'da koştu, temiz profil ölçüldü, yeniden
> üretilebilirlik **ölçüldü ve olumsuz çıktı** ("ölçülmedi" değil), ve
> commit/PR **yapıldı**. Tek ve güncel liste
> [`docs/verification/paket-i.md`](docs/verification/paket-i.md) §12'dedir;
> burada tekrarlanmaz. Playwright de o turda **koştu**: 74/74 yeşil.

- **İmzalama doğrulanamaz** (sertifika yok, secret yok). Artefakt imzasız.
- **Çift örnek yarışının gerçekten bozup bozmadığı** ölçülmedi; koruma
  ADR-0010 §8'in gerekçesiyle var.
- **Kaldırma akışı elle denenmedi.** Artefakt hiçbir yere **kurulmadı**;
  program dizini oluşmadı. Kullanıcının veri dizinine **dokunulmadı** — dört
  dosyanın adı, boyutu ve mtime'ı önce–sonra karşılaştırıldı, birebir aynı.
  Ölçüm için kullanılan geçici `STATION_DATA_DIR` sonra silindi.
- Gerçek DID/seed/private key/recovery/`.tcrec`/API anahtarı **okunmadı,
  istenmedi, yazılmadı**. Gerçek Technocore'a hiçbir istek gitmedi.

---

## Aşama 12 / Paket J — bütünleşik inceleme ve temizlik (5 Eylül 2026, kod aşaması 11)

Kapsam kararları: [`docs/decisions/0011-paket-j-kapsam-kararlari-2026-09-05.md`](docs/decisions/0011-paket-j-kapsam-kararlari-2026-09-05.md)

Bu paket **yeni yetenek getirmedi**: yeni rota, yeni bağımlılık, yeni giden
yüzey yok. `OUTBOUND_CLIENT_MODULES` beşte kaldı. Yaptığı iş, belgelerin
ürünle uzlaşmasıdır.

### En önemli satır: **bayatlamanın mekanizması bulundu ve kapatıldı**

- [x] **`-qq` tuzağı kapatıldı (ADR-0011 §1).** `pytest.ini` zaten
      `addopts = -q` veriyor; `AGENTS.md` ve `CLAUDE.md`'nin kapı komutu bir
      `-q` daha ekliyordu, yani **efektif `-qq`** — ve `-qq` **özet satırını
      bastırır**. Kapıyı yerelde koşan hiç kimse "N passed" satırını
      görmüyordu; test sayılarının fark edilmeden bayatlamasının mekanizması
      buydu. Her iki dosyadaki fazladan `-q` düşürüldü ve **ölçüldü**:
      `pytest ../../tests/security/test_bind.py -q` özet satırı basmıyor,
      `-q`'suz aynı komut `18 passed, 1 warning in 2.71s` basıyor.
- [x] **SI tablosunun her test adı artık ölçülüyor (ADR-0011 §2).** Yeni test:
      `tests/security/test_security_invariants_doc.py` (6 test). Tablodaki
      **924 test referansını** ayrıştırıp suite'e karşı çözer; joker bir
      referansı **reddeder** (joker çözülemez, dolayısıyla alıntı değildir).
      Ölçülen bayat referanslar tek tek düzeltildi:
      - **SI-211** olmayan bir ada işaret ediyordu
        (`test_planned_modules_name_the_package_that_opens_them`); gerçek adlar
        `test_the_registry_satisfies_the_planned_module_contract` ve
        `test_no_module_is_registered_as_planned_any_more`.
      - **SI-277** hem olmayan bir ada işaret ediyordu hem **beklenen metni
        bayattı** (`RUNNING`/`PAUSED` "üretilemez" diyordu; `UNPRODUCIBLE_STATES`
        H2'den beri **boş**).
      - **SI-243**'ün `test_the_credential_is_absent_from_*` jokeri "yedi yüzey"
        diyordu ama **altısını** tutuyordu; yedincisi
        `test_no_artefact_anywhere_in_the_data_directory_carries_the_credential`
        adını taşıyor ve joker ona hiç ulaşmıyordu. Yedisi de tek tek yazıldı.
      - **SI-105**'in `::test_*` jokeri gerçek parametrik testlerle değiştirildi.
- [x] **`security-invariants.md` §9 kaldırıldı (ADR-0011 §2).** Başlığı
      *"Aşama 2+ değişmezleri (bugün kod yolu yok)"* idi ve altındaki **sekiz**
      satırın hepsinin bugün bir kod yolu vardı. SI-49/SI-50/SI-52 §6'ya,
      SI-51/SI-53/SI-54/SI-56 §9c'ye, SI-55 §9e'ye **test adlarıyla** taşındı.
      Aynı kusurdan bir tane daha bulundu ve düzeltildi: **SI-38**'in Test
      sütunu "Aşama 2" yazıyordu; `test_seed_leakage.py` beş yüzeyi ölçüyor.
      **Ölçülen ve kapatılmayan boşluk:** `generate_seed`'in CSPRNG kullandığını
      doğrulayan bir test **yok**; SI-50'nin yalnız *içeri alma* yarısı test
      edilmiş durumda ve bu belgeye yazıldı.
- [x] **Kod aşaması `10 → 11` (ADR-0011 §3).** Altı yerde **atomik**:
      `cli/__main__.py:91`, `launcher.py:183`, `routes/api.py:115`,
      `tests/conftest.py:295`, `apps/station-web/e2e/harness/serve.py:111` ve
      pinli sabit `tests/security/test_module_registry.py:101`.
      `CURRENT_MIGRATION_HEAD` **`0009`'da kaldı**.
      `test_every_entry_point_names_the_same_release_stage` beş giriş
      noktasının hepsini aynı sayıda tutuyor. İki numaralandırma bu belgede
      **"(kod aşaması N)"** ekiyle hizalandı: F=6, G=7, H1=7 (ayrışma burada
      başladı — paket kendine "Aşama 8" dedi, kodun sayısını taşımadı), H2=8,
      H3=9, I=10, J=11. **Tarihsel raporlar yeniden yazılmadı.**
- [x] **Ölü yüzey silindi (ADR-0011 §7).** AST ile ölçülüp kaldırılanlar:
      `attachJson` (`e2e/fixtures.ts`, tek export, hiç çağrılmıyordu — kullanılmayan
      `TestInfo` importu da düştü), `ProofBundle.missing_count` (hiç okunmuyordu),
      ve `__all__`'da olup **hiçbir yerden import edilmeyen yedi ad**:
      `AUTHORITY_DETAIL`, `SOURCE_DETAIL`, `BudgetError`,
      `OFFICIAL_SEED_HEX_LENGTH`, `StoredCredential`, `measured_facilities`,
      `refs_from`. "İkizi kullanılıyor" savunması **ölçüldü ve tutmadı**:
      `STATE_DETAIL`'in canlı bir tüketici zinciri (`views.detail_for_state`,
      `service`, `states.refuse`) ve kapsamını denetleyen bir testi var;
      `AUTHORITY_DETAIL` ile `SOURCE_DETAIL`'in **ikisi de yok**.
      `OFFICIAL_SEED_HEX_LENGTH = 64` ayrıca iki regex'teki `{64}`'ün üçüncü
      bir kopyasıydı — sürüklenme yeri, kapı değil.
      **`WorkScanRingDrop` silinmedi**: belgelenmiş, bilinçli bir boşluktur
      (`paket-h1.md:161`, `ui-action-map.md:657`) ve silmek "alan ve gösterim
      birlikte gelmeli" kararını kaybettirirdi.
- [x] **Playwright kaydı düzeltildi (ADR-0011 §10).** `PROJECT_STATUS.md` ve
      `docs/verification/paket-i.md` §12 "koşturulmadı" diyordu. **Koşuldu:**
      `npm --prefix apps/station-web run test:e2e` → **74 passed (48.4s)**.
- [x] **`PROJECT_STATUS.md` düzgün kapanıyor (ADR-0011 §8).** Yanlış yerdeki
      "Sonraki asama" başlığı kaldırıldı (gövdesi H3'ün kapanış metniydi ve
      orada kaldı); Paket I'nın ardına bu tek bölüm kondu; Aşama 3 beyanının
      başlığına **"(tarihsel)"** eklendi ve içeriği **yeniden yazılmadan**
      yerinde bırakıldı.
- [x] **"Bu turda ölçülmeyenler" bloğunun dört maddesi silindi (ADR-0011 §9):**
      `packaging.yml` CI'da koştu, temiz profil ölçüldü, yeniden üretilebilirlik
      **ölçüldü-olumsuz** ("ölçülmedi" değil), commit/PR **yapıldı**. Tek ve
      güncel liste `docs/verification/paket-i.md` §12'dedir.

### Diğer düzeltilen bayat yüzeyler — hepsi ölçülerek

- [x] **`docs/architecture.md`:** migration aralığı `0001…0007` → **`0001…0009`**;
      tablo listesi **14 ad sayıyordu, gerçekte 20 tablo var** — taze bir
      veritabanı açılıp `sqlite_master` sayıldı: 19'unu migration'lar yaratıyor,
      `schema_migrations` Alembic'in kendi tablosu. Eksik altısı
      (`opencode_catalog_check`, `opencode_credential_metadata`,
      `opencode_model_snapshot`, `agent_run`, `agent_run_step`, `activity_event`)
      eklendi. §6'nın "paketleme/installer yapılmadı" maddesi `~~üstü çizili~~
      **Kapandı:**` kalıbına çevrildi. Bütçe maddesine görev katmanı ile agent
      koşu tavanının (`agent/budget.py`) **ayrı** olduğu netleştirmesi eklendi.
- [x] **`SECURITY.md` Aşama 3'ten bugüne taşındı.** Son teknik bölümü §6.2 idi.
      Yeni **§6.3** D→I arasını **dar kapsamda** anlatır ve ayrıntı için
      `docs/security-invariants.md`'ye işaret eder — her paketin ayrıntısını
      kopyalamak dördüncü bir sürüklenme yüzeyi olurdu. §7'ye iki kayıtlı sınır
      eklendi: **imzasız artefakt / SmartScreen / yeniden üretilemezlik**, ve
      **insan güvenlik incelemesinin yokluğu** (ADR-0001 §5).
- [x] **`AGENTS.md`** belge tablosu **11 belgeyi** anmıyordu; on biri de
      eklendi, yanına `docs/verification/` ve Paket J'nin iki kılavuz belgesi.
- [x] **`docs/ui-action-map.md`** başlığı H3'ü (§15) atlıyordu.
- [x] **`NOTICE`** lisans haritası `packaging/` dizinini listelemiyordu.
- [x] **`docs/identity-lifecycle.md` §5 write-gate tablosu koda karşı
      denetlendi.** `conformance_verified` ve `manifest_current` için
      "Aşama 4 / `not_implemented`" diyordu; `identity/write_gate.py`'nin altı
      `GateCheck`'i tek tek okundu: aşamalar **2 / 2B / 3**'tür ve `evaluate`
      bugün **hiçbir kontrolü** `NOT_IMPLEMENTED` üretmiyor — altısı da
      `PASSED` ya da `BLOCKED`. `CheckState.NOT_IMPLEMENTED` üyesi bilinçli
      olarak **duruyor**. Aynı dosyada ikinci bir bayat satır bulundu:
      parola "(Aşama 4'te) imzalama" için isteniyor deniyordu; imzalama
      **Paket D'de** geldi.
- [x] **`SettingsHelpPage.tsx`** "kullanim kilavuzu Paket J'de eklenecek"
      diyordu; kılavuz artık var. Kopya düzeltildi ve
      `pages.test.tsx`'teki iddia **silinmedi, çevrildi**: artık kılavuzun
      adının geçtiğini **ve** "eklenecek" sözünün geçmediğini birlikte ölçüyor.
- [x] **`docs/decisions/README.md`** indeksine ADR-0011 satırı eklendi.

### Bu turda ölçülmeyenler — adıyla

- **Gerçek DID, seed, private key, vault, `.tcrec` veya API anahtarı**
  okunmadı, istenmedi, üretilmedi. Kullanıcının `%LOCALAPPDATA%\TechnocoreStation`
  dizinine **dokunulmadı**.
- **Gerçek Technocore'a hiçbir istek gitmedi**; lobby hedef olmadı.
- **Hiçbir şey kurulmadı**, admin alınmadı, `git commit`/`push`/PR/tag
  **yapılmadı**.
- **İnsan güvenlik incelemesi hâlâ yok.** Bu paket onu kapatmaz —
  `SECURITY.md` §7'de **görünür** kılar.
- **`generate_seed`'in CSPRNG kullandığı** doğrudan test edilmiyor (yukarıda).
- **`apps/station-web/e2e/` ağacı lint edilmiyor**; `eslint.config.js` bir depo
  hook'u tarafından yazmaya kapalı ve bunu bir agent kaldıramaz. Kabul
  listesine gerekçesiyle aittir (ADR-0011 §7).

### Kapılar (bu turun son head'inde)

| Komut | Sonuç |
|---|---|
| `uv run --directory apps/station-api ruff check .` | **All checks passed!** |
| `uv run --project apps/station-api ruff check apps/station-api/src packages/technocore-conform/src tests` | **All checks passed!** |
| `uv run --project apps/station-api mypy --config-file apps/station-api/pyproject.toml` | **Success: no issues found in 133 source files** |
| `uv run --directory apps/station-api pytest ../../tests -p no:warnings` | **2212 passed** |
| `npm --prefix apps/station-web run lint` | **temiz** |
| `npm --prefix apps/station-web run test` | **315 passed** |
| `npm --prefix apps/station-web run build` | **başarılı** |
| `npm --prefix apps/station-web run test:e2e` | **74 passed** |

Taban 2206 pytest idi; Paket J altı test ekledi
(`test_security_invariants_doc.py`) ve hiçbirini silmedi.
**Mutasyon skoru: 7/7** — yedi mutant tek tek ekilip suite sürüldü
(SI-211/SI-243/SI-277/SI-105'in eski hâlleri, tam nitelikli bir referansın
yanlış dosyaya taşınması, alıntılanan bir test fonksiyonunun yeniden
adlandırılması, ve tablodaki her satır kimliğinin bozulması); **yedisi de
öldü**.

---
## Bu turda yapılmayanlar (Aşama 3 beyanı — **tarihsel**)

> Bu bölüm **Aşama 3'te** yazıldı ve o turun beyanıdır; bugünkü durumu
> anlatmaz (imzalama Paket D'de, Evidence/HMAC Paket E'de, agent çalışma
> ortamı Paket H2'de geldi). Tarihsel kayıt olarak **yeniden yazılmadan**
> bırakıldı; güncel durum yukarıdaki Paket J bölümündedir.

- **Gerçek kullanıcı kimlik durumu bu depo tarafından takip edilmez.**
  Depoya hiçbir operasyonel DID, seed, vault veya recovery dosyası
  eklenmemiştir; bir test bunu tarayarak doğrular. Bu aşamada geliştirme
  sırasında kullanıcının kurulu kimliğine dokunulmamıştır.
- **Operasyonel seed veya private key üretilmedi.** Tüm anahtar materyali
  `TEST-ONLY` etiketli, depoda yayımlanmış fixture'lardır.
- **Gerçek `.tcrec` recovery dosyası bırakılmadı.**
- **Identity vault açılmadı.**
- **Technocore'a hiçbir yazma isteği gönderilmedi.** Aşama 3 ile birlikte
  uygulama giden bir salt-okunur istemci taşır — tek modül, sabit kaynak
  registry'si — fakat hiçbir write yolu yoktur ve bir test bunu kaynak
  taramasıyla doğrular. (Aşama 2 ve öncesindeki "giden istemci yok" beyanı o
  aşamalar için doğruydu; bugünkü durum budur.)
- **Vendor pini güncellenmedi.** Upstream `main` ilerlemiş olsa da pin
  `7707cb63…` olarak bırakıldı.
- Nonce sayacı, rezervasyon, replay reddi ve gerçek imzalama yazılmadı (Aşama 4).
- LLM/Agent Runtime, Evidence/HMAC zinciri, çoklu DID yazılmadı.
- Commit, push, PR, tag, release veya deploy yapılmadı.
- Telemetri, analytics veya bulut servisi eklenmedi.

---

**Tarihsel Paket J beyanı: CODE_COMPLETE_USER_ACCEPTANCE_PENDING** (5 Eylül 2026).
Bağımsız incelemeyle model/teslim akışı eksikleri yeniden doğrulandığından güncel
tamamlanma beyanı değildir.

## Bağımsız inceleme düzeltmesi — devam ediyor

`codex/review-regressions`, taban `58b5423`. F1–F5 bağımsız regresyonlarla
yeniden üretildi. Geri alma/devam, çıktı sürümüne bağlı kabul ve kesilen
çalışma uzlaştırması uygulandı; bekleyen start/resume sırasında Durdur çalışır.
AppStatus cevap doğrulaması ve bölüm hata sınırı eklendi.
Dosyalar ve kırmızı/yeşil kanıt: [düzeltme raporu](docs/verification/review-fixes.md).
Yeni bağımlılık yok; mevcut kilitli sürümler korunuyor.
İlk tam koşudaki paket/index/test-yardımcısı hataları gideriliyor.
Sonraki iş model → plan → araç → çıktı → doğrulama → kabul → teslim akışı.
PR'lar bu turda merge edilmeden bağımsız incelemeye bırakılacak.
Canlı model/DID operasyonuna son mesajla yetki verildi; henüz yapılmadı.
Manuel tarayıcı ve görsel kabul yapılmadı; kullanıcıya ait.

## Paket H4 — model plan yolu ve makinece denetlenen kabul koşulları

Bağlayıcı karar: [ADR-0012](docs/decisions/0012-model-yolu-sozlesme-dogrulamasi-2026-09-06.md).
Uygulanmış hâli: [`docs/model-planning.md`](docs/model-planning.md).
Değişmezler: `docs/security-invariants.md` §9m (SI-330 … SI-343).

Bu paket **hiçbir güvenlik değişmezini gevşetmedi**; iki *olguyu* değiştirdi
ve o olgulara dayanan cümleleri düzeltti.

### Ne açıldı

- [x] **Model plan önerebiliyor.** `station_api/planner` üçüncü bir paket
      olarak eklendi: `station_api.agent` giden yüzey edinemez (kendi
      sınır taraması bunu reddeder), `station_api.opencode` görev/çalışma
      sahibi olamaz, birleştirme ikisini de içe alan ama hiçbirinin içe
      almadığı bir pakette yapıldı.
- [x] **Model kendi planını başlatamıyor.** Öneri `planned` fazında bir
      çalışmadır; `plan_run` yolu bir kişinin yazdığı planla aynıdır.
      `start_run`/`resume_run`/`request_stop` adları planner ağacında **hiç
      geçmiyor** ve bu sözdizim ağacından okunuyor.
- [x] **`reasoning_content` hiçbir yere gidemiyor.** Düzeltildi (bağımsız
      inceleme): korumanın tip düzeyinde olduğu ölçüldü — `PlanProposal`'ın
      böyle bir alanı yok — ve ölü `pop` döngüsü kaldırıldı. **"Gösterilmez"**
      yarısı tutmuyordu: sağlayıcı hata gövdesinin alıntısı `error` üyeli bir
      `200`'de tüm gövdeyi taşıyordu. Deny-list, kimlik bilgisi
      redaksiyonuyla aynı fonksiyona taşındı (`client._excerpt`); alıntı
      sağlayıcının hata metnini korur, muhakeme üyelerini kaybeder.
- [x] **Dördüncü tavan birimi:** `model_call_count`. `usage` ve `cost`
      olduğu gibi kaydediliyor, **tavan olarak okunmuyor**.
- [x] **Kabul koşulları** (yedinci kapalı registry) ve gerçek bir
      `test_result`; `ready_to_publish` artık **kanıttan türeyerek**
      erişilebilir. SI-222 korundu: hiçbir istek gövdesi bu durumu
      adlandıramıyor.
- [x] Migration **`0010`**: `agent_run.acceptance_json` (tek sütun, katkısal).

### Ne açılmadı

- **Keyfi kod/kabuk yürütmesi kapalı kaldı** (ADR-0008 §1). Planner ağacında
  `subprocess`/`exec`/`eval`/`os.system` yok ve tarama ekili çağrıda kırmızı.
- **Streaming açılmadı**: biçimi ölçülmedi, `streaming_supported` `False`.
- **Altıncı giden yüzey açılmadı**: `OUTBOUND_CLIENT_MODULES` beşte.
- **Zamanlayıcı yok**: bir tur, onu isteyen isteğin içinde olur.
- **Model oturumu diske yazılmıyor**; yeniden başlatmada kaybolur (SI-224).

### Bu turda ölçülenler

- Dört kapı yeşil (`ruff`, `ruff` ikinci kapsam, `mypy`, `pytest`).
- Her yeni guard mutasyonla sürüldü; skorlar düzeltme raporundadır.
- **Gerçek bir sağlayıcı isteği yapılmadı**: bütün testler
  `httpx.MockTransport` kullanıyor ve kimlik bilgisi depodaki sentetik
  `TEST-ONLY` sabitidir. Anahtar koda, teste, belgeye veya loga yazılmadı.
- Manuel tarayıcı kabulü ve görsel kabul **yapılmadı**; kullanıcıya aittir.


---

## Temizlik turu — ölü sabitler ve H4 sonrası bayatlayan cümleler (6 Eylül 2026)

Yeni yetenek yok. Bu tur iki şey yaptı: **ölçerek** ölü kod sildi ve model
yolu açılınca (ADR-0012, Paket H4) **yanlışa düşen** cümleleri düzeltti.
Hiçbir güvenlik testi silinmedi, `skip`/`xfail` edilmedi veya zayıflatılmadı;
bir tane **eklendi**.

### Ölçüm önce geldi

Bütün `apps/station-api/src` ve `packages/technocore-conform/src` ağacı AST
ile tarandı; her tanımlı ad için depo genelinde (kaynak + testler + belgeler
+ `packaging/` + `.github/` + `apps/station-web/src`) sözcük sınırlı referans
sayıldı, ve `getattr`/`globals`/`importlib` gibi dinamik erişim noktaları ayrı
listelendi. Sonuç: **ölü fonksiyon veya sınıf yok**. Yalnız üç modül düzeyi
adı yalnızca kendi tanımından ibaretti.

### Silinenler — üçünün ikisi

| Silinen | Kanıt | Neden gerçekten ölü |
|---|---|---|
| `technocore/projection.py::_SIGNED_BODY_FIELDS` | depo genelinde referans **1** (kendi tanımı) | `PLANNED_BODY_FIELDS` onu **geçersizleştirmişti**: `evaluate_signed_body` alan kümesini çağırandan (`PLANNED_BODY_FIELDS[lane]`) alıyor. Üstelik eski sabit **payload alanını** (`text`/`value`) taşımıyordu, yani biri onu geri bağlasa her `anyOf` dalını **yanlış** kümeye karşı yargılardı — ADR-0004 §2'nin adlandırdığı sessiz drift |
| `agent/service.py::MAX_PLAN_ACCEPTANCE` (+ `__all__` satırı) | referans **2** (tanımı + `__all__`) | Yorumu "route katmanı gövdeyi servisle aynı sayıya karşı sınırlasın diye yeniden dışa aktarıldı" diyordu. **Hiçbir route onu import etmiyordu**; servis doğrudan `MAX_ACCEPTANCE_CONDITIONS` kullanıyor. Yani iki sayı aslında **korumasızdı** ve üstlerinde koruduğunu söyleyen bir sabit duruyordu |

`_SIGNED_BODY_FIELDS`'in taşıdığı karar (`from` alanı bilerek yok) silinmedi;
`PLANNED_BODY_FIELDS`'in yorumuna taşındı.

### Silinen sabitin yerine **gerçek** koruma

`schemas.py` bilerek bir yaprak modüldür — `station_api`'den hiçbir şey
import etmez, çünkü bu süreçten çıkabilecek her alan orada tanımlıdır. Bu
yüzden `MAX_PLAN_ACCEPTANCE` tarif ettiği işi **yapamazdı**. Sabitin yerine
tarif ettiği koruma yazıldı:

`test_agent_acceptance.py::test_the_request_bound_is_the_same_number_the_service_enforces`
— `AgentPlanRequest.acceptance`'ın `max_length`'i `MAX_ACCEPTANCE_CONDITIONS`
ile **eşit** olmalı.

**Mutasyonla sürüldü:** `max_length` 8 → 7 yapıldığında test kırmızıya döndü
(`assert [7] == [8]`), geri alındığında yeşile. Yani ölü sabit, gerçekten
öldüren bir iddiaya dönüştü.

### Düzeltilen yanlış cümleler — hepsi H4/ADR-0012 sonrası bayatlamıştı

| Yer | Önce | Sonra |
|---|---|---|
| `README.md` | "…keyfi kod ve kabuk yürütmesi kapalıdır, **model çağrısı yoktur**…" | Madde listeden çıkarıldı; model yolunun ölçülerek açıldığı, modelin plan **önerebildiği** ama kendi planını başlatamadığı/onaylayamadığı yazıldı |
| `docs/opencode-connection.md` §"Doğrulanamayan" tablosu | "Streaming ve tool-call biçimi \| `TOOL_CALLS_SUPPORTED = False`" | Satır ikiye ayrıldı: streaming tabloda kaldı, tool-call **ölçüldüğü için** tablodan çıktı |
| `docs/opencode-connection.md` §4 | "**Streaming ve tool-call yoktur** (ADR-0005 §2)" | "Streaming yoktur… **Tool-call vardır**" — tek cümle ikisinden biri hakkında zorunlu olarak yanlış olduğu için ayrıldı |
| `docs/opencode-connection.md` §10 | "Tool-call \| H2 — aynı gerekçe"; "Gerçek bütçe sınırı ve eşzamanlılık \| H2" | İkisi de **kapandı** olarak işaretlendi; nereye kapandıkları yazıldı |
| `docs/proof-workspace.md` §4 | "`test_result` \| `not_implemented` \| Aynı sebep; H2'den devralınır" | Satır tablodan **çıktı**: H4 alanı gerçekten üretiyor. Yalnız cümle taşıyan plan hâlâ `not_implemented` |
| `docs/proof-workspace.md` §4 | "`independent_check` … **Model yolu kapalı** (ADR-0008 §2)" | Öncül düzeltildi: model yolu açık; alan yerinde kalıyor çünkü **planı öneren model o planın üçüncü tarafı değildir** |
| `docs/proof-workspace.md` §10 | "…`ready_to_publish`'e taşıyan bir kullanıcı rotası yoktur. Bu… **açık bir boşluktur**" | Boşluk H4'te `POST /api/tasks/{id}/publish-readiness` ile kapandı; SI-222'nin gevşetilmediği dört madde hâlinde yazıldı |
| `docs/architecture.md` paket tablosu | Aşama 6'da bitiyordu; `opencode/`, `workscan/`, `agent/`, `proof/`, `planner/` **yoktu** | Beş satır eklendi |
| `docs/architecture.md` secret sınırı | "**Gelecekteki** bir LLM/model adaptörü bu paketi import edemez" | Adaptör artık mevcut; kural bir öngörü değil `test_planner_boundary.py`'nin **ölçtüğü** olgu |
| `tasks/states.py` docstring | "the run never records a `test_result` reference… `ready_to_publish` stays out of reach" | İkisi de artık yanlış; SI-222'nin gerçek iddiası ("türetilir, **istenemez**") ayırt edilerek yazıldı |
| `modules/registry.py` `_PROOF_WORKSPACE_REQUIREMENTS` yorumu | "The model lane is closed (ADR-0008 2), so there is no second opinion" | Öncül gitti, sonuç kaldı ve **keskinleşti** |
| `PROJECT_STATUS.md` aşama checklist'i | Aşama **7'de bitiyordu** ve "Aşama 7 — Packaging" diyordu | Aşama 7 OpenCode'dur, paketleme **11**'dir. Tablo gövdedeki başlıklara göre düzeltildi ve her satır doğrulama raporuna bağlandı |

### Bilerek **yapılmayan** bir düzeltme — adıyla

`modules/registry.py`'deki `run_test_result_recorded` hâlâ
`implemented=False` ve `detail`'i "hiçbir kod yolu bu kanıtı üretemez" diyor.
Bu artık makinece denetlenebilir koşul taşıyan planlar için **doğru değil**.
Bayrak bu turda **çevrilmedi**, çünkü `complete` bayraktan türer: onu
çevirmek `agent_workspace` modülünün "tamamlandı" diyebilmesi demektir ve bu
bir belge düzeltmesi değil, **ürün durumu iddiası**dır — H3'ün
`user_accepted_the_run_output`'u kendi yüzeyini kuran commit'te çevirmesi
gibi, onu ölçen pakete aittir. Sessizce bırakılmadı: sebebi sabitin kendi
yorumuna yazıldı.

### Bu turda ölçülmeyenler ve dokunulmayanlar — adıyla

- **`apps/station-web/**` hiç açılmadı.** Ön yüz ajanı çalışıyordu.
  `api/types.ts` `tool_calls_supported`'ı hâlâ `false` **tipiyle** taşıyor
  (paket-h4 §5'te de kayıtlı) ve `TasksPanel.test.tsx` hâlâ "model çıktısı
  diye bir şey yoktur" metnini bekliyor. Frontend kapıları **koşulmadı**.
- **`workscan/**`, `routes/workscan.py` ve `schemas.py`'nin oda şemaları**
  başka bir ajanın canlı yazımıdır; okunmadı diye değil, **dokunulmadı** diye
  raporlanıyor. `workscan/snapshot.py::measured_caveat` referans sayısı 1
  ölçüldü ve **silinmedi**; o ajanın işi bitince bakılmalı.
- `docs/ui-action-map.md`'deki "model çıktısı diye bir şey yoktur" satırları
  **düzeltilmedi**: o belge arayüzün ne gösterdiğini anlatır ve arayüz şu an
  değişiyor. Belgeyi arayüzden önce düzeltmek onu ikinci kez yanlış yapardı.
- `client.py::AUTH_HEADER_CAVEAT` hâlâ "bu bir varsayımdır ve
  **doğrulanmamıştır**" diyor. ADR-0012'nin ölçümü `Authorization: Bearer`'ı
  metered uçta 200 ile geçirdi, yani cümlenin ikinci yarısı tartışmalı hâle
  geldi. **Değiştirilmedi**: ADR-0012 §6 güncellemeyi açıkça
  `tool_calls_supported` ve düzyazısıyla sınırladı, ve değişiklik iki
  `tests/security` iddiasına ve SI-235'e dokunurdu. Karar kullanıcıya bırakıldı.
