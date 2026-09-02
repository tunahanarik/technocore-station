# PROJECT_STATUS

> Ana karar kaynağı: [`Technocore-Station-Proje-Kunyesi.md`](Technocore-Station-Proje-Kunyesi.md)
> Çalışma kuralları: [`AGENTS.md`](AGENTS.md) · [`CLAUDE.md`](CLAUDE.md)
> Son güncelleme: **1 Eylül 2026** (Aşama 3.1)

## Aşama checklist

- [x] **Aşama 0 — Spesifikasyon** — tamamlandı
- [x] **Aşama 1 — Güvenli iskelet** — tamamlandı
- [x] **Aşama 2 — Identity & Recovery** — tamamlandı
- [x] **Aşama 2B — Conformance** — tamamlandı
- [x] **Aşama 3 — Salt okunur Technocore** — tamamlandı
- [x] **Aşama 3.1 — Protokol projeksiyonu düzeltmesi** — tamamlandı
- [ ] **Aşama 4 — Composer & Participation** — sıradaki
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
- [x] 17 test fonksiyonu / 50 parametrik senaryo; **795 pytest** + 59 Vitest.
- [x] SI-120…SI-124, IMP-254…IMP-258.

## Sonraki aşama: Aşama 4 — Composer & Participation

Kapsam: kullanıcı onaylı mesaj/note oluşturma, nonce rezervasyonu (transaction
içinde, `(did, room)` başına monoton), vault üzerinden imzalama ve gönderim.
Kabul kriterleri: **AC-13, AC-14, AC-16**.

Aşama 4 gelene kadar Compose yüzeyi kilitli kalır ve üründe hiçbir giden
yazma kodu bulunmaz.

Ön koşul: kullanıcı açıkça "başlayalım" demeden gerçek gönderim yapılmaz.

---

## Bu turda yapılmayanlar (Aşama 3 beyanı)

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
