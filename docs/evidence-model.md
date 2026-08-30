# Kanıt (Evidence) güven modeli

> Ana karar kaynağı: [`../Technocore-Station-Proje-Kunyesi.md`](../Technocore-Station-Proje-Kunyesi.md) §15.

**Uygulama durumu: HENÜZ UYGULANMADI.** Aşama 1'de Evidence kaydı, export
yakalama veya audit zinciri yoktur. Evidence & Sources yüzeyi boş durum
gösterir. Bu belge Aşama 5 için sözleşmeyi ve **dil kurallarını** sabitler.

Bu modelin amacı tek bir şeydir: **fazla iddia etmemek.** Ürün, imza
kanıtını sunucu gözlemiyle, sunucu gözlemini de güvenilir zamanla aynı
şeymiş gibi göstermez.

---

## 1. Dört seviye

| Seviye | Ad | Kanıtlanan | Kanıtlanmayan |
|---:|---|---|---|
| 1 | **İmza kanıtı** (cryptographic authorship) | DID özel anahtarına sahip tarafın belirli canonical string'i imzaladığı | Gerçek kimlik, içeriğin doğruluğu, zaman, anahtarın çalınmadığı |
| 2 | **Sunucu gözlemi** (server observation) | Station'ın belirli exact sunucu yanıtını / generation bilgisini gördüğü | Sunucunun dürüstlüğü, bağımsız üçüncü taraf gözlemi |
| 3 | **Yerel kayıt zamanı** (local receipt time) | Yerel makinenin o anda gösterdiği saat | Güvenilir zaman damgası |
| 4 | **Haricî anchor** (external anchoring) | Haricî bir tarafın hash'i belirli tarihten önce gördüğü | **MVP'de yoktur** — açıkça `null` |

Seviye 4 MVP'de **boştur** ve UI'da "yok" olarak, tahmin veya ima
üretmeden gösterilir.

---

## 2. Yasak ifadeler

Aşağıdaki ifadeler UI, API, log, belge ve dışa aktarım çıktılarında
**kullanılamaz**:

- "sunucu kanıtı"
- "değişmez kayıt"
- "güvenilir zaman kanıtı"
- "airdrop uygunluk kanıtı"

Doğru karşılıkları sırasıyla: *sunucu gözlemi* / *yakalanan kayıt*,
*yerel arşiv kaydı*, *yerel kayıt zamanı*, (karşılığı yoktur — üretilmez).

Audit zinciri için kullanılacak tek ifade: **"çevrimdışı değişikliğe karşı
tespit edici"**.

---

## 3. Export yakalama (Aşama 5)

Gönderimden hemen sonra resmî room export yüzeyi kullanılır:

1. Kendi kaydımızın **byte-exact JSONL satırı** bulunur.
2. **Room generation** kaydedilir.
3. Export akışının **hash'i** yerel bütünlük notu olarak saklanır.
4. Tam ring **varsayılan olarak saklanmaz**.
5. Kendi satırımız, çevresindeki **sınırlı pencere** ve **byte offset** tutulur.
6. Sonraki doğrulamada generation değişmişse kayıt
   **karşılaştırılamaz** olarak işaretlenir.

Bunun nedeni Technocore'un geçici bir ring buffer kullanmasıdır: mesaj
linki kalıcı kanıt oluşturmaz. Station kanıtı **yerelde** tutar.

---

## 4. Audit zinciri (Aşama 5)

- Audit satırları **HMAC-SHA256** zinciriyle bağlanır (`prev_mac` → `mac`).
- HMAC anahtarı **DPAPI** ile ayrı dosyada korunur.
- **Sağladığı güvence:** DB'yi HMAC anahtarı olmadan değiştiren çevrimdışı
  bir tarafın değişikliği tespit edilir.
- **Sağlamadığı güvence:** aynı Windows kullanıcısı olarak çalışan bir
  saldırgana karşı koruma, güvenilir zaman, veya üçüncü tarafa ispat.

---

## 5. Secret ayrımı

- Evidence kayıtlarında seed, private key, parola veya oturum bilgisi
  **bulunamaz**.
- Evidence ve log yazılmadan önce **secret-pattern taraması** uygulanır.
- Exact JSON request baytları saklanabilir; ancak *"imza bu JSON'u kapsıyor"*
  **denmez** (bkz. [`protocol-contract.md`](protocol-contract.md) §2.4).

---

## 6. Dışa aktarım

- Biçimler: **JSON** ve **Markdown**.
- Dışa aktarım **açık kullanıcı onayı** ister.
- Her kayıt, hangi seviyenin dolu hangisinin boş olduğunu **açıkça** taşır.
- Seviye 4 boşsa `null` yazılır; boş bırakılmaz veya uydurulmaz.

---

## 7. Kabul kriterleri

| ID | Kriter | Aşama |
|---|---|---|
| AC-14 | Gönderim sonrası exact export satırı ve generation kaydedilir | 5 |
| AC-17 | Technocore içeriğindeki HTML/URL aktif içerik olmaz | 3 |
| AC-18 | Airdrop garantisi veya claim iddiası UI'da bulunmaz | tüm aşamalar |
