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
| SI-48 | **Seed, private key veya recovery parolası** için giriş/gösterim alanı yoktur (Paket G'de daraltıldı: provider API anahtarı girişi ADR-0001 §6'nın yetkilendirdiği dar istisnadır ve anahtarı **geri gösteren** hiçbir alan yoktur) | yok | `apps/station-web` vitest: `pages.test.tsx` | A1 → G |

## 9. Aşama 2+ değişmezleri (bugün kod yolu yok)

| ID | Değişmez | Aşama |
|---|---|---|
| SI-49 | Seed hiçbir tabloda bulunmaz; ayrı DPAPI zarfındadır | 2 |
| SI-50 | Paroladan seed türetilmez | 2 |
| SI-51 | Restore-test tamamlanmadan hiçbir Technocore write çalışmaz | 2 |
| SI-52 | Yanlış parola ve kurcalanmış recovery **aynı** genel hatayı verir | 2 |
| SI-53 | TLS doğrulaması kapatılamaz; host allow-list zorunludur | 3 — **uygulandı**, bkz. §9c |
| SI-54 | Technocore içeriği HTML veya tıklanabilir dış link olarak render edilmez | 3 — **uygulandı**, bkz. §9c |
| SI-55 | Kullanıcı onayı olmadan mesaj/note gönderilemez | 4 |
| SI-56 | Manifest imza alanı değişirse write gate kapanır | 3 — **uygulandı**, bkz. §9c |

## 9c. Aşama 3 değişmezleri (uygulandı)

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-65 | Yalnız `https://technocore.chat`; şema/host/port tam eşleşme | allow-list dışı her biçim reddedilir | `test_technocore_readonly.py::test_every_way_around_the_allow_list_is_refused` | A3 |
| SI-66 | İstemci URL, method, header veya TLS ayarı kabul etmez | parametre yok | `::test_the_client_takes_no_url_method_or_tls_setting` | A3 |
| SI-67 | TLS doğrulaması kapatılamaz | `verify=` hiçbir yerde geçmez | `::test_tls_verification_is_never_disabled` | A3 |
| SI-68 | Redirect takip edilmez | 3xx hata | `::test_a_redirect_is_never_followed` | A3 |
| SI-69 | Boyut sınırı decompress edilmiş bayt üzerinde | gzip bombası reddedilir | `::test_a_body_over_the_cap_is_refused_on_decompressed_bytes` | A3 |
| SI-70 | Retry sınırlı; `Retry-After` üst sınırla | en çok 3 deneme | `::test_retries_are_bounded_and_then_give_up`, `::test_a_retry_after_header_is_honoured_but_clamped` | A3 |
| SI-71 | **Technocore istemcilerinin** giden isteğinde cookie/auth/DID/CSRF yok (Paket G'de daraltıldı; OpenCode için SI-234) | header temiz | `::test_the_request_carries_no_identity_or_credential` | A3 → G |
| SI-72 | GET yazma yollarına ulaşan kod yolu yok | AST literal taraması | `test_write_gate.py::test_no_code_path_can_reach_a_technocore_write_endpoint` | A3 |
| SI-73 | HTTP istemcisi yalnız **incelenmiş dört** modülde; allow-list düz küme veya dizin adı değil, **kaynak köküne göreli tam yol** kümesidir (D'de üçe, G'de dörde genişletildi — daraltılarak) | `station_api/technocore/{client,write_client,evidence_client}.py` + `station_api/opencode/client.py`; başka hiçbir yol, ve bir dizinin adını ödünç alan yeni bir dizin muafiyet almaz | `test_write_gate.py::test_httpx_is_imported_only_by_the_reviewed_clients`, `::test_every_reviewed_client_module_actually_exists`, `::test_the_allow_list_is_keyed_by_full_path_and_not_by_a_bare_name`, `::test_a_client_planted_where_a_directory_borrows_an_allowed_name_is_refused`, `::test_a_client_planted_where_a_directory_borrows_the_technocore_name_is_refused`, `::test_the_write_client_is_not_reachable_from_the_read_path` | A3 → D → G |
| SI-74 | Açılışta otomatik dış istek yok | `never_checked` | `::test_reading_status_makes_no_outbound_request` | A3 |
| SI-75 | Refresh session + CSRF gerektirir | 401/403 | `::test_refresh_requires_session_and_csrf` | A3 |
| SI-76 | Kritik alan değişince `manifest_current=false` (AC-15) | `drifted` | `::test_a_critical_change_makes_the_manifest_not_current` | A3 |
| SI-77 | Ağ hatası eski başarılı verdict'i kullanmaz | `unavailable` | `::test_a_later_failure_does_not_inherit_an_earlier_success` | A3 |
| SI-78 | Persist edilen snapshot yeni process'te kapıyı açmaz | `never_checked` | `::test_a_persisted_check_does_not_open_a_fresh_process` | A3 |
| SI-79 | API yanıtında raw gövde yoktur | belge işaretleri yok | `::test_the_response_carries_no_document_body` | A3 |
| SI-80 | DB'de cookie veya keyfi header saklanmaz | temiz | `::test_the_database_never_stores_a_cookie_or_arbitrary_header` | A3 |
| SI-81 | Snapshot retention sınırlıdır | son 50 koşu | `::test_snapshots_are_written_and_retained_within_the_limit` | A3 |
| SI-82 | Uzak içerik link veya HTML olmaz (AC-17) | anchor yok | `pages.test.tsx` — "never turns a remote URL into a clickable link" | A3 |
| SI-83 | ~~Tüm ön koşullar geçse bile yazma yolu yoktur~~ → **Paket D ile bilinçli olarak değişti**, bkz. §9e ve SI-129 | tüm kapılar açıkken bile hiçbir yazma çıkmaz | `test_technocore_readonly.py::test_no_write_leaves_the_process_even_when_every_check_passes` | A3 → **D'de değiştirildi** |
| SI-84 | Resmî belgede hiçbir kritik alan "bulunamadı" olmaz | 0 okunamayan alan | `::test_the_official_documents_raise_no_missing_field_alarm` | A3.1 |
| SI-85 | İmzalı lane kısıtları koşullu şemadan okunur | `dependentSchemas.did` | `test_manifest_oracle.py::test_the_credentials_are_conditional_not_unconditional_properties` | A3.1 |
| SI-86 | Sadece `properties`'e yazılmış kısıt, koşullu güvence olmadan geçmez | `current` değil | `::test_a_missing_conditional_schema_is_not_rescued_by_properties` | A3.1 |
| SI-87 | Her iki lane'de `sig`/`nonce` zorunluluğu kaybolursa kapı kapanır | `current` değil | `::test_a_critical_change_makes_the_manifest_not_current` | A3.1 |
| SI-88 | Desteklenmeyen koşullu şema fail-closed davranır | `unavailable` | `::test_an_unsupported_conditional_schema_is_never_current` | A3.1 |
| SI-89 | Değerlendirilemeyen alan "sunucu değiştirdi" iddiası üretmez | gerekçe "doğrulanamadı" | `::test_an_unevaluable_field_never_claims_the_server_changed_anything` | A3.1 |
| SI-90 | Gölge (noktalı) anahtar gerçek konumu gölgeleyemez | verdict değişmez | `::test_a_shadow_key_cannot_redirect_a_pointer` | A3.1 |
| SI-91 | Karşılaştırma tipi doğrular; `"86"` ≠ `86` | `current` değil | `::test_a_length_bound_of_the_wrong_type_is_not_accepted` | A3.1 |
| SI-92 | Canonical payload'a eklenen boşluk/kontrol karakteri silinip eşit sayılmaz | `drifted` | `::test_whitespace_around_a_canonical_payload_is_not_the_same_payload` | A3.1 |
| SI-93 | Sözleşmeyi reddeden açıklama, doğru kelimeleri taşısa da geçmez | `current` değil | `::test_a_description_that_denies_the_contract_does_not_pass` | A3.1 |
| SI-94 | Beklenen imza kalıbı canlıdan değil kendi motorumuzdan türetilir | `SIGNATURE_PATTERN` | `::test_the_expectation_comes_from_our_own_conformance_engine` | A3.1 |
| SI-95 | Referans belgeleri pinlenmiş üreticiyle bayt bayt aynıdır | bayt eşitliği | `test_manifest_oracle.py::test_the_stored_documents_are_byte_identical_to_a_fresh_run` | A3.1 |
| SI-96 | UI, okunamayan alanı "değişmiş" diye göstermez | ayrı uyarı | `pages.test.tsx` — "does not call an unreadable field a change the server made" | A3.1 |
| SI-97 | Alan düğümündeki `not`/`$ref`/`allOf`/`oneOf`/`if`/`enum`/`const` sessizce yok sayılmaz | `unavailable` | `::test_any_unreadable_keyword_in_a_field_node_closes_the_gate` | A3.1 |
| SI-98 | Koşulsuz ve koşullu uzunluk sınırları birlikte değerlendirilir | `drifted` (boş aralık) | `::test_an_unconditional_length_that_contradicts_the_conditional_one` | A3.1 |
| SI-99 | Koşulsuz ve koşullu `type` çelişkisi kapıyı kapatır | `drifted` | `::test_an_unconditional_type_that_contradicts_the_conditional_one` | A3.1 |
| SI-100 | İkinci bir koşulsuz `pattern` yok sayılmaz | `unavailable` | `::test_a_second_unconditional_pattern_is_not_silently_ignored` | A3.1 |
| SI-101 | DID'i yasaklayan `anyOf` kapıyı kapatır | `unavailable` | `::test_an_any_of_that_forbids_the_did_is_not_current` | A3.1 |
| SI-102 | Hiçbir dalı imzalı gövdeyle sağlanamayan `anyOf` kapıyı kapatır | `drifted` | `::test_an_any_of_with_no_satisfiable_branch_is_not_current` | A3.1 |
| SI-103 | Yalnız açıklama/başlık/örnek değişimi protokol alarmı üretmez | `current` | `::test_annotations_anywhere_in_the_body_are_not_a_protocol_change` | A3.1 |
| SI-104 | Gövde şeması anahtar sırası değişimi drift değildir | `current` | `::test_reordering_the_body_schema_keys_is_not_a_protocol_change` | A3.1 |
| SI-105 | Her iki lane aynı değerlendiriciden geçer | mesaj + note parametrik | `::test_*` (`_LANES` ile parametrik) | A3.1 |
| SI-106 | Gövde/koşullu düğüm `type` değeri okunur; `"object"` değilse kapı kapanır | `drifted` | `::test_a_schema_that_refuses_the_signed_body_is_never_current[body-type-not-object]` | A3.1 |
| SI-107 | Gövde `required` planlanan gövdede olmayan ad isterse kapı kapanır | `drifted` | `::test_a_schema_that_refuses_the_signed_body_is_never_current[body-requires-unknown-field]` | A3.1 |
| SI-108 | İmzalı gövdenin taşıdığı **her** alana bağlı `dependentSchemas` uygulanır | `drifted` | `::test_a_dependency_on_any_carried_field_applies` | A3.1 |
| SI-109 | Koşullu `properties` içindeki `did` de denetlenir | `unavailable` | `::test_a_schema_that_refuses_the_signed_body_is_never_current[conditional-did-negated]` | A3.1 |
| SI-110 | Bozuk uzunluk sınırı "sınır yok" diye okunmaz | `unavailable` | `::test_a_malformed_bound_is_not_read_as_no_bound` | A3.1 |
| SI-111 | `null`/`false`/`0` eksik anahtardan ayrılır | `unavailable` | `::test_a_type_that_is_not_a_string_is_unreadable`, `::test_a_required_list_that_is_not_a_list_of_names_is_unreadable` | A3.1 |
| SI-112 | `bool` uzunluk olarak kabul edilmez | `unavailable` | `::test_a_boolean_is_not_accepted_as_a_length` | A3.1 |
| SI-113 | Negatif uzunluk sınırı geçersizdir | `unavailable` | `::test_a_negative_length_bound_is_unreadable` | A3.1 |
| SI-114 | Station'ın gönderdiği uzunluğu dışlayan sınır kapıyı kapatır | `current` değil | `::test_a_bound_excluding_what_station_sends_closes_the_gate` | A3.1 |
| SI-115 | İzin verilen her doğrulama anahtarı fiilen değerlendirilir | her anahtar için kapanma | `::test_every_allowed_validation_keyword_is_actually_evaluated` | A3.1 |
| SI-116 | Yalnız `/healthz` 503 iken protokol verdict'i etkilenmez | `current`, kaynak hatası görünür | `::test_only_health_returning_503_leaves_the_protocol_verdict_intact` | A3.1 |
| SI-117 | `/openapi.json` 503 iken kapı kapanır | `unavailable` | `::test_openapi_returning_503_closes_the_gate` | A3.1 |
| SI-118 | Başarılı kontrolden sonra gelen 503 eski verdict'i geri getirmez | `unavailable`, eski zaman görünür | `::test_a_503_after_a_success_shows_the_old_time_but_not_the_old_verdict` | A3.1 |
| SI-119 | Zorunlu belge denemesi sınırlıdır | 3 deneme | `::test_a_required_document_is_retried_a_bounded_number_of_times` | A3.1 |
| SI-120 | Şema üyesindeki `null` geçersiz üyedir, yokluk değildir | `unavailable` | Aşama B testleri (`Stage B: schema boundaries`) | B |
| SI-121 | `required`/`anyOf.required` tekrarlı ad içeremez | `unavailable` | Aşama B testleri | B |
| SI-122 | Derlenemeyen veya payload'da yayımlanan pattern değerlendirilemez | `unavailable` | Aşama B testleri | B |
| SI-123 | Nonce aralığını daraltan sınır kapıyı kapatır (SOME-exclusion) | `drifted` | Aşama B nonce sınır matrisi | B |
| SI-124 | Payload limit değişikliği uyarıdır; etkin limit tavanla kırpılıp dışa verilir | `current`+uyarı | Aşama B payload testleri | B |

## 9d. Paket C değişmezleri — hata sözleşmesi (uygulandı)

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-125 | Her HTTP yanıtı sunucu üretimi `X-Station-Request-Id` taşır; middleware retleri (421/403) dahil, değer istemciden asla yansıtılmaz | 32-hex `uuid4().hex`, istek başına benzersiz | `test_error_contract.py::test_every_response_class_carries_a_unique_request_id`, `::test_a_csrf_rejection_carries_a_request_id`, `::test_a_client_supplied_request_id_is_never_reflected` | C |
| SI-126 | İşlenmeyen istisna istemciye traceback sızdırmaz: gövde tam olarak `{"detail": "internal_error"}`, traceback yalnız sunucu logunda ve request id ile anahtarlı | 500 + sertleştirme başlıkları + request id | `test_error_contract.py::test_an_unhandled_exception_returns_exactly_the_contract_body`, `::test_the_500_body_leaks_no_traceback_and_no_secret_shape`, `::test_the_500_response_is_as_hardened_as_any_other` | C |
| SI-127 | Redaksiyon kaydın **her** metin yüzeyine uygulanır: mesaj, traceback (`exc_info`/`exc_text`) ve `stack_info`. Traceback'i formatlayıcı, filtreler çalıştıktan *sonra* üretir; istisnanın kendi `repr`'i sızdıran değeri taşıyabilir. Zırhın logladığı traceback ile uvicorn'un yeniden fırlatma sonrası yazdığı ikinci kopya aynı filtreden geçer | Formatlanmış handler çıktısında `<redacted>`; kayıtlı gizli değer ve `/session/<token>` yok | `test_logging.py::test_a_traceback_is_redacted_in_the_formatted_log_output`, `::test_a_chained_cause_in_a_traceback_is_redacted`, `::test_a_stack_dump_is_redacted_in_the_formatted_log_output`, `::test_an_already_rendered_exc_text_is_redacted`, `::test_the_uvicorn_loggers_carry_the_filter_themselves`, `::test_the_shielded_500_traceback_is_redacted_end_to_end` | C |
| SI-128 | Hata yanıtı hangi yolda doğarsa doğsun önbelleklenemez: zırh `no-store` + `Pragma: no-cache` başlıklarını `NO_STORE_PREFIXES`'ten bağımsız uygular | 500 → `Cache-Control: no-store`, `Pragma: no-cache`; `/api` dışı yollarda da | `test_error_contract.py::test_a_500_outside_the_no_store_prefixes_is_still_uncacheable`, `::test_the_500_response_is_as_hardened_as_any_other`, `::test_a_success_outside_the_no_store_prefixes_stays_cacheable` | C |

## 9e. Paket D değişmezleri — Composer & Participation (uygulandı)

### SI-83 neden ve nasıl değişti

Paket D'ye kadar SI-83 şunu söylüyordu: *"Tüm ön koşullar geçse bile yazma
yolu yoktur."* Bu, Aşama 3 için **dürüst** bir ifadeydi; ürün gerçekten bir
yazma kodu taşımıyordu. Paket D bunu **bilinçli olarak** değiştirir
(ADR-0002 §5): artık bir yazma yolu vardır.

Değişmez silinmedi, **daraltıldı**. Eski cümlenin koruduğu şey "route yok"
değildi; korumaya çalıştığı şey *kullanıcının kararı olmadan hiçbir şeyin
dışarı çıkmaması*ydı. Yeni hâli tam olarak bunu söyler ve daha güçlü bir
şekilde test edilir: eski test route adlarında `compose`/`sign`/`send`
geçmediğini iddia ediyordu — ve o iddia, kullanılan FastAPI sürümünde
`app.routes` yol taşımayan sarmalayıcı nesneler döndürdüğü için **boş
kümeye** bakıyordu, yani hiçbir şey doğrulamıyordu. Yeni test giden yazma
taşıyıcısını doğrudan izler: bütün kapılar açıkken, manifest güncelken ve her
okuma yüzeyi defalarca okunurken **tek bir yazma isteği bile** süreçten
çıkmaz (SI-129).

Bu değişiklik hiçbir güvenlik değişmezini gevşetmez. INV-01…INV-09 aynen
geçerlidir; gerçek servise yazma bu turda yapılmamıştır ve insan güvenlik
incelemesi ertelenmiş kalan risktir (ADR-0001 §5).

### Yeni değişmezler

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-129 | Bütün ön koşullar geçse **bile** kullanıcı onayı olmadan hiçbir yazma süreçten çıkmaz (AC-16) | 0 giden istek | `test_technocore_readonly.py::test_no_write_leaves_the_process_even_when_every_check_passes` | D |
| SI-130 | Nonce `(did, room)` başına kesin monotondur | ardışık değerler artar, tekrar yok | `test_nonce_reservation.py::test_successive_reservations_strictly_increase`, `::test_the_counter_is_scoped_to_the_did_and_the_room` | D |
| SI-131 | Eşzamanlı ayırmalar aynı nonce'u üretemez | 16 iş parçacığı × 12, hepsi farklı; iki bağımsız reserver aynı DB'de çakışmaz | `::test_concurrent_reservations_never_collide`, `::test_two_independent_reservers_on_one_database_never_collide`, `::test_the_database_itself_refuses_a_duplicate` | D |
| SI-132 | Saat geri giderse nonce yeniden verilmez | `max(yerel+1, saat)` | `::test_a_clock_that_jumps_backwards_does_not_reissue_a_number` | D |
| SI-133 | Crash/resume sonrası nonce yeniden kullanılmaz | yeni değer eskisinden büyük | `::test_a_crash_between_reserving_and_sending_burns_the_number`, `test_compose_flow.py::test_the_reservation_survives_a_reopened_engine` | D |
| SI-134 | İptal edilen nonce dolaşıma dönmez | `cancelled` + sayaç ilerlemiş | `::test_a_cancelled_reservation_is_not_returned_to_circulation`, `test_compose_flow.py::test_a_failed_signature_does_not_leave_a_dangling_reservation` | D |
| SI-135 | Başında sıfır olan nonce asla üretilmez (ADR-0002 §4.2) | `"007"` üretilemez | `::test_no_reserved_nonce_ever_carries_a_leading_zero` | D |
| SI-136 | 19 hane sınırı aşılmaz; taşma yerine reddedilir | `NonceExhaustedError`, satır yazılmaz | `::test_a_counter_at_the_ceiling_refuses_rather_than_overflowing`, `::test_the_exhausted_counter_writes_no_row` | D |
| SI-137 | Nonce imzadan **önce**, transaction içinde ayrılır | imzalanan payload ayrılmış nonce'u taşır | `test_compose_flow.py::test_the_nonce_is_reserved_before_the_signature_exists` | D |
| SI-138 | Taslak adımı imzalamaz ve nonce ayırmaz | signer çağrılmaz, sayaç 0 | `test_compose_flow.py::test_the_draft_step_signs_nothing_and_reserves_no_nonce` | D |
| SI-139 | Metin veya hedef değişirse eski onay imzalayamaz | `draft_digest_mismatch` | `test_compose_flow.py::test_changing_the_text_changes_the_digest`, `::test_changing_the_room_changes_the_digest`, `::test_a_digest_from_a_different_draft_is_refused` | D |
| SI-140 | Gönderim onayı tek kullanımlıktır ve 180 saniyede dolar | 2. kullanım ve süre sonrası ret | `test_compose_flow.py::test_a_reused_approval_is_refused`, `::test_an_expired_approval_is_refused`, `::test_the_approval_ttl_is_the_documented_three_minutes` | D |
| SI-141 | Çift tıklama ikinci kez gönderemez | tam 1 giden istek | `test_compose_flow.py::test_a_double_click_sends_exactly_once` | D |
| SI-142 | Onay oturuma bağlıdır; başka oturum harcayamaz | `approval_foreign_session` | `test_compose_flow.py::test_an_approval_from_another_session_is_refused`, `::test_a_draft_from_another_session_cannot_be_signed`, `::test_ending_a_session_forgets_its_drafts_and_approvals` | D |
| SI-143 | Manifest verdict'i değişirse onay geçersizdir (stale verdict) | `stale_verdict` | `test_compose_flow.py::test_a_new_manifest_check_invalidates_a_pending_approval`, `::test_a_verdict_that_stops_being_current_invalidates_the_approval` | D |
| SI-144 | Write gate **her adımda** yeniden koşar; UI disable'a güvenilmez | 3 adım = 3 gate çağrısı; her ön koşul tek başına bloklar | `test_compose_flow.py::test_every_step_re_runs_the_write_gate`, `::test_a_closed_gate_refuses_the_draft`, `::test_a_gate_that_closes_between_sign_and_send_stops_the_write` | D |
| SI-145 | Gönderilen gövde imzalanan baytlarla bire bir aynıdır | canonical digest eşleşmezse gönderilmez | `test_compose_flow.py::test_the_three_steps_publish_exactly_what_was_approved`, `::test_a_body_that_drifted_from_the_signed_bytes_is_not_sent` | D |
| SI-146 | Sabit imza uzunluğu ön kontrolü gerçek doğrulamanın yerine geçmez | 86 karakterlik sahte imza reddedilir | `test_compose_flow.py::test_a_signature_that_does_not_verify_is_never_sent`, `::test_a_wrong_key_produces_a_signature_the_send_path_refuses` | D |
| SI-147 | Gövde alanları ve **etkin limitler** canlı projeksiyondan doğrulanır | `{did, sig, nonce, text}`, `from` yok; sınır canlıdan | `test_compose_flow.py::test_the_limits_come_from_the_live_projection`, `::test_a_tighter_published_limit_is_honoured`, `::test_the_body_carries_no_from_field` | D |
| SI-148 | Üretim yazması **POST**'tur; gizli GET fallback yoktur | POST `/r/{room}`; GET yazma markerı yok | `test_write_client.py::test_the_request_is_a_post_to_the_message_lane`, `test_write_gate.py::test_no_code_path_can_reach_a_technocore_write_endpoint` | D |
| SI-149 | Yazma sonucu üç durumludur; `outcome_unknown` gizlenmez | 2xx→accepted, 400/403/413/422→refused, diğer hepsi→outcome_unknown | `test_write_client.py::test_a_2xx_is_accepted`, `::test_a_response_that_proves_nothing_was_written_is_refused`, `::test_everything_else_is_outcome_unknown`, `::test_a_lost_response_is_outcome_unknown_not_a_failure` | D |
| SI-150 | Yazma yolunda **hiçbir** otomatik tekrar yoktur | 429/5xx/timeout'ta tam 1 deneme; modülde attempt/backoff/sleep yok | `test_write_client.py::test_a_retryable_looking_status_is_not_retried`, `::test_a_retry_after_header_is_ignored_entirely`, `::test_the_module_contains_no_attempt_loop`, `test_compose_flow.py::test_no_outcome_is_retried_automatically` | D |
| SI-151 | Ayrılan nonce üç sonucun **hepsinde** harcanmış sayılır | `spent` + sayaç ilerlemiş | `test_nonce_reservation.py::test_every_send_outcome_leaves_the_nonce_spent`, `test_compose_flow.py::test_a_spent_nonce_is_never_offered_again` | D |
| SI-152 | Public read ve explicit write ayrı kapalı registry taşır | kaynak registry'sinde `/r/` yok; write registry'sinde belge yok, note lane yok | `test_write_gate.py::test_the_source_registry_contains_only_read_only_documents`, `::test_the_write_registry_carries_exactly_one_lane_and_no_documents` | D |
| SI-153 | Oda adı manifest'in `room_classes` konvansiyonuna göre doğrulanır; tahmin edilmez | konvansiyon yoksa hiçbir oda çözülmez; tanınmayan sınıf reddedilir | `test_write_client.py::test_the_markers_are_read_from_the_pinned_manifest`, `::test_without_a_manifest_convention_no_room_resolves`, `::test_a_room_class_this_build_does_not_understand_is_refused` | D |
| SI-154 | Lobby açıkça reddedilir (INV-05, ADR-0002 §4.1) | `room_refused` | `test_write_client.py::test_a_rendezvous_room_is_refused`, `test_write_gate.py::test_the_lobby_is_refused_as_a_write_target`, `test_compose_flow.py::test_the_lobby_is_refused_as_a_composer_target` | D |
| SI-155 | Yazma istemcisi URL, method, TLS ayarı veya retry parametresi kabul etmez | parametre yok | `test_technocore_readonly.py::test_the_write_client_takes_no_url_method_or_tls_setting`, `test_write_client.py::test_no_tls_setting_is_passed_anywhere` | D |
| SI-156 | Seed yalnız signer katmanında, tek çağrı boyunca kullanılır; sonuçlara sızmaz | signer yalnız `CanonicalPayload` alır; yanıtlarda anahtar materyali yok | `test_compose_flow.py::test_the_signer_only_ever_receives_a_canonical_payload`, `::test_nothing_in_the_composer_result_carries_key_material`, `test_compose_http.py::test_no_response_in_the_chain_carries_key_material` | D |
| SI-157 | İmza zinciri pinlenmiş resmî imzalayıcıyla **diferansiyel** olarak aynıdır | karakter karakter eşitlik; alan duyarlılığı kanıtlı | `test_message_lane_differential.py::test_the_composed_signature_equals_the_reference_signature`, `::test_the_request_body_carries_the_bytes_the_reference_signed`, `::test_the_oracle_comparison_is_sensitive_to_every_signed_field` | D |
| SI-158 | Test oturumu gerçek dış HTTP taşıyıcısını kullanamaz (ADR-0002 §4.4) | mock unutulursa gürültüyle kırılır; loopback serbest | `test_outbound_guard.py::test_the_guard_is_actually_installed`, `::test_a_read_client_with_no_mock_transport_fails_loudly`, `::test_a_write_client_with_no_mock_transport_fails_loudly`, `::test_loopback_is_still_reachable` | D |
| SI-159 | Composer rotaları oturum + CSRF arkasındadır ve GET ile yazma yapılamaz | 401/403; GET → 405 | `test_compose_http.py::test_every_composer_route_requires_a_session`, `::test_a_state_changing_composer_call_without_csrf_is_refused`, `::test_no_composer_route_accepts_a_get_write` | D |
| SI-160 | Note gönderme yolu yoktur ve yokluğu açıkça belirtilir (ADR-0002 §1) | `note` içeren route yok; `note_lane_available=false` + gerekçe | `test_conformance_boundary.py::test_no_technocore_write_endpoint_was_added`, `test_compose_http.py::test_the_capability_read_explains_the_closed_door` | D |
| SI-161 | Nonce rezervasyon tablosu yalnız public protokol değeri tutar | sütun adlarında ve **değerlerinde** sır yok | `test_database.py::test_schema_has_no_secret_columns`, `test_nonce_reservation.py::test_the_reservation_row_holds_only_public_protocol_values` | D |
| SI-162 | Kasa parolası imzalama çağrısı boyunca redaksiyon registry'sine kayıtlıdır ve çağrı bitince düşürülür | formatlanmış log çıktısında `<redacted>`; çağrı sonrası registry temiz | `test_compose_flow.py::test_the_vault_passphrase_is_registered_for_redaction_while_signing`, `::test_the_passphrase_is_dropped_from_the_registry_when_signing_ends`, `::test_the_passphrase_is_dropped_even_when_signing_fails` | D |
| SI-163 | Yazma yanıtı **akış üstünde** sınırlanır; gövde asla tümüyle tamponlanmaz | 8 MiB teklif edilir, cap kadarı okunur | `test_write_client.py::test_an_oversized_body_is_never_fully_buffered`, `::test_the_write_client_streams_rather_than_buffering` | D |
| SI-164 | İstenmeyen `Content-Encoding` taşıyan yanıt hiç açılmaz | 65 KB gzip → 64 MiB: sıfır bayt okunur, durum yine sınıflanır | `test_write_client.py::test_a_compressed_bomb_is_never_decompressed_at_all`, `::test_any_unrequested_content_encoding_leaves_the_body_unread`, `::test_an_identity_encoded_body_is_still_read` | D |
| SI-165 | İki giden istemciye de TLS doğrulaması kapalı bir taşıyıcı enjekte edilemez | yalnız `httpx.MockTransport` kabul edilir; diğeri `TypeError` | `test_write_client.py::test_a_transport_with_tls_verification_off_cannot_be_injected`, `::test_even_a_verifying_real_transport_is_refused`, `::test_the_read_client_refuses_the_same_injection` | D |
| SI-166 | Üretim wiring'i vault signer'ı ve taşıyıcısız yazma istemcisini kurar | `VaultMessageSigner`, `SignedWriteClient`, `_transport is None` | `test_compose_flow.py::test_the_application_wires_the_vault_signer_and_the_write_client`, `::test_the_production_read_client_also_carries_no_injected_transport`, `::test_the_seams_are_still_seams` | D |
| SI-167 | `send` içindeki **her** ret yolu rezervasyonu defterde kapatır | `cancelled` + `not_sent`; hiçbir satır `reserved` kalmaz | `test_compose_flow.py::test_a_body_refusal_settles_the_reservation_like_every_other_refusal`, `::test_every_refusal_path_in_send_leaves_a_settled_reservation` | D |
| SI-168 | Kilitli sayaç veritabanı açıklanabilir bir ret üretir, zırhlı 500 değil | `NonceStorageError` → 409; hiçbir nonce dağıtılmaz | `test_nonce_reservation.py::test_a_locked_counter_database_is_an_explainable_refusal_not_a_crash`, `::test_a_locked_counter_database_hands_out_no_nonce`, `::test_a_locked_database_at_commit_time_refuses_before_anything_is_sent`, `::test_the_composer_turns_a_locked_counter_into_a_refusal` | D |
| SI-169 | Bloklayan composer rotaları event loop'u tutmaz | `sign`/`send` coroutine değil; uçuştaki bir gönderim başka isteği bekletmez; eşzamanlı iki gönderim yine tek yayım | `test_compose_http.py::test_the_blocking_composer_routes_are_not_coroutines`, `::test_a_send_in_flight_does_not_stall_another_request`, `::test_a_slow_signature_does_not_stall_another_request`, `::test_two_concurrent_sends_over_http_publish_exactly_once` | D |
| SI-170 | Test oturumu soket katmanında da dışarı çıkamaz; loopback ve bu makinenin kendi adresleri serbest | `socket`, `urllib`, `httpcore` yolları da bloklanır | `test_outbound_guard.py::test_a_raw_socket_to_a_foreign_host_is_refused`, `::test_urllib_cannot_reach_a_foreign_host`, `::test_httpcore_cannot_reach_a_foreign_host`, `::test_a_loopback_socket_is_still_reachable` | D |

## 9f. Paket E değişmezleri — Evidence & Audit (uygulandı)

### SI-73 ve SI-152 neden genişletildi, gevşetilmedi

SI-73 "httpx yalnız incelenmiş istemcilerde" der; SI-152 "public read ile
explicit write ayrı kapalı registry taşır" der. Paket E ikisini de
**genişletir**: üçüncü bir kabiliyet (kanıt okuma) üçüncü bir kapalı
registry (`evidence_targets.py`) ve üçüncü bir istemci
(`evidence_client.py`) alır.

Bu bir gevşetme değildir, çünkü genişleyen şey **liste**dir, kural değil.
`OUTBOUND_CLIENT_MODULES` iki'den üçe çıkar ve bir test hâlâ *başka hiçbir
modülün* HTTP istemcisi import edemeyeceğini iddia eder; ayrıca listedeki
her adın gerçekten var olduğunu da doğrular, çünkü kaybolmuş bir ada izin
vermek sessiz bir genişlemedir. `SOURCES` altı sabit belge olarak kalır ve
`"/r/" not in source.path` iddiası aynen geçer.

### Yeni değişmezler

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-171 | Belge registry'si altı sabit belge olarak kalır; hiçbir girdisi oda veya şablon taşımaz | küme eşitliği; `"/r/"` ve `"{"` yok | `test_evidence_stream.py::test_the_document_registry_still_holds_exactly_six_fixed_documents` | E |
| SI-172 | Kanıt okuma üçüncü kapalı registry'dedir ve yalnız `/r/{room}/export` şablonunu taşır | tek şablon, sabit origin, `GET` | `test_evidence_stream.py::test_the_evidence_registry_holds_the_export_template_and_nothing_else` | E |
| SI-173 | Kanıt okuma oda adını **yazma yolunun aynı politikasından** geçirir (`DENIED_ROOMS` dâhil) | lobby/meta reddedilir; işaretçi yoksa reddedilir; geçersiz ad reddedilir | `test_evidence_stream.py::test_the_evidence_lane_refuses_every_denied_room`, `::test_the_evidence_lane_refuses_a_room_with_no_manifest_markers`, `::test_the_evidence_lane_refuses_a_name_that_is_not_a_room`, `test_evidence_record.py::test_a_capture_never_reaches_a_denied_room` | E |
| SI-174 | Kanıt istemcisine URL/method/TLS ayarı verilemez; taşıyıcı yalnız `MockTransport`; salt-okuma istemcisinin imzası değişmedi | parametre yok; `HTTPTransport` → `TypeError`; `fetch(self, source)` aynı | `test_evidence_stream.py::test_the_evidence_client_takes_no_url_method_or_tls_setting`, `::test_a_transport_with_tls_verification_off_cannot_be_injected`, `::test_the_read_only_client_signature_is_unchanged` | E |
| SI-175 | Export akışı **hiçbir zaman tamponlanmaz**; tavan 12 MiB ve tutulan bayt gövdeden bağımsızdır | 1 MB gövde, tutulan < gövde/10; tavan aşılırsa `stream_truncated` | `test_evidence_stream.py::test_the_scanner_never_holds_the_stream_it_scanned`, `::test_the_cap_stops_the_scan_and_says_so`, `::test_an_overlong_line_is_dropped_rather_than_buffered`, `test_evidence_record.py::test_a_truncated_scan_is_not_an_absent_record` | E |
| SI-176 | Kanıt olarak **ham baytlar** saklanır; yeniden serialize edilmiş hiçbir bayt kanıt değildir | satır baytı = akıştaki bayt, offset ile doğrulanır | `test_evidence_stream.py::test_our_own_line_comes_back_as_the_bytes_that_arrived`, `::test_a_record_is_json_parseable_but_stored_as_bytes` | E |
| SI-177 | Nonce big-integer-safe karşılaştırılır; float'a yuvarlanmış bir nonce eşleşmeye dönüşmez | 2^53+1 ile 2^53 ayrılır; JSON float eşleşmez; yinelenen anahtar okunamaz | `test_evidence_stream.py::test_a_nineteen_digit_nonce_is_compared_without_rounding`, `::test_a_nonce_published_as_a_float_is_not_rounded_into_a_match`, `::test_a_duplicate_key_line_cannot_claim_to_be_ours` | E |
| SI-178 | Yakalama altı ayrı durumla biter; yalnız biri sunucu gözlemidir ve hiçbiri yazma tekrarına izin vermez | 6 durum, 1 gözlem, `may_retry_write` her zaman `False` | `test_evidence_record.py::test_only_one_of_the_six_states_is_a_server_observation` ve altı durum testi | E |
| SI-179 | `line_not_found` bir `outcome_unknown` gönderimini `not_sent`'e çevirmez | gönderim sonucu değişmez; metin "kanıtlamaz" der | `test_evidence_record.py::test_line_not_found_proves_nothing_and_never_becomes_not_sent`, `::test_an_unknown_outcome_is_archived_and_still_not_called_sent` | E |
| SI-180 | Generation farkı, bulunmuş bir satıra **baskındır**; kayıt karşılaştırılamaz sayılır | `generation_changed`, gözlem değil | `test_evidence_record.py::test_a_changed_generation_makes_the_record_incomparable` | E |
| SI-181 | Kanıt satırı ile nonce defteri arasındaki FK **CASCADE etmez**; kanıt bir yan etkiyle silinemez | `ondelete` yok; silme `IntegrityError` | `test_evidence_record.py::test_the_reservation_foreign_key_does_not_cascade`, `::test_deleting_a_reservation_cannot_silently_remove_its_evidence` | E |
| SI-182 | Kanıt ve audit zinciri **asla budanmaz** | 60 kayıt, 60 kayıt; kaynakta `_prune`/`RETAINED` yok | `test_evidence_record.py::test_evidence_is_never_pruned`, `::test_the_evidence_service_carries_no_retention_policy`, `test_audit_chain.py::test_the_chain_carries_no_retention_policy` | E |
| SI-183 | Kanıt satırı ve audit satırı **tek transaction'da** yazılır; biri olmadan diğeri kalmaz | rollback sonrası ne satır ne link | `test_evidence_record.py::test_a_failed_archive_writes_neither_the_row_nor_the_audit_link` | E |
| SI-184 | Kanıt/audit tablolarında secret-şekilli sütun adı yoktur | `seed`/`private`/`secret`/`mnemonic`/`passphrase`/`password`/`key` yok | `test_evidence_record.py::test_no_evidence_or_audit_column_is_secret_shaped`, `test_database.py::test_schema_has_no_secret_columns` | E |
| SI-185 | Secret taraması **allow-list'i önce** uygular ve isabet hâlinde **yazmayı reddeder**, redakte etmez. Red kuralları "en az" uzunluktur: dolgu saklamaz | imzalı gövde geçer; ≥64-hex ve ≥43-b64url reddeder; ret değeri yankılamaz | `test_evidence_record.py::test_the_allow_list_runs_before_the_deny_rules`, `::test_a_sixty_four_hex_run_refuses_the_write`, `::test_a_seed_length_base64url_run_refuses_the_write`, `::test_a_registered_value_refuses_the_write`, `::test_a_secret_canary_refuses_the_evidence_write_rather_than_redacting_it` | E |
| SI-186 | HMAC zinciri ortadan silme, alan değiştirme ve yeniden sıralamayı tespit eder | üçü de `broken_link` + ilk bozuk satır | `test_audit_chain.py::test_a_removed_middle_link_is_detected`, `::test_an_altered_field_is_detected`, `::test_every_stored_field_is_covered_by_the_mac`, `::test_reordering_two_links_is_detected` | E |
| SI-187 | Zincir materyali ayrı DPAPI zarfındadır, hiçbir tabloya girmez, üzerine yazılmaz ve sürümlüdür | dosya + fingerprint; DB'de materyal yok; ikinci `create` reddedilir; yanlış `kind` reddedilir | `test_audit_chain.py::test_the_mac_material_lives_in_its_own_file_and_not_in_any_table`, `::test_the_material_is_not_stored_in_the_clear`, `::test_the_material_is_never_overwritten`, `::test_the_envelope_is_versioned_and_kind_checked` | E |
| SI-188 | Zincir başı ayrı zarftadır; sonun kesilmesi **yalnız** onunla tespit edilir ve bu bir **garanti olarak sunulmaz** | kesme → `head_mismatch`; baş da yeniden yazılırsa `intact` (test bu saldırıyı uygular) | `test_audit_chain.py::test_a_cut_off_tail_is_detected_only_because_the_head_is_separate`, `::test_a_truncation_is_invisible_when_the_head_goes_with_it`, `::test_a_missing_head_is_reported_as_a_limit_rather_than_as_tampering` | E |
| SI-189 | Yarıda kalan bir yazma "kurcalama" diye raporlanmaz; append ile baş aynı transaction sınırındadır | `head_mismatch` + "yarıda kalan" cümlesi; rollback sonrası link yok | `test_audit_chain.py::test_a_head_that_is_behind_is_named_as_an_interrupted_write`, `::test_a_replaced_tail_link_is_distinguished_from_a_count_change`, `::test_an_append_and_its_head_share_one_transaction_boundary` | E |
| SI-190 | Materyal açılamıyorsa sonuç `unavailable`'dır, asla "geçti" değil | `ChainVerdict.UNAVAILABLE`, `is_intact` yanlış | `test_audit_chain.py::test_a_missing_envelope_is_unavailable_and_never_a_pass`, `::test_a_chain_with_a_different_material_does_not_verify` | E |
| SI-191 | Yasak ifadeler **ürünün kendi cümlelerinde** geçemez: audit satırı, dışa aktarım metinleri, seviye adları, yakalama cümleleri. İhlal **yazmayı/dosyayı reddeder** | dört charter ifadesi + iki truncation ifadesi; katlanmış eşleşme; mutasyon kontrolü: koruma no-op yapılınca dört test kırmızıya döner | `test_evidence_language.py::test_a_forbidden_phrase_in_our_own_export_wording_refuses_the_file`, `::test_an_audit_detail_carrying_a_forbidden_claim_refuses_the_link`, `::test_assert_no_forbidden_claim_names_what_it_found`, `::test_no_string_literal_in_the_evidence_package_carries_a_forbidden_phrase`, `test_audit_chain.py::test_no_report_this_module_can_produce_carries_a_forbidden_phrase`, `::test_the_forbidden_list_still_carries_the_charter_four`, `test_evidence_export.py::test_no_export_can_carry_a_forbidden_phrase` | E |
| SI-199 | **İçe alınan metin bir iddia değil, veridir**: uzak hata alıntısı ürünün cümlesine katılmadan önce nötrlenir; kullanıcının kendi mesajı olduğu gibi arşivlenir. Hiçbiri dışa aktarımı, yazmayı veya API yanıtını **reddedemez** | 429 + yasak ifade taşıyan gövde → `fetch_failed`, ifade nötrlenmiş, iki biçim de iki kez dışa aktarılır, yeniden yakalama çalışır; ifade taşıyan kullanıcı mesajı arşivlenir ve dışa aktarılır | `test_evidence_language.py::test_a_hostile_remote_error_body_cannot_lock_the_archive`, `::test_a_users_own_message_is_archived_verbatim_and_exports_fine`, `::test_every_registered_phrase_is_neutralised_in_both_spellings`, `::test_a_neutralised_excerpt_never_removes_more_than_the_phrase`, `test_evidence_http.py::test_no_evidence_response_body_carries_a_forbidden_phrase` | E |
| SI-200 | Ürünün kendi dil hatası bile **temiz bir ret**tir, 500 değil: `ForbiddenClaimError` `EvidenceError`'a sarılır | servis `EvidenceError` yükseltir; route sözleşmesi 400 | `test_evidence_language.py::test_our_own_over_claim_is_a_refusal_and_not_a_five_hundred`, `test_evidence_http.py::test_an_export_without_the_acknowledgement_is_refused` | E |
| SI-201 | Secret tarama allow-list'i **şekil değil, çağıranın bildirdiği tam değerlerdir**; bildirilen değer ayrıca public şekli sağlamak zorundadır | imzalı gövde bildirimle geçer, bildirimsiz reddedilir; seed'i imza diye bildirmek işe yaramaz | `test_evidence_record.py::test_the_allow_list_runs_before_the_deny_rules` | E |
| SI-202 | Seed, allow-list'in etrafından **dolandırılamaz**: `did:key:z` kuyruğu, imza uzunluğuna dolgu, 64'ten uzun hex koşu | üç prob da `recorded=False`; canary veritabanında yok | `test_evidence_record.py::test_a_seed_cannot_be_smuggled_past_the_allow_list`, `::test_the_did_allow_rule_admits_only_the_published_multibase_length` | E |
| SI-203 | Dışa aktarım **koşulsuz** bayt-bayt deterministiktir: `exported_at` gövdede değil, header'dadır | saat ilerlerken bile iki dosya aynı; `X-Station-Exported-At` zamanı taşır | `test_evidence_export.py::test_two_exports_taken_at_different_times_are_byte_identical`, `::test_the_service_returns_the_export_time_beside_the_bytes`, `test_evidence_http.py::test_the_export_is_byte_identical_on_a_second_request` | E |
| SI-204 | `generation_changed` **yapışkandır** ve baseline dondurulur; yakalanan satır hangi generation'da okunduğuyla birlikte saklanır | üçüncü yakalama hâlâ `generation_changed`; header kaybolsa da öyle; `capture_generation` satırla eşleşir | `test_evidence_record.py::test_a_changed_generation_is_sticky_and_the_baseline_is_frozen`, `::test_a_changed_generation_stays_changed_when_the_header_disappears`, `::test_a_capture_records_the_generation_its_line_was_read_under`, `::test_a_record_that_was_never_captured_carries_no_generation_at_all` | E |
| SI-205 | `Content-Disposition` **uzun adlarda da** uzantıyı korur ve Windows aygıt adı üretmez | 300 karakterlik ad → `.json` duruyor; `CON`/`NUL`/`COM1` yeniden adlandırılır | `test_evidence_export.py::test_the_header_keeps_the_extension_on_a_long_name`, `::test_the_header_is_idempotent_over_an_already_safe_name`, `::test_a_windows_device_name_is_not_handed_to_the_browser`, `::test_a_dot_that_is_not_an_extension_stays_part_of_the_stem` | E |
| SI-206 | Zincir materyali açılamasa bile **satır sayısı gerçektir**; `unavailable` "boş zincir" gibi okunamaz | `link_count == chain.count()`, sıfır değil | `test_audit_chain.py::test_a_missing_envelope_is_unavailable_and_never_a_pass` | E |
| SI-207 | Generation başlığı yalnız **ASCII** rakam kabul eder | `٧`, `７`, `߇` düşürülür; `7` kalır | `test_evidence_stream.py::test_a_non_ascii_digit_generation_is_dropped`, `::test_an_ascii_digit_generation_still_arrives` | E |
| SI-208 | Tarama tavana dayandığında `stream_sha256` **taranan önekin** hash'idir ve belge bunu söyler; satır sayımı sonlandırıcısız son satırı da kapsar; CRLF'te sondaki `\r` ham baytlarda **kalır** | prefix hash'i eşleşir; 201 satır 201 sayılır; `\r` saklanan baytta | `test_evidence_stream.py::test_the_hash_at_the_cap_covers_the_scanned_prefix_and_says_so`, `::test_the_last_line_is_counted_after_the_window_is_complete`, `::test_a_crlf_stream_keeps_the_carriage_return_in_the_stored_bytes` | E |
| SI-209 | İki dışa aktarım biçimi de imzanın kapsadığı **kanonik metni** taşır; ham baytlar yalnız JSON'dadır ve Markdown bunu **dosyanın içinde** söyler | her iki biçimde canonical; Markdown'da kapsam notu; `b64url` yalnız JSON'da | `test_evidence_export.py::test_both_formats_carry_the_canonical_string_a_signature_covers` | E |
| SI-192 | Dışa aktarım **açık onay** olmadan imkânsızdır (model, servis ve route) | `acknowledged` varsayılansız → 422; `False` → 400; sahte consent → ret | `test_evidence_export.py::test_an_export_without_consent_is_unrepresentable_and_refused`, `::test_the_service_refuses_an_export_without_consent`, `::test_the_export_request_model_has_no_default_acknowledgement`, `test_evidence_http.py::test_an_export_without_the_acknowledgement_is_refused` | E |
| SI-193 | Dışa aktarım deterministiktir ve Seviye 4'ü `null` olarak yazar | aynı girdi → aynı bayt; dört seviye adlandırılır | `test_evidence_export.py::test_the_same_records_produce_the_same_bytes`, `::test_the_json_export_is_canonical_json`, `::test_every_level_is_named_and_level_four_is_null`, `test_evidence_http.py::test_the_export_is_byte_identical_on_a_second_request` | E |
| SI-194 | Markdown/HTML/link enjeksiyonu dışa aktarımda etkisizdir; **hiçbir karakter silinmez ve hiçbir değer kırpılmaz** — görünmez karakterler **görünür bir boşluğa** dönüşür, metakarakterler escape'lenir | bir karakter girer, bir karakter çıkar; 5000 karakter kırpılmaz; kaçışlar çıkarıldığında ne `<img` ne `](javascript:` kalır | `test_evidence_export.py::test_the_markdown_escaper_neutralises_every_markup_weapon`, `::test_dangerous_imported_text_is_inert_in_the_markdown_export`, `::test_a_bidi_override_cannot_reach_the_export`, `test_evidence_language.py::test_the_markdown_escaper_substitutes_and_never_deletes` | E |
| SI-195 | `Content-Disposition` adı allow-list'ten yeniden kurulur; recovery indirmesi de aynı yardımcıyı kullanır | tırnak/CRLF/`;`/`../`/RTL/non-ASCII yok; tam iki tırnak | `test_evidence_export.py::test_the_filename_sanitiser_removes_every_header_weapon`, `::test_a_name_that_sanitises_to_nothing_falls_back`, `::test_the_stem_is_bounded_so_the_suffix_always_survives`, `::test_the_recovery_download_now_goes_through_the_same_helper`, `test_evidence_http.py::test_a_consented_export_is_a_download_with_a_safe_name` | E |
| SI-196 | Kanıt yüzeyi hiçbir yeniden gönderim yolu eklemez ve oturum + CSRF arkasındadır | dört route; `send`/`resend`/`retry`/`note` yok; 401/403/405 | `test_evidence_http.py::test_the_evidence_surface_adds_no_resend_route`, `::test_every_evidence_route_requires_a_session`, `::test_a_state_changing_evidence_call_without_csrf_is_refused`, `::test_no_evidence_route_accepts_a_get_write` | E |
| SI-197 | Arşivlenen request baytları **süreçten çıkan** baytlardır | `request_body` == mock taşıyıcının gördüğü içerik; SHA-256 eşleşir | `test_evidence_record.py::test_a_send_archives_the_bytes_that_actually_left_the_process` | E |
| SI-198 | Kanıt katmanı yoksa gönderim yine yapılır ve arşivlenmediği **söylenir** | `evidence_recorded=False` + gerekçe; gönderim `accepted` | `test_evidence_record.py::test_a_send_without_an_evidence_layer_still_sends` | E |


## 9g. Paket F değişmezleri — proje/görev modülü temeli (uygulandı)

Kapsam kararları [`decisions/0004-paket-f-kapsam-kararlari-2026-09-04.md`](decisions/0004-paket-f-kapsam-kararlari-2026-09-04.md);
uygulama ayrıntısı [`task-modules.md`](task-modules.md).

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-210 | Modül registry'si **derleme zamanında sabittir**; diskten plugin/import yükleme yolu yoktur ve yasak **dört yazımda birden** aranır | `modules/` ve `tasks/` ağaçlarında yasak import, yasak **bare ad** (`runner = __import__`), yasak **attribute** (`builtins.__import__`, `mod.exec`) ve yasak **ad alanı** (`sys.modules`, `getattr(builtins, ...)`) yok; `compile`'ın yalnız bare adı yasak (`re.compile` serbest); `getattr` adları yalnız `EvidenceField` enum'undan gelir | `test_module_registry.py::test_no_module_is_ever_loaded_from_disk`, `::test_the_only_computed_attribute_names_come_from_the_field_enum`, `::test_the_registry_is_a_closed_set_with_unique_identifiers`, `::test_an_unregistered_module_cannot_be_looked_up` | F |
| SI-211 | Kayıt var olan koda **işaret eder**; Proje 0 taşınmaz ve registry paketi sorumluluk üstlenmez | her `owners` girdisi bir dosyaya çözülür; `modules/` dört dosyadır ve `compose`/`evidence`/`vault` import etmez; `planned` kayıt kod sahiplenmez | `test_module_registry.py::test_project_zero_is_represented_and_its_code_was_not_moved`, `::test_no_module_record_moved_code_into_the_registry_package`, `::test_planned_modules_name_the_package_that_opens_them` | F |
| SI-212 | Uygulanmamış gereksinim `not_implemented` raporlar, asla `passed`; **politika reddi** ayrı işaretlenir | dokuz çıktı künye sırasında; üçü `not_implemented`; `lobby_greeting_sent` `policy_refused` ve `lobby` `DENIED_ROOMS` içinde; `complete` daima `False` | `test_module_registry.py::test_project_zero_carries_the_nine_charter_outputs_in_order`, `::test_the_lobby_greeting_is_refused_by_policy_not_merely_unbuilt`, `::test_the_unbuilt_requirements_are_exactly_the_three_that_are_unbuilt`, `::test_a_module_with_an_unbuilt_requirement_is_never_complete` | F |
| SI-213 | Görev katmanı **ve Paket H2'nin `agent/` paketi** dördüncü giden yüzey, ikinci kasa/signer veya ikinci gate açmaz | `modules/`+`tasks/` içinde HTTP istemcisi, `socket`, `urllib`, `station_api.vault` ve `station_api.compose` import'u yok; `tasks.gate.CheckState` **write_gate'inkiyle aynı nesnedir** ve `gate.py` paralel enum tanımlamaz. **H2 ile genişletildi (SI-285):** aynı yasak `station_api/agent` ve `routes/agent.py` üzerinde de uygulanır ve `station_api.vault`'tan yalnız **iki** modül (`windows_acl`, `errors`) birebir allow-list ile serbesttir | `test_module_registry.py::test_the_task_layer_has_no_outbound_surface`, `::test_the_task_layer_reaches_no_vault_and_no_signer`, `::test_the_task_gate_reuses_the_write_gates_check_state`, `test_agent_boundary.py::test_the_agent_package_has_no_outbound_surface`, `::test_the_agent_package_reaches_no_signer_vault_or_credential`, `::test_the_only_vault_imports_are_the_two_that_carry_no_secret`, `::test_the_agent_package_declares_no_second_gate`. **H3 ile yine genişletildi (SI-310):** aynı yasak `station_api/proof` ve `routes/proof.py` üzerinde de uygulanır ve orada **hiçbir vault muafiyeti yoktur** — paket dosya sistemine hiç dokunmadığı için ACL yardımcısına ihtiyacı yok; ayrıca `test_proof_boundary.py::test_the_proof_package_has_no_outbound_surface`, `::test_the_proof_package_reaches_no_signer_vault_or_credential`, `::test_the_proof_package_declares_no_second_gate` | F, H2, H3 |
| SI-214 | Görev tablolarında secret-şekilli sütun adı yoktur (**`key` dahil**); migration `0007` yalnız ekler | üç tabloda `seed`/`private`/`secret`/`mnemonic`/`passphrase`/`password`/`key` yok; on mevcut tablo yerinde | `test_module_registry.py::test_the_task_tables_have_no_secret_shaped_columns`, `::test_migration_0007_changed_no_existing_table`, `test_database.py::test_schema_has_no_secret_columns`, `::test_migration_chain_is_deterministic` | F |
| SI-215 | Dokuz durum tanımlıdır ve geçiş tablosu **tek yerde açıktır**; doğrulama saf bir fonksiyondur | dokuz ad; `ALLOWED_TRANSITIONS` her durumu kapsar; her hedef bilinen bir durum; her duruma bir aksansız Türkçe cümle | `test_task_states.py::test_all_nine_states_are_defined`, `::test_every_state_carries_one_sentence`, `::test_the_transition_table_is_explicit_and_total`, `::test_every_permitted_edge_between_producible_states_is_permitted` | F |
| SI-216 | Üretilemeyen durum kümesi **ölçülmüş bir gerçektir**, temenni değil: bir durum ancak **üreticisi yazıldığında** açılır ve açılış kayda geçer. H1 `suggested`'ı, **H2 `running` ve `paused`'ı** açtı; küme artık **boştur** | üretici taraması `TaskService`'in **her public metodunu** introspection ile sürer ve durumları doğrudan tablodan okur; ulaşılan küme testte **elle yazılı** `EXPECTED_PRODUCIBLE`'a eşittir — `PRODUCIBLE_STATES` sabiti ayrı satırda denetlenir, böylece sabiti düzenlemek oracle'ı büyütmez; boşalan küme yüzünden **vacuous** hâle gelen iki test sessizce bırakılmadı: reddetme mekanizması artık bir durum test süresince **kapatılarak sürülür** (kapatmadan önce aynı kenarın izinli olduğu da denetlenir) ve boş `parametrize` kaldırıldı; tablodaki kenarlar durur ve artık **izinli** oldukları da denetlenir | `test_task_states.py::test_no_code_path_can_produce_an_unproducible_state`, `::test_the_producer_walk_actually_drives_every_public_method`, `::test_every_defined_state_is_now_producible_and_nothing_is_left_closed`, `::test_the_refusal_mechanism_still_closes_a_state_when_one_is_closed`, `::test_the_service_refuses_a_state_the_build_has_closed`, `::test_the_service_still_refuses_an_edge_that_is_not_in_the_table`, `::test_the_executor_edges_the_table_kept_are_the_ones_h2_opened` | F, H1, H2 |
| SI-217 | Son durumdan çıkış yoktur ve başlangıç durumu `suggested` değildir | `failed`/`published` hiçbir hedefe gitmez; yayımlanmış görev geri alınamaz; `INITIAL_STATE == awaiting_approval` | `test_task_states.py::test_terminal_states_have_no_exit`, `::test_a_published_task_cannot_be_walked_back`, `::test_the_initial_state_is_not_suggested`, `::test_a_terminal_state_is_named_as_finished_rather_than_as_a_bad_edge` | F |
| SI-218 | Kabul edilen her geçiş yalnız-ekleme deftere yazılır; **reddedilen geçiş satır yazmaz** | dört adımlık yol dört satır üretir; reddedilen geçiş sonrası satır sayısı değişmez | `test_task_states.py::test_every_accepted_transition_is_appended_to_the_ledger`, `::test_a_refused_transition_leaves_no_ledger_row` | F |
| SI-219 | Dört alan **dört ayrı sütun grubudur**; tek bir boolean'a toplanmaz | her alan için `_ref_id`/`_verified`/`_version_id`/`_detail`/`_recorded_at`; `done`/`success`/`completed`/`passed`/`score` sütunu yok | `test_task_evidence.py::test_the_four_fields_are_four_column_groups_and_not_one_flag`, `::test_there_are_exactly_four_fields_and_three_decide_publication` | F |
| SI-220 | `public_share` Paket F'te **temsil edilemezdi**; H3 onu **yalnız arşivlenmiş bir gönderime bağlanabilir** yaptı ve alan yayımı hâlâ **engellemez** (ayrıntı SI-300) | Paket F'te: yapıcı her `public_share` referansını reddeder. H3'ten sonra: yapıcı **şekli** (32 küçük harf hex) reddeder, servis **satırın yokluğunu** reddeder, `verified` gönderimin kendi sonucundan gelir; kanıt kaydedilmemişken alan `blocked`'tır ve üç yayım alanı doğrulanmışken `ready_to_publish` yine `True` | `test_task_evidence.py::test_a_public_share_reference_needs_an_evidence_record_identity`, `::test_the_service_refuses_a_public_share_pointer_with_no_row_behind_it`, `::test_public_share_is_blocked_until_an_archived_send_is_recorded`, `::test_public_share_does_not_block_a_finished_task` | F, H3 |
| SI-221 | **Bir kaydın varlığı tek başına başarı değildir**; `verified` varsayılansızdır | `verified=False` üç alan → üçü de `blocked` ve cümle bunu söyler; modül kapısı da aynı ayrımı yapar | `test_task_evidence.py::test_a_record_that_merely_exists_is_not_success`, `::test_a_module_check_passes_only_on_verified_evidence` | F |
| SI-222 | `ready_to_publish` **kanıttan türer**; elle istenemez ve tek eksik alan yeter | kanıtsız istek `evidence_incomplete`; iki alan doğrulanmış, üçüncü eksikken hâlâ ret; uygulanmamış gereksinimler `passed` sayılmaz | `test_task_evidence.py::test_ready_to_publish_cannot_be_asked_for_without_the_evidence`, `::test_one_missing_field_is_enough_to_refuse`, `::test_unimplemented_requirements_are_never_counted_as_passed` | F |
| SI-223 | Kaynak kimliği **registry enum'undan** gelir; içerik değişince kimlik değişir ve **eski kanıt eşleşmez** — bu karşılaştırmayı yapan **iki** yol (`tasks/gate.py` ve `modules/completion.py`) ayrı ayrı testlidir | serbest string `TaskSourceError`; bozuk digest reddedilir; aynı kaynak + farklı içerik → farklı kimlik; eski kanıt yeni sürüme karşı kapıda `blocked`; **doğrulanmış ama başka sürüme bağlı** referans modül tamamlanmasında da `blocked`; kayıt görevin kendi sürümüne bağlanır; alan ayrımı ve uzunluk öneki korunur | `test_task_evidence.py::test_a_source_identifier_must_come_from_the_registry`, `::test_a_malformed_content_digest_is_refused`, `::test_changed_content_produces_a_different_identity`, `::test_evidence_for_the_old_content_does_not_match_the_new_content`, `::test_a_module_check_refuses_evidence_bound_to_another_content_version`, `::test_the_same_reference_passes_once_its_version_matches`, `::test_recorded_evidence_is_bound_to_the_tasks_own_content_version`, `::test_the_identity_is_domain_separated_and_length_prefixed`, `::test_the_same_content_from_a_different_source_is_a_different_identity` | F |
| SI-224 | Başlangıç uzlaştırması **okur**: sıfır giden istek, sıfır satır değişikliği, sıfır otomatik devam | tarama sırasında ve `create_app` sırasında giden deneme sayısı **0**; defter bayt bayt aynı ve satır hâlâ `in_flight`; `resumed_any` `False`; modül hiçbir yazma yolunu çağıramaz; veritabanı yoksa boş rapor | `test_task_evidence.py::test_the_startup_scan_makes_zero_outbound_requests`, `::test_building_the_application_makes_zero_outbound_requests`, `::test_the_startup_scan_changes_no_row`, `::test_the_scan_resumes_nothing_and_says_so`, `::test_the_reconciliation_module_can_reach_no_write_path`, `::test_the_startup_scan_lists_unfinished_sends`, `::test_a_settled_send_is_not_reported_as_unfinished`, `::test_a_scan_with_no_database_is_an_empty_report_rather_than_a_crash` | F |
| SI-225 | **Görev katmanında bütçe alanı yoktur** — ve H2 bir tavan yazdıktan sonra da yoktur; erteleme yerine **tavanın nerede olduğu** belgede ve telde görünür | görev/registry paketlerinde bütçe biçimli sütun veya tanımlayıcı yok (tek istisna açıklama cümlesi); `budget_available` `Literal[False]`; `budget_detail` artık tavanın **çalışmaya** ait olduğunu ve token/para biriminin sayılmadığını söyler | `test_task_evidence.py::test_the_task_layer_opens_no_budget_field`, `::test_the_task_layer_states_where_the_ceiling_lives_rather_than_implying_none`, `::test_the_budget_scan_reaches_the_proof_package_and_would_fire_there` | F, H2, H3 |
| SI-226 | Bir görevin durumunu yazan **tek** kod yolu `TaskService.transition`'dır — ve tarama H2'nin `agent/` ve H3'ün `proof/` ağaçlarını da kapsar | `modules/`+`tasks/`**+`agent/`** sözdizim ağacında `.state`'e atama (düz, annotate, artırmalı ve sabit adlı `setattr`) yalnız `service.py:transition` içinde; sentetik ikinci yazıcı taramada görünür. **Üçüncü ad taşıyıcıdır:** `running`/`paused`'ı üreten kod o ağaçtadır ve tarama genişletilmeseydi bu değişmez tam da onu delen commit'te sessizce delinirdi. Agent paketi kendi defter sütununu bilerek `state` değil `phase` diye adlandırır. **H3 dördüncü adı ekledi:** kabulden sonra görevi `ready_to_publish`'e taşıyan bir metot tam olarak birinin `proof/` içine yazacağı metottur ve ADR-0009 §8 onu yasaklar; tarama `proof/` içine ekilen böyle bir yazıcıyla sürülmüştür | `test_task_states.py::test_only_the_transition_method_writes_a_task_state`, `::test_the_state_write_scan_would_see_a_second_writer`, `::test_the_state_write_scan_reaches_the_proof_package` | F, H2, H3 |
| SI-227 | Kanıt işaretçisi de **süpürülür ve sınırlanır**; hiçbir şeye inen işaretçi reddedilir | bidi override + NUL + 406 karakter → saklanan değerde yok, uzunluk ≤ 64 ve yanıt modeli aynı değeri taşır; yalnız görünmez karakterden oluşan işaretçi `evidence_field_refused` | `test_task_evidence.py::test_an_evidence_pointer_is_swept_and_bounded_like_every_other_string`, `::test_a_pointer_that_sweeps_down_to_nothing_is_refused` | F |
| SI-228 | **Boş kontrol kümesi yayıma hazır değildir**; kapı üç yayım alanının *varlığını* ister | `TaskGateStatus(checks=())` → `ready_to_publish=False` ve üç alan da `blocking_fields`'ta; bir alanı düşürülmüş küme de `False` | `test_task_evidence.py::test_an_empty_gate_status_is_not_ready_to_publish`, `::test_a_gate_status_missing_one_field_entirely_still_blocks` | F |
| SI-229 | `resumed_any` **kurucu argümanı olmayan** bir property'dir ve projeksiyon değeri rapordan okur | `ReconciliationReport(..., resumed_any=True)` → `TypeError`; dataclass alanları arasında yok; `to_reconciliation` `resumed_any=report.resumed_any` yazar | `test_task_evidence.py::test_resumed_any_cannot_be_constructed_as_true`, `::test_the_projection_reads_resumed_any_rather_than_defaulting_it`, `::test_the_scan_resumes_nothing_and_says_so` | F |
| SI-230 | Dinamik yükleme taraması **dolaylı yazımları da** yakalar ve masum yazımları rahat bırakır | on sentetik atlatma (`builtins.__import__`, `getattr(builtins, 'ex'+'ec')`, `sys.modules` yazma/okuma, `__builtins__`, bare `__import__`, aliaslı import, `from` import, attribute `eval`, düz `exec`) yakalanır; `re.compile` ve hesaplanmış `getattr` sütun adı temiz | `test_module_registry.py::test_the_dynamic_loading_scan_catches_the_indirect_spellings`, `::test_the_dynamic_loading_scan_leaves_the_innocent_spellings_alone` | F |
| SI-231 | Kayıtsız modül kimliği **gösterilebilir bir rettir**, çıplak `KeyError` değil | `open_task` bilinmeyen modülde `module_unknown`, bilinmeyen kaynakta `source_invalid` verir; mesajda repr tırnağı ve girdi yok; `ModuleRegistryError` yine bir `KeyError`'dur | `test_task_evidence.py::test_an_unregistered_module_is_a_shown_refusal_and_not_a_bare_key_error`, `::test_the_registry_still_raises_a_key_error_for_an_unknown_identifier`, `test_module_registry.py::test_an_unregistered_module_cannot_be_looked_up` | F |
| SI-232 | Aşama numarası **bütün giriş noktalarında aynıdır** | `launcher.py`, `cli/__main__.py` ve `routes/api.py`'nin taşıdığı sayı tek bir değerdir ve test edilen sürümle eşleşir | `test_module_registry.py::test_every_entry_point_names_the_same_release_stage` | F |

## 9h. Paket G değişmezleri — OpenCode Go bağlantısı (uygulandı)

Kapsam kararları [`decisions/0005-paket-g-kapsam-kararlari-2026-09-04.md`](decisions/0005-paket-g-kapsam-kararlari-2026-09-04.md);
uygulama ayrıntısı [`opencode-connection.md`](opencode-connection.md).

### SI-71, SI-73 ve SI-48 neden **daraltıldı**, gevşetilmedi

Üçü de aynı biçimde değişti: kural aynı kaldı, **kapsamı adıyla söylendi**.

**SI-71** "giden istekte cookie/auth/DID/CSRF yok" diyordu. Bu, üç Technocore
istemcisi için doğrudur ve doğru kalır. OpenCode istemcisi için doğru
*olamaz* — taşıdığı tek şey bir sağlayıcı anahtarıdır ve onu göndermek
özelliğin kendisidir. Kuralı OpenCode'u kapsayacak şekilde gevşetmek yerine,
SI-71 Technocore istemcilerine ait kaldı ve OpenCode için **daha dar** bir
değişmez yazıldı (SI-234): *giden istekte yalnız sağlayıcı anahtarı; DID,
CSRF, oturum çerezi ve kullanıcı dosya yolu asla*.

**SI-73** "yalnız incelenmiş modüller" diyor ve genişleyen şey **liste**,
kural değil. Fakat liste artık düz bir küme olamazdı. Bu paragraf bir süre
gerekçeyi **ters** anlattı; doğrusu şudur: eski yazım
`path.name not in MODULES or path.parent.name != "technocore"`'du ve
`opencode/client.py` httpx import etseydi **reddedilirdi** — adı listedeydi
ama dizini `technocore/` değildi.

İlk düzeltme listeyi **çıplak üst dizin adına** göre anahtarladı ve bir
inceleme onu kırdı: `station_api/plugins/opencode/client.py` konumundaki
sahte bir istemci, üst dizininin adı `opencode` olduğu için tüm testleri
geçti. Liste bugün **kaynak köküne göreli tam yolla** anahtarlanır
(`station_api/opencode/client.py`), incelemecinin probu regresyon testi
olarak durur ve `technocore` adının ödünç alınması da aynı şekilde
reddedilir.

**SI-48** "secret input veya private key alanı yoktur" diyordu. ADR-0001 §6
provider anahtarı girişini zaten yetkilendirmişti; değişmezin koruduğu şey
"hiçbir alan yok" değil, *seed/private key/recovery materyalinin hiçbir
zaman girilmemesi ve gösterilmemesi*ydi. Yeni hâli tam olarak bunu söyler ve
üstüne bir şey ekler: anahtarı **geri gösteren** hiçbir alan da yoktur.

### Yeni değişmezler

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-233 | Dördüncü giden yüzey **kapalı bir adres registry'sindedir**; istemci URL, method, header, TLS ayarı veya retry parametresi kabul etmez ve taşıyıcı yalnız `MockTransport`'tur | dört sabit adres; `verify` paket genelinde hiç yazılmaz; `HTTPTransport` → `TypeError`; şema/host/port/user-info/fragment/traversal **ve query** reddedilir | `test_opencode_client.py::test_every_way_around_the_allow_list_is_refused`, `::test_the_client_takes_no_url_method_or_tls_setting`, `::test_tls_verification_is_never_disabled`, `::test_a_transport_with_tls_verification_off_cannot_be_injected`, `::test_a_query_string_is_refused_because_a_key_could_ride_in_one` | G |
| SI-234 | OpenCode giden isteğinde **yalnız sağlayıcı anahtarı** bulunur; DID, CSRF, oturum çerezi, request id ve dosya yolu asla. Katalog isteği anahtar bile taşımaz | header kümesi temiz; anahtarı taşıyan tek header `authorization`; User-Agent kendimizindir ve başka istemciyi taklit etmez | `test_opencode_client.py::test_the_outbound_request_carries_no_identity_cookie_or_csrf_value`, `::test_the_catalog_request_carries_no_credential_at_all`, `::test_the_user_agent_is_ours_and_impersonates_nobody`, `test_opencode_leakage.py::test_the_outbound_request_carries_the_credential_in_one_header_and_nowhere_else` | G |
| SI-235 | Kimlik doğrulama başlığı **tek bir yerde** tanımlıdır ve "resmî belgede doğrulanmamış" etiketi hem kodda hem kullanıcı yüzeyindedir | başka hiçbir modülde `Authorization`/`Bearer ` **string sabiti** yok (docstring prose sayılmaz); `auth_header_caveat` yanıtta | `test_opencode_client.py::test_the_credential_header_is_written_in_exactly_one_module`, `::test_the_unverified_header_assumption_is_labelled_where_it_lives`, `test_opencode_http.py::test_the_status_document_carries_the_unverified_header_caveat` | G |
| SI-236 | `x-opencode-session` **oturum başına rastgeledir**, kimliğe/kullanıcıya bağlanmaz ve kalıcı değildir | 32 hex; iki istemci farklı değer üretir; diskte yok | `test_opencode_client.py::test_the_session_header_is_sent_and_is_not_tied_to_anything` | G |
| SI-237 | **Ücretli** uç nokta tam bir kez denenir; kayıp yanıt tekrarlanmaz, adıyla raporlanır. Ücretsiz katalog sınırlı tekrarlıdır ve `Retry-After` tavanlanır | 429/500/503'te tam 1 istek; timeout → `OpenCodeLostResponseError`; katalog en çok 2 deneme; bekleme ≤ 5 sn; `post_completion` içinde döngü yok | `test_opencode_client.py::test_a_metered_request_is_attempted_exactly_once_on_a_retryable_status`, `::test_a_lost_response_on_a_metered_lane_is_named_rather_than_retried`, `::test_the_free_catalog_is_retried_a_bounded_number_of_times`, `::test_a_retry_after_header_is_honoured_but_clamped`, `::test_the_module_contains_no_retry_loop_on_the_metered_path` | G |
| SI-238 | Ağ kesici bu istemcinin hata işlemesi tarafından **yutulmaz** | `OutboundNetworkBlockedError` yakalanan hiçbir tipin alt sınıfı değil; `client.py`'de `Exception`/`BaseException`/`AssertionError` yakalayan `except` yok; mock'suz katalog çağrısı gürültüyle kırılır | `test_outbound_guard.py::test_an_opencode_client_with_no_mock_transport_fails_loudly`, `::test_the_guard_is_not_swallowed_by_the_opencode_clients_error_handling`, `::test_the_opencode_client_catches_nothing_that_could_hide_the_guard` | G |
| SI-239 | Anahtar ayrı bir DPAPI zarfındadır, hiçbir tabloya girmez, **sürümlü ve kind denetimlidir**, ve alan ayrımı in-band'dir | zarf `{format, version, kind, created_at, dpapi_blob}`; anahtar dosyada düz değil; yanlış `version`/`kind`/`format`, **eksik veya fazla alan** ve yanlış tipli `created_at` reddedilir; audit materyali zarfı **anahtar diye okunamaz**; ACL yalnız SYSTEM + geçerli kullanıcı. **Düzeltme:** `test_the_envelope_is_versioned_and_kind_checked` dosyayı **birikmeli** bozuyordu — her tur bir önceki turun bozuk dosyasını okuyup üstüne yazıyordu, `version=99` ilk turda takılıyor ve `kind`/`format` dalları **hiç** çalışmıyordu; `require_exact_keys` ile `created_at` tip denetimini ise hiçbir test tutmuyordu. Döngü artık her turda taze zarftan başlar ve her turdan sonra sağlam zarfı geri yükleyip okur | `test_opencode_credentials.py::test_the_envelope_has_the_audit_shape_and_hides_the_credential`, `::test_the_envelope_is_versioned_and_kind_checked`, `::test_an_envelope_with_a_missing_or_extra_or_mistyped_field_is_refused`, `::test_an_audit_material_envelope_cannot_be_read_as_a_credential`, `::test_the_acl_is_restricted_to_the_current_user_and_system` | G |
| SI-240 | Anahtar **üzerine yazılabilir** (audit materyalinin tersi) ve bu fark **yan yana** sabitlenmiştir | ikinci `store` başarılı ve yeni değeri okur; ikinci `create_material` `AuditEnvelopeError` | `test_opencode_credentials.py::test_a_credential_is_replaceable_because_a_user_must_be_able_to_rotate_one`, `::test_the_audit_material_still_refuses_to_be_overwritten` | G |
| SI-241 | Redaksiyona kaydedilemeyecek kadar kısa bir anahtar **saklanmaz**; uzunluk hem kapıda hem kullanım anında denetlenir | `MIN_KEY_LENGTH > _MIN_REGISTERABLE_LENGTH`; kısa değer `CredentialEnvelopeError` → HTTP 400; biçim kontrolü **yoktur** | `test_opencode_credentials.py::test_a_credential_too_short_to_redact_is_refused`, `::test_storing_does_not_validate_the_shape_of_a_credential`, `test_opencode_http.py::test_a_credential_too_short_to_redact_is_a_clean_refusal` | G |
| SI-242 | DB'ye yalnız **göreli yol + zaman + fingerprint** girer; saklanan anahtarı geri gösteren/kopyalayan endpoint **yoktur** ve sütun adlarında `key` yasaktır | beş sütun; yol göreli; yanıt gövdelerinde `api_key`/`key`/`credential`/`token` alanı yok; route kümesi tam beş ve hiçbiri okuma yolu değil | `test_opencode_credentials.py::test_only_a_relative_path_a_time_and_a_fingerprint_reach_the_database`, `test_opencode_http.py::test_the_status_document_has_no_field_that_could_hold_a_credential`, `::test_the_surface_offers_exactly_five_routes_and_no_completion_lane`, `test_module_registry.py::test_the_opencode_tables_have_no_secret_shaped_columns` | G |
| SI-243 | Anahtar canary'si **hiçbir yüzeyde** görünmez: başarılı yolun HTTP gövdeleri **ve header'ları**, **reddedilen bir gövdenin 422'si**, OpenAPI, SQLite, zarf, veri dizini, log+exception, frontend bundle. Canary depoda başka yerde yoktur | her yüzeyde yok; canary redaksiyon eşiğinin üzerinde ve benzersiz. **Düzeltme:** ilk yazımda "HTTP gövdeleri ve header'ları" deniyordu ama yalnız **başarılı** store sonrası GET'ler ölçülüyordu; hata yolu kapsam dışıydı ve orada anahtar fiilen yankılanıyordu (bkz. SI-257) | `test_opencode_leakage.py::test_the_credential_is_absent_from_*` (yedi yüzey), `::test_a_rejected_credential_body_is_not_quoted_back_in_the_422`, `::test_the_canary_appears_nowhere_else_in_the_repository`, `::test_the_canary_is_long_enough_for_the_redaction_registry_to_hold_it` | G |
| SI-244 | Upstream anahtarı hata gövdesinde **yansıtsa bile** kullanıcıya veya loga ulaşmaz; anahtar istek boyunca kayıtlıdır ve iş bitince düşürülür | 401 gövdesindeki anahtar `<redacted>`; `failure.detail` temiz; çağrı sonrası registry temiz — hata yolunda da | `test_opencode_leakage.py::test_an_upstream_body_that_echoes_the_credential_never_reaches_the_user`, `::test_the_credential_is_dropped_from_the_registry_when_the_request_ends`, `::test_the_credential_is_dropped_even_when_the_request_fails` | G |
| SI-245 | Model → protokol eşlemesi **derleme zamanı kapalı tablodur**; çekilen katalog hiçbir modeli seçilebilir yapamaz ve iddia ettiği URL fetch edilmez | `protocol`/`endpoint`/`selectable` alanı taşıyan katalog satırı yine `selectable=False`; tablo resmî "Endpoints" tablosunun **27 satırlık transkripsiyonudur** (4/8/15) ve aile başına küme olarak denetlenir | `test_opencode_catalog.py::test_the_catalog_cannot_make_a_model_selectable`, `test_opencode_protocols.py::test_the_closed_table_transcribes_all_twenty_seven_published_rows`, `::test_grok_is_filed_under_responses_and_not_chat_completions`, `::test_every_documented_protocol_resolves_to_a_registered_address` | G |
| SI-256 | Desteklenen bir model **gerçekten seçilebilir**: `selectable_model_ids()` boş dönemez ve seçim HTTP yüzeyinden uçtan uca çalışır ("göstermelik API kutusu" regresyonu) | küme tam **27** kimlik; üç ailenin her birinden bir model seçilebilir; `POST /api/opencode/model` 200 döner ve `selected_model` backend'de saklanır; `model_count` ile `selectable_count` **ayrı** alanlardır | `test_opencode_protocols.py::test_this_build_can_actually_address_a_model`, `test_opencode_catalog.py::test_this_build_can_address_the_documented_models`, `::test_a_model_on_each_documented_family_can_be_chosen`, `test_opencode_http.py::test_a_documented_model_can_be_chosen_over_http_and_survives_a_reread`, `::test_a_refresh_lists_every_model_and_marks_which_ones_are_addressable` | G |
| SI-246 | Katalogda olup resmî tabloda **olmayan** model (canlı katalog 34, tablo 27 — 7 fazlalık) **listelenir ama seçilemez**, nedeni görünür ve kullanıcının seçtiği model sessizce **başka modele çevrilmez** | her seçilemez modelde `reason`; "satır yok" ile "satır var, ailesi yayımlanmamış" **ayrı cümlelerdir**; seçim denemesi 400 + gerekçe; `selected_model` boş kalır; fallback yok | `test_opencode_catalog.py::test_a_model_with_no_table_entry_is_listed_and_not_selectable`, `::test_the_catalog_surplus_is_listed_with_its_reason_and_cannot_be_chosen`, `::test_a_row_that_is_present_but_unverified_says_so_and_not_something_else`, `::test_a_surplus_model_is_refused_through_the_real_table`, `::test_an_unmapped_model_is_refused_and_nothing_is_substituted`, `test_opencode_http.py::test_choosing_an_unaddressable_model_is_a_refusal_with_the_reason`, `::test_choosing_an_unknown_model_is_refused_and_nothing_is_substituted` | G |
| SI-247 | **Bilinmeyen veri saklama koşuluna "saklanmıyor" denmez**; eğitim için kullanılan modeller varsayılan seçilemez ve ek onay ister. Koşul **model başınadır** ve yayımlandığı gibi taşınır | `unknown` da `requires_training_acknowledgement=True` ve kaynaksız/tarihsizdir; iki `muse-spark-*` satırı `documented` **olduğu hâlde** onaysız seçilemez, onayla geçer; onay eşlemesiz modeli açmaz; `0 days*` yıldızı korunur; `30 days` sıfır diye gösterilmez; koşul bildiren her satır `privacy_source` + `privacy_read_on` taşır | `test_opencode_catalog.py::test_an_unknown_retention_term_is_never_shown_as_not_retained`, `::test_a_documented_training_model_is_listed_selectable_and_still_gated`, `::test_an_acknowledgement_does_not_unlock_an_unaddressable_model`, `::test_a_training_family_identifier_raises_the_bar_and_never_lowers_it`, `::test_a_training_model_is_not_selectable_by_default_and_needs_acknowledgement`, `test_opencode_protocols.py::test_the_muse_spark_rows_are_training_models_and_need_acknowledgement`, `::test_no_other_documented_row_asks_for_a_training_acknowledgement`, `::test_the_deepseek_footnote_marker_survives_transcription`, `::test_the_two_thirty_day_rows_are_not_described_as_zero_retention`, `test_opencode_http.py::test_a_training_model_is_refused_over_http_until_it_is_acknowledged` | G |
| SI-248 | Katalog **yarım parse edilmez**, sınırlıdır, süpürülür; cache tarihi ve erişim hatası **ayrı ayrı** gösterilir ve dosya yolu API'ye dönmez | okunamayan satır tüm belgeyi reddettirir; yinelenen kimlik reddedilir; bidi override süpürülür; başarısız yenileme cache'i silmez ve kendi tarihini ödünç vermez; cache tabloda, dosyada değil | `test_opencode_catalog.py::test_a_catalog_that_half_parses_is_refused_whole`, `::test_a_catalog_that_lists_one_identifier_twice_is_refused`, `::test_an_imported_identifier_is_swept_and_bounded`, `::test_a_failed_refresh_shows_the_error_without_deleting_the_cache`, `::test_the_cache_leaves_no_file_behind_and_no_path_to_leak` | G |
| SI-249 | **HTTP 200 içinde sağlayıcı hatası taşıyan gövde başarı sayılamaz**; tanınmayan şekil boş cevap değildir | üç ailede de 200+`error` → `PROVIDER_ERROR`; tanınmayan şekil `MALFORMED_BODY`; boş gövde `EMPTY_BODY` | `test_opencode_protocols.py::test_a_two_hundred_carrying_a_provider_error_is_not_a_success`, `::test_an_unrecognised_shape_is_malformed_and_not_an_empty_answer`, `::test_an_empty_body_is_named_as_empty` | G |
| SI-250 | Token/maliyet sağlayıcıdan gelmiyorsa `unknown`; **sıfır uydurulmaz** ve `bool` token sayısı sayılmaz | usage yoksa `None`, `total_tokens` `None`; `True`/negatif değer reddedilir | `test_opencode_protocols.py::test_a_body_with_no_usage_is_unknown_and_never_zero`, `::test_a_boolean_is_not_accepted_as_a_token_count` | G |
| SI-251 | `budget_available: Literal[False]` **değişmez**; abonelik "sınırsız" denmez ve "Use balance"ın engellendiği **iddia edilmez** | yanıtta `False`; ürünün kendi cümlelerinde `sinirsiz`/`unlimited` yok (çalışma zamanında denetlenir); konsol ifadesi taşınır | `test_opencode_http.py::test_the_spending_context_opens_no_budget_and_claims_nothing_unlimited` | G |
| SI-252 | Streaming ve tool-call **yoktur ve yokluğu söylenir**; üç ailenin gövde şeklinin kaynağı beyan edilir | `streaming_supported`/`tool_calls_supported` `Literal[False]`; erteleme cümlesi ve `shape_provenance` yanıtta | `test_opencode_protocols.py::test_streaming_and_tool_calls_are_absent_and_say_so`, `::test_the_shape_provenance_is_stated_rather_than_implied`, `test_opencode_http.py::test_the_protocol_context_states_the_two_deferrals` | G |
| SI-253 | Bağlantı denetimi **rozet üretmez**: `verified` diye bir durum yoktur ve gerekçeler çoğuldur. Biçim kontrolüyle başarı üretilmez | durum en fazla `key_saved_unverified`; en az iki gerekçe; katalog okumak durumu değiştirmez | `test_opencode_http.py::test_storing_a_credential_answers_saved_and_not_verified`, `::test_a_fresh_install_reports_not_configured_and_never_verified`, `test_opencode_catalog.py::test_a_catalog_read_says_nothing_about_the_credential` | G |
| SI-254 | Açılışta ve durum okurken **sıfır** giden istek; katalog yalnız kullanıcı eylemiyle çekilir. Sayılarak ölçülür, iddia edilmez | `create_app` sırasında 0; üç `status` okumasında 0; model seçiminde 0 | `test_opencode_http.py::test_building_the_application_makes_no_outbound_request`, `::test_reading_the_status_makes_no_outbound_request`, `test_opencode_catalog.py::test_building_the_service_and_reading_it_contacts_nobody`, `::test_choosing_a_model_sends_nothing` | G |
| SI-257 | **Doğrulama hatası gönderilen değeri yankılamaz.** 422 gövdesinden `input` ve `ctx` düşürülür; `loc`/`msg`/`type` kalır | canary bir tip hatasıyla reddedildiğinde gövdede yoktur; kural tüm route'lar için geçerlidir; 422 sertleştirme başlıklarını ve `no-store`'u taşır | `test_opencode_leakage.py::test_a_rejected_credential_body_is_not_quoted_back_in_the_422`, `::test_a_rejected_body_carries_no_submitted_value_on_any_route`, `::test_the_422_carries_the_hardening_headers_and_is_never_cached`, `::test_the_stripper_drops_every_value_bearing_key_and_keeps_the_rest` | G |
| SI-258 | Giden istemci allow-list'i **tam yolla** anahtarlanır; bir dizinin adını ödünç alan yeni dizin muafiyet almaz | `station_api/plugins/opencode/client.py` ve `station_api/vendor/technocore/*.py` probları reddedilir; izinli tam yol geçer | `test_write_gate.py::test_a_client_planted_where_a_directory_borrows_an_allowed_name_is_refused`, `::test_a_client_planted_where_a_directory_borrows_the_technocore_name_is_refused`, `::test_the_allow_list_is_keyed_by_full_path_and_not_by_a_bare_name` | G |
| SI-259 | Seçilemezlik cümleleri **kaynak sayfa hakkında değil, bu sürümün pinli tablosu hakkında** konuşur; tablonun okunma tarihi her zaman görünür ve katalog pinli fazlalığı aşınca **görünür bir bayatlık uyarısı** çıkar | `UNMAPPED_REASON`/`UNVERIFIED_REASON` "bu sürümün pinli tablosu" der ve okuma tarihini taşır; `TABLE_PROVENANCE` koşulsuz gösterilir; `EXPECTED_UNMAPPED_COUNT` (7) aşılınca `drift_notice` dolar ve panelde uyarı olarak render edilir | `test_opencode_catalog.py::test_the_unselectable_sentences_speak_about_this_build_and_not_the_source`, `::test_the_table_provenance_is_always_available_and_carries_both_dates`, `::test_the_drift_notice_fires_on_the_reading_the_review_actually_took`, `::test_a_catalog_that_outgrew_the_table_says_so_through_the_service`, `OpenCodeConnectionPanel.test.tsx` (üç test) | G |
| SI-260 | "Sınırsız" yasağı **Türkçe katlamayla** uygulanır; noktasız `ı` ASCII `i`'ye eşlenir ve test yasağı bağımsız yazımla sürer | `s\u0131n\u0131rs\u0131z` her yazımıyla reddedilir; masum cümleler geçer; kural sunum yolunda koşar | `test_opencode_http.py::test_the_guard_sees_the_word_as_turkish_actually_spells_it`, `::test_the_guard_still_admits_a_sentence_that_does_not_make_the_claim`, `::test_the_status_route_would_refuse_to_serve_an_unlimited_claim` | G |
| SI-261 | Tarayıcı paketinin **kendi disiplini testten önce** denetlenir ve `only`/`skip` ile susturulamaz; giden sayaç **context** seviyesindedir ve `context.request`'i de kapsar | tarama `globalSetup`'ta koşar; `forbidOnly: true` koşulsuz; `.only`, `.skip/.fixme`, `tests/**` altındaki her `setTimeout` ve ölçülemeyen `request` kanalı koşuyu kırar; hem `blocked` hem `seen` için negatif kontrol vardır | `e2e/harness/discipline.ts` + `e2e/global-setup.ts`; `suite-discipline.spec.ts::the tree keeps its own rules`, `::a focused run cannot report success`; `shell.spec.ts::the guard is live...`, `::the api request channel is refused and counted too`, `::a same-origin api request is measured and allowed through` | G |
| SI-262 | Şema aşama numarası **beş** giriş noktasında da aynıdır; tarayıcı harness'ı da taranır | `apps/station-web/e2e` kökü de `CURRENT_SCHEMA_STAGE` ile denetlenir | `test_module_registry.py::test_every_entry_point_names_the_same_release_stage` | G |
| SI-255 | Görev katmanı **OpenCode'a da** erişemez; yasak liste `station_api.opencode`'un tamamını kapsar | `modules/`+`tasks/` ağacında import yok | `test_module_registry.py::test_the_task_layer_has_no_outbound_surface` | G |
| SI-263 | Metadata satırı **hiçbir zaman** diskteki anahtardan başka bir anahtarı adlandıramaz; fingerprint ile zarf ayrışamaz | `store_credential` satırı **önce düşürür**, zarfı yazar, sonra satırı yeniden yazar; `session.add` patlatıldığında durum `not_configured` olur ve eski fingerprint **gösterilmez**; zarfsız bir satır fingerprint'i ve iki zamanı da boş bırakır. **Bulgu:** eski sıra dosya-önce'ydi ve arada transaction yoktu; DB hatası sonrası `/status` "yapılandırılmış, `9359c4e2`" derken zarfta başka bir anahtar duruyordu | `test_opencode_credentials.py::test_a_failed_metadata_write_never_leaves_a_fingerprint_naming_another_key`, `::test_a_row_without_an_envelope_names_no_key_at_all` | G |
| SI-264 | Zarf yazımı `os.replace`'in **her iki yanında** fail-closed'dur | rename'den önceki hata eski zarfı bırakır; rename'den **sonraki** hata yeni dosyayı da siler, `.tmp` artığı kalmaz, sonuç "zarf yok" olur. **Bulgu:** eski `except BaseException` yalnız geçici dosyayı siliyordu; rename olduysa yapacak bir şeyi yoktu, çağıran hata görürken eski anahtar gitmiş ve korumasız yeni anahtar canlı kalıyordu | `test_opencode_credentials.py::test_a_failure_after_the_rename_leaves_no_envelope_at_all` | G |
| SI-265 | Kısıtlayıcı ACL, zarfın **ilk baytından önce** uygulanır ve dizin de kısıtlanır | dosya `O_CREAT|O_EXCL` ile boş açılır, ACL sıfır baytken uygulanır, sonra yazılır; bir dosya üzerindeki ilk ACL çağrısı **0 bayt** görür; `opencode/v1` dizininin DACL'i de yalnız SYSTEM + geçerli kullanıcıdır. **Bulgu:** üç modülün docstring'i "ACL yeniden adlandırmadan önce uygulanır, dolayısıyla zarf asla kısa süre kalıtılmış izinlerle okunabilir olmaz" diyordu; izleme `mkstemp`'in kalıtılmış DACL'ini ve ACL çağrısı anında **zaten yazılmış 537 baytı** gösterdi. `credential_store.py` düzeltildi; `evidence/audit_envelope.py` ve `vault/service.py` docstring'leri gerçeğe indirildi (bkz. SI-266) | `test_opencode_credentials.py::test_the_envelope_is_restricted_before_a_single_byte_is_written`, `::test_the_credential_directory_is_restricted_too` | G |
| SI-266 | **Kabul edilen sınır (kapatılmadı).** `vault/service.py` ve `evidence/audit_envelope.py` zarflarını hâlâ yaz → fsync → ACL sırasıyla yazar ve dizinlerine ACL uygulamaz; `vault/service.py` ACL'i **doğrulamaz** | Her iki docstring artık bunu söyler; "ve doğrulanır" iddiası kaldırıldı (`windows_acl.acl_grantee_sids` vardır ve testler kullanır, yazma yolu kullanmaz). Kapatılmama gerekçesi: pencerede duran şey DPAPI şifreli metindir, Windows'ta Administrator zaten sahipliği alabildiği için dizin ACL'i gerçek bir güven sınırı değildir, ve audit materyalinin yazma yolunu değiştirmek zincirin doğrulamasının dayandığı tek dosyaya dokunurdu | docstring'ler: `vault/service.py::DpapiVault._atomic_write`, `evidence/audit_envelope.py::_atomic_write` | G |
| SI-267 | OpenCode kimlik-bilgisi katmanının **her** arızası OpenCode hiyerarşisindedir; hiçbir `VaultError` veya çıplak `OSError` route'a ulaşmaz | DPAPI kullanılamaz / ACL uygulanamaz → `OpenCodeConfigurationError` → **503** ve mesaj DPAPI'yi adlandırır; bozulmuş zarf, okunamayan dosya → `CredentialEnvelopeError` → **400**; özgün hata `__cause__`'ta durur; hiçbir mesajda anahtar yok. **Bulgu:** bu iki arıza `station_api.vault.errors.*` fırlatıyordu, route yakalamıyordu ve shield opak 500 üretiyordu — sızıntı yoktu (traceback ölçüldü), sözleşme yanlıştı | `test_opencode_credentials.py::test_a_dpapi_capability_failure_is_named_in_the_opencode_hierarchy`, `::test_an_acl_failure_is_named_in_the_opencode_hierarchy`, `::test_a_blob_dpapi_cannot_unprotect_is_a_credential_refusal_not_a_vault_error`, `test_opencode_http.py::test_a_machine_without_dpapi_is_told_so_rather_than_given_an_opaque_500`, `::test_a_credential_file_that_cannot_be_written_is_a_refusal_and_not_a_500` | G |
| SI-268 | Tek zarf dosyasının okuyucuları ve yazıcıları süreç içinde **sıralanır**; eşzamanlı erişim çıplak `OSError` üretmez | iki yazıcı × 15 + iki okuyucu × 30 iş parçacığında **sıfır** hata; okunan değer daima iki anahtardan biri; `.tmp` artığı yok; süreç dışı bir yazıcıya karşı okuma sınırlı (4 deneme) yeniden dener ve sonunda `CredentialEnvelopeError` verir. **Bulgu:** kilitsiz hâlde 160 işlemde 53 hata, 13'ü `PermissionError`; yazma fail-safe'ti ama hata tipi hiyerarşi dışıydı — ve `load()`'un üretim çağıranı Paket H'de gelecek | `test_opencode_credentials.py::test_concurrent_readers_and_writers_never_raise_a_raw_os_error` | G |
| SI-269 | Anahtarı redaksiyona kaydetmek **çağırandan alınmıştır**: `opened()` register/forget çiftini bloğa bağlar, `load()` hiçbir şey kaydetmez ve bunu söyler | `opened()` içinde anahtar registry'dedir, çıkışta değildir, blok **hata fırlatsa bile** düşürülür; `load()` tek başına kaydetmez. **Bulgu:** `load()` docstring'i "`OpenCodeService` her kullanımda ikisini de yapar" diyordu; servis `load()`'u hiç çağırmıyordu, yani var olmayan bir çağıranı garanti gibi gösteriyordu | `test_opencode_credentials.py::test_opened_registers_the_key_for_the_block_and_forgets_it_after`, `::test_opened_forgets_the_key_even_when_the_block_raises`, `::test_load_on_its_own_registers_nothing` | G |
| SI-270 | **Kabul edilen sınır (kapatılmadı).** Sağlayıcı anahtarı için bellek temizliği **yoktur** ve modül bunu açıkça yazar | `opencode/` altında `bytearray`/sıfırlama yoktur; anahtar Pydantic'ten itibaren `str`'dir ve Python'da yerinde ezilemez. Yalnız zarf katmanını `bytes`'a çevirmek üstteki üç çerçevedeki aynı değişmez nesneyi bırakırdı — koruma değil tiyatro olurdu. Geçerli korumalar: DPAPI zarfı, kısıtlayıcı ACL, redaksiyon registry'si; bir crash dump veya takas edilmiş sayfa **kapsam dışıdır** | `credential_store.py` modül docstring'i ("What is deliberately **not** here"); `vault/service.py` aynı sınırı scrub *ettiği* seed için zaten yazıyor | G |

---

## 9i. Paket H1 değişmezleri — kamuya açık oda taraması (uygulandı)

Kapsam kararları [`decisions/0007-paket-h1-kapsam-kararlari-2026-09-04.md`](decisions/0007-paket-h1-kapsam-kararlari-2026-09-04.md);
uygulama ayrıntısı [`work-scan.md`](work-scan.md).

### SI-73 ve SI-152 neden yine **genişletildi**, gevşetilmedi

**SI-73** ("yalnız incelenmiş modüller giden istemci taşıyabilir") beşinci bir
satır aldı: `station_api/workscan/client.py`. Kural değişmedi, liste değişti —
ve liste Paket G'den beri **kaynak köküne göreli tam yolla** anahtarlandığı
için, bu ilk kez `technocore/` veya `opencode/` dışında bir dizinde yaşayan
istemci olmasına rağmen hiçbir muafiyet doğurmadı. `workscan` adını ödünç alan
ikinci bir dizin de reddedilir.

**SI-152** ("her kabiliyet kendi kapalı registry'sini taşır") dördüncü
registry'yi aldı: `workscan/targets.py`. `SOURCES` hâlâ **tam altı belge**dir
ve testi hâlâ hem `len(SOURCES) == 6` hem `set(SourceId)` eşitliğini tutar.
ADR-0007 §3'ün not düştüğü ayrıntı burada kayıtlıdır: `test_evidence_stream.py`
içindeki `"/r/" not in source.path` iddiasını `/rooms` **geçerdi** (`/r/` alt
dizgisi yok), yani "izleme yolu bir odayı adresleyemez" özelliğini fiilen
koruyan satır, sanılan satır değildir.

### Yeni değişmezler

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-271 | Tarama yüzeyi **dördüncü kapalı registry**dedir ve beşinci giden istemci URL, method, header, TLS ayarı veya serbest yol kabul etmez; taşıyıcı yalnız `MockTransport`'tur. Sorgu dizesi **yazılır, alınmaz** | iki sabit adres (`/rooms`, `/r/{room}`); `/r/events` kapsam dışı; `verify` paket genelinde hiç yazılmaz; `HTTPTransport` → `TypeError`; şema/host/port/user-info/fragment/traversal **ve hazır query** reddedilir; `fetch(self, source)` imzası değişmemiştir ve bu istemcide `fetch` diye bir metot yoktur | `test_work_scan_client.py::test_the_registry_holds_exactly_the_two_addresses_the_adr_opened`, `::test_the_six_document_registry_did_not_grow`, `::test_the_read_clients_fetch_signature_is_unchanged`, `::test_every_way_around_the_allow_list_is_refused`, `::test_a_transport_with_tls_verification_off_cannot_be_injected`, `::test_tls_verification_is_never_disabled`, `test_write_gate.py::test_httpx_is_imported_only_by_the_reviewed_clients` | H1 |
| SI-272 | **Zamanlayıcı, arka plan görevi ve `wait` (long-poll) yoktur**; yenileme yalnız açık kullanıcı eylemiyle olur ve açılışta giden istek **sıfırdır** | `wait`/`n` hiçbir query'de yok ve `NEVER_SENT_PARAMS`'ta; paket ağacında `asyncio`/`threading`/`sched`/`concurrent` importu ve `create_task`/`Timer`/`Thread` çağrısı yok (`time` yalnız `client.py`'deki iki deneme arası bekleyiş için); `create_app` sırasında **0** istek, üç `status` okumasında **0** istek — sayılarak ölçülür | `test_work_scan_client.py::test_the_long_poll_parameter_is_never_sent`, `::test_no_module_in_the_package_names_wait_as_a_query_parameter`, `::test_the_package_starts_no_timer_or_background_task`, `test_work_scan_http.py::test_building_the_application_makes_no_outbound_request`, `::test_reading_the_status_makes_no_outbound_request` | H1 |
| SI-273 | Tarama kapsamı **kullanıcının seçtiği oda kümesidir**; bütün oda evreni taranmaz ve `DENIED_ROOMS` (lobby, meta) **okumada da** geçerlidir | istek gövdesindeki liste kapsamdır ve en çok 10 odayla sınırlıdır; "hepsini tara" rotası yoktur; `lobby` → `room_refused`; okunamayan oda **adıyla** raporlanır, boş oda diye değil; **raporlanan kapsam yanıtın `room` alanından değil çözümlenmiş hedeften gelir** (SI-282) | `test_work_scan_client.py::test_the_denied_rooms_are_refused_on_the_read_path_too`, `::test_no_markers_means_every_room_is_refused`, `test_work_scan_http.py::test_a_scan_reads_only_the_rooms_in_the_body`, `::test_the_lobby_is_refused_on_the_scan_route_too`, `::test_a_room_that_cannot_be_read_is_named_rather_than_reported_as_empty`, `::test_the_surface_offers_exactly_four_routes_and_no_scan_everything_lane` | H1 |
| SI-274 | **Bayatlık eşiği uydurulmaz**: etiket her zaman gösterilir ve ölçülen okuma anı ile sunucunun kendi beyanını (`ROOMS_CACHE_SECONDS = 3`) birlikte taşır | `StalenessNote` üzerinde `is_stale`/`fresh` alanı **yoktur**; not her anlık görüntüde vardır, yalnız bir sorun varken değil; yanıt gövdesinde `declared_cache_seconds == 3` | `test_work_scan_snapshot.py::test_the_staleness_note_carries_the_reading_time_and_the_declared_bound`, `::test_the_snapshot_has_no_freshness_verdict_field`, `::test_the_note_is_present_on_every_snapshot_and_not_only_on_a_bad_one`, `test_work_scan_http.py::test_the_room_overview_carries_both_caller_written_caveats` | H1 |
| SI-275 | Ring düşüşü **sunucunun kendi yayımladığı sinyaldir** ve bayatlıktan **ayrı** bir uyarıdır; `count`/`last_seq`/`first_seq` yanıttan okunur, varsayılmaz | `first_seq > since + 1` tam kuralı; imleç yoksa iddia yok; `count` ile gelen dizi uzunluğu ayrışırsa **iki sayı da** gösterilir ve biri diğerinin yerine geçmez; `count: true` reddedilir; eksik zorunlu alan belgeyi bütünüyle reddettirir | `test_work_scan_snapshot.py::test_the_ring_drop_fires_on_exactly_the_published_rule`, `::test_no_cursor_means_no_ring_drop_claim`, `::test_a_snapshot_with_a_gap_carries_its_own_notice_beside_the_staleness_one`, `::test_the_counts_are_read_from_the_reply_and_the_disagreement_is_shown`, `::test_a_boolean_is_not_accepted_as_a_count`, `::test_a_missing_required_field_refuses_the_whole_document` | H1 |
| SI-276 | Üçüncü otorite seviyesi (`community`) tanımlıdır: **yollar seviye 1, içerikleri seviye 3**. `topic` bir onay değildir, `from` `did:key` değilse kendi beyan ettiği takma addır ve uzak içerik **veridir** | `path_authority == 1`, `authority == 3` her mesajda ve her oda kaydında; `did:key` satırı bile "bu mesaj o anahtarla imzalandı" demez; bir karakter fazla/eksik benzeri dizi takma ad sayılır; görünmez ve bidi karakterler süpürülür; yanıtın kendi `untrusted` listesi kısaltılsa bile güven genişlemez | `test_work_scan_snapshot.py::test_room_content_is_level_three_even_though_the_path_is_level_one`, `::test_a_did_key_author_and_a_nickname_get_different_sentences`, `::test_a_lookalike_did_is_treated_as_a_nickname`, `::test_the_caller_written_fields_are_named_in_our_own_module`, `::test_invisible_characters_in_remote_text_are_swept` | H1 |
| SI-277 | `PUBLIC_ROOM_SCAN` kaynaklı görev **hiçbir görünümde** `OPERATOR_REQUEST` gibi sunulamaz; ayrım **iki bağımsız katmandadır** (farklı kaynak → farklı `source_version_id`, ve farklı başlangıç durumu) | `SUGGESTED` üretilebilir, `RUNNING`/`PAUSED` üretilemez kalır, **`INITIAL_STATE` `AWAITING_APPROVAL` kalır**; iki üretici birbirinin kaynağını reddeder; bayt-birebir aynı içerik iki kaynakta **farklı** `source_version_id` üretir; `suggested` görev ancak kullanıcının geçişiyle onaya gider ve kanıtsız yayıma geçemez | `test_task_states.py::test_the_initial_state_is_not_suggested`, `::test_the_unproducible_states_are_exactly_the_two_that_await_an_executor`, `::test_no_code_path_can_produce_an_unproducible_state`, `test_work_scan_http.py::test_the_two_producers_refuse_each_others_sources`, `::test_the_same_content_gets_a_different_identity_under_the_two_sources`, `::test_suggesting_a_candidate_opens_a_task_in_suggested_and_approves_nothing`, `::test_a_suggested_task_still_has_to_be_approved_by_a_person` | H1 |
| SI-278 | Her aday **sekiz öğeyi** taşır ve taşımayan aday **yapısal olarak üretilemez**; işin durumu için kesin dil yasaktır, çalışma tahmini **tahmin olarak etiketlidir** ve bütçe `not_implemented`'tır | `SourceQuote`/`EffortEstimate`/`WorkCandidate` `__post_init__`'te reddeder (`EvidenceRef` kalıbı); `label` bir parametre değildir; `budget_state` `PASSED` olamaz; yanıt gövdesinde `is_open` diye bir alan yoktur, yalnız `read_at` ile bir cümle vardır. **Beş zorunlu cümle ve kimlik kontrolü de mutasyonla ölçüldü** — ilk yazımda bunları kapsayan test yoktu, gövdeyi `return None` yapmak yalnız 3 testi kırıyordu; artık boş/boşluklu her alan ve kimliksiz aday testlidir | `test_work_scan_candidates.py::test_a_candidate_carries_all_eight_elements`, `::test_a_quote_without_its_coordinates_cannot_be_constructed`, `::test_a_negative_sequence_number_is_refused`, `::test_an_effort_estimate_cannot_present_itself_as_a_measurement`, `::test_a_candidate_cannot_claim_a_budget_this_release_does_not_have`, `::test_a_candidate_without_permissions_or_risks_cannot_be_constructed`, `::test_element_eight_is_a_sentence_with_a_timestamp_and_never_a_boolean`, `::test_a_candidate_missing_any_mandatory_sentence_cannot_be_constructed`, `::test_a_candidate_without_an_identity_cannot_be_constructed`, `test_work_scan_http.py::test_no_response_field_reports_a_work_item_as_open` | H1 |
| SI-279 | Aday üretimi **deterministiktir** (model çağrısı yok) ve altı yasak iş biçimi **sinyal aranmadan önce** reddedilir; reddedilen satır gösterilir, sessizce düşürülmez | paket `station_api.opencode`'u ve hiçbir sağlayıcı SDK'sını import etmez; aynı satır her koşuda aynı kimliği ve aynı içerik baytlarını verir; cüzdan/ödeme, puan kasma, spam, boş "done", kendi işini onaylama ve duplicate teslimat reddedilir; hem sinyal hem yasak taşıyan satır **aday üretmez**; aynı `seq` iki aday üretemez ve ikinci satır artık `duplicate_sequence` gerekçesiyle **gösterilir**, sessizce düşmez (SI-284) | `test_work_scan_candidates.py::test_the_package_calls_no_model_and_imports_no_completion_path`, `::test_the_same_line_produces_the_same_candidate_every_time`, `::test_every_string_on_a_candidate_comes_from_the_line_or_from_the_table`, `::test_a_prohibited_line_produces_no_candidate_even_when_it_matches_a_signal`, `::test_a_refused_line_is_reported_rather_than_silently_dropped`, `::test_the_same_line_cannot_produce_two_candidates_in_one_scan` | H1 |
| SI-280 | Yasak ifade denetimi H1 metinlerini **kapsar**: paketteki **her string literal** taranır, kural çalışma zamanında da uygulanır ve **mutasyonla** doğrulanmıştır | Paket E'nin altı ifadesi devralınır, H1 yedi ifade ekler; katlama (`ı` → `i`) yeniden kullanılır ve test yazımı bağımsız üretir; uzak metin **nötrlenir**, hiçbir taramayı reddettirmez; korumayı kapatınca kırmızıya dönen testler ölçülmüştür (aşağıdaki mutasyon kaydı) | `test_work_scan_language.py::test_no_string_literal_in_the_work_scan_package_carries_a_forbidden_phrase`, `::test_the_route_layer_is_scanned_too`, `::test_the_static_scan_is_actually_scanning_something`, `::test_a_phrase_is_caught_in_every_spelling`, `::test_remote_text_carrying_a_forbidden_phrase_is_neutralised_not_refused`, `::test_turning_the_guard_into_a_no_op_turns_this_file_red`, `::test_the_guard_is_wired_into_the_producer_and_not_only_defined` | H1 |
| SI-281 | Kibble için **kayıt açılır, istemci yazılmaz ve hiçbir istek gönderilmez**; doğrulanan/doğrulanamayan ayrımı ekranda taşınır, `community` etiketi zorunludur ve hiçbir üçüncü taraf `score`/`rank` alanı ürünün kendi cümlesine katılmaz | `support_unverified`; `adapter_written`/`contacted` **türetilmiştir**, daima `False`'tur ve **rota bu iki özelliği kayıttan okur** (şemadaki `Literal[False]` varsayılanı tel değişmezini korur, ama türetme yarısını test edilemez bırakıyordu — iki mutasyon 0 test kırmızıya döndürmüştü); `kibble.py` httpx import etmez; beş giden istemcinin hiçbirinde bu alan adı geçmez; yanıt gövdesinin **hiçbir yerinde** `score`/`rank`/`reputation`/`eligibility` anahtarı yoktur; servisin kendi iki İngilizce cümlesi **yanıt gövdesinde** birebir taşınır (`self_description_source`, `score_self_description`) ve frontend kendi kopyasını tutmaz; `TABLE_PROVENANCE` koşulsuz gösterilir | `test_work_scan_http.py::test_the_kibble_record_is_open_and_carries_both_columns`, `::test_the_kibble_record_itself_says_it_was_never_written_or_contacted`, `::test_the_response_carries_the_records_own_two_flags`, `::test_the_services_own_disclaimer_is_carried_verbatim`, `::test_the_services_own_words_reach_the_screen_over_the_wire`, `::test_the_score_caveat_travels_with_the_record`, `::test_no_response_anywhere_carries_a_third_party_score_or_rank`, `::test_no_module_in_the_package_can_reach_the_recorded_origin` | H1 |
| SI-282 | Bir yanıt **taramanın kapsamını yeniden adlandıramaz**: `room` alanı yanıttan okunur ama hiçbir yerde kapsam, kimlik, referans veya cümle olarak kullanılmaz; oda politikası **üç katmanda** uygulanır | `parse_room_messages` çözümlenmiş odayı **zorunlu** argüman olarak alır (varsayılanı yoktur) ve uyuşmazlıkta `SnapshotParseError` fırlatır — reddetme mesajı yanıtın seçtiği adı **tekrarlamaz**; `snapshot.room`/`reported_room` ikisi de istenen addır; `candidate_id`, `SourceQuote.room`, `reference` ve fayda şablonu istenen adı kullanır, iki farklı oda tek adaya çökemez; `RoomScanTarget.__post_init__` adı, `DENIED_ROOMS`'u ve tanınan oda sınıflarını yeniden doğrular; `assert_allowed_url` giden yolda `DENIED_ROOMS`'u yeniden kontrol eder; `{"room": "lobby"}` dönen bir tarama yanıtında `lobby` **hiç geçmez** | `test_work_scan_snapshot.py::test_a_reply_naming_another_room_is_refused_rather_than_relabelled`, `::test_the_refusal_does_not_repeat_the_name_the_reply_chose`, `::test_the_snapshot_carries_the_requested_room_and_says_so_separately`, `::test_the_requested_room_cannot_be_omitted`, `test_work_scan_http.py::test_a_reply_cannot_rename_the_room_it_answers_for`, `::test_two_rooms_answering_with_the_same_sequence_stay_two_candidates`, `::test_a_reply_borrowing_another_rooms_name_cannot_collapse_two_candidates`, `test_work_scan_client.py::test_a_scan_target_cannot_be_hand_built_for_a_denied_room`, `::test_the_outbound_path_is_re_checked_against_the_room_policy`, `::test_no_request_to_a_denied_room_reaches_the_transport` | H1 |
| SI-283 | Yasak iş biçimlerinde **yapısal olan sıralamadır, eşleşme bir kalıp listesidir** — ve bu sınır kullanıcıya söylenir. Liste, okuyanın aynı kelime olarak gördüğü yazımları da yakalar | `fold()` biçim (`Cf`) karakterlerini siler ve Kiril/Yunan benzer harfleri Latin karşılığına eşler; yasak kapısı ayrıca `tighten()` ile (kelime içi boşluk/tire/nokta atılmış) eşleşir ve altı karakterden kısa iğneler daraltılmış kümeye alınmaz; eş anlamlılar eklendi; inceleme probundaki **19 satırın hepsi** reddedilir ve hiçbiri aday üretmez; sıradan bir yardım/hata satırı hâlâ aday üretir; `status` yanıtı her okumada `prohibition_statement` taşır | `test_work_scan_candidates.py::test_a_wallet_request_is_refused_however_it_is_spelled`, `::test_none_of_those_lines_produces_a_candidate`, `::test_an_ordinary_help_request_is_still_a_candidate`, `test_work_scan_http.py::test_the_status_document_says_the_prohibitions_are_pattern_matched`, `WorkScanPanel.test.tsx::says the prohibited work shapes are pattern-matched, not understood` | H1 |
| SI-284 | Reddedilen satır **her gerekçede** gösterilir ve bir satırın reddi **bir satıra** mal olur: bir oda taramayı, bir tarama da okunmuş odaları düşüremez | tekrarlanan `seq` → `duplicate_sequence` gerekçesiyle listelenir (eskiden sessizce düşüyordu); zorunlu kaynak alanı eksik satır → `unusable_source` (eskiden `CandidateError` bütün taramadan fırlıyor ve HTTP 500 dönüyordu); servis katmanında oda başına `room_underivable`, rota katmanında tarama başına **502** yedeği vardır ve ikisi de hata enjeksiyonuyla sürülür; `wait`/`n` **her yazımda** reddedilir (`WAIT` dahil); zamanlayıcı/long-poll statik taraması `routes/workscan.py`'yi de kapsar | `test_work_scan_candidates.py::test_a_repeated_sequence_number_is_shown_rather_than_dropped`, `::test_a_line_without_a_timestamp_refuses_itself_and_not_the_room`, `test_work_scan_http.py::test_an_unusable_line_does_not_turn_the_whole_scan_into_a_500`, `::test_a_repeated_sequence_number_is_visible_on_the_wire`, `::test_a_derivation_that_fails_outright_costs_one_room_and_not_the_scan`, `::test_a_scan_that_fails_as_a_whole_answers_502_and_not_500`, `test_work_scan_client.py::test_the_never_sent_parameters_are_refused_in_any_casing`, `::test_the_route_layer_is_scanned_for_timers_and_long_polls_too` | H1 |

### Mutasyon kaydı (SI-282, SI-283, SI-284, SI-278, SI-281)

PR #17'nin bağımsız incelemesi iki korumanın **hiçbir testi kırmadığını**
ölçmüştü. Her düzeltmeden sonra koruma tekrar kapatıldı ve **ölçülen** sonuç
yazıldı; on üç mutasyonun hepsi geri alındı ve depo mutasyonsuz hâldedir.
Ölçüm kapsamı beş work-scan test dosyası artı `test_evidence_language.py`.

| Mutasyon | Sonuç |
|---|---|
| `parse_room_messages` oda uyuşmazlığı kontrolü kaldırıldı ve `room` yanıttan alındı | **4 test kırmızı** (kapsam yeniden adlandırma, kimlik çökmesi, iki reddetme testi) |
| `AdapterRecord.adapter_written` → `True` | **23 test kırmızı** — düzeltmeden **önce 0** idi. Hedefli olanlar: `test_the_kibble_record_itself_says_it_was_never_written_or_contacted`, `test_the_response_carries_the_records_own_two_flags`; kalanlar rota artık `True` bir kaydı serileştirmeyi reddettiği için |
| `AdapterRecord.contacted` → `True` | **23 test kırmızı** — düzeltmeden **önce 0** idi |
| Yasak kapısında `tighten()` samanlığı kaldırıldı | **10 test kırmızı** (`w a l l e t`, `wal-let`, `w.a.l.l.e.t` ve sıfır-genişlikli/yumuşak tire varyantları) |
| `fold()`'un biçim-karakteri silmesi ve benzer-harf eşlemesi kaldırıldı | **8 test kırmızı** (Kiril `а` taşıyan `claim`/`cuzdan` ve dört görünmez karakter varyantı) |
| `RoomScanTarget.__post_init__` gövdesi `return` yapıldı | **2 test kırmızı** |
| `assert_allowed_url`'ün oda kontrolü `return` ile atlandı | **1 test kırmızı** |
| `assert_allowed_query` yeniden büyük/küçük harf duyarlı yapıldı | **1 test kırmızı** |
| `derive_from_room`'un satır başına `except CandidateError`'ı devre dışı | **2 test kırmızı** |
| Servisin oda başına `except CandidateError`'ı devre dışı | **1 test kırmızı** (hata enjeksiyonlu test) |
| Rotanın `except WorkScanError`'ı devre dışı | **1 test kırmızı** (hata enjeksiyonlu test) |
| `WorkCandidate.__post_init__`'in `missing` döngüsü devre dışı | **15 test kırmızı** — düzeltmeden **önce 0** idi |
| `WorkCandidate.__post_init__`'in `if not self.id` kontrolü devre dışı | **1 test kırmızı** — düzeltmeden **önce 0** idi |
| Tekrarlanan `seq` yeniden sessizce düşürüldü | **2 test kırmızı** |


### Mutasyon kaydı (SI-280)

Koruma üç ayrı biçimde kapatıldı ve her seferinde **ölçülen** sonuç yazıldı;
üçü de geri alındı ve depo mutasyonsuz hâldedir.

| Mutasyon | Sonuç |
|---|---|
| `assert_no_forbidden_claim` gövdesi `return None` yapıldı | **2 test kırmızı**: `test_our_own_over_claim_fails_closed`, `test_turning_the_guard_into_a_no_op_turns_this_file_red` |
| `WORK_SCAN_FORBIDDEN_PHRASES` boş demete çevrildi | **6 test kırmızı**: registry devralma, ADR maddeleri, çalışma zamanı reddi, nötrleme, ekilen ifade probu ve mutasyon kontrolü |
| `targets.py`'ye yasak ifade taşıyan bir literal eklendi | **1 test kırmızı**: `test_no_string_literal_in_the_work_scan_package_carries_a_forbidden_phrase`, ifadeyi dosya adı ve satır numarasıyla adlandırarak |

---
## 9j. Paket H2 değişmezleri — agent çalışma ortamı ve Activity Desk (uygulandı)

Kapsam kararları [`decisions/0008-paket-h2-kapsam-kararlari-2026-09-05.md`](decisions/0008-paket-h2-kapsam-kararlari-2026-09-05.md);
uygulama ayrıntısı [`agent-runtime.md`](agent-runtime.md).

### SI-213, SI-216, SI-225 ve SI-226 neden **güncellendi**, silinmedi

Dördü de bu paketle birlikte söylediği şeyi değiştirdi, ve dördü de yerinde
düzeltildi:

**SI-213** ("görev katmanı dördüncü giden yüzey açmaz") arkasındaki tarama
`station_api/modules` ve `station_api/tasks` ağaçlarını okuyordu. Yeni bir
paket o taramanın dışındadır, yani **yeni paket muaf olurdu** — bir kuralın,
yazıldığı kodu kapsamayı bırakmasının yolu tam olarak budur. Aynı taramalar
artık `station_api/agent` ve önündeki rota dosyası üzerinde de koşar. Tek
esneme `station_api.vault`'tan iki modüldür (`windows_acl`, `errors`) ve o da
bir önek muafiyeti değil, **birebir allow-list**'tir: üçüncü bir isim testi
kırar.

**SI-216** ("`suggested`, `running` ve `paused` hiçbir kod yolundan
üretilemez") artık üç adı da içeremez. H1 birini, H2 diğer ikisini açtı —
her seferinde **önce üretici yazılarak**. Kritik nokta şudur:
`UNPRODUCIBLE_STATES` boşalınca üç test **boş parametreyle sessizce yeşile**
düşüyordu. Boş bir döngü hiçbir şey kanıtlamaz ve geçen bir testten ayırt
edilemez, bu yüzden hiçbiri öyle bırakılmadı — ikisi mekanizmayı **sürecek**
biçimde yeniden yazıldı (bir durum test süresince kapatılıyor), biri
yeniden adlandırılıp iddiaları **güçlendirildi**. `STATE_DETAIL[RUNNING]` ve
`[PAUSED]`'ın "bu sürümde hiçbir kod yolu bu durumu üretemez" cümleleri yalan
hâline geldiği için düzeltildi.

**SI-225** ("bütçe alanı yoktur") harfiyen doğru **kaldı**, çünkü tavan
bilinçli olarak `tasks/` ve `modules/` dışına, yeni `agent/` paketine
yazıldı. Değişen, ertelemeyi duyuran cümledir: H2 tavanı yazdıktan sonra "G ve
H2'ye ertelenmiştir" demek, sevk edilmiş bir şey için bekleme duyurusu
bırakmak olurdu.

**SI-226** ("durumu yazan tek yol `transition`") arkasındaki tarama iki ağacı
okuyordu ve `running`/`paused`'ı üreten kod üçüncü bir ağaçtadır. Tarama
genişletilmeseydi bu değişmez, tam da onu delen commit'te sessizce delinmiş
olurdu.

### Yeni değişmezler

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-285 | Keyfi kod ve kabuk yürütmesi **yapısal olarak** kapalıdır; `execution_unavailable` gerekçesi ve ölçülen izolasyon envanteri kullanıcıya gösterilir, ölçülemeyen bir olanak "yok" diye yazılmaz | `agent/` ve `routes/agent.py` ağacında `subprocess`/`multiprocessing`/`ctypes`/`importlib`/`builtins` importu ve `exec`/`eval`/`__import__`/`system`/`popen` adı **yok** (`compile` yalnız çıplak adda yasak, `re.compile` serbest ve bu muafiyet ayrı test edilir); tarama ekili bir çağrıyla sürülmüştür; `arbitrary_execution_supported` `Literal[False]`; envanterde Docker **`present` + `relied_upon:false`** ve optional feature'lar **`not_measured`**; her bulgu `relied_upon:false` | `test_agent_boundary.py::test_the_agent_package_cannot_run_a_program`, `::test_the_execution_scan_would_catch_a_planted_call`, `::test_the_innocent_spelling_of_compile_is_left_alone`, `test_agent_http.py::test_the_surface_states_that_execution_is_closed_and_why` | H2 |
| SI-286 | Araç registry'si **altıncı kapalı registry**dir: derleme zamanı tuple, tipli parametreler, ve **agent kendine araç ekleyemez**; kayıtsız kimlik **gösterilebilir bir ret** döner | `TOOLS` ve `_BY_ID` tam olarak birer kez atanır ve üzerlerinde mutasyon çağrısı yoktur; kayıt sekiz araçtır ve oracle **elle yazılıdır**; `ToolRegistryError(reason="tool_unknown")` (çıplak `KeyError` değil) ve mesaj istenen adı tekrarlamaz; `path`/`url` diye parametre tipi yoktur; `tool_calls_supported` `Literal[False]` ve `OUTBOUND_CLIENT_MODULES` **beşte** kalır | `test_agent_tools.py::test_the_registry_is_exactly_the_tools_this_release_has`, `::test_the_registry_is_never_written_at_runtime`, `::test_an_unregistered_identifier_gets_a_shown_refusal`, `::test_no_parameter_type_can_carry_an_address`, `test_agent_boundary.py::test_the_agent_package_has_no_outbound_surface` | H2 |
| SI-287 | Geliştirme sırasında verilen commit/PR/merge yetkisi **ürüne miras verilmez**; güven sınırı **import zamanında** denetlenir | git, PR, merge, paket kurulumu, ayar, izin listesi, plugin, shell, signer, vault, credential, env, home ve repo parçalarını taşıyan bir kayıt varsa uygulama **başlamaz**; denetim ekili bir `git_commit` kaydıyla sürülmüştür; on ayrı yetki adı tek tek reddedilir | `test_agent_tools.py::test_the_import_time_check_actually_refuses_a_planted_tool`, `::test_no_registered_tool_crosses_the_forbidden_capability_list`, `::test_the_authority_a_developer_had_is_not_inherited` | H2 |
| SI-288 | Tool runner **kabuk dizesi değil, tipli araç + doğrulanmış argüman** kullanır | tanınmayan anahtar, eksik zorunlu argüman, sade ad olmayan dosya adı (yol ayracı, sürücü harfi, `..`, NUL, CRLF, bidi, aşırı uzunluk) ve hex olmayan özet **reddedilir**; ad **kısaltılmaz, reddedilir**; metin süpürülür ve sınırlanır; pakette hiçbir çağrı `shell=` taşımaz veya bir runner adına gitmez (sözdizim ağacından okunur, metinden değil) | `test_agent_tools.py::test_an_undeclared_argument_is_refused`, `::test_a_missing_required_argument_is_refused`, `::test_a_file_name_parameter_refuses_anything_that_is_not_a_bare_name`, `::test_a_digest_parameter_refuses_anything_that_is_not_one`, `::test_the_tool_runner_takes_no_command_string` | H2 |
| SI-289 | Tavan **yalnız ölçülebilir üç birimdedir** (araç çağrısı, duvar saati, eşzamanlılık=1); token ve para birimi **gerekçesiyle reddedilir** ve hiçbir kod yolu tavana yazmaz | `BUDGET_UNITS` üç ad; `refused_units` telde `["token","currency"]` ve gerekçesiyle; `max_concurrency` `Literal[1]`; `CEILING` `frozen` ve **dört yazımda birden** (atama, öznitelik, artırmalı, sabit adlı `setattr`) taranır — tarama ekili bir yazıcıyla sürülmüştür; registry'de tavanı değiştiren araç yok; paket içinde hiçbir çağrı `ceiling=` geçmez; `agent_can_raise_ceiling` `Literal[False]` | `test_agent_budget.py::test_no_code_path_writes_the_ceiling`, `::test_the_ceiling_write_scan_would_see_a_planted_writer`, `::test_there_is_no_token_and_no_currency_unit`, `::test_the_ceiling_is_not_represented_as_a_tool`, `::test_the_ceiling_default_is_never_supplied_by_a_call_site`, `test_agent_http.py::test_the_surface_publishes_the_ceiling_and_the_units_it_refuses` | H2 |
| SI-290 | Çalışma alanı `<data_dir>/workspace/v1/<32-hex>` altındadır ve **dört katmanla** savunulur; **arşiv açan yol hiç yoktur** | ad allow-list'ten yeniden kurulur ve **yeniden yazılacaksa reddedilir**; her okuma/yazımda `resolve()`+`is_relative_to`; dosyadan köke kadar `is_symlink()` **ve** `os.path.isjunction()`; 64 dosya / 512 KiB / 4 MiB tavanları **diskten** okunur; `zipfile`/`tarfile`/`shutil`/`gzip` import edilmez ve `symlink`/`link` oluşturulmaz; on beş düşmanca ad, iki görev arası okuma ve üst dizindeki bağ reddedilir; symlink OS izin verdiğinde **gerçekten** oluşturulup denenir, izin vermediğinde predikat zorlanır (hiçbir makinede atlanmaz) | `test_agent_workspace.py::test_a_name_carrying_syntax_is_refused_rather_than_rewritten`, `::test_the_containment_check_refuses_a_path_that_leaves_the_root`, `::test_two_tasks_cannot_reach_each_other`, `::test_a_link_inside_the_workspace_is_refused`, `::test_a_link_above_the_file_is_refused_too`, `::test_the_total_byte_ceiling_is_read_from_disk_not_from_a_counter`, `test_agent_boundary.py::test_no_archive_is_ever_unpacked`, `::test_the_package_never_creates_a_link` | H2 |
| SI-291 | Çalışma alanı dizini ve her dosyası **SYSTEM + geçerli kullanıcıya** kısıtlanır (SI-265 kalıbı) | DACL grantee kümesi tam olarak iki SID; dosya boş oluşturulup ACL uygulandıktan sonra yazılır | `test_agent_workspace.py::test_the_workspace_directory_is_restricted_to_this_user`, `::test_a_written_file_is_restricted_too` | H2 |
| SI-292 | Plan, adımlar, söz verilen çıktılar ve başarı ölçütü **çalışma başlamadan** kaydedilir; planı değiştirmek başarı kriterini **sessizce gevşetemez** | `plan_sha256` üçünü birden kapsar ve `start_run` yeniden türetir (`plan_changed`); her adımın argümanları çağrıdan **hemen önce** yeniden özetlenir (`plan_arguments_changed`); ikisi de **satır doğrudan düzenlenerek** (her rota atlanarak) sürülür; plan düzenleme rotası yoktur, farklı plan **yeni çalışmadır** ve eskisi ölçütünü korur | `test_agent_runtime.py::test_an_edited_plan_is_refused_rather_than_carried_out`, `::test_edited_step_arguments_are_refused_at_the_call`, `::test_replanning_opens_a_new_run_and_leaves_the_old_digest_alone`, `::test_planning_records_everything_and_runs_nothing` | H2 |
| SI-293 | Test sonucu **modelin boolean'ı değil kaydedilmiş sonuçtur**; yürütme kapalı olduğu için alan `not_implemented` kalır ve görev `ready_to_publish`'e **geçemez** | biten çalışma dosya üretir, deterministik doğrulayıcı koşar, ve görev `review_needed`'da durur; `task_outcome` yazılır, `test_result` ve `user_acceptance` **yazılmaz**; kanıtsız yayım isteği `evidence_incomplete`; kanıt kaydeden rota **yoktur** | `test_agent_runtime.py::test_a_finished_run_produces_files_and_still_cannot_be_published`, `::test_the_runner_records_the_output_it_produced_and_no_test_result`, `test_agent_http.py::test_a_finished_run_reports_its_test_field_as_not_implemented` | H2 |
| SI-294 | Bütçe dolması, araç hatası, kullanıcı iptali, üretilmeyen çıktı ve yeniden başlatma **ayrı ayrı** raporlanır; durdur sonraki çağrıyı engeller ve **geç yanıt yan etki üretmez**; açılışta otomatik devam yoktur | beş ayrı faz ve ayrı cümleler; durdurulmuş çalışmada çalışma alanı **boş**; çağrı sırasında durdurma bayrağı kalkarsa adım `skipped` yazılır ve **üretilen dosya kaldırılır**; `interrupted_runs()` listeler, hiçbir şey devam etmez ve `create_app` sırasında `agent_run` satırı ve aktivite satırı **sıfırdır**; devam yalnız kullanıcının `resume`'udur | `test_agent_runtime.py::test_the_ceiling_ends_a_run_with_its_own_phase_and_audit_event`, `::test_a_tool_failure_is_a_different_ending_from_the_ceiling`, `::test_a_promised_artifact_that_was_not_produced_is_not_a_success`, `::test_a_stop_blocks_the_next_tool_call`, `::test_a_result_arriving_after_a_stop_leaves_nothing_behind`, `::test_a_run_interrupted_by_a_restart_is_listed_and_never_resumed`, `::test_creating_the_application_starts_no_run` | H2 |
| SI-295 | Kapsam dışı araç/ad/secret isteği **`permission_denied` olarak kaydedilir** ve zincire girer; görev otomatik olarak **başka bir hedefe kaydırılmaz** | kayıtsız araç ve çalışma alanı dışı çıktı adı reddedilir, olay yazılır, görev `awaiting_approval`'da kalır ve **hiç çalışma açılmaz** | `test_agent_runtime.py::test_an_unregistered_tool_is_refused_and_recorded_as_a_permission_denial`, `::test_an_out_of_scope_artifact_name_is_refused_and_recorded` | H2 |
| SI-296 | Activity Desk **ayrı yalnız-ekleme tablodur**, kendi retention'ı vardır ve satırları **zincir halkası değildir**; zincire yalnız **beş karar noktası** girer ve **zincirin atıfta bulunduğu hiçbir satır budanamaz veya silinemez**; silme bir audit olayıdır | `chain_referenced` yalnız append başarılı olduktan sonra yazılır; retention 500 satırda budar ve işaretli satırı **hiç** silmez (tavanın 50 üstünde hacimle sürülür); silme iki sayıyı **ayrı ayrı** raporlar, `activity_deleted` zincire yazılır ve zincir sonrasında `INTACT` doğrular; zincir açılamayan makinede satır yazılır ama bayrak **yazılmaz**; `actor` yalnız `user`/`station_runner` — `model` aktörü yoktur; tablolarda `reasoning`/`prompt`/`completion`/`payload` biçimli sütun yoktur ve yanıt anahtarları birebir sabittir | `test_agent_activity.py::test_a_decision_point_lands_in_both_layers_and_is_flagged`, `::test_a_step_event_is_not_flagged_and_reaches_no_chain`, `::test_retention_never_removes_a_row_the_chain_refers_to`, `::test_deleting_timeline_rows_keeps_the_ones_the_chain_names`, `::test_a_deletion_is_written_to_the_audit_chain`, `::test_a_machine_without_a_chain_records_but_claims_nothing`, `test_agent_boundary.py::test_no_agent_table_can_hold_a_model_reasoning_trace`, `test_agent_http.py::test_no_timeline_row_carries_a_reasoning_or_payload_field` | H2 |
| SI-297 | Yasak ifade denetimi **H2 metinlerini kapsar**: paketteki ve rota dosyasındaki **her string literal** taranır, kural çalışma zamanında da uygulanır ve **mutasyonla** doğrulanmıştır | Paket E'nin altı ve H1'in yedi ifadesi devralınır, H2 yedi ekler; katlama yeniden kullanılır ve test yazımı bağımsız üretir; kullanıcı metni **nötrlenir**, hiçbir çalışmayı reddettirmez; nötrleme **denetimden sonra değil, servis sınırında** yapılır — ilk yazımda `_clean` içinde nötrleyip sonra denetlemek guard'ı sessizce no-op yapıyordu ve test bunu yakaladı; korumayı kapatınca kırmızıya dönen testler ölçülmüştür (aşağıdaki mutasyon kaydı) | `test_agent_language.py::test_no_string_literal_in_the_agent_package_carries_a_forbidden_phrase`, `::test_the_route_layer_is_scanned_too`, `::test_the_static_scan_is_actually_scanning_something`, `::test_a_phrase_is_caught_in_every_spelling`, `::test_user_text_carrying_a_forbidden_phrase_is_neutralised_not_refused`, `::test_turning_the_guard_into_a_no_op_lets_an_over_claim_be_stored`, `::test_turning_the_guard_into_a_no_op_lets_a_run_report_an_over_claim`, `::test_the_guard_is_wired_into_the_runner_and_not_only_defined` | H2 |
| SI-298 | Görev ve activity rotaları `no-store` + CSRF + `StrictModel(extra="forbid")` ile açılır; **komut çalıştıran, kanıt kaydeden veya doğrudan `running`/`paused`'a geçiren rota yoktur** | on rota, elle yazılı küme ile birebir; `TaskUserTransitionName` `running`/`paused`/`ready_to_publish` taşımaz (422); yoldaki çalışma kimliği yoldaki göreve ait değilse 404; her okuma `no-store`; her durum değiştiren rota CSRF'siz 403; fazla anahtar 422 | `test_agent_http.py::test_the_router_serves_exactly_these_paths`, `::test_a_person_cannot_ask_for_the_runners_states_over_http`, `::test_a_run_belonging_to_another_task_is_not_acted_on`, `::test_every_read_is_no_store`, `::test_every_state_changing_route_requires_csrf`, `::test_every_request_model_forbids_extra_fields` | H2 |
| SI-299 | Migration `0009` **tek head**tir ve yalnız ekler; agent tablolarında secret biçimli (`key`/`token` dâhil) veya model-çıktısı biçimli sütun yoktur | on altı mevcut tablo yerinde, üç yeni tablo var; `seed`/`private`/`secret`/`mnemonic`/`passphrase`/`password`/`key`/`token` ve `reasoning`/`prompt`/`completion`/`payload` yok | `test_agent_boundary.py::test_migration_0009_changed_no_existing_table`, `::test_the_agent_tables_have_no_secret_shaped_columns`, `::test_no_agent_table_can_hold_a_model_reasoning_trace`, `::test_the_migration_chain_head_is_the_one_this_package_added`, `test_database.py::test_migration_chain_is_deterministic` | H2 |

### Mutasyon kaydı (SI-285, SI-289, SI-292, SI-296, SI-297)

Her satır fiilen çalıştırıldı; "kırmızıya döner" bir tahmin değil, ölçüm.

| Mutasyon | Sonuç |
|---|---|
| `agent/` içine `import subprocess`, `runner = exec` ve `os.system(...)` ekli bir dosya kondu | **2 iddia kırmızı**: import taraması ve ad/öznitelik taraması, dosya adı ve satır numarasıyla |
| Registry'ye `git_commit` adlı bir kayıt eklendi | **1 test kırmızı**: import zamanı güven sınırı denetimi `tool_outside_trust_boundary` ile reddediyor |
| `CEILING`'e dört ayrı yazımla (atama, öznitelik, artırmalı, `setattr`) yazan bir dosya kondu | **4 offender**: tarama dördünü de görüyor |
| `agent_run.test_condition` satırı veritabanında doğrudan düzenlendi | **1 test kırmızı**: `start_run` `plan_changed` ile reddediyor, faz `planned` kalıyor |
| `agent_run_step.arguments_json` satırı doğrudan düzenlendi | **1 test kırmızı**: adım `refused`, dosya üretilmiyor, görev `blocked` |
| Bir aracın çağrısı sırasında durdurma bayrağı kaldırıldı | **1 test kırmızı**: adım `skipped`, üretilen dosya kaldırılmış, çalışma alanı boş |
| `activity_module.assert_no_forbidden_claim` no-op yapıldı | **1 test kırmızı**: yasak ifade taşıyan satır artık **saklanıyor** (mutasyonsuz hâlde reddediliyor) |
| `RUN_HONESTY_SENTENCE` yasak bir cümleyle değiştirildi + iki modülün guard'ı no-op yapıldı | **1 test kırmızı**: guard varken çalışma reddediliyor, guard yokken aynı cümle olay satırına yazılıyor |
| `_clean` içinde denetimden **önce** nötrleme yapıldı (ilk yazım) | **1 test kırmızı** — ve bu mutasyon kazara yazılmıştı: guard'ın no-op olduğu bu şekilde yakalandı ve nötrleme servis sınırına taşındı |

Yukarıdakiler suite'in **içinde** sürülen mutasyonlardır. Aşağıdakiler ürün
kaynağı fiilen düzenlenerek, testler koşularak ve dosya geri yüklenerek
ölçüldü; sayılar tahmin değil, koşu çıktısıdır.

| Kaynağa uygulanan mutasyon | Ölçülen sonuç |
|---|---|
| `ActivityLog.record` içindeki `assert_no_forbidden_claim` çağrısı silindi | **3 test kırmızı**: `test_agent_language.py::test_turning_the_guard_into_a_no_op_lets_an_over_claim_be_stored`, `::test_the_guard_is_wired_into_the_runner_and_not_only_defined`, `test_agent_activity.py::test_a_forbidden_claim_in_our_own_wording_fails_closed` |
| `workspace.read_text` içindeki `_assert_no_reparse_point` çağrısı silindi | **2 test kırmızı**: `test_a_link_inside_the_workspace_is_refused`, `test_a_link_above_the_file_is_refused_too` |
| `start_run` içindeki `_assert_plan_intact` çağrısı silindi | **1 test kırmızı**: `test_an_edited_plan_is_refused_rather_than_carried_out` — düzenlenen plan sessizce yürütülüyor |
| `safe_name` yeniden adlandırılan adı **reddetmek yerine kabul** etti | **17 test kırmızı**: on beş düşmanca adın tamamı, dizin adı reddi ve rota katmanındaki kapsam dışı çıktı adı |

---
## 9k. Paket H3 değişmezleri — kanıt çalışma alanı (uygulandı)

Kapsam kararları [`decisions/0009-paket-h3-kapsam-kararlari-2026-09-05.md`](decisions/0009-paket-h3-kapsam-kararlari-2026-09-05.md);
uygulama ayrıntısı [`proof-workspace.md`](proof-workspace.md).

### SI-213, SI-220, SI-225 ve SI-226 neden **güncellendi**, silinmedi

**SI-220** ("`public_share` temsil edilemez") artık doğru değildir ve
gerçek değiştiği için **cümle** düzeltildi, iddia zayıflatılmadı. Alan
doldurulabilir oldu, fakat yalnızca **arşivlenmiş bir gönderimin kanıt kaydı
kimliğiyle** (ADR-0009 §1). Bu tek bir kontrol değil, birbirinin yerine
geçmeyen üç kontroldür: yapıcı **şekli**, servis **satırın varlığını**,
`ProofService` de kaydın **kendi gönderim sonucunu** denetler. Değişmeyen iki
şey açıkça korundu: `PUBLICATION_FIELDS` **üçte** kaldı, ve alan
`ready_to_publish`'i **engellemez** — `test_public_share_does_not_block_a_finished_task`
gerekçesiyle birlikte durur, yalnız beklenen durum `not_implemented`'tan
`blocked`'a geçti. Bu test artık daha keskindir: eski hâli alan **inert**
olduğu için de geçebilirdi.

**SI-219**'un ikinci testi (`test_there_are_exactly_four_fields_and_three_decide_publication`)
`PUBLICATION_FIELDS == set(EvidenceField) - UNFILLABLE_FIELDS` iddiasını
taşıyordu. `UNFILLABLE_FIELDS` boşalınca bu "üç, dördün eksi hiçbiri" demek
olur — yani **yanlış** bir iddia — ve onu yeşile döndürmenin yolu
`public_share`'i `PUBLICATION_FIELDS`'e sokmaktı, yani ADR-0004 §4'ün
reddettiği düzenleme. İddia bu yüzden **elle yazılı bir oracle**'a çevrildi.

**SI-213 ve SI-226**'nın arkasındaki taramalar yine yeni pakete
genişletilmedikçe **yeni paketi muaf tutacaktı** — bu, H2'de birebir yaşanan
şeydir ve ADR-0009 §5 onu merge şartı yaptı. `REGISTRY_SCANNED_DIRS`
(eski adıyla `PACKAGE_F_DIRS`) ve `STATE_WRITER_DIRS` `proof`'u kapsayacak
şekilde genişletildi; sabitin **adı da** içeriğiyle birlikte değişti, çünkü
H3 paketini listeleyen `PACKAGE_F_DIRS` adı kendi kapsamı hakkında yanlış
konuşan bir yorum olurdu.

**SI-225**'in bütçe taraması aynı sebeple `proof`'a genişletildi: bir kanıt
çalışma alanı, `estimated_cost` adlı bir alanın doğal görüneceği yerdir.

### Sessiz kalmayacak biçimde sürülen boş dallar

`UNFILLABLE_FIELDS` boşalınca **beş dal** hiç çalışmaz hâle gelir ve hiçbiri
kırmızı vermez: `tasks/gate.py`, `tasks/service.py`'nin satır okuyucusu,
`modules/completion.py`, `EvidenceRef.__post_init__` ve `tasks/views.py`'nin
`public_share_available` türetmesi. Bu, H2'nin `UNPRODUCIBLE_STATES`
tuzağının birebir tekrarıdır ve aynı çözümü aldı: mekanizma, **gerçekten
doldurulabilir bir alan** test süresince kapatılarak sürülür — ve kapatmadan
**önce** aynı yolun izinli olduğu denetlenir, yoksa "her şeyi reddeden" bir
fonksiyon da geçerdi.

Beşincisi H3 boyunca **sayılmıyordu**. Bir düşman inceleme
`tasks/views.py`'nin türetmesini sabit bir `True`'ya çevirip **sıfır** kırmızı
ölçtü: "tel ile kural ayrışamaz" diyen iki test de sabit bir literal'e karşı
geçiyordu — `public_share_available is True` ile `PUBLIC_SHARE not in
UNFILLABLE_FIELDS` ikisi de tek başına doğrudur, aralarında bağ yoktur. İlk
dördü refüze eden dallar, beşincisi onların **raporu**; kuraldan ayrışan bir
rapor kullanıcıya kapalı bir alanı açık diye söyler, ki bu
`arbitrary_execution_supported` hatasının yeni yerde tekrarıdır. Kapalı alan
artık `public_share` seçilerek — bugün gerçekten doldurulabilir olan alan —
sürülüyor ve mutasyon **1 kırmızı** veriyor.

Aynı şekilde `proof_workspace` **son `PLANNED` kayıttı**: açılınca
`test_planned_modules_name_the_package_that_opens_them`'in üç `assert`'i
sessizce ölürdü. Test ikiye ayrıldı — sözleşme bir fonksiyona çıkarıldı ve
testte kurulan kayıtlarla (geçerli bir `planned` kayıt dâhil, yoksa "hepsini
reddeden" bir denetleyici de geçerdi) **sürülür**; ayrıca "artık planlanan
modül yok" kendi adlandırılmış iddiası oldu. `test_work_scan_candidates.py`'nin
planlı-modül testi de aynı disiplinle yeniden yazıldı: kaydı test süresince
`PLANNED` yapıyor ve önce açık hâlini okuyor.

### Yeni değişmezler

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-300 | `public_share` **yalnız arşivlenmiş bir gönderimin kanıt kaydı kimliğiyle** doldurulabilir ve alan yayımı hâlâ engellemez. Dört katman vardır ve **ürün yolunda hepsi ateşlenmez**: HTTP'de `min_length=32`, sonra fiilen reddeden `EvidenceService.get` — kaydın `write_outcome` değeri `verified`'ın girdisi olduğu için satır her şeyden önce okunur — ardından `ProofService`'i **atlayan** çağıranlar için iki derinlik savunması: `record_evidence`'ın satır-varlık denetimi ve `EvidenceRef`'in şekil denetimi. İkisi de **kendi seviyelerinde** ayrıca sürülür | elle yazılan dize, büyük harfli/kısaltılmış/uzatılmış kimlik yapıcıda `EvidenceFieldError`; şekli doğru fakat satırı olmayan kimlik `record_evidence`'ta `evidence_record_missing`; `ProofService` üzerinden uydurulmuş bir kimlik ile elle yazılmış bir dize **aynı** gerekçeyi (`evidence_record_missing`) alır, çünkü orada kapı arşiv okumasıdır; gerçek satır kabul edilir ve kapıda `passed`; `outcome_unknown` dönmüş gönderim **kaydedilir fakat `verified` değildir**; `PUBLICATION_FIELDS` üçtür ve `public_share` `ready_to_publish`'i engellemez | `test_task_evidence.py::test_a_public_share_reference_needs_an_evidence_record_identity`, `::test_the_service_refuses_a_public_share_pointer_with_no_row_behind_it`, `::test_a_public_share_pointing_at_a_real_archived_send_is_accepted`, `::test_public_share_is_blocked_until_an_archived_send_is_recorded`, `::test_public_share_does_not_block_a_finished_task`, `test_proof_bundle.py::test_a_send_whose_outcome_is_unknown_is_recorded_but_not_verified`, `::test_a_public_share_does_not_make_a_task_ready_to_publish`, `::test_a_public_share_pointer_that_names_no_send_is_refused`, `::test_the_two_shadowed_public_share_refusals_are_driven_where_they_fire` | H3 |
| SI-301 | `UNFILLABLE_FIELDS` boşaldı fakat onu okuyan **beş dal** sessiz bırakılmadı: mekanizma, geçici olarak kapatılmış gerçek bir alanla **sürülür** ve kapatmadan önce aynı yolun izinli olduğu denetlenir | beş dal ayrı ayrı: kapı `not_implemented` verir ve `ready_to_publish` düşer; satır okuyucu kapalı alanın sütunlarını atlar; modül gereksinimi `not_implemented` sayılır; yapıcı reddeder ve diğer alanlar **etkilenmez**; servis `evidence_field_refused` döner; **görev görünümü `public_share_available: false` döner** ve gerekçe cümlesi yerinde kalır. Küme `EXPECTED_UNFILLABLE` oracle'ına karşı ayrıca denetlenir | `test_task_evidence.py::test_the_gate_still_reports_a_closed_field_as_not_implemented`, `::test_the_row_reader_still_skips_a_closed_fields_columns`, `::test_a_requirement_bound_to_a_closed_field_is_never_counted_as_passed`, `::test_a_reference_for_a_closed_field_cannot_be_constructed`, `::test_the_service_refuses_to_record_a_closed_field`, `::test_the_task_status_view_still_reports_a_closed_field_as_unavailable`, `::test_there_are_exactly_four_fields_and_three_decide_publication` | H3 |
| SI-302 | Registry'de **planlanan modül kalmadı** ve planlı-modül sözleşmesi buna rağmen **sürülür**; bir kayıt sözleşmeyi bozarsa yakalanır | `MODULES` içinde `PLANNED` kayıt yok, hepsi `available_from == ""` ve hepsinin sahibi ve gereksinimi var; sözleşme fonksiyonu geçerli bir `planned` kaydı **kabul eder** ve dört bozuk şekli (açan paket adı yok, kod sahibi var, gereksinimi var, available olduğu hâlde açan paket adı taşıyor) **reddeder** | `test_module_registry.py::test_no_module_is_registered_as_planned_any_more`, `::test_the_registry_satisfies_the_planned_module_contract`, `::test_the_planned_module_contract_would_catch_a_record_that_breaks_it`, `test_work_scan_candidates.py::test_a_planned_module_produces_a_capability_that_says_the_code_is_absent` | H3 |
| SI-303 | Kanıt paketi **hiçbir yola yazılmaz**: iki biçim, `Content-Disposition`, yeni dosya kökü yok, **zip yok** ve pakette dosya yazan/bağlantı kuran hiçbir fiil yok | `proof/` ve `routes/proof.py` ağacında `zipfile`/`tarfile`/`shutil`/`gzip`/`zlib` importu ve `symlink`/`write_text`/`mkdir`/`open` adı **yok**, hepsi ekili çağrılarla sürülmüştür; arşiv/bağlantı biçimli **isim** taşıyan fonksiyon veya sınıf yok; paket kurulup iki biçimi üretilip teslim edildikten sonra çalışma alanı dizini **bayt bayt aynı** | `test_proof_boundary.py::test_no_archive_is_produced_or_unpacked`, `::test_the_package_writes_no_file_and_creates_no_link`, `::test_the_module_has_no_archive_or_link_creating_helper`, `::test_the_name_scans_would_catch_a_planted_call`, `test_proof_bundle.py::test_nothing_is_written_to_the_workspace_when_a_bundle_is_built` | H3 |
| SI-304 | Paket **deterministiktir** ve kopyanın ne zaman alındığı gövdeye **girmez**; kümenin özeti çalışmanın kaydettiği **aynı sayıdır** | aynı görev iki kez paketlenince iki biçim de bayt bayt aynı; belgede `prepared_at`/`built_at`/`exported_at`/`generated_at` anahtarı yok, an `X-Station-Delivered-At` başlığında; `artifact_set_sha256` `AgentService._artifact_set_digest` ile birebir eşit; JSON `loads_strict` ile geri okunur | `test_proof_bundle.py::test_two_exports_of_an_unchanged_bundle_are_byte_identical`, `::test_no_document_carries_the_moment_the_copy_was_made`, `::test_the_artifact_set_digest_is_the_same_number_the_run_recorded`, `::test_the_json_document_is_canonical_and_re_readable`, `::test_the_markdown_document_carries_the_digests_it_summarises` | H3 |
| SI-305 | Dış paylaşım **tek kullanımlık** bir onay ister; onay **paket digest'ine**, göreve, içerik sürümüne ve oturuma bağlıdır ve **her sonuçta** harcanır | ikinci kullanım `approval_invalid`; başka oturum `approval_foreign_session`; başka görev `approval_foreign_task`; artifact değişince `bundle_changed`; **reddedilen** teslim de token'ı harcar (ikinci deneme `approval_invalid`); TTL dolunca `approval_invalid`; oturum kapanınca yalnız o oturumun onayları düşer; TTL sabiti **180'e sabitlenmiştir**; onaylama **tek katta** uygulanır — `ProofShareRequest.acknowledged` `Literal[True]` ve varsayılansızdır — ve annotation'ın kendisi sabitlenmiştir; handler'daki erişilemez ikinci denetim kaldırıldı | `test_proof_bundle.py::test_a_share_approval_is_spent_exactly_once`, `::test_an_approval_from_another_session_is_refused`, `::test_an_approval_for_another_task_is_refused`, `::test_an_approval_falls_when_the_artifact_set_changes`, `::test_a_refused_delivery_still_spends_the_approval`, `::test_an_expired_approval_is_refused`, `::test_ending_a_session_discards_its_pending_approvals`, `::test_the_share_approval_ttl_is_the_documented_three_minutes`, `test_proof_http.py::test_a_share_token_is_spent_once_over_http`, `::test_a_share_without_the_acknowledgement_never_reaches_a_handler`, `::test_the_acknowledgement_is_enforced_by_the_annotation_and_only_there` | H3 |
| SI-306 | "Bağımsız kontrol" ve "gerçek exit code" **`not_implemented` kalır ve gerekçesini söyler**; ölçüt ve yeniden üretme talimatı **metin olarak** paketlenir, sayı uydurulmaz | `claims.independent_check`, `claims.exit_code` ve `claims.test_result` üçü de `not_implemented` ve üçünün de cümlesi var; gerekçeler model yolunun ve keyfi yürütmenin kapalı olduğunu **adıyla** söyler; planın `test_condition`'ı belgede fakat yanında `test_result_state` de var; tamamlanmış bir çalışmadan sonra bile görev `ready_to_publish` değil ve `evidence.test_result` eksikler listesinde | `test_proof_bundle.py::test_the_independent_check_and_the_exit_code_stay_not_implemented`, `::test_the_success_criterion_is_packaged_as_text_and_never_as_a_result`, `::test_a_finished_run_still_leaves_the_task_short_of_ready_to_publish`, `test_proof_http.py::test_the_two_unproduced_claims_are_reported_with_their_reasons` | H3 |
| SI-307 | Eksikler **adıyla** listelenir; hiçbir yerde skor, yüzde veya tek rozet yoktur | eksik anahtarları `evidence.*`, `requirement.*`, `run.*` ve `artifact.*` ön ekleriyle ayrı ayrı üretilir ve her birinin cümlesi vardır; söz verilip üretilmeyen çıktı adıyla görünür; JSON gövdesinde `score`/`percent`/`completeness`/`grade`/`rating`/`badge` **geçmez** | `test_proof_bundle.py::test_every_gap_is_named_rather_than_counted`, `::test_a_promised_artifact_that_is_gone_is_named_in_the_bundle`, `test_proof_http.py::test_the_read_names_every_gap_and_states_what_a_digest_proves`, `::test_the_response_carries_no_score_and_no_single_badge` | H3 |
| SI-308 | `user_acceptance` **yalnız insan eyleminden** doğar, **görülen paketin özetine** bağlanır ve **hiçbir durumu taşımaz** | tamamlanmış bir çalışmadan sonra alan hâlâ `blocked`; kabul rotası alanı `passed` yapar ve `ref_id` paket özetidir; kabul öncesi ve sonrası görev durumu **aynıdır**; paket o arada değiştiyse `bundle_changed`; `TaskUserTransitionName` `ready_to_publish` taşımaz (SI-222 korunur) | `test_proof_bundle.py::test_an_acceptance_records_the_field_and_moves_no_state`, `::test_an_acceptance_for_a_bundle_that_has_since_changed_is_refused`, `::test_no_automatic_path_fills_user_acceptance`, `test_proof_http.py::test_an_acceptance_records_the_field_and_leaves_the_state_alone`, `::test_an_acceptance_for_a_stale_bundle_is_a_conflict` | H3 |
| SI-309 | Yasak ifade denetimi **H3 metinlerini kapsar**: paketteki ve rota dosyasındaki **her string literal** taranır, kural çalışma zamanında uygulanır ve **mutasyonla** doğrulanmıştır; hash'in ne kanıtladığı cümlesi kendi guard'ından geçer | E'nin altı, H1'in yedi ve H2'nin yedi ifadesi devralınır, H3 yedi ekler; katlama yeniden kullanılır ve test yazımları bağımsız üretir; kullanıcı metni **nötrlenir**, hiçbir paketi reddettirmez; nötrleme `safe_text` içinde guard'dan **önce** yapılır ve `safe_text` guard'ı **çağırmaz**; süpürme nötrlemenin **içinde ve öncesinde** yapılır — `fold` görünmez karakteri **siler**, `sweep_untrusted` onu **boşlukla değiştirir**, bu yüzden iki kelimenin arasına konan bir U+200B ham metinde nötrleyiciye görünmez ve süpürmeden sonra birebir yasak ifade hâline gelir; sıra ters çevrilince kullanıcının kendi notu yakalanmayan bir 500'e döner; guard'ı kapatınca paket yasak cümleyi taşır, nötrlemeyi kapatınca kullanıcının kendi kelimeleri ürünü konuşmaz hâle getirir | `test_proof_language.py::test_no_string_literal_in_the_proof_package_carries_a_forbidden_phrase`, `::test_the_route_layer_is_scanned_too`, `::test_the_static_scan_is_actually_scanning_something`, `::test_a_phrase_is_caught_in_every_spelling`, `::test_the_permitted_wording_passes_its_own_guard`, `::test_user_text_carrying_a_forbidden_phrase_is_neutralised_not_refused`, `::test_turning_the_guard_into_a_no_op_lets_a_bundle_carry_an_over_claim`, `::test_turning_the_neutraliser_off_lets_a_users_words_refuse_the_product`, `::test_the_guard_is_wired_into_the_package_and_not_only_defined`, `::test_the_neutralising_step_runs_before_the_guard_and_not_after`, `::test_a_zero_width_character_cannot_smuggle_a_phrase_into_our_sentence`, `::test_the_sweep_happens_inside_the_neutralise_call_and_not_around_it` | H3 |
| SI-310 | Yeni `proof/` paketi **her sınır taramasının içindedir**: giden yüzey, kasa/signer, ikinci gate, yürütme, arşiv, bağlantı, zamanlayıcı, durum yazıcısı, bütçe alanı ve dinamik yükleme | `OUTBOUND_CLIENT_MODULES` **beşte** kalır ve pakette HTTP istemcisi/`socket`/`ssl` importu yok; `station_api.vault`/`compose`/`recovery`/`seed_import`/`opencode.credential_store` importu yok ve **muafiyet de yok**; `CheckState`/`WriteGateStatus`/`TaskGateStatus` yeniden tanımlanmaz; `STATE_WRITER_DIRS`, `BUDGET_SCANNED_DIRS` ve `REGISTRY_SCANNED_DIRS` `proof`'u kapsar ve üçü de **ekili ihlalle** sürülmüştür; taramaların gerçekten `proof/` dosyalarını açtığı ayrıca ölçülür | `test_proof_boundary.py::test_the_proof_package_has_no_outbound_surface`, `::test_the_proof_package_reaches_no_signer_vault_or_credential`, `::test_the_proof_package_declares_no_second_gate`, `::test_the_import_scans_would_catch_a_planted_import`, `::test_the_boundary_scan_opens_the_package_and_its_route`, `test_task_states.py::test_the_state_write_scan_reaches_the_proof_package`, `test_task_evidence.py::test_the_budget_scan_reaches_the_proof_package_and_would_fire_there`, `test_module_registry.py::test_the_registry_scans_reach_the_proof_package` | H3 |
| SI-311 | Proof rotaları `no-store` + CSRF + `StrictModel(extra="forbid")` ile açılır; **yol/dizin parametresi, adres alanı ve gönderim yapan rota yoktur** ve H3 **yeni tablo eklemez** | beş rota, elle yazılı kümeyle birebir; hiçbir proof yolu `say`/`note`/`exec`/`shell`/`file`/`path`/`download` içermez; her okuma `no-store`, her durum değiştiren rota CSRF'siz 403, fazla anahtar 422; `public-share` gövdesi yalnız kanıt kaydı kimliği ve not alır — `room`/`url`/`text`/`did`/`host` **422**; migration head hâlâ `0009` | `test_proof_http.py::test_the_router_serves_exactly_these_paths`, `::test_no_proof_route_names_a_write_lane_a_path_or_a_command`, `::test_every_proof_read_is_no_store`, `::test_every_state_changing_route_requires_csrf`, `::test_every_request_model_forbids_extra_fields`, `::test_a_public_share_body_carries_no_address_and_no_text`, `test_proof_boundary.py::test_no_new_migration_was_added_by_this_package` | H3 |
| SI-312 | Tek kullanımlık token deposu **sınırsız büyümez**: her `issue` önce süresi dolanları temizler, sonra `MAX_PENDING_TOKENS` tavanını uygular ve tavana varılmışsa **en eskisini** düşürür | 50 hazırlık → 50 bekleyen; saat TTL'i geçtikten sonra 5 hazırlık daha → **5** (55 değil); tavanı 4 olan bir depoda 10 hazırlık → 4 bekleyen ve **en yenisi** hâlâ harcanabilir, en eskisi değil; uygulamanın kurduğu varsayılan deponun tavanı `MAX_PENDING_TOKENS`'tır | `test_proof_bundle.py::test_abandoned_share_approvals_stop_occupying_memory`, `::test_the_share_approval_store_has_a_ceiling_and_the_shipped_one_uses_it` | H3 |
| SI-313 | Çalışma alanında bir **reparse point** bulunması kanıt okumasını 500'e değil, **söylenmiş bir redde** çevirir; aynı ret çalışma listesi rotasında zaten vardı | `workspace/v1/<task_id>` üzerine kurulan **gerçek** bir junction ile `GET /api/proof/{id}` **400** döner ve gövde çalışma alanı katmanının kendi cümlesini taşır; ne ekilen yol ne de karşı taraf gövdede geçer; reparse point yokken aynı okuma **200**'dür; `GET /api/tasks/{id}/runs` de 400 döner (`WorkspaceError` bir `AgentError`'dır); junction kurulamayan makinede predikat aynı gerçek yolda zorlanır, **skip yok** | `test_proof_http.py::test_a_reparse_point_in_the_workspace_is_a_stated_refusal_not_a_500` | H3 |

### Mutasyon kaydı (SI-300, SI-301, SI-302, SI-303, SI-305, SI-309, SI-310)

Her satır **ürün kaynağı fiilen düzenlenerek, tam suite koşularak ve dosya
geri yüklenerek** ölçüldü. Sayılar tahmin değil, koşu çıktısıdır; tam liste
[`verification/paket-h3.md`](verification/paket-h3.md)'dedir.

| Kaynağa uygulanan mutasyon | Ölçülen sonuç |
|---|---|
| `EvidenceRef.__post_init__`'in **kanıt kaydı kimliği şekli** kontrolü kapatıldı | **3 kırmızı**: `test_a_public_share_reference_needs_an_evidence_record_identity`, `::test_the_service_refuses_a_public_share_pointer_with_no_row_behind_it`, `::test_a_public_share_row_written_directly_is_passed_by` — üçüncüsü, elle düzenlenmiş bir satırın artık yakalanmamış bir hataya dönüştüğünü gösteriyor |
| `record_evidence`'ın **satır varlığı** kontrolü kapatıldı | **1 kırmızı**: `::test_the_service_refuses_a_public_share_pointer_with_no_row_behind_it` — şekli doğru, uydurulmuş kimlik geçiyor |
| `tasks/gate.py`'nin `UNFILLABLE_FIELDS` dalı kapatıldı | **1 kırmızı**: `::test_the_gate_still_reports_a_closed_field_as_not_implemented` |
| `tasks/service.py`'nin `UNFILLABLE_FIELDS` atlaması kapatıldı | **1 kırmızı**: `::test_the_row_reader_still_skips_a_closed_fields_columns` |
| `modules/completion.py`'nin `UNFILLABLE_FIELDS` dalı kapatıldı | **1 kırmızı**: `::test_a_requirement_bound_to_a_closed_field_is_never_counted_as_passed` |
| `EvidenceRef.__post_init__`'in `UNFILLABLE_FIELDS` reddi kapatıldı | **2 kırmızı**: `::test_a_reference_for_a_closed_field_cannot_be_constructed`, `::test_the_service_refuses_to_record_a_closed_field` |
| `build_document`'ın `assert_product_language` çağrısı silindi | **1 kırmızı**: `test_proof_language.py::test_turning_the_guard_into_a_no_op_lets_a_bundle_carry_an_over_claim` |
| `safe_text`'in `neutralise` adımı silindi | **2 kırmızı**: `::test_the_neutralising_step_runs_before_the_guard_and_not_after`, `::test_turning_the_neutraliser_off_lets_a_users_words_refuse_the_product` |
| `deliver_share`'in **paket digest'i** karşılaştırması kapatıldı | **2 kırmızı**: `test_proof_bundle.py::test_an_approval_falls_when_the_artifact_set_changes`, `::test_a_refused_delivery_still_spends_the_approval` |
| `record_acceptance`'ın **paket digest'i** karşılaştırması kapatıldı | **2 kırmızı**: `::test_an_acceptance_for_a_bundle_that_has_since_changed_is_refused`, `test_proof_http.py::test_an_acceptance_for_a_stale_bundle_is_a_conflict` |
| `record_public_share` `verified=True`'yu **koşulsuz** yazdı | **1 kırmızı**: `::test_a_send_whose_outcome_is_unknown_is_recorded_but_not_verified` |
| `proof_workspace` kaydı `PLANNED`'a geri alındı | **3 kırmızı**: `test_module_registry.py::test_no_module_is_registered_as_planned_any_more`, `::test_the_registry_satisfies_the_planned_module_contract`, `test_work_scan_candidates.py::test_a_planned_module_produces_a_capability_that_says_the_code_is_absent` |
| `launcher.py` veritabanını eski aşamada (`stage=8`) açtı | **1 kırmızı**: `test_module_registry.py::test_every_entry_point_names_the_same_release_stage` |
| `tasks/views.py`'nin `public_share_available` türetmesi sabit `True` yapıldı | **1 kırmızı**: `test_task_evidence.py::test_the_task_status_view_still_reports_a_closed_field_as_unavailable` — düzeltmeden önce **0 kırmızıydı** |
| `safe_text`'in sırası `sweep_untrusted(neutralise(v))` olarak ters çevrildi | **2 kırmızı**: `test_proof_language.py::test_a_zero_width_character_cannot_smuggle_a_phrase_into_our_sentence`, `::test_the_sweep_happens_inside_the_neutralise_call_and_not_around_it` — düzeltmeden önce **0 kırmızıydı** |
| `ProofShareRequest.acknowledged` `Literal[True]` → `bool` | **2 kırmızı**: `test_proof_http.py::test_a_share_without_the_acknowledgement_never_reaches_a_handler`, `::test_the_acknowledgement_is_enforced_by_the_annotation_and_only_there` |
| `ProofShareRequest.acknowledged`'a `= True` varsayılanı eklendi | **2 kırmızı**: aynı iki test |
| `SHARE_TOKEN_TTL_SECONDS` 180 → 86400 | **1 kırmızı**: `test_proof_bundle.py::test_the_share_approval_ttl_is_the_documented_three_minutes` — düzeltmeden önce **0 kırmızıydı** |
| `SingleUseStore.issue`'nun **süresi dolanı temizleme** adımı silindi | **1 kırmızı**: `::test_abandoned_share_approvals_stop_occupying_memory` |
| `SingleUseStore.issue`'nun **kapasite tavanı** silindi | **1 kırmızı**: `::test_the_share_approval_store_has_a_ceiling_and_the_shipped_one_uses_it` |
| `ProofService.build`'in `AgentError` → `ProofError` çevirisi silindi | **1 kırmızı**: `test_proof_http.py::test_a_reparse_point_in_the_workspace_is_a_stated_refusal_not_a_500` — yakalanmayan `WorkspaceError`, yani 500 |

Ekili ihlaller — hepsi `station_api/proof/` içine konan tek bir dosyayla,
ölçüldükten sonra silindi. Üçünde `test_tracked_sources.py`'nin iki testi de
kırmızıya dönüyor, çünkü ekilen dosya git'te yok; bu **beklenen** ve o
kontrolün de çalıştığının ayrı bir kanıtı — aşağıdaki sayılar onları da
içeriyor.

| Ekilen ihlal | Ölçülen sonuç |
|---|---|
| `proof/` içine `row.state = 'ready_to_publish'` yazan bir metot | **3 kırmızı**: `test_task_states.py::test_only_the_transition_method_writes_a_task_state` + iki `test_tracked_sources` |
| `proof/` içine `estimated_budget = 10` | **3 kırmızı**: `test_task_evidence.py::test_the_task_layer_opens_no_budget_field` + iki `test_tracked_sources` |
| `proof/` içine `import httpx`, `import subprocess` ve `from station_api.vault.service import ...` | **9 kırmızı**: `test_proof_boundary.py`'nin dört testi (giden yüzey, secret sınırı, yürütme, ve "gerçek import'lar rahat bırakılıyor" muafiyeti), `test_module_registry.py`'nin iki registry taraması, `test_write_gate.py::test_httpx_is_imported_only_by_the_reviewed_clients` ve iki `test_tracked_sources` |
| `proof/` içine yasak ifade taşıyan bir string literal | **3 kırmızı**: `test_proof_language.py::test_no_string_literal_in_the_proof_package_carries_a_forbidden_phrase` + iki `test_tracked_sources` |

**Yirmi üç mutasyonun yirmi üçü en az bir testi öldürdü.** Sıfır öldüren
guard yok.

Son yedisi H3 birleştirildikten **sonra** yapılan bağımsız bir düşman
incelemenin bulgularıdır: üçü (`tasks/views.py`'nin türetmesi, `safe_text`'in
sırası, `SHARE_TOKEN_TTL_SECONDS`) o inceleme sırasında **sıfır** kırmızı
veriyordu, ve o üç satır bu tablonun neden mutasyonla yazıldığının kendi
kanıtıdır: bir guard'ın var olması, onun ölçülmüş olması demek değildir.


---

## 9l. Paket I değişmezleri — Windows paketleme (uygulandı)

Kapsam kararları [`decisions/0010-paket-i-kapsam-kararlari-2026-09-05.md`](decisions/0010-paket-i-kapsam-kararlari-2026-09-05.md);
uygulama ayrıntısı [`packaging.md`](packaging.md).

### SI-02 ve SI-232 neden **güncellendi**, silinmedi

**SI-02** ("bind adresi asla `0.0.0.0` değildir") doğruydu ama **kapsamı**
dardı: taraması yalnız `apps/station-api/src` altındaki `.py` dosyalarını
okuyordu. Paket I bu depoya `.spec` uzantılı ilk dosyayı getirdi, yani
kuralın kapsaması gereken dosya türü tam olarak bu pakette ortaya çıktı.
Tarama `packaging/` ağacına, on beş uzantıya ve `.github/workflows` altına
genişletildi; iddia zayıflatılmadı, **büyütüldü**.

**SI-232** (bir sürüm, bir aşama numarası) beş giriş noktasını
`CURRENT_SCHEMA_STAGE` ile denetlemeye devam ediyor; değer `9 → 10` olarak
atomik biçimde taşındı. `CURRENT_MIGRATION_HEAD` **`0009`'da kaldı**: Paket
I şemaya dokunmadı.

| ID | Değişmez | Beklenen | Test | Durum |
|---|---|---|---|---|
| SI-314 | Paketlenmiş bir çalıştırma **"Arayuz derlenmemis" 503'ünü üretemez**; ret iki bağımsız katmandadır | donmuş süreçte SPA'sı olmayan bir paket için `shipped_web_dist()` **`PackagedLayoutError`** yükseltir, ve `_mount_spa` açıkça verilen boş bir dizini de reddeder; aynı boş dizin **donmamış** bir çalışmada hâlâ 503 sayfasını ve `npm ... run build` komutunu verir | `test_packaging_boundary.py::test_a_frozen_run_with_no_spa_refuses_instead_of_serving_the_no_build_page`, `::test_a_frozen_run_serves_the_spa_the_bundle_carries`, `::test_a_development_checkout_still_gets_the_no_build_page` | I |
| SI-315 | Ürün yolları **`__file__` dizin sayımıyla** değil, `importlib.resources` ve donmuş dalda `sys._MEIPASS` ile çözülür | `app.py` ve `db/migrations_runner.py` içinde `Path(__file__)` **geçmez**; donmuş bir çalışmada migration ağacı `sys._MEIPASS/station_api/db/migrations`'tır ve Alembic `script_location`'ı odur; ağaç yoksa `PackagedLayoutError` | `test_packaging_boundary.py::test_the_resolver_no_longer_counts_directories_from_dunder_file`, `::test_a_frozen_run_finds_the_migration_tree_in_the_bundle`, `::test_a_frozen_run_with_no_migration_tree_refuses_in_words` | I |
| SI-316 | Arayüzün yeri **ortam değişkeninden okunmaz** (`LOOPBACK_HOST` ile aynı gerekçe: CSP `'self'` altında keyfi JS servis etmenin yolu) | `resources.py` içinde `os.environ`, `getenv` ve `import os` **yok**; `STATION_WEB_DIST`/`STATION_DIST`/`STATION_SPA_DIR` ayarlandığında çözülen yol **değişmez** | `test_packaging_boundary.py::test_no_path_in_the_resolver_is_read_from_the_environment` | I |
| SI-317 | `0.0.0.0` taraması **paketleme ağacını ve CI workflow'larını** kapsar | tarama `SCANNED_TREES`'in **beş** ağacının her birinden dosya açar ve bu **listeden okunarak** denetlenir; ayrıca yürütme taramasının açtığı her `.py`'yi ve diskteki her workflow dosyasını açtığı, **listeden değil depodan türetilen** bir beklentiyle ölçülür (bağımsız inceleme: elle sayılmış iki ağaç sabitleniyordu ve diğer ikisi listeden düşürüldüğünde **sıfır kırmızı** çıkıyordu); ekili bir ihlal `.spec`, `.ps1`, `.bat`, `.iss` ve `.yml` uzantılarının **her birinde** ayrı ayrı raporlanır | `test_bind.py::test_no_wildcard_bind_in_source`, `::test_the_wildcard_scan_opens_every_tree_it_claims_to_open`, `::test_the_wildcard_scan_covers_everything_the_execution_scan_covers`, `::test_the_wildcard_scan_reports_a_planted_violation` | I |
| SI-318 | `subprocess`/`exec`/`eval`/`os.system` yasağı **ürün geneline** uygulanır; iki modül yalnız **`ctypes` sembolünden** muaftır, dosyadan değil | taramanın kapsamı **depodan türetilerek** denetlenir: `tests/` ve `vendor/` dışındaki **her** `.py` taramanın içindedir ve bu iki istisnanın gerekçesi yazılıdır; ayrıca listedeki dört ağacın her birinin fiilen katkı verdiği ölçülür. Muafiyet **sembol bazlıdır**: `dpapi.py` ve `windows_acl.py` yalnızca `ctypes`'ı kaybeder, `EXECUTION_IMPORTS`'un geri kalanı onlarda da uygulanır. Ekili `subprocess`/`multiprocessing`/`ctypes`/`runpy` import'u ve ekili `exec`/`eval`/`os.system`/`os.popen`/**`subprocess.Popen`**/**`check_output`**/**`os.startfile`**/**`os.execv`** çağrısı raporlanır; `dpapi.py` ve `windows_acl.py` gerçekten `ctypes` kullanır ve `CreateProcess`/`ShellExecute`/`WinExec` adlarını **taşımaz**; `importlib.resources` rahat bırakılır | `test_packaging_boundary.py::test_no_product_source_runs_a_program`, `::test_no_python_file_in_this_repository_escapes_the_execution_scan`, `::test_every_named_tree_actually_contributes_to_the_execution_scan`, `::test_the_ctypes_exemption_subtracts_one_symbol_and_not_the_whole_ban`, `::test_the_attribute_ban_names_the_process_starting_entry_points`, `::test_the_two_ctypes_modules_exist_and_start_no_process`, `::test_the_execution_import_scan_reports_a_planted_import`, `::test_the_execution_name_scan_reports_a_planted_call`, `::test_the_execution_scan_leaves_the_products_real_imports_alone` | I |
| SI-319 | Gönderilen SPA, denetlenen `dist` ile **bayt-birebir** aynıdır | spec'in kopyaladığı kaynak `apps/station-web/dist`, hedefi `BUNDLED_WEB_DIR`'dir; paket üretilmişse ağaçların dosya-başına SHA-256 haritaları **eşittir**; paket varken SPA'sı beklenen yerde değilse test **kırmızıdır**; karşılaştırma tek baytlık farkta **hangi dosya** olduğunu adıyla raporlar | `test_frontend_bundle.py::test_the_packaging_spec_ships_the_audited_dist_and_nothing_else`, `::test_the_shipped_spa_is_byte_for_byte_the_audited_dist`, `::test_the_byte_identity_comparison_reports_a_single_changed_byte` | I |
| SI-320 | Paket **`onedir`**'dir ve `%TEMP%`'e açılmaz; **konsol görünür kalır** | spec `COLLECT` ile biter ve `exclude_binaries=True` taşır; yorum satırları çıkarıldığında spec kodunda `onefile` ve `TEMP` **geçmez**; `console=True`'dur, `console=False`/`noconsole`/`--windowed` yoktur; `codesign_identity=None`'dır | `test_packaging_boundary.py::test_the_spec_is_onedir_and_not_onefile`, `::test_the_spec_keeps_the_console`, `::test_the_spec_names_no_signing_identity`, `::test_the_spec_carries_the_migration_tree_and_the_pinned_vectors`, `::test_the_spec_excludes_the_test_only_signature_library` | I |
| SI-321 | Bir veri dizinini aynı anda **tek** Station açar; ret bir cümledir ve **silinecek dosyayı adıyla** söyler | ilk kilit tutulurken ikinci `acquire` `AlreadyRunningError`; mesaj kilit dosyasının tam yolunu ve "sil" fiilini taşır; kilit **veri dizinindedir**, `%TEMP%`'te değil; iki farklı veri dizini birbirini engellemez; bırakma **idempotenttir**; kilit dosyası pid ve zaman damgası dışında hiçbir şey taşımaz; launcher kilidi **veritabanını açmadan önce** alır ve `finally` ile bırakır | `test_packaging_boundary.py::test_a_second_instance_is_refused_while_the_first_holds_the_lock`, `::test_the_refusal_names_the_file_to_delete`, `::test_releasing_the_lock_lets_the_next_start_succeed`, `::test_two_data_directories_do_not_block_each_other`, `::test_the_lock_file_carries_no_secret`, `::test_the_lock_lives_in_the_data_directory_and_not_in_temp`, `::test_releasing_twice_is_not_an_error`, `::test_the_launcher_claims_the_lock_before_it_opens_the_database`, `::test_the_launcher_releases_the_lock_when_the_server_stops` | I |
| SI-322 | **Satır taşıyan** eski bir şema yükselir ve satırlarını korur; **daha yeni** bir şemayı açan eski kod **anlaşılır biçimde** reddeder | `0007` şemasına yazılan kimlik, görev ve metadata satırları `0009`'a yükseltildikten sonra **değer değer** aynıdır ve revizyon `0009`'dur; tanınmayan bir revizyonla işaretli veritabanı `SchemaAheadError` alır, mesaj revizyonu adıyla ve verinin **değiştirilmediğini** söyler, damga **el değmemiş** kalır; boş ve bilinen revizyonlar yanlışlıkla "ileride" sayılmaz | `test_database.py::test_an_upgrade_from_an_older_release_keeps_the_rows_it_found`, `::test_a_database_from_a_newer_build_is_refused_in_words`, `::test_a_database_at_a_known_revision_is_not_mistaken_for_a_newer_one` | I |
| SI-323 | Yayımlanan artefakt özeti **düz SHA-256**'dır (kullanıcı `Get-FileHash` ile doğrulayabilir) ve yanında **imzasızlık cümlesi** vardır | `file_digest` değeri `hashlib.sha256(bayt)` ile birebir eşittir ve alan-ayrılmış digest'e **eşit değildir**; build betiği "yalnızca dosya bütünlüğünü tanımlar", "IMZASIZDIR" ve "kimin urettigini de kanitlamaz" cümlelerini taşır; SmartScreen **beklenen** olarak anılır ve **"kapatın" demez**; ikinci bir hash yardımcısı yoktur (`hashlib` build betiğinde geçmez) | `test_packaging_boundary.py::test_the_artefact_digest_is_the_plain_sha256_a_user_can_reproduce`, `::test_the_build_script_publishes_the_unsigned_sentence`, `::test_the_build_script_reuses_the_products_own_digest_module` | I |
| SI-324 | Build betiği **ön koşulunu dürüstçe raporlar** ve üretmediği bir artefaktı **üretti demez** | `--check` üç ön koşulu tek tek yazar ve çıkış kodu raporla **tutarlıdır** (hepsi OK → 0, biri EKSIK → 2); ön koşul eksikken build yolu çıkış kodu 2 ve `URETILMEDI` verir ve `packaging/artifacts` **oluşmaz** | `test_packaging_boundary.py::test_the_build_script_reports_every_precondition_and_agrees_with_its_exit_code`, `::test_the_build_script_never_claims_an_artefact_it_did_not_produce` | I |
| SI-325 | Paketleme ağacındaki kaynak dosyalar **git'in içindedir**; PyInstaller'ın varsayılan çıktı adları bir **muafiyet** üretmez | `SHIPPED_TREES` `packaging/`'i kapsar, `SOURCE_SUFFIXES` `.spec`/`.ps1`/`.bat`/`.cmd`/`.iss`/`.nsi`/`.wxs`/`.psm1` taşır ve ağacın `.py` dışında da katkı verdiği ölçülür; `packaging/dist/helper.py`, `packaging/build/helper.py` ve `packaging/out/helper.py` git tarafından **gerçekten yok sayılır** fakat tarama tarafından **muaf tutulmaz** — üçü de ayrı ayrı sürülür. Bağımsız inceleme `dist`'in bu listede kaldığını ölçtü: PyInstaller'ın **varsayılan distpath**'i tam olarak odur, yani muafiyetin en olası hâle geldiği ad. Muaf dizinler tam yolla yazılır — `packaging/artifacts` (build çıktısı) ve `apps/station-web/dist` (SPA yapısı) — ve build betiğinin yazdığı yerin `packaging/artifacts` olduğu ayrıca denetlenir; depo kökündeki `packaging/` dizini kurulu `packaging` dağıtımını **gölgelemez** | `test_tracked_sources.py::test_every_shipped_source_file_is_tracked_by_git`, `::test_the_packaging_tree_contributes_files_and_not_only_python`, `::test_a_source_file_in_a_pyinstaller_default_output_directory_is_not_exempt`, `::test_the_only_exempt_packaging_directory_is_where_the_build_script_writes`, `test_packaging_boundary.py::test_the_repository_packaging_directory_does_not_shadow_the_distribution` | I |
| SI-326 | Konsoldan yapılan **normal kapanış** — Ctrl+C **ve** Ctrl+Break — **çıkış kodu 0** verir, konsola çöküş metni basmaz ve tek örnek kilidini **bırakır** | `SHUTDOWN_SIGNALS` `SIGINT`, `SIGTERM` ve (Windows'ta) `SIGBREAK` taşır; `absorbing_shutdown_signals()` yalnız `uvicorn.Server.run` çevresinde kuruludur ve çıkışta bulduğu handler'ları **geri koyar**; uvicorn'un `capture_signals` davranışı birebir taklit edilerek sürülür — pencere içinde yeniden yükseltilen sinyal sürece ulaşmaz, pencere dışında **aynı** taklit `KeyboardInterrupt` üretir; gerçek bir çökme **hâlâ** yayılır ve kilit yine bırakılır; ana iş parçacığı dışında pencere sessizce no-op'tur | `test_packaging_boundary.py::test_the_absorbed_signal_set_covers_both_console_stop_keys`, `::test_a_re_raised_interrupt_inside_the_window_does_not_reach_the_process`, `::test_a_re_raised_break_inside_the_window_does_not_reach_the_process`, `::test_without_the_window_the_same_re_raise_is_a_keyboard_interrupt`, `::test_the_window_puts_back_the_handlers_it_found`, `::test_the_window_is_a_no_op_off_the_main_thread`, `::test_a_clean_stop_exits_zero_and_leaves_no_lock_behind`, `::test_a_break_stop_also_exits_zero_and_releases_the_lock`, `::test_a_real_crash_is_still_a_crash`, `::test_the_launcher_wraps_the_server_run_in_the_absorbing_window` | I |
| SI-327 | `0.0.0.0` taramasının açtığı dosya kümesi **build durumundan bağımsızdır**: tarama **kaynağı** okur, üretilmiş kopyayı değil | tek muafiyet `packaging/artifacts` **tam yoludur**, dizin adı değil, ve `build_bundle.py`'nin yazdığı yerle aynı olduğu denetlenir (`test_tracked_sources.py`'nin muafiyetiyle **tek tanım**); `build`, `dist` ve `out` artık **ada göre atlanmaz**, üçünde de ekili bir `0.0.0.0` raporlanır; sentetik bir ağaçta bundle kopyaları atlanır ve kaynak okunur, ve atlanan kopyaların gerçekten okunabilir uzantılar taşıdığı ayrıca ölçülür; gerçek depoda taramanın açtığı **hiçbir** dosya çıktı dizininin içinde değildir | `test_bind.py::test_the_scan_reads_the_packaging_sources_and_not_the_bundle_beside_them`, `::test_the_bundle_the_scan_skips_really_did_contain_readable_files`, `::test_a_wildcard_in_a_pyinstaller_default_output_directory_is_still_reported`, `::test_no_file_the_real_scan_opens_lives_in_the_build_output_directory`, `::test_the_exempt_directory_is_the_one_the_build_script_writes_to` | I |
| SI-328 | Tek örnek kilidi **başlatmanın tamamını** sarar: kilit alındıktan sonraki **hiçbir** hata onu geride bırakamaz | `lock = single_instance.acquire(...)`'dan hemen sonra açılan `try`, `initialise_database`, soket rezervi ve `create_app` çağrılarının **hepsini** içine alır ve `finally: lock.release()` ile kapanır; migration sırasındaki `KeyboardInterrupt`, soketin rezerve edilememesi ve `PackagedLayoutError` üçü de hatayı **kendisi olarak** yayar ve kilidi geride **bırakmaz**; `SchemaAheadError` dalı çıkış kodu 5 verir ve kilidi yine bırakır (elle `release()` çağrısı kaldırıldı, kaynakta `lock.release()` **bir kez** geçer) | `test_packaging_boundary.py::test_a_failure_during_start_up_does_not_strand_the_lock`, `::test_a_database_from_a_newer_build_still_releases_the_lock`, `::test_the_lock_release_covers_the_whole_start_up_and_not_only_the_server`, `::test_the_launcher_releases_the_lock_when_the_server_stops` | I |
| SI-329 | Gönderilen arşiv **üretildiği makineyi adlandırmaz** ve derlenmiş bytecode taşımaz; **hangi iğnenin hangi üyelere uygulandığı testin koştuğu makineye bağlı değildir** | ZIP'te hiçbir `__pycache__` girdisi ve hiçbir `.pyc` yoktur (**arşivin tamamı**); **depo yolu** iğnesi — bu çalışma kopyasının mutlak yolu, iki ayraç yazımında — **arşivin tamamına** uygulanır, çünkü başka bir makinede derlenmiş bir ikili onu taşıyamaz; **hesap adı ve ev dizini** iğneleri yalnız `station.spec`'in **bizim ağaçlarımızdan kopyaladığı** üyelere uygulanır ve bu kapsam spec'in `*_TARGET` atamalarından **AST ile türetilir**, ada göre yazılmış bir muafiyet listesinden değil; kapsamın ne boş ne hayalî olduğu ayrıca denetlenir (üç önek, her biri arşivde en az bir gerçek üyeyle eşleşir); `station.spec` iki Python ağacını dizin olarak değil **dosya dosya** kopyalar ve önbellekleri dışarıda bırakır; üçüncü taraf ikililerin **kendi** derleme makinelerinin yolunu taşıdığı sessizce muaf tutulmaz, **iddia edilir**: başka bir makinenin yolunu taşıyan her üye derlenmiş bir ikilidir ve **asla** spec'in kopyaladığı bir dosya değildir. Tarama üç yönde de ekili sızıntıda kırmızıdır — bizim ağacımızdaki bir üyede, arşivin herhangi bir yerindeki depo yolunda, ve `runneradmin` **düz metin** olduğu için her makinede aynı sonucu veren üçüncü taraf sürüşünde. Paketleme workflow'u bu testi **build'den sonra** koşar, çünkü bundle yokken karşılaştıracak bir şey yoktur | `test_packaging_boundary.py::test_the_shipped_archive_names_no_developer_and_no_home_directory`, `::test_the_leak_scan_reports_a_planted_path`, `::test_the_copied_scope_is_read_off_the_spec_and_finds_real_members`, `::test_a_leak_in_a_copied_member_is_reported`, `::test_a_third_party_binarys_upstream_build_path_is_not_our_leak`, `::test_the_repository_path_is_refused_anywhere_in_the_archive`, `::test_the_third_party_binaries_carry_their_own_build_machine` | I |

### Mutasyon kaydı (SI-314 … SI-325)

Her satır **kaynak fiilen düzenlenerek**, hedef test dosyaları koşularak ve
dosya geri yüklenerek ölçüldü. Taban: **0 kırmızı**; geri yükleme sonrası
yine **0 kırmızı**.

| Mutasyon | Ölçülen sonuç |
|---|---|
| `shipped_web_dist`'in donmuş dalındaki `raise` silindi | **1 kırmızı**: `test_a_frozen_run_with_no_spa_refuses_instead_of_serving_the_no_build_page` |
| `_mount_spa`'nın donmuş reddi silindi | **1 kırmızı**: aynı test — iki katman **ayrı ayrı** öldürüyor |
| `migrations_dir`'in donmuş dalındaki `raise` silindi | **1 kırmızı**: `test_a_frozen_run_with_no_migration_tree_refuses_in_words` |
| Yol çözümü `Path(__file__).resolve().parents[4]`'e geri alındı | **1 kırmızı**: `test_the_resolver_no_longer_counts_directories_from_dunder_file` |
| `run_migrations`'tan `guard_against_a_newer_schema` çağrısı silindi | **1 kırmızı**: `test_a_database_from_a_newer_build_is_refused_in_words` |
| Kilit oluşturmadan `O_EXCL` çıkarıldı | **2 kırmızı**: `test_a_second_instance_is_refused_while_the_first_holds_the_lock`, `test_the_refusal_names_the_file_to_delete` |
| Launcher kilidi **veritabanından sonra** aldı | **1 kırmızı**: `test_the_launcher_claims_the_lock_before_it_opens_the_database` |
| Launcher'ın `finally: lock.release()` bloğu silindi | **1 kırmızı**: `test_the_launcher_releases_the_lock_when_the_server_stops` |
| Spec'te `console=True` → `console=False` | **1 kırmızı**: `test_the_spec_keeps_the_console` |
| Spec'in SPA kaynağı `dist` dışına yöneltildi | **1 kırmızı**: `test_the_packaging_spec_ships_the_audited_dist_and_nothing_else` |
| Spec'ten `COLLECT` kaldırıldı (onefile) | **1 kırmızı**: `test_the_spec_is_onedir_and_not_onefile` |
| Spec'e `0.0.0.0` literali ekildi | **1 kırmızı**: `test_no_wildcard_bind_in_source` — eski tarama **görmezdi** |
| `packaging/build_bundle.py`'ye `import subprocess` ekildi | **1 kırmızı**: `test_no_product_source_runs_a_program` — eski tarama **görmezdi** |
| `station_api/resources.py`'ye `import subprocess` ekildi | **2 kırmızı**: `test_no_product_source_runs_a_program`, `test_the_execution_scan_leaves_the_products_real_imports_alone` |
| Üçüncü bir modül `ctypes` import etti | **1 kırmızı**: `test_no_product_source_runs_a_program` — allow-list gerçekten iki dosya |
| `file_digest` alan-ayrılmış hâle getirildi | **1 kırmızı**: `test_the_artefact_digest_is_the_plain_sha256_a_user_can_reproduce` |
| Bir giriş noktası `stage=9`'da bırakıldı | **1 kırmızı**: `test_every_entry_point_names_the_same_release_stage` |
| `packaging/build/helper.py` ekildi (git yok sayıyor) | **2 kırmızı**: `test_every_shipped_source_file_is_tracked_by_git`, `test_the_tracking_scan_would_notice_a_missing_file` |
| `packaging/extra.spec` ekildi (takip edilmeyen) | **2 kırmızı**: aynı iki test — yeni uzantı gerçekten taranıyor |
| Build betiği ön koşul eksikken **çıkış kodu 0** verdi | **1 kırmızı**: `test_the_build_script_never_claims_an_artefact_it_did_not_produce` |

**Yirmi mutasyonun yirmisi en az bir testi öldürdü.** Sıfır öldüren guard
yok. İkisi (`.spec`'e ekilen `0.0.0.0`, `build_bundle.py`'ye ekilen
`subprocess`) Paket I'dan **önce sıfır kırmızı** verirdi; ADR-0010 §3'ün
ölçtüğü iki delik bunlardır.

### Mutasyon kaydı (SI-326, SI-327) — kusur kapanış turu

Aynı yöntem: kaynak fiilen düzenlendi, hedef test dosyası koşuldu, dosya geri
yüklendi. Taban **0 kırmızı**, geri yükleme sonrası yine **0 kırmızı**.

| Mutasyon | Ölçülen sonuç |
|---|---|
| `with absorbing_shutdown_signals():` ve `except KeyboardInterrupt` tümüyle kaldırıldı (kusur öncesi hâl) | **2 kırmızı**: `test_a_clean_stop_exits_zero_and_leaves_no_lock_behind`, `test_the_launcher_wraps_the_server_run_in_the_absorbing_window` — ayrıca **gerçek artefakt** üzerinde çıkış kodu `1`/`3`'e geri döndü |

### Mutasyon kaydı (SI-317, SI-318, SI-325, SI-328, SI-329) — bağımsız inceleme turu

Bağımsız bir düşman inceleme yirmi iki mutasyon yaptı ve **beşi sıfır kırmızı**
verdi. Aşağıdaki satırların "önce" sütunu o ölçümün **yeniden üretilmiş**
hâlidir: mutasyon uygulandı, ilgili test dosyaları **düzeltme öncesi** sürümle
(`git show HEAD:...`) koşuldu, sonra düzeltilmiş sürümle koşuldu, sonra her
şey geri yüklendi.

| Mutasyon | Önce | Sonra |
|---|---|---|
| `packaging/dist/helper.py` ekildi (`import subprocess` + `subprocess.Popen`; git yok sayıyor) | **0 kırmızı** | **3 kırmızı**: `test_no_product_source_runs_a_program`, `test_every_shipped_source_file_is_tracked_by_git`, `test_the_tracking_scan_would_notice_a_missing_file` |
| `vault/dpapi.py`'ye `import subprocess` + `subprocess.Popen` ekildi | **0 kırmızı** (ruff ve mypy de yeşildi) | **1 kırmızı**: `test_no_product_source_runs_a_program` |
| `EXECUTION_SCANNED_TREES` dörtten ikiye indirildi | **0 kırmızı** | **1 kırmızı**: `test_no_python_file_in_this_repository_escapes_the_execution_scan` |
| `test_bind.SCANNED_TREES`'ten `technocore-conform/src` ve `e2e/harness` düşürüldü | **0 kırmızı** | **1 kırmızı**: `test_the_wildcard_scan_covers_everything_the_execution_scan_covers` |
| Kilit `finally`'si yalnız `Server.run`'ı sarıyordu (düzeltme öncesi `launcher.py`) | **4 kırmızı** (yeni testler) | **0 kırmızı** |
| Gönderilen ZIP'te `__pycache__` (düzeltme öncesi `station.spec` ile üretilmiş artefakt) | **0 kırmızı** — böyle bir tarama yoktu | **1 kırmızı**: `test_the_shipped_archive_names_no_developer_and_no_home_directory`, 11 dosyayı **adıyla** raporladı |
| Gönderilen SPA kopyasının son baytı çevrildi, paketleme workflow'unun **yeni** pytest adımı koşuldu | — | **1 kırmızı**: `test_the_shipped_spa_is_byte_for_byte_the_audited_dist`; bayt geri yüklendi, yeşil |
| `subprocess.Popen` / `check_output` / `os.startfile` / `os.execv` ekildi (sentetik dosya) | **0 kırmızı** — `EXECUTION_ATTRIBUTES` yalnız küçük harf `popen` taşıyordu | dördü de raporlandı |
| Workflow'un eski regex `PATH` filtresi, yeni iddianın altında | — | iddia **ateşlerdi**: gerçek bir Windows 11 kabuğunda filtre sonrası `uv` (`\.local\bin`) ve `python` (`WindowsApps`) hâlâ çözülüyordu |

**Bir bulgu ölçülerek reddedildi.** İncelemenin F6 için önerdiği düzeltme —
"guard'ı listeye bağla, `for tree in SCANNED_TREES: assert ...`" — **kendisi
totolojiktir**: bu hâliyle yazıldı ve `EXECUTION_SCANNED_TREES` dörtten ikiye
indirildiğinde **yine 0 kırmızı** verdi, çünkü döngü listeyle birlikte
küçülüyor. Bir listeyi kendisiyle doğrulamak doğrulama değildir. Bu yüzden
guard iki yarıya bölündü: listeyi gezen yarı (ölü girdiyi yakalar) ve
**depoyu** gezen yarı (listeden düşürülmüş ağacı yakalar). Kırmızıyı veren
ikincisidir.
| `SHUTDOWN_SIGNALS`'tan `SIGBREAK` düşürüldü | **1 kırmızı**: `test_the_absorbed_signal_set_covers_both_console_stop_keys` |
| `SHUTDOWN_SIGNALS`'tan `SIGINT` düşürüldü | **kırmızı** (çıkış kodu 2): aynı test, ve yeniden yükseltilen `KeyboardInterrupt` oturumu düşürüyor |
| `absorb_shutdown_signal` `return None` yerine `raise KeyboardInterrupt` yaptı | **kırmızı** (çıkış kodu 2) |
| `except KeyboardInterrupt` → `except Exception` | **1 kırmızı**: `test_a_real_crash_is_still_a_crash` — pencere bir çökmeyi sessiz başarıya çeviremez |
| Pencere çıkışta handler'ları geri koymadı | **1 kırmızı**: `test_the_window_puts_back_the_handlers_it_found` |
| `ARTIFACT_DIR` yanlış yazıldı (`artefacts`) | **3 kırmızı**: sentetik tarama, kopya sayacı ve muafiyet-yeri testi |
| `_is_produced_copy` her zaman `False` | **2 kırmızı** |
| `_is_produced_copy` her zaman `True` | **3 kırmızı**, aralarında `test_the_wildcard_scan_opens_the_packaging_tree` — boş tarama yakalanıyor |
| `build`/`dist`/`out` yeniden **ada göre** atlandı | **1 kırmızı**: `test_a_wildcard_in_a_pyinstaller_default_output_directory_is_still_reported` |

**On mutasyonun onu** en az bir testi öldürdü. İkisi (SIGINT düşürme,
handler'ın kendisi yükseltme) oturumu `KeyboardInterrupt` ile düşürüyor;
biri — `SIGBREAK` pencereden çıkarılıp Ctrl+Break testi koşturulursa —
**test sürecini** CRT `abort()`'uyla sonlandırır. Üçü de tespittir ve ilgili
testin docstring'inde bu açıkça yazılıdır, çünkü sessizce geçmekten farkı
görülmelidir.

### Mutasyon kaydı (SI-329) — makineye bağlılık turu

Bu taramanın ilk sürümü **yerelde yeşil, CI'da kırmızıydı — aynı arşiv
baytları için**. Sebep ölçüldü: iğnelerin hepsi `Path.home()`'dan geliyordu.
Geliştirici makinesinde bu kendi hesabı, GitHub Actions runner'ında
`runneradmin`, ve `cryptography` ile `pydantic-core`'un Windows
wheel'lerini **upstream de** GitHub Actions'ta derliyor. Yerelde bulunan
artefakt tarandı: tam **iki** üye `C:\Users\runneradmin` taşıyor —
`_internal/cryptography/hazmat/bindings/_rust.pyd` ve
`_internal/pydantic_core/_pydantic_core.cp312-win_amd64.pyd` — ve taşıdıkları
şey `.cargo\registry\src\index.crates.io-<hash>\<crate>` biçiminde Rust panic
konumları (openssl, pyo3, asn1, jiter, regex-automata ve yirmiden fazla
crate). Arşivin **başka hiçbir** üyesi ne o dizeyi ne bu deponun mutlak
yolunu taşıyor.

CI koşulu yerelde birebir yeniden üretildi (`Path.home()` geçici olarak
`C:\Users\runneradmin` yapıldı, gerçek arşiv tarandı): eski tarama **tam o
iki dosyayı, tam o iki etiketle** (`account-name, home-directory`) raporladı;
yeni tarama aynı koşulda **hesap iğneleri için 0**, **depo yolu iğnesi için
0** verdi.

| Mutasyon | Ölçülen sonuç |
|---|---|
| `_repository_needles` `{}` döndürdü | **1 kırmızı**: `test_the_repository_path_is_refused_anywhere_in_the_archive` |
| `_leaking_entries`'in `within` süzgeci yok sayıldı (her zaman tüm arşiv) | **1 kırmızı**: `test_a_third_party_binarys_upstream_build_path_is_not_our_leak` |
| `_spec_copied_prefixes` `()` döndürdü (kapsam boş) | **3 kırmızı**, aralarında `test_the_copied_scope_is_read_off_the_spec_and_finds_real_members` — kör geçiş yakalanıyor |
| `BUNDLE_INTERNAL_DIR` `_internals` yazıldı (kapsam hayalî) | **1 kırmızı**: aynı test — önekler hiçbir gerçek üyeyle eşleşmiyor |
| Kapsam yeniden bundle köküne genişletildi (**CI regresyonunun kendisi**) | **2 kırmızı**: `::test_a_third_party_binarys_upstream_build_path_is_not_our_leak`, `::test_the_third_party_binaries_carry_their_own_build_machine` — ikisi de `runneradmin`'i **düz metin** kullandığı için bu **her makinede** kırmızı |
| `_build_account_needles` `{}` döndürdü | **2 kırmızı**: `::test_the_leak_scan_reports_a_planted_path`, `::test_a_leak_in_a_copied_member_is_reported` |
| `_string_literals` `[]` döndürdü (spec okunamaz hâle geldi) | **4 kırmızı** |

**Yedi mutasyonun yedisi** en az bir testi öldürdü. Ayrıca **gerçek
artefaktın geçici bir kopyasına** üç ekim yapıldı ve üçü de kırmızı verdi:
bizim ağacımızdaki bir `__pycache__/*.pyc` (bytecode yasağı), üçüncü taraf
gibi adlandırılmış bir `.pyd` içinde **depo yolu** (arşiv geneli iğne), ve
`station_web` altında ev dizini taşıyan bir dosya (kapsanmış hesap iğnesi).
Kopya sonrasında silindi; gönderilen arşive dokunulmadı.

### Kapsanmayan, ve iddia edilmeyen

- ~~**Artefakt üretilmedi.**~~ **Artık üretildi ve çalıştırıldı.** Bu satır
  PyInstaller depoya `dev` bağımlılığı olarak eklenmeden önce yazılmıştı ve
  o zaman doğruydu; kayıt olarak duruyor, iddia olarak değil. SI-319'un
  bayt-birebir karşılaştırması bugün **gerçek bir pakete karşı koşuyor**
  ([`verification/paket-i.md`](verification/paket-i.md) §13).
- **CI paketleme işi hiç çalıştırılmadı.** `packaging.yml` yazıldı ve YAML'i
  ayrıştırıldı; GitHub Actions bu turda koşturulmadı.
- **İmzalama doğrulanamaz.** Sertifika ve secret yok (ADR-0010 §9).
- **`%LOCALAPPDATA%` dışına yazılmadığı** yalnız CI işinde denetlenir ve o
  iş koşmadı; süreç içinde denetlenen şey kilidin veri dizininde olduğudur.

---

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
