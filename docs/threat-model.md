# Tehdit modeli

> Ana karar kaynağı: [`../Technocore-Station-Proje-Kunyesi.md`](../Technocore-Station-Proje-Kunyesi.md) §17
> İlgili: [`../SECURITY.md`](../SECURITY.md) · [`security-invariants.md`](security-invariants.md) · [`identity-lifecycle.md`](identity-lifecycle.md)

Bu belge, ürünün neyi savunduğunu ve **neyi savunmadığını** açıkça söyler.
İkincisi en az birincisi kadar önemlidir: savunulmayan bir şeyi savunuluyor
gibi göstermek, kullanıcının yanlış bir güvenle davranmasına yol açar.

---

## 1. Varlıklar

| Varlık | Hassasiyet | Nerede |
|---|---|---|
| **Secret seed** (32 bayt) | Kritik | Yalnız DPAPI kasa dosyası |
| Recovery parolası | Kritik | Hiçbir yerde saklanmaz |
| Kasa parolası | Kritik | Hiçbir yerde saklanmaz |
| `.tcrec` dosyası | Yüksek | Kullanıcının seçtiği yer |
| Oturum cookie / CSRF | Orta | Yalnız process memory |
| Public DID / fingerprint | Yok (public) | SQLite, UI |

---

## 2. Bu ürünün **savunmadığı** durumlar

Bunlar kapsam dışıdır. Ürün bunlara karşı koruma **iddia etmez**.

### 2.1 Aynı Windows kullanıcısı olarak çalışan malware
DPAPI current-user kapsamında çalışır. Sizin hesabınızda kod çalıştırabilen
bir program, DPAPI'yi **sizin adınıza** çağırabilir.

> **DPAPI, aynı Windows kullanıcısı olarak çalışan malware'e karşı mutlak bir
> koruma değildir.**

`dpapi+passphrase` modu bu senaryoyu **azaltır**: saldırganın ayrıca parolayı
da elde etmesi gerekir. Ortadan kaldırmaz.

### 2.2 Keylogger ve debugger
Aynı kullanıcı bağlamında çalışan bir keylogger parolanızı yazarken
yakalayabilir; bir debugger süreç belleğini okuyabilir. **Her ikisi de kapsam
dışıdır.**

### 2.3 Python bellek temizliği
Seed kullanım sonrası `bytearray` üzerinde sıfırlanır, ancak **Python belleği
güvenilir biçimde sıfırlanamaz**. CPython değeri tahsis veya çöp toplama
sırasında kopyalamış olabilir. Bu bir en-iyi-çaba önlemidir, garanti değildir.

### 2.4 Zayıf recovery parolası
`.tcrec` dosyasının güvenliği **tamamen recovery parolasının gücüne
bağlıdır**. Argon2id (64 MiB, 3 iterasyon) kaba kuvveti pahalı kılar; zayıf
bir parolayı güçlü yapmaz.

### 2.5 Kötü niyetli tarayıcı uzantısı
Host izni verilmiş bir uzantı, sayfanın DOM'unu ve isteklerini görebilir.
Uzantıya karşı tam bir savunma yoktur.

### 2.6 Diğerleri
- Resmî FLOP/Technocore domain'inin ele geçirilmesi.
- Güvenilen bir upstream paketin ele geçirilmesi (supply-chain).
- Kullanıcının manuel port yönlendirmesi yapması.
- Yedeklerde, gölge kopyalarda veya dosya sistemi günlüğünde kalan izler
  (revoke bir **güvenli disk silme değildir**).

---

## 3. Savunulan tehditler ve karşılıkları

| Tehdit | Karşılık | Kalan risk |
|---|---|---|
| Seed'in frontend'e/response'a sızması | Allow-list response modelleri, OpenAPI taraması, canary seed testi (AC-06) | Coding agent testi de değiştirebilir; insan review'u zorunlu |
| Seed'in loga sızması | Zorunlu redaksiyon filtresi, `access_log=False`, exception metni testi | Bilinmeyen bir format kaçabilir |
| Kasa dosyasının başka makineye kopyalanması | DPAPI current-user kapsamı | Aynı kullanıcı olarak çalışan saldırgan |
| Kasa dosyasının başka kullanıcı tarafından okunması | Protected DACL: yalnız current user ve SYSTEM; Windows API ile uygulanır ve okunarak doğrulanır | Yönetici hakları olan saldırgan |
| `.tcrec` çalınması | Argon2id + ChaCha20-Poly1305 | Zayıf parola |
| `.tcrec` kurcalanması | Header alanları AAD; her değişiklik AEAD'i kırar | — |
| Hostile `.tcrec` ile kaynak tüketimi | KDF parametreleri **türetmeden önce** alt/üst sınırlarla doğrulanır; dosya 64 KiB ile sınırlı | — |
| Yanlış parola / kurcalama ayrımı | Tek dış hata sözleşmesi (aynı durum ve aynı mesaj) | **Zamanlama eşitliği iddia edilmez** |
| Yarım yazma / orphan kayıt | Atomik yazma ve iki yönlü rollback | — |
| Path traversal ile kasa yolu | Identity id uygulama tarafından üretilir ve 32-hex olarak doğrulanır; yol HTTP girdisinden türetilmez | — |
| Raw seed'in HTTP'ye girmesi | Böyle bir endpoint **yoktur**; import yalnız yerel CLI | — |
| Seed/parolanın shell geçmişine düşmesi | CLI argümanı değil; `getpass` | — |
| CSRF / DNS rebinding / cross-origin | Aşama 1 korumaları değişmeden yürürlükte | Kötü niyetli uzantı |
| Doğrulanmamış kimlikle dış yazma | Merkezî write gate; recovery doğrulanmadan kapalı | — |
| Uygulanmamış gereksinimlerin geçmiş sayılması | `not_implemented` durumu asla `passed` sayılmaz | — |

---

## 4. Kimlik ne kanıtlar, ne kanıtlamaz

Bir `did:key`, ilgili özel anahtara sahip olduğunuzu gösterir. Bundan
fazlasını **kanıtlamaz**:

> **DID; gerçek kimliğinizi, dürüstlüğünüzü, bir içeriğin doğruluğunu, token
> sahipliğini veya herhangi bir airdrop hakkını kanıtlamaz.**

Ürün hiçbir yerde airdrop garantisi, uygunluk skoru veya tahsis iddiası
üretmez.

---

## 4.1 Uygunluk ne kanıtlar, ne kanıtlamaz (Aşama 2B)

| Kanıtlar | Kanıtlamaz |
|---|---|
| Bu yapının **pinlenmiş referans commit** ile aynı sweep/canonical/imza davranışını ürettiği | Canlı Technocore sunucusunun hâlâ aynı protokolde olduğu |
| İmzanın canonical string'i kapsadığı | İmzanın JSON request gövdesinin tamamını kapsadığı |
| Anahtar sahipliği (`did:key`) | Gerçek kimlik, dürüstlük, içerik doğruluğu, güvenilir zaman |
| Çalışma zamanı Unicode veritabanının vektörlerle aynı sürümde olduğu | Kapsanmayan bir Unicode sürümünde davranışın aynı kalacağı |

Sunucu güncelliği *manifest drift* kontrolüdür ve **Aşama 3**'e aittir. İki
iddianın karıştırılması, write gate'in önlemek için var olduğu yanlışın ta
kendisidir.

## 5. Aşama 2 kapsam beyanı

- **Technocore'a hiçbir okuma veya yazma isteği gönderilmedi.** Üründe giden
  bir HTTP istemcisi yoktur; bir test bunu kaynak taramasıyla doğrular.
- **Hiçbir LLM veya model adaptörü kullanılmadı.** Vault paketi, gelecekteki
  bir model yüzeyinin erişemeyeceği bir paket sınırıdır.
- Temiz profilden kurtarma **aynı Windows hesabı içinde bağımsız bir veri
  kökü** ile doğrulanmıştır. **Farklı bir Windows hesabında test
  edilmemiştir**; öyleymiş gibi raporlanmaz.
