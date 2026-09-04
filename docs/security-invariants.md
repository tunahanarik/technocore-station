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
