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

**Backend işi için sahici kanıt (planlanandan güçlü):** PR #10'un ilk head'i
`c44f3c9` üzerindeki ilk gerçek CI koşusu (run 33669302148) backend işinde
**failure** üretti — staged bir kırılma değil, runner ortamının yakaladığı 5
gerçek ortam-taşınabilirlik hatası:

| Hata | Kök neden | Düzeltme |
|---|---|---|
| 3 CLI testi exit 0 (beklenen ≠0) | `_read_stdin()` konsolun locale kodlamasıyla okuyordu; cp1252 runner'da UTF-8 girdi mojibake olup görünür karaktere dönüşüyor, sweep "başarılı" çıkıyordu — **gerçek ürün hatası**, UTF-8 olmayan konsollu her kullanıcıda tetiklenir | CLI stdin'i sözleşme gereği bayt akışından UTF-8 okur; UTF-8 olmayan girdi traceback değil açık mesajla `EXIT_USAGE`; stdout/stderr UTF-8'e reconfigure edilir. 3 yeni regresyon testi runner koşulunu `PYTHONIOENCODING=cp1252` ile birebir üretir |
| ACL testi | SDDL, iyi bilinen hesapları kısaltır (runner'ın Administrator'ı `LA` diye yazılır); substring araması hesaba bağımlıydı | `windows_acl.acl_grantee_sids()` eklendi: DACL ACE'leri gerçekten yürünüp SID'ler string'e çevrilir; test artık **çözümlenmiş SID kümesi eşitliği** kurar (`{S-1-5-18, current_user_sid()}`) — daha güçlü iddia |
| `test_tests_never_touch_the_real_installation` | 8.3 kısa yol (`RUNNER~1`) ile `resolve()` uzun yolu uyuşmuyor | Karşılaştırmanın iki tarafı da `Path(...).resolve()` ile normalize edilir |

Düzeltme sonrası yerel suite: **739 pytest** (736 + 3 yeni) + 59 Vitest.
Hiçbir test silinmedi/gevşetilmedi; ACL testi güçlendirildi.

**Frontend işi için staged kanıt (uygulandı):** bilerek kırık Vitest testi
`6d76929b850e906e5b70a8d565b15c385477a285` commit'iyle itildi → CI sonucu
`frontend gates (windows): failure`, `backend gates (windows): success` →
normal revert commit'iyle geri alındı. İki commit de tarihçede duruyor;
gizlenmedi.

Böylece her iki CI işinin de gerçekten fail edebildiği kanıtlandı: backend
sahici hatalarla (run 33669302148), frontend staged örnekle.

## Bağımsız inceleme sonucu

- **Copilot review kota sınırına takıldı** ("unable to review ... quota
  limit") — bu bir inceleme DEĞİLDİR ve öyle sayılmadı.
- Yerine **temiz bağlamlı, yazardan ayrı bir Claude reviewer subagent'ı** son
  head (`77f50c9`) diffini inceledi ve kendi karşı örneklerini fiilen
  çalıştırdı: pin'lerin canlı `gh api` doğrulaması; cp1252 konsol byte
  probları (CRLF stripping, JSON byte eşitliği, UTF-8 olmayan stdin → exit 2);
  DACL'e DENY/Everyone/inheritance ACE enjekte eden adversarial prob (DENY
  eski testi **geçiyor**, yeni SID-küme testini **kırıyor** — güçlenmenin
  somut kanıtı); workflow'da `${{ }}` enjeksiyon yüzeyi taraması.
- Sonuç: **P0/P1 yok.** 1 P2 (workflow'daki ölü NOTES.md işaretçileri) ve 4
  P3 (docstring/yorum gecikmeleri) bulundu; hepsi merge'den önce düzeltildi.
- Bu inceleme bir **insan güvenlik incelemesi değildir** (ADR-0001 §5'teki
  kalan risk aynen geçerli).

## Sınırlar

- Gerçek DID/kasa/recovery/parola okunmadı, değiştirilmedi.
- Technocore'a hiçbir istek gönderilmedi (baseline dahil — suite çevrimdışı).
- Tag/release/deploy yok; PR #7'ye dokunulmadı.
- Bağımsız inceleme: Copilot PR review (AI) + orkestratör dışı doğrulama
  agent'ları. Bu bir **insan güvenlik incelemesi değildir**; insan incelemesi
  bu döngüde ertelenmiştir ve ilk gerçek kullanım öncesi kalan risktir
  (ADR-0001 §5).
