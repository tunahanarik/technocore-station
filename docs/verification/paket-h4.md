# Paket H4 doğrulama raporu — model plan yolu ve kabul koşulları

Tarih: 2026-09-06 · Kapsam kararı:
[`ADR-0012`](../decisions/0012-model-yolu-sozlesme-dogrulamasi-2026-09-06.md) ·
Uygulanmış hâli: [`model-planning.md`](../model-planning.md) ·
Değişmezler: `security-invariants.md` §9m (SI-330 … SI-343).

Bu belgede yazan her sayı **koşularak ölçüldü**. Ölçülmeyen hiçbir şey
iddia edilmiyor; ölçülemeyenler §5'te.

---

## 1. İş 1 — geç yanıt kuralı ikiye ayrıldı

**Kusur.** Tek bir test iki farklı davranışı tek cümleyle sabitliyordu:
*"iptalden sonra dönen sonucun ürettiği dosya çalışma alanından kaldırılır."*
Bu cümle `write_workspace_file` için doğru, `update_workspace_file` için
**yanlıştı** — orada hedef dosya **önceki, tamamlanmış** bir adımın çıktısıdır
ve onu silmek, kullanıcıya zaten gösterilmiş bir işi yok etmek olurdu.

**Kırmızı (önce).**

```
$ uv run --directory apps/station-api pytest ../../tests/security/test_agent_runtime.py -q -k after_a_stop
FAILED test_a_result_arriving_after_a_stop_leaves_no_new_file_behind
FAILED test_a_result_arriving_after_a_stop_restores_the_previous_bytes
```

**Düzeltme.** `_discard` artık **hangi geri almanın koştuğunu söyleyen cümleyi
döndürüyor** (üç durum: yeni dosya kaldırıldı / önceki baytlar geri yüklendi /
geri alınacak bir şey yoktu). `STOP_HONESTY_SENTENCE` de düzeltildi: eski hâli
kullanıcıya "durdurmak işinizi silebilir" diye söz veriyordu.

**Yeşil (sonra).**

```
$ uv run --directory apps/station-api pytest ../../tests/security/test_agent_runtime.py ../../tests/security/test_agent_language.py -q
54 passed
```

**Mutasyon.**

| Mutasyon | Öldürülen |
|---|---|
| `_discard` her zaman siler (düzeltme öncesi davranış) | **2** (`::test_a_result_arriving_after_a_stop_restores_the_previous_bytes`, `test_review_regressions.py::test_stop_restores_previous_bytes_and_resume_retries_discarded_step[True]`) |
| iki cümle takas edilir | **2** (her iki yarı da) |

---

## 2. İş 2 — model yolu

Yeni: `station_api/opencode/planner.py` (protokol adaptörü),
`station_api/planner/` (koordinatör), `routes/planner.py`,
`agent/tools.py::json_schema`, `agent/budget.py`'de dördüncü birim.

**Yeşil.**

```
$ uv run --directory apps/station-api pytest ../../tests/security/test_model_planner.py ../../tests/security/test_planner_boundary.py -q
44 passed
```

**Mutasyon skorları** (tam `tests/security` koşusu; `test_frontend_bundle`
başka bir ajanın `dist` yeniden derlemesi yüzünden her koşuda kırmızı ve
sayılmadı).

| # | Mutasyon | Öldürülen |
|---|---|---|
| N1 | `reasoning_content` düşürülmez, `text`'e taşınır | **2** |
| N2 | kayıtsız çağrılar atlanır, kalan plan kaydedilir | **3** |
| N3 | model çağrısı tavanı kaldırılır | **1** |
| N4 | döngü yalnız `finish_reason`'a bakar | **1** |
| N5 | `cost` yoksa `"0"` uydurulur | **1** |
| N6 | planner kaydettiği çalışmayı kendisi başlatır | **5** (`test_planner_boundary::test_the_planner_cannot_start_a_run` dâhil) |
| N7 | 200 olmayan durum satırı okunmaz | **1** |

N7 ilk koşuda **sıfır** öldürdü. Nedeni ölçüldü: bütün sağlayıcı-hatası
testleri gövdesinde `error` üyesi taşıyordu, dolayısıyla durum satırı
denetimi **hiç sürülmemişti**. Boşluk
`test_a_failing_status_is_a_failure_even_when_the_body_looks_like_an_answer`
ile kapatıldı — gövdesi kusursuz bir `tool_calls` yanıtı olan bir **500** — ve
mutasyon tekrar koşulduğunda **1** öldürdü.

Ayrıca `tool_calls_supported` telde **sabit yazılırsa**
`test_the_wire_follows_the_constant_rather_than_a_second_hard_coded_answer`
kırmızıya döner (**1** öldürür). Bu, H3'ün bağımsız incelemesinde türetilmiş
bir alanın sabite dönüştürülmesinin **hiçbir şey öldürmediği** ölçümünün
tekrarlanmaması içindir.

---

## 3. İş 3 — kabul koşulları ve görev sonuçlandırma

Yeni: `station_api/agent/acceptance.py` (yedinci kapalı registry),
migration `0010` (`agent_run.acceptance_json`),
`POST /api/tasks/{id}/publish-readiness`.

**Yeşil.**

```
$ uv run --directory apps/station-api pytest ../../tests/security/test_agent_acceptance.py -q
28 passed
```

**Mutasyon skorları.**

| # | Mutasyon | Öldürülen |
|---|---|---|
| M1 | `test_result_state` yine sabit `not_implemented` | **3** |
| M2 | koşucu `test_result` kanıtını hiç yazmaz | **5** |
| M3 | koşulsuz küme `passed` sayılır (`all([])` boşluğu) | **6** |
| M4 | kabul koşulları plan özetinden çıkarılır | **2** |
| M5 | kaydedilen sonuç her zaman `verified=True` | **1** |
| M6 | her koşul sağlanmış sayılır | **8** |

---

## 4. Neden bazı güvenlik testleri **değişti**

Hiçbiri gevşetilmedi; hepsinde değişen şey **olgu**ydu ve gerekçe testin
docstring'ine yazıldı.

| Test | Neden |
|---|---|
| `test_agent_budget.py::test_the_units_are_the_ones_this_build_can_measure` | üç birim dört oldu: model çağrısı **sayılabilir** hâle geldi. Tuple hâlâ elle yazılı ve eşitlikle karşılaştırılıyor |
| `::test_there_is_no_token_and_no_currency_unit` | iddia aynı, **gerekçe sertleşti**: sağlayıcı artık ikisini de gönderiyor ve yine tavan olmuyorlar |
| `test_agent_activity.py::test_the_step_by_step_actions_stay_out_of_the_chain` | üç yeni zaman çizelgesi eylemi; hiçbiri karar noktası değil (hacim gerekçesi docstring'de) |
| `::test_there_is_no_model_actor` | **iddia değişmedi**, docstring'in gerekçesi değişti: "model yok" değil, "modelin kendi başına bir şey yaptığı söylenmez" |
| `test_opencode_protocols.py::test_streaming_is_absent_and_says_so_and_tool_calls_were_measured` | eski adı iki ertelemeyi sabitliyordu; biri ölçüldü. Streaming yarısı **daha sıkı** sabitlendi ve ölçülen yarıya provenance zorunluluğu eklendi |
| `test_opencode_http.py::test_the_protocol_context_states_the_deferral_and_the_measurement` | aynı sebep; değer artık sabite karşı karşılaştırılıyor, elle yazılmıyor |
| `test_agent_boundary.py` / `test_database.py` — `CURRENT_MIGRATION_HEAD` | `0010` eklendi; ayrıca `test_migration_0010_only_added_a_column` katkısallığı ölçüyor |
| `test_proof_boundary.py::test_no_new_migration_was_added_by_this_package` | iddiası "H3 bir migration eklemedi"ydi ama **baş numarasına** bağlıydı, yani başkası bir migration eklediğinde kırılıyordu. Artık H3'ün yazabileceği revizyon adlarını arıyor |
| `test_agent_http.py::EXPECTED_PATHS` | iki yeni yol (`model-plan`, `publish-readiness`) envantere eklendi |
| `test_task_states.py::STATE_WRITER_DIRS` | beşinci ağaç `planner` eklendi — "yeni paket taramanın dışında kalır" kusurunun dördüncü tekrarı |
| `test_agent_runtime.py` — `RunCeiling(...)` | dördüncü alan eklendi (varsayılan **yok**: her çağrı yerinde açıkça yazılır) |

---

## 5. Ölçülmeyenler ve yapılmayanlar

- **Gerçek bir sağlayıcı isteği yapılmadı.** Bütün testler
  `httpx.MockTransport` kullanıyor; kimlik bilgisi depodaki sentetik
  `TEST-ONLY` sabitidir. Anahtar koda, teste, belgeye veya loga yazılmadı.
  ADR-0012'deki canlı ölçüm bu turdan **önce** yapılmıştı ve bu turda
  tekrarlanmadı.
- **Arayüz güncellenmedi.** `apps/station-web/**` bu turun kapsamı dışıydı.
  `tool_calls_supported` telde `false` iken `true` oldu ve
  `apps/station-web/src/api/types.ts` onu hâlâ `false` **tipiyle** taşıyor;
  arayüz tarafında düzeltilmesi gereken bir satır olarak bırakıldı.
- **`test_frontend_bundle.py::test_the_shipped_spa_is_byte_for_byte_the_audited_dist`
  kırmızı.** Bu turda `apps/station-web/**` altında hiçbir dosyaya
  dokunulmadı; başka bir ajanın `dist` yeniden derlemesinden kaynaklanıyor.
- **Manuel tarayıcı ve görsel kabul yapılmadı**; kullanıcıya aittir.
- **İnsan güvenlik incelemesi** ertelenmiş kalan risktir (ADR-0001 §5).
