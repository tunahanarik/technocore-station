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
```bash
uv run --directory apps/station-api ruff check .
uv run --directory apps/station-api mypy src
uv run --directory apps/station-api pytest ../../tests -q
npm --prefix apps/station-web run lint
npm --prefix apps/station-web run test
npm --prefix apps/station-web run build
```
Başarısız testi gizleme veya atlama. Ortam nedeniyle çalışmayan bir test
varsa sebebini ve yeniden çalıştırma komutunu `PROJECT_STATUS.md` içine yaz.
