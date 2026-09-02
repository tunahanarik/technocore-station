# Paket A doğrulama raporu — Başlangıç, kapsam eki, tekrarlanabilir CI

Tarih: 2026-09-02 · Taban: `5411171dd2302c6fea5a2af22695503859317c27` (PR #9 merge'ü)

## Başlangıç uzlaştırması

- Hesap/remote doğrulandı: `tunahanarik/technocore-station`, local `main` =
  `origin/main` = GitHub API = `5411171`.
- Çalışma ağacında önceki oturumdan üç taslak bulundu (ADR-0001,
  execution-plan, execution-state); silinmedi, okundu ve benimsendi.
- Açık PR yalnız #7 (kullanıcının otomasyon testi) — bu pakette dokunulmadı.

## Temiz klon baseline (bağımsız tekrar)

Ayrı bir doğrulama agent'ı, `git clone --no-local` ile taze klonda, taze venv
ve `npm ci` ile bütün kapıları koştu:

| Kapı | Sonuç |
|---|---|
| ruff (AGENTS.md biçimi) | geçti |
| ruff (üç ağaç) | geçti |
| mypy strict | 53 dosya, 0 hata |
| pytest (dist üretilmeden) | 730 geçti, **6 kırmızı** — hepsi `dist/` isteyen bundle güvenlik testleri, açık yönergeyle |
| `npm ci` | lockfile ile, 0 açık |
| eslint / vitest / build | geçti / **59 geçti** / geçti |
| pytest (build sonrası) | **736 geçti, 0 hata** |
| vendor SHA-256 | 8/8 OK |
| conformance self-test | PASS |

**736 + 59 = 795** iddiası bağımsız olarak birebir doğrulandı. CRLF/fresh-clone
regresyonu üremedi. Suite tamamen çevrimdışı koştu; technocore.chat'e istek
atılmadı; gerçek profil dizinlerine dokunulmadı.

**Bulgu (tasarım gereği, düzeltme gerekmez):** 6 bundle güvenlik testi
`apps/station-web/dist` yokken `pytest.fail` ile açık yönerge verir. CI
sıralaması buna göre kuruldu: backend işi pytest'ten **önce** frontend'i
kurar ve build eder.

## CI workflow kararları

`.github/workflows/quality.yml` — iki iş, ikisi de `windows-latest`:

1. **Tetikleyici:** `pull_request`→main + `push`→main. `pull_request_target`
   bilinçli olarak YOK (untrusted PR kodu yetkili bağlamda çalışmaz).
2. **İzinler:** üst düzeyde `permissions: contents: read`; hiçbir secret
   okunmaz; `persist-credentials: false`.
3. **Pinler** (2026-09-02'de `gh api repos/<o>/<r>/git/ref/tags/<tag>` ile
   doğrulandı, orkestratör tarafından ayrıca spot-check edildi):

   | Action | Tag | SHA |
   |---|---|---|
   | actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
   | astral-sh/setup-uv | v10.0.1 | `20cfd1bf945f4377ade1205e4dbc17946fc9a30d` |
   | actions/setup-node | v7.0.0 | `820762786026740c76f36085b0efc47a31fe5020` |

   setup-uv tercih gerekçesi: uv CPython 3.12'yi kendisi kurar; curl-pipe uv
   kurulumu pinleme politikasını delerdi. uv sürümü de pinli (0.11.26).
4. **Lockfile-only kurulum:** `uv sync --locked --project apps/station-api`
   (technocore-conform editable path bağımlılığı olarak aynı sync'e girer;
   kendi lockfile'ı yoktur) ve `npm ci`.
5. **Cache yok** — bilinçli: lockfile'lar tekrarlanabilirliği zaten sağlar ve
   hiçbir cache byte-exact denetimleri zehirleyemez.
6. **Runner OS gerekçesi:** DPAPI kasa testleri gerçek Windows API'si ister.
   Ayrıca `test_git_hands_a_fresh_checkout_the_exact_pinned_bytes` çalışma
   ağacını `git cat-file blob` ile karşılaştırır — bu test yalnız
   `core.autocrlf=true` checkout'ta (Windows varsayılanı) kırılabilir; ubuntu
   üzerinde vakumda geçer. CI bu yüzden `core.autocrlf`'i DEĞİŞTİRMEZ.
7. **Uyarı görünürlüğü:** CI pytest'i `-p no:warnings` olmadan koşar;
   belgelenmiş kapı uyarıları gizlemez, CI da gizlemez.

## Negatif kanıt planı (PR üzerinde uygulanacak)

Yeni test işlerinin gerçekten fail edebildiğini göstermek için: PR dalına
bilerek kırık bir commit itilir → kırmızı check gözlenir → normal bir revert
commit'iyle geri alınır → yeşil check gözlenir. Her iki commit de tarihçede
kalır; bu dürüst kanıttır, gizlenmez. Sonuç SHA'larıyla bu rapora eklenecek.

## Negatif kanıt sonucu

(PR açıldıktan sonra doldurulacak.)

## Sınırlar

- Gerçek DID/kasa/recovery/parola okunmadı, değiştirilmedi.
- Technocore'a hiçbir istek gönderilmedi (baseline dahil — suite çevrimdışı).
- Tag/release/deploy yok; PR #7'ye dokunulmadı.
- Bağımsız inceleme: Copilot PR review (AI) + orkestratör dışı doğrulama
  agent'ları. Bu bir **insan güvenlik incelemesi değildir**; insan incelemesi
  bu döngüde ertelenmiştir ve ilk gerçek kullanım öncesi kalan risktir
  (ADR-0001 §5).
