# station-api

Technocore Station'ın yerel çekirdeği. **Yalnız loopback.** CORS yok.
Bu aşamada hiçbir giden network isteği yoktur.

Tam mimari: [`../../docs/architecture.md`](../../docs/architecture.md).
Güvenlik değişmezleri: [`../../docs/security-invariants.md`](../../docs/security-invariants.md).

## Çalıştırma

Depo kökünden:

```bash
uv run --project apps/station-api python -m station_api
```

Launcher `127.0.0.1:0` adresine bind eder, işletim sisteminden efemer bir
port alır, tek kullanımlık bir açılış token'ı üretir ve tarayıcıyı açar.
**Token loglanmaz.**

## Modül haritası

| Modül | Sorumluluk |
|---|---|
| `config.py` | Fail-closed ayarlar; `LOOPBACK_HOST` sabiti |
| `launcher.py` | Socket bind, efemer port, token, tarayıcı, uvicorn |
| `app.py` | FastAPI factory, middleware zinciri, SPA servisi |
| `logging_setup.py` | Zorunlu log redaksiyonu |
| `security/tokens.py` | Tek kullanımlık, 30 sn ömürlü açılış token'ı |
| `security/sessions.py` | Bellek içi oturum ve CSRF değeri |
| `security/middleware.py` | Host / Origin / Sec-Fetch-Site / CSRF / başlıklar |
| `db/engine.py` | SQLite engine, WAL + foreign_keys PRAGMA |
| `db/models.py` | `app_metadata` (secret sütunu yok) |
| `db/migrations_runner.py` | Alembic sürücüsü, `schema_migrations` ledger |
| `routes/session.py` | `/session/<token>` handoff |
| `routes/api.py` | `/api/health`, `/api/session/bootstrap`, `/api/app/status` |
| `schemas.py` | Pydantic response modelleri |

## Endpoint yüzeyi (Aşama 1)

| Method | Yol | Koruma | Not |
|---|---|---|---|
| GET | `/api/health` | public | Minimum bilgi |
| GET | `/session/{token}` | token | Tek kullanımlık, 30 sn |
| GET | `/api/session/bootstrap` | cookie | CSRF değerini döndürür, `no-store` |
| GET | `/api/app/status` | cookie | DB yolu **dönmez** |

Henüz **yok**: identity, seed/recovery, signing, Technocore write, network
client. OpenAPI şeması HTTP üzerinden **servis edilmez**
(`openapi_url=None`); testler `app.openapi()` ile in-process okur.

## Ortam değişkenleri

| Değişken | Varsayılan | Not |
|---|---|---|
| `STATION_DEV` | *(kapalı)* | Fail-closed; yalnız `1/true/yes/on` açar |
| `STATION_DATA_DIR` | `%LOCALAPPDATA%\TechnocoreStation` | Testler geçici dizin kullanır |
| `STATION_DEV_PORT` | `8787` | Yalnız dev; production efemer porttur |
| `STATION_DEV_ORIGIN` | `http://127.0.0.1:5173` | Yalnız dev'de kabul edilir |

## Migration

Migration'lar her açılışta çalışır ve idempotenttir. Elle:

```bash
uv run --project apps/station-api alembic upgrade head
```

Version tablosu Alembic varsayılanı `alembic_version` değil,
**`schema_migrations`**'tır (IMP-102).
