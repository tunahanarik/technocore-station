# CLAUDE.md — Technocore Station

Claude Code için proje talimatları. **Kanonik kural seti
[`AGENTS.md`](AGENTS.md) dosyasındadır**; bu dosya aynı değişmezleri
tekrarlar ve Claude Code'a özgü notlar ekler.

## Ana kaynak

Ürün, kapsam, güvenlik ve mimari kararlarında tek karar kaynağı:
[`Technocore-Station-Proje-Kunyesi.md`](Technocore-Station-Proje-Kunyesi.md)

Her turda oku: bu dosya → `AGENTS.md` → `PROJECT_STATUS.md`.

## Değişmez kurallar

Aşağıdakiler ihlal edilemez. Bir görev bunlardan birini gerektiriyorsa
**dur ve kullanıcıya sor**.

1. **Secret seed frontend'e, API response'a, loga veya LLM'e çıkamaz.**
   Response modellerinde `seed`, `private_key`, `secret`, `mnemonic` alanı
   olamaz.
2. **`0.0.0.0` bind yasaktır.** Yalnız `127.0.0.1` + efemer port.
3. **CORS middleware yasaktır.** Aynı-origin mimarisi; dev'de Vite proxy.
4. **TLS doğrulaması kapatılamaz.** `verify=False` ve eşdeğerleri yasak.
5. **Gerçek Technocore write işlemi otomatik testlerde yasaktır.** Lobby
   hiçbir testte hedef olamaz.
6. **Güvenlik testleri silinemez veya gevşetilemez.** `tests/security/`
   altındaki testler `skip`/`xfail` edilemez, iddiaları zayıflatılamaz.
   Test kırmızıysa kodu düzelt.
7. **HeroUI v2/NextUI kalıpları yasaktır.** Yalnız HeroUI v3, yalnız
   ücretsiz bileşenler. API tahmin edilmez — `heroui-react` MCP'den
   doğrulanır. HeroUI Pro kullanılmaz.
8. **Kullanıcı açıkça istemedikçe commit, push veya deploy yapılamaz.**
9. **Her aşamanın sonunda `PROJECT_STATUS.md` güncellenir.**

## Claude Code'a özgü notlar

### HeroUI v3 MCP ön koşulu
Bir HeroUI bileşenine dokunmadan önce `heroui-react` MCP bağlantısının açık
olduğunu doğrula. Bağlantı yoksa **bileşen API'si tahmin etme**; kullanıcıya
bağlantıyı kurmasını söyle ve orada dur.

İş akışı: `list_components` → `get_component_docs` → kod.

### Aşama disiplini
Her turda yalnız verilen aşamayı uygula. Aşama sınırları
[`PROJECT_STATUS.md`](PROJECT_STATUS.md) içindeki checklist'tedir. Sonraki
aşamanın kodunu önden yazma.

### Yasak eylemler (kullanıcı açıkça istemedikçe)
- Gerçek DID, seed, private key veya `.tcrec` recovery dosyası oluşturmak.
- Technocore'a mesaj, note veya başka bir yazma isteği göndermek.
- `git commit` / `git push` / deploy / public repo.
- Gizli telemetri, analytics veya bulut servisi eklemek.
- Mevcut kullanıcı dosyalarını ezmek.

### Yeni bağımlılık
Gerekçe + lisans yaz, `README.md` bağımlılık tablosuna satır ekle, lockfile'ı
güncelle. Bağımlılıkları minimumda tut.

### Aşama sonu kontrol listesi

Kanonik liste [`AGENTS.md`](AGENTS.md) §4'tedir; aşağısı birebir aynı
olmak zorundadır (`tests/security/test_gate_parity.py` iki dosyayı
karşılaştırır) ve `.github/workflows/` altındaki kapıların tamamıdır.
Kurulum adımları (`npm ci`, `uv sync --locked`, `uv python install`,
`playwright install`, PyInstaller sürüm çıktısı) kapı değildir.

**CI her PR'da bu listenin tamamını çalıştırır.** Yerelde bir komutu atlamak
onu ortadan kaldırmaz, yalnız hatanın nerede görüneceğini değiştirir: CI'da.

#### Hızlı kapı (her değişiklikte)

Ölçüldü (6 Eylül 2026, iki ardışık koşu, sıcak mypy cache'i): toplam
**44–45 sn** (ruff 0–1 sn + <1 sn, mypy 1 sn, eslint 8–9 sn, vitest
23–24 sn, build 11 sn).

```bash
uv run --directory apps/station-api ruff check .
uv run --project apps/station-api ruff check apps/station-api/src packages/technocore-conform/src tests
uv run --project apps/station-api mypy --config-file apps/station-api/pyproject.toml
npm --prefix apps/station-web run lint
npm --prefix apps/station-web run test
npm --prefix apps/station-web run build
```

İki ruff komutu farklı ağaçları kapsar; biri diğerinin yerine geçmez.
Birincisi `tests/` klasörünü hiç açmaz — oradaki bir bulguyu (ölçülmüş örnek:
`B007`) yalnız ikincisi görür. `mypy src` de yeterli değildir: CI'ın komutu
**142** dosya denetler, `mypy src` **140**.

#### Tam kapı (push öncesi)

Hızlı kapının tamamı, **artı** aşağıdakiler. Ölçüldü (6 Eylül 2026, iki
ardışık koşu): bu dört komut **4 dk 50 sn – 5 dk 11 sn** (pytest 179–182 sn,
e2e 67–72 sn, bundle 35–53 sn, bundle pytest'i 6–7 sn); hızlı kapıyla
birlikte ~6 dk.

```bash
uv run --directory apps/station-api pytest ../../tests
npm --prefix apps/station-web run test:e2e
uv run --project apps/station-api python packaging/build_bundle.py
uv run --directory apps/station-api pytest -p no:warnings ../../tests/security/test_frontend_bundle.py ../../tests/security/test_packaging_boundary.py
```

Son iki komut sıralıdır: `test_frontend_bundle.py` ve
`test_packaging_boundary.py` diskte bir bundle yoksa erken döner. Son satır
`packaging.yml`'den birebir alınmıştır. Orada bir `-q` vardı; `pytest.ini`
zaten `-q` verdiği için `-qq` oluyor ve özet satırını bastırıyordu (ADR-0011
§1'in tuzağı). CI adımından da düştü.

Başarısız testi gizleme veya atlama. Ortam nedeniyle çalışmayan bir test
varsa sebebini ve yeniden çalıştırma komutunu `PROJECT_STATUS.md` içine yaz.
