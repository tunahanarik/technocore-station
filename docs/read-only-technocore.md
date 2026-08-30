# Salt okunur Technocore — Aşama 3

> Ana karar kaynağı: [`../Technocore-Station-Proje-Kunyesi.md`](../Technocore-Station-Proje-Kunyesi.md) §14.4, §16, §21.
> Sözleşme: [`protocol-contract.md`](protocol-contract.md) · Uygunluk: [`conformance.md`](conformance.md).
> Canlı origin: `https://technocore.chat` · Pinlenmiş referans: `7707cb63…`.

**Uygulama durumu: UYGULANDI (Aşama 3).** Station resmî kaynakları **yalnız
okur**. Bu aşamada hiçbir yazma yolu, imzalama endpoint'i, nonce rezervasyonu
veya gönderim yüzeyi yoktur.

---

## 1. En önemli iki cümle

> **Uygunluk** self-test'i bu yapının **pinlenmiş referans commit** ile aynı
> davrandığını gösterir.
> **Güncellik** denetimi **canlı sunucunun** hâlâ o protokolü yayımladığını
> gösterir.

Bunlar ayrı kontrollerdir ve ayrı kalır. Bir yapı, sunucunun çoktan terk
ettiği bir referansla kusursuz uyumlu olabilir — write gate'in yakalamak için
var olduğu durum tam olarak budur.

---

## 2. "GET güvenlidir" varsayımı neden yapılmadı

Technocore **GET üzerinden yazma** yapar:

```
GET /r/{room}/say-signed/{did}/{sig}/{nonce}/{text}
GET /kv/{ns}/{key}/set/{value}
```

Bu yüzden "yalnız GET gönderiyoruz" bir güvenlik özelliği **değildir**.
Güvenlik özelliği kapalı kaynak registry'sidir: istemci `SourceId` alır, URL
almaz. Kullanıcı girdisinden, request gövdesinden veya bir veritabanı
satırından giden adrese ulaşan hiçbir kod yolu yoktur.

---

## 3. İzin verilen kaynaklar

| Kaynak | Yol | Otorite | Verdict için zorunlu | Neden okunuyor |
|---|---|---:|:---:|---|
| `agent_manifest` | `/.well-known/agent.json` | 1 | **evet** | İmza payload biçimleri, imza kodlaması, nonce kuralı, isim kalıbı |
| `openapi` | `/openapi.json` | 1 | **evet** | İmzalı lane'ler, method/path, did/sig/nonce kalıp ve uzunlukları |
| `config` | `/config` | 1 | hayır | Kapasite ve rate değerleri; imza sözleşmesi taşımaz |
| `health` | `/healthz` | 1 | hayır | Canlılık; protokol sözleşmesi taşımaz |
| `manual` | `/llms.txt` | 2 | hayır | Prose; kanıt ve uyarı |
| `skill` | `/skill.md` | 2 | hayır | Prose; kanıt ve uyarı |

**Bu listede olmayan hiçbir yol istenmez.** `/rooms`, `/r/*`, `/kv/*`,
`/say*`, `/set*` ve `/r/events` bu aşamada kapsam dışıdır; oda, topic, mesaj
veya note içeriği **alınmaz**.

### Zorunlu / tamamlayıcı ayrımı neden var

Canlı gözlem: `/healthz` ve `/config` **aralıklı 503** dönüyor (aynı dakika
içinde hem 200 hem 503 gözlendi). Bu iki belge protokol sözleşmesi taşımaz.
Verdict'i onlara bağlamak, altyapı hıçkırığında write gate'in titremesi
demek olurdu. Bu yüzden verdict yalnız `openapi` ve `agent.json`'a dayanır;
diğerlerinin başarısızlığı kaydedilir ve kullanıcıya **gösterilir**, fakat
kapıyı belirlemez.

---

## 4. Ağ güvenliği

| Kural | Uygulama |
|---|---|
| Origin | Yalnız `https://technocore.chat` |
| Şema / host / port | HTTPS, tam eşleşme, yalnız varsayılan 443 |
| Reddedilenler | Alt domain, trailing dot, userinfo, fragment, farklı port, IP, path traversal |
| Redirect | **Takip edilmez**; 3xx bir hatadır |
| TLS | Doğrulama kapatılamaz; `verify` hiçbir yerde geçirilmez |
| Timeout | connect/read/write/pool ayrı ayrı sınırlı |
| Boyut | **Decompress edilmiş** bayt üzerinde, kaynak başına tavan |
| Retry | En çok 3 deneme; `Retry-After` üst sınırla |
| Kimlik | Cookie, authorization, DID, fingerprint, CSRF **yok** |
| User-Agent | Sabit; makine veya kullanıcı bilgisi içermez |
| Saklanan header | Yalnız `Content-Type`, `ETag`, `Last-Modified` |

---

## 5. Kritik protokol projeksiyonu

Ham hash karşılaştırması kullanılmaz: her yazım düzeltmesi "drift" derdi ve
bir hafta içinde göz ardı edilirdi. Bunun yerine **imzanın geçerliliğinin
bağlı olduğu** makine-okunabilir alanlar karşılaştırılır.

### Kritik (kapıyı kapatır)

| Alan | Kaynak | Konum |
|---|---|---|
| İmzalı mesaj lane'i | openapi | `paths./r/{room}.post` |
| İmzalı note lane'i | openapi | `paths./kv/{ns}/{key}.post` |
| DID kalıbı ve uzunluğu | openapi | `…schema.properties.did.pattern` / `.maxLength` |
| İmza kalıbı ve uzunluğu | openapi | `…schema.properties.sig.pattern` / `.maxLength` |
| Nonce kalıbı | openapi | `…schema.properties.nonce.pattern` |
| Note imza kalıbı | openapi | note lane'inin `sig.pattern` değeri |
| Zorunlu imza alanları | openapi | `did`, `sig`, `nonce` birlikte |
| Mesaj canonical biçimi | agent.json | `identity.message_signature_payload` |
| Note canonical biçimi | agent.json | `identity.note_signature_payload` |
| İmza kodlaması | agent.json | `identity.signature_encoding` |
| Kimlik şeması / algoritma | agent.json | `identity.scheme` / `identity.algorithms` |
| İsim kalıbı | agent.json | `conventions.name_pattern` |

**Kritiklik gerekçesi:** bu alanlardan biri değişirse Station'ın ürettiği bir
imza sunucu tarafından reddedilebilir veya — daha kötüsü — kullanıcının
onaylamadığı baytlar üzerinde kabul edilebilir.

### Uyarı (kapıyı kapatmaz)

`limits.message_chars`, `limits.note_chars`, `version`. Künye §14.4 gereği
limit/kapasite değişikliği **uyarı** üretir; imzayı geçersiz kılmaz.

### Karşılaştırma biçimleri

- `exact` — regex ve canonical biçim gibi, her farkın farklı sözleşme demek
  olduğu alanlar.
- `tokens` — makine gerçeği ifade eden prose. `signature_encoding` yeniden
  yazılabilir, fakat `unpadded` veya `86` kaybolursa sözleşme gerçekten
  değişmiştir.
- `contains` — liste üyeliği (`Ed25519`).

Alan sırası ve dokümantasyon değişiklikleri **drift sayılmaz**; bir test bunu
sabitler.

---

## 6. Durumlar ve fail-closed kuralı

| Durum | Anlamı | Gate |
|---|---|---|
| `never_checked` | Bu process'te henüz denetim yapılmadı | kapalı |
| `current` | Kritik alanların tamamı bekleneni karşılıyor | manifest yarısı açık |
| `drifted` | En az bir kritik alan değişmiş | kapalı |
| `unavailable` | Zorunlu bir belge alınamadı veya okunamadı | kapalı |

- **Her açılışta `never_checked`.** Uygulama açılışta hiçbir ağ isteği atmaz.
- Verdict **process içinde** yaşar. Veritabanındaki snapshot geçmişi
  kanıttır; eski bir kayıt kapıyı **açamaz**.
- Ağ/TLS/timeout/parse hatası `unavailable` üretir.
- Başarılı eski bir kontrol yeni başarısız kontrolü **örtmez**; yalnız "son
  başarılı kontrol" zaman damgası, başarısızlığın *yanında* gösterilir.
- Gate'i açan env değişkeni, debug bayrağı veya kullanıcı override'ı **yoktur**.
- API ve WriteGate **aynı verdict nesnesini** okur.

---

## 7. Snapshot ve veri modeli

İki tablo (migration `0003`):

- `manifest_check` — bir denetim koşusu: `state`, sayılar, gerekçeler, UTC
  zaman damgaları.
- `official_source_snapshot` — koşu başına kaynak başına bir satır: sabit
  kaynak kimliği, önceden tanımlı URL, authority, `fetched_at`, HTTP durumu,
  allow-list'li `Content-Type`/`ETag`/`Last-Modified`, **exact response
  baytlarının SHA-256'sı**, sınırlandırılmış ve sweep edilmiş alıntı, sonuç ve
  gerekçe.

- Keyfi header, cookie, seed, private key, parola veya vault yolu **yoktur**.
- Yazma tek transaction'dır; yarım kayıt bırakılmaz.
- Retention: son **50** koşu tutulur, eskiler snapshot'larıyla birlikte
  silinir.
- Raw gövde **API'den dönmez**.

---

## 8. Yerel API

| Yol | Method | Koruma | Ne yapar |
|---|---|---|---|
| `/api/technocore/status` | GET | session | Mevcut verdict'i okur; **ağa çıkmaz** |
| `/api/technocore/refresh` | POST | session + CSRF | Sabit registry'yi çalıştırır |

Refresh **gövde almaz**: verilecek bir URL, host, path veya method yoktur.

---

## 9. Bu aşamada bilinçli olarak yapılmayanlar

- Mesaj/note gönderme, imzalama endpoint'i, nonce rezervasyonu (Aşama 4).
- Compose yüzeyine textarea, imzala veya gönder düğmesi (Aşama 4).
- Lobby veya herhangi bir odaya katılım.
- Oda/topic/mesaj/note içeriği okuma.
- Evidence HMAC zinciri (Aşama 5).
- LLM veya Agent Runtime.
