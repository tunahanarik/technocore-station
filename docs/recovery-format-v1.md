# `.tcrec` recovery format, sürüm 1

> Uygulama: [`../apps/station-api/src/station_api/recovery/format.py`](../apps/station-api/src/station_api/recovery/format.py)
> Testler: `tests/security/test_identity_vault.py`
> Ana karar kaynağı: [`../Technocore-Station-Proje-Kunyesi.md`](../Technocore-Station-Proje-Kunyesi.md) §13.3–13.4

Bir `.tcrec` dosyası, Ed25519 seed'inizin **parolayla şifrelenmiş, taşınabilir**
bir kopyasıdır. DPAPI'den **bağımsızdır**: başka bir bilgisayarda, başka bir
Windows hesabında, yalnızca recovery parolasıyla açılır. Kimliğinizi gerçekten
kurtarabilecek tek şey budur.

**Güvenliği tamamen recovery parolanızın gücüne bağlıdır.** Dosyayı ele
geçiren biri, parolayı kırabilirse seed'i elde eder. Argon2id bunu pahalı
kılar; imkânsız kılmaz.

---

## 1. Dosya yapısı

Dosya, tek bir JSON nesnesidir (UTF-8, tek satır, boşluksuz). Uzantı `.tcrec`.

| Alan | Tip | Açıklama | AAD? |
|---|---|---|:--:|
| `format` | string | Sabit: `technocore-station.recovery` | evet |
| `version` | int | Sabit: `1` | evet |
| `did` | string | Seed'in ürettiği `did:key` | evet |
| `created_at` | string | ISO-8601, timezone'lu | evet |
| `kdf` | string | Sabit: `argon2id` | evet |
| `kdf_time_cost` | int | Argon2id iterasyon sayısı | evet |
| `kdf_memory_kib` | int | Argon2id bellek maliyeti (KiB) | evet |
| `kdf_parallelism` | int | Argon2id paralellik | evet |
| `salt` | string | 16 bayt, unpadded base64url | evet |
| `aead` | string | Sabit: `chacha20poly1305` | evet |
| `nonce` | string | 12 bayt, unpadded base64url | evet |
| `ciphertext` | string | AEAD çıktısı, unpadded base64url | **hayır** |

`ciphertext` **dışındaki her alan AAD'dir**. Bu alanlardan biri değiştirilirse
AEAD doğrulaması kırılır ve dosya açılmaz.

---

## 2. Kripto parametreleri

| Parametre | Değer |
|---|---|
| KDF | Argon2id |
| Bellek | **64 MiB** (65536 KiB) |
| İterasyon | **3** |
| Paralellik | **1** |
| Türetilen anahtar | 32 bayt |
| AEAD | ChaCha20-Poly1305 |
| Salt | dosya başına **yeni** 16 rastgele bayt |
| Nonce | dosya başına **yeni** 12 rastgele bayt |
| Plaintext | 32 baytlık seed |

Salt ve nonce her dosyada yeniden üretildiği için, **aynı seed ve aynı
parolayla üretilen iki dosya byte olarak farklıdır**. Bu bir testle sabitlenir.

### Parola normalizasyonu
Parola önce **NFC** normalize edilir, sonra UTF-8'e çevrilir. Normalizasyon
olmadan aynı parola farklı klavye/platformda farklı baytlar üretebilir ve
dosya başka bir makinede açılamaz hâle gelirdi.

---

## 3. AAD v1 canonicalization

`ciphertext` hariç header alanları şu algoritmayla baytlara çevrilir:

1. `ciphertext` alanı çıkarılır.
2. Anahtarlar **Unicode code point** sırasıyla sıralanır.
3. Ayırıcılar tam olarak `,` ve `:`; **boşluk eklenmez**.
4. `ensure_ascii=false` eşdeğeri (ASCII olmayan karakterler kaçışlanmaz).
5. UTF-8'e çevrilir.

Bu, `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
karşılığıdır.

### Sabit test vektörü

Header (TEST-ONLY değerler):

```json
{"format":"technocore-station.recovery","version":1,"did":"did:key:zTEST","created_at":"2026-08-30T00:00:00+00:00","kdf":"argon2id","kdf_time_cost":3,"kdf_memory_kib":65536,"kdf_parallelism":1,"salt":"AAAA","aead":"chacha20poly1305","nonce":"BBBB","ciphertext":"SHOULD-NOT-APPEAR"}
```

Üretilen AAD (byte-exact):

```text
{"aead":"chacha20poly1305","created_at":"2026-08-30T00:00:00+00:00","did":"did:key:zTEST","format":"technocore-station.recovery","kdf":"argon2id","kdf_memory_kib":65536,"kdf_parallelism":1,"kdf_time_cost":3,"nonce":"BBBB","salt":"AAAA","version":1}
```

Bu vektör `test_aad_v1_is_byte_exact` ile pinlenmiştir. Değerler
**TEST-ONLY**dir; gerçek anahtar materyali değildir.

---

## 4. Kodlama kararı: unpadded base64url

Tüm binary alanlar **padding'siz** base64url ile yazılır ve **canonical**
olmalıdır:

- `=` içeren değer **reddedilir**.
- Çözülüp yeniden kodlandığında aynı diziyi vermeyen değer **reddedilir**
  (artık bitleri sıfır olmayan girdiler).

Böylece bir bayt dizisinin tek bir kabul edilebilir yazımı olur.

---

## 5. Fail-closed doğrulama

Bir dosya açılmadan önce sırasıyla reddedilir:

| Durum | Sonuç |
|---|---|
| Dosya > 64 KiB | reddedilir (parse edilmeden) |
| Geçersiz UTF-8 / JSON | reddedilir |
| **Duplicate JSON anahtarı** | reddedilir |
| Eksik veya fazla alan | reddedilir |
| Yanlış tip (ör. string yerine bool) | reddedilir |
| `version != 1` | reddedilir |
| `kdf != argon2id`, `aead != chacha20poly1305` | reddedilir |
| KDF parametresi politika sınırları dışında | **türetmeden önce** reddedilir |
| `salt` 16 bayt değilse, `nonce` 12 bayt değilse | reddedilir |
| Padding'li veya canonical olmayan base64url | reddedilir |
| AEAD doğrulaması başarısız | reddedilir |
| Çözülen seed'den türeyen DID header DID ile uyuşmuyor | reddedilir |

### KDF politika sınırları (production)

| Parametre | Alt sınır | Üst sınır |
|---|---:|---:|
| `kdf_time_cost` | 3 | 10 |
| `kdf_memory_kib` | 65536 | 262144 |
| `kdf_parallelism` | 1 | 4 |

Üst sınırlar, kötü niyetli bir dosyanın gigabaytlarca RAM ayırtmasını veya
dakikalarca CPU harcatmasını engeller. **Alt** sınırlar da aynı derecede
önemlidir: ucuz parametrelerle üretilmiş bir dosya production tarafından
açılamaz, böylece test amaçlı düşük maliyet bir downgrade yoluna dönüşemez.

Argon2 bazı parametre **kombinasyonlarını** ayrıca reddeder (örneğin
`memory_cost < 8 x parallelism`). Bu durum da aynı fail-closed hataya
eşlenir; kütüphane istisnası dışarı sızmaz.

---

## 6. Hata sözleşmesi

Yanlış parola, kurcalanmış `ciphertext` ve kurcalanmış authenticated header
**aynı** HTTP durumunu (400) ve **aynı** Türkçe mesajı döndürür:

> Recovery dosyasi acilamadi. Parola yanlis olabilir veya dosya degistirilmis olabilir.

**Zamanlama eşitliği iddia edilmez.** Argon2id ve AEAD doğrulamasının veriye
bağlı zamanlaması vardır ve bunu kontrol etmiyoruz. Verilen garanti tek bir
*dış hata sözleşmesidir*, zamanlama kanalı kapatma değildir.

---

## 7. Saklanan metadata

Dosya üretildiğinde SQLite'a **yalnız** şunlar yazılır:

- Dosyanın SHA-256 fingerprint'i (secret değildir)
- KDF adı ve parametreleri
- Oluşturulma ve doğrulanma zamanları

**Ciphertext ve parola veritabanına asla yazılmaz.**

---

## 8. Kullanıcı sorumluluğu

- En az **iki bağımsız çevrimdışı kopya** alın.
- Dosyayı ve parolayı **ayrı** yerlerde saklayın.
- Parola kaybolursa kimlik **geri getirilemez**; `did:key` için gerçek bir
  key rotation yoktur.
- Kimliği revoke etmek **mevcut recovery dosyalarını geçersizleştirmez**.
