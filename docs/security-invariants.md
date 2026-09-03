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
| SI-71 | Giden istekte cookie/auth/DID/CSRF yok | header temiz | `::test_the_request_carries_no_identity_or_credential` | A3 |
| SI-72 | GET yazma yollarına ulaşan kod yolu yok | AST literal taraması | `test_write_gate.py::test_no_code_path_can_reach_a_technocore_write_endpoint` | A3 |
| SI-73 | HTTP istemcisi yalnız **incelenmiş** iki modülde (Paket D'de daraltılarak genişletildi) | `client.py` + `write_client.py`, başka hiçbir modül | `test_write_gate.py::test_httpx_is_imported_only_by_the_two_reviewed_clients`, `::test_both_reviewed_client_modules_actually_exist`, `::test_the_write_client_is_not_reachable_from_the_read_path` | A3 → D |
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
