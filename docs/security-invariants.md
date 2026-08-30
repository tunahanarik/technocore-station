# Güvenlik değişmezleri

> Ana karar kaynağı: [`../Technocore-Station-Proje-Kunyesi.md`](../Technocore-Station-Proje-Kunyesi.md) §11, §13, §17.
> Politika özeti: [`../SECURITY.md`](../SECURITY.md).

Bu belge **test edilebilir** değişmezleri listeler. Her satır bir testle
eşleşir. Testler `tests/security/` altındadır ve **silinemez, `skip`/`xfail`
edilemez, iddiaları gevşetilemez** (bkz. `AGENTS.md` INV-06).

Durum sütunu: **A1** = Aşama 1'de uygulandı ve test edildi.
**A2+** = ilgili aşamada uygulanacak; bugün kod yolu yoktur.

---

## 1. Ağ ve bağlanma

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-01 | Uygulama yalnız `127.0.0.1` üzerinde bind olur | soket adresi `127.0.0.1` | `test_bind.py::test_launcher_binds_only_loopback` | A1 |
| SI-02 | Bind adresi asla `0.0.0.0` / `::` / LAN IP değildir | kaynakta yok | `test_bind.py::test_no_wildcard_bind_in_source` | A1 |
| SI-03 | Seçilen port işletim sisteminden alınan efemer porttur | 1024 < port < 65536, sabit değil | `test_bind.py::test_port_is_ephemeral` | A1 |

## 2. Açılış token'ı ve oturum

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-04 | Açılış token'ı 256-bit kriptografik rastgeledir | >=32 bayt entropi, benzersiz | `test_session.py::test_bootstrap_token_entropy` | A1 |
| SI-05 | Açılış token'ı **tek kullanımlıktır** | 2. kullanım 404 | `test_session.py::test_bootstrap_token_is_single_use` | A1 |
| SI-06 | Açılış token'ı **30 saniye** sonra geçersizdir | süre sonrası 404 | `test_session.py::test_bootstrap_token_expires_after_30_seconds` | A1 |
| SI-07 | Token hiçbir logda görünmez | log çıktısında yok | `test_logging.py::test_bootstrap_token_never_appears_in_logs` | A1 |
| SI-08 | Oturum cookie'si HttpOnly + SameSite=Strict + Path=/ | başlıkta doğrulanır | `test_session.py::test_session_cookie_flags` | A1 |
| SI-09 | Token ve session yalnız process memory'dedir | diske yazılmaz | `test_session.py::test_session_store_is_memory_only` | A1 |
| SI-10 | Cookie'siz korumalı endpoint **401** döner | 401 | `test_session.py::test_protected_endpoint_without_cookie_is_401` | A1 |

**Secure bayrağı notu:** Oturum loopback HTTP üzerinde çalıştığı için
cookie'ye `Secure` bayrağı **bilinçli olarak konmaz**. Tarayıcılar düz HTTP
üzerinde `Secure` cookie'leri tutarlı biçimde kabul etmez; uygulanamayacak
bir güvenlik iddiası üretmemek için bu bayrak dışarıda bırakılmıştır. Test
gerçek davranışı doğrular. Koruma `HttpOnly`, `SameSite=Strict`, exact-Host
kontrolü ve CSRF katmanından gelir.

## 3. Origin / Host / Fetch metadata

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-11 | `Host` tam olarak `127.0.0.1:<port>` olmalıdır | eşleşmeyen **421** | `test_host_origin.py::test_foreign_host_rejected_with_421` | A1 |
| SI-12 | `Host: localhost:<port>` **reddedilir** | 421 | `test_host_origin.py::test_localhost_host_rejected` | A1 |
| SI-13 | Yanlış port taşıyan `Host` reddedilir | 421 | `test_host_origin.py::test_wrong_port_host_rejected` | A1 |
| SI-14 | `Origin` varsa yalnız mevcut origin kabul edilir | yabancı **403** | `test_host_origin.py::test_foreign_origin_rejected` | A1 |
| SI-15 | `Sec-Fetch-Site: cross-site` reddedilir | 403 | `test_host_origin.py::test_cross_site_fetch_metadata_rejected` | A1 |
| SI-16 | `Sec-Fetch-Site: none` yalnız güvenli navigasyonda kabul edilir | POST'ta 403 | `test_host_origin.py::test_sec_fetch_site_none_rejected_on_state_change` | A1 |
| SI-17 | Production modunda dev origin kabul edilmez | 403 | `test_host_origin.py::test_dev_origin_rejected_in_production_mode` | A1 |
| SI-18 | `STATION_DEV` varsayılan **kapalı** ve fail-closed | default False | `test_host_origin.py::test_station_dev_defaults_to_closed` | A1 |

## 4. CSRF

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-19 | State-changing istek `X-Station-CSRF` **olmadan 403** | 403 | `test_csrf.py::test_state_change_without_csrf_header_is_403` | A1 |
| SI-20 | **Yanlış** CSRF değeri 403 | 403 | `test_csrf.py::test_state_change_with_wrong_csrf_is_403` | A1 |
| SI-21 | Doğru CSRF ile state-changing istek geçer | 200 | `test_csrf.py::test_state_change_with_valid_csrf_passes` | A1 |
| SI-22 | CSRF karşılaştırması sabit zamanlıdır | `compare_digest` | `test_csrf.py::test_csrf_comparison_is_constant_time` | A1 |
| SI-23 | CSRF değeri loglanmaz | log çıktısında yok | `test_logging.py::test_csrf_token_never_appears_in_logs` | A1 |
| SI-24 | CSRF değeri tarayıcıda kalıcı depolamaya yazılmaz | localStorage vb. yok | `test_frontend_bundle.py::test_no_browser_storage_for_csrf` | A1 |

## 5. CORS ve güvenlik başlıkları

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-25 | Hiçbir yanıtta CORS başlığı **yoktur** | `Access-Control-*` yok | `test_headers.py::test_no_cors_headers_in_any_response` | A1 |
| SI-26 | Kaynak ağacında CORS middleware yok | import yok | `test_headers.py::test_no_cors_middleware_in_source_tree` | A1 |
| SI-27 | Katı CSP uygulanır | `default-src 'none'`, `script-src 'self'` | `test_headers.py::test_content_security_policy_is_strict` | A1 |
| SI-28 | `Referrer-Policy: no-referrer` | eşleşir | `test_headers.py::test_referrer_policy` | A1 |
| SI-29 | `X-Content-Type-Options: nosniff` | eşleşir | `test_headers.py::test_content_type_options_nosniff` | A1 |
| SI-30 | Frame kullanımı engellenir | `frame-ancestors 'none'` + `X-Frame-Options: DENY` | `test_headers.py::test_framing_is_blocked` | A1 |
| SI-31 | `Permissions-Policy` gereksiz yetkileri kapatır | kamera/mikrofon/geo kapalı | `test_headers.py::test_permissions_policy_disables_capabilities` | A1 |
| SI-32 | Session/bootstrap yanıtları `Cache-Control: no-store` | eşleşir | `test_headers.py::test_no_store_on_session_and_bootstrap` | A1 |
| SI-33 | Hata yanıtları da sertleştirme başlıklarını taşır | 421/403'te var | `test_headers.py::test_security_headers_present_on_error_responses` | A1 |

## 6. Secret sızıntısı

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-34 | OpenAPI şemasında seed/private/secret/mnemonic alanı yok | yok | `test_no_secret_fields.py::test_openapi_schema_has_no_secret_field_names` | A1 |
| SI-35 | Response modellerinde secret alanı yok | yok | `test_no_secret_fields.py::test_response_models_have_no_secret_fields` | A1 |
| SI-36 | Veritabanı yolu API yanıtında dönmez | yok | `test_no_secret_fields.py::test_database_path_is_not_exposed` | A1 |
| SI-37 | Frontend bundle'da hardcoded localhost backend portu yok | yok | `test_frontend_bundle.py::test_no_hardcoded_backend_port_in_bundle` | A1 |
| SI-38 | Seed hiçbir HTTP response, log veya bundle'da görünmez | — (AC-06) | Aşama 2 | A2 |

## 7. Veritabanı

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-39 | SQLite **WAL** modu aktif | `journal_mode = wal` | `test_database.py::test_wal_journal_mode_enabled` | A1 |
| SI-40 | `foreign_keys` **aktif** | `PRAGMA foreign_keys = 1` | `test_database.py::test_foreign_keys_enabled` | A1 |
| SI-41 | Migration ikinci kez çalıştırıldığında hata vermez | idempotent | `test_database.py::test_migrations_are_idempotent` | A1 |
| SI-42 | Migration sırası deterministiktir | tek head, lineer zincir | `test_database.py::test_migration_chain_is_deterministic` | A1 |
| SI-43 | Şemada seed/secret sütunu yoktur | yok | `test_database.py::test_schema_has_no_secret_columns` | A1 |

## 8. Frontend

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-44 | HeroUI v2 / NextUI bağımlılığı yoktur | package.json temiz | `test_frontend_bundle.py::test_no_heroui_v2_or_nextui_dependency` | A1 |
| SI-45 | Uzak CDN / Google Fonts referansı yoktur | yok | `test_frontend_bundle.py::test_no_remote_asset_references` | A1 |
| SI-46 | Production build başarılıdır | `dist/` üretilir | `test_frontend_bundle.py::test_production_build_output_exists` | A1 |
| SI-47 | `index.html` içinde inline script yoktur | CSP `script-src 'self'` ile uyumlu | `test_frontend_bundle.py::test_no_inline_script_in_index_html` | A1 |
| SI-48 | Secret input veya private key alanı yoktur | yok | `apps/station-web` vitest: `pages.test.tsx` | A1 |

## 9. Aşama 2+ değişmezleri (bugün kod yolu yok)

| ID | Değişmez | Aşama |
|---|---|---|
| SI-49 | Seed hiçbir tabloda bulunmaz; ayrı DPAPI zarfındadır | 2 |
| SI-50 | Paroladan seed türetilmez | 2 |
| SI-51 | Restore-test tamamlanmadan hiçbir Technocore write çalışmaz | 2 |
| SI-52 | Yanlış parola ve kurcalanmış recovery **aynı** genel hatayı verir | 2 |
| SI-53 | TLS doğrulaması kapatılamaz; host allow-list zorunludur | 3 |
| SI-54 | Technocore içeriği HTML veya tıklanabilir dış link olarak render edilmez | 3 |
| SI-55 | Kullanıcı onayı olmadan mesaj/note gönderilemez | 4 |
| SI-56 | Manifest imza alanı değişirse write gate kapanır | 4 |

## 9b. Aşama 2B değişmezleri (uygulandı)

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-57 | Uygunluk self-test'i başarısızsa write gate kapanır | `allowed=False`, `conformance_verified` bloklar | `test_conformance_boundary.py::test_a_failing_self_test_closes_the_write_gate` | A2B |
| SI-58 | Self-test crash'i "geçti" sayılmaz | `passed=False` | `test_conformance_boundary.py::test_a_crashing_self_test_is_not_a_pass` | A2B |
| SI-59 | `/api/conformance/status` yanıtı anahtar materyali taşımaz | beklenen digest dışında 64-hex yok | `test_conformance_boundary.py::test_conformance_status_exposes_no_key_material` | A2B |
| SI-60 | Uygunluk paketi uygulama, platform veya ağ modülü import etmez | offender yok | `test_conformance_boundary.py::test_the_conformance_package_imports_nothing_heavy` | A2B |
| SI-61 | Paket importunun dosya veya ağ yan etkisi yoktur | import-time çağrı yok, socket açılmaz | `test_conformance_boundary.py` + `test_selftest.py::test_importing_the_package_runs_no_self_test` | A2B |
| SI-62 | CLI seed, parola veya seed-dosyası argümanı sunmaz | seçenek yok, `os.environ` yok | `test_conformance_boundary.py::test_the_conformance_cli_offers_no_seed_input` | A2B |
| SI-63 | PyNaCl production import grafiğinde bulunmaz | `sys.modules` temiz | `test_conformance_boundary.py::test_pynacl_is_absent_from_the_production_import_graph` | A2B |
| SI-64 | Vektör paketi düzenlenerek kapı gevşetilemez | digest pini tutmazsa fail-closed | `test_selftest.py::test_a_tampered_bundle_digest_fails_closed` | A2B |

---

## 10. Kalan riskler (dürüst kapsam)

Bu değişmezlerin **savunmadığı** durumlar [`../SECURITY.md`](../SECURITY.md)
§7'de listelenir: aynı Windows kullanıcısı olarak çalışan malware, host izni
verilmiş kötü niyetli tarayıcı uzantısı, zayıf recovery parolası, resmî
domain ele geçirilmesi ve supply-chain saldırıları.

Güvenlik testlerinin "değiştirilemez" olduğu iddiası teknik olarak mutlak
değildir — bir coding agent dosyayı değiştirebilir. Test tabanı yalnız
**yardımcı** bir kontroldür; **insan review'u zorunludur**.
