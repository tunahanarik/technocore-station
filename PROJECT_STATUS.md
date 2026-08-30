# PROJECT_STATUS

> Ana karar kaynağı: [`Technocore-Station-Proje-Kunyesi.md`](Technocore-Station-Proje-Kunyesi.md)
> Çalışma kuralları: [`AGENTS.md`](AGENTS.md) · [`CLAUDE.md`](CLAUDE.md)
> Son güncelleme: **30 Ağustos 2026**

## Aşama checklist

- [x] **Aşama 0 — Spesifikasyon** — tamamlandı
- [x] **Aşama 1 — Güvenli iskelet** — tamamlandı
- [ ] **Aşama 2 — Identity & Recovery** — sıradaki
- [ ] **Aşama 2B — Conformance**
- [ ] **Aşama 3 — Salt okunur Technocore**
- [ ] **Aşama 4 — Composer & Participation**
- [ ] **Aşama 5 — Evidence & Audit**
- [ ] **Aşama 6 — Project Modules**
- [ ] **Aşama 7 — Packaging**

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

## Sonraki aşama: Aşama 2 — Identity & Recovery

Kapsam: DPAPI vault, seed üretme/import, `.tcrec` şifreli recovery
(Argon2id + ChaCha20-Poly1305), restore-test gate.
Kabul kriterleri: **AC-01, AC-06, AC-10, AC-11, AC-12**.

Ön koşul: kullanıcı açıkça "başlayalım" demeden gerçek DID/seed üretilmez
(künye §20.2).

---

## Bu turda yapılmayanlar (açık beyan)

- **Gerçek DID oluşturulmadı.**
- **Secret seed, private key veya recovery dosyası oluşturulmadı.**
- **Technocore'a write isteği gönderilmedi.** Hiçbir mesaj, note veya başka
  yazma isteği gönderilmedi; uygulamada giden network istemcisi yoktur.
- Git commit, push, deploy veya public repo işlemi yapılmadı.
- Telemetri, analytics veya bulut servisi eklenmedi.
