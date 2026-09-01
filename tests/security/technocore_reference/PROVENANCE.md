# Üretilmiş Technocore referans belgeleri

Bu dizindeki iki JSON dosyası **elle yazılmamıştır**. Pinlenmiş resmî
üreticinin (`vendor/technocore-reference/src/manifest.py`) çalıştırılmasıyla
üretilmiştir. Aşama 3 fixture'ı canlı servisten okunarak elle yazılmıştı ve
imzalı lane'in şemasını yanlış konuma koyuyordu; elle yazılmış bir fixture
yalnız "okuyuşum ile kodum birbiriyle uyumlu" iddiasını kanıtlayabilir.

## Kaynak

| Alan | Değer |
|---|---|
| Upstream repo | https://github.com/flop-labs/technocore-chat |
| Pinlenmiş commit | `7707cb63ebf638e8ef0cf59d1364818b9fef7d24` |
| Üretici dosya | `vendor/technocore-reference/src/manifest.py` |
| Sürüm kaynağı | `vendor/technocore-reference/pyproject.toml` → `project.version` |
| Üretilen sürüm | `0.10.0` |

Pin **değişmemiştir**. Aşama 3.1'de vendor dizinine yalnız aynı commit'ten üç
kaynak dosya (`manifest.py`, `didkey.py`, `config.py`) ve `pyproject.toml`
eklenmiştir; ayrıntı `vendor/technocore-reference/PROVENANCE.md`.

## Üretme komutu

```bash
uv run --directory apps/station-api pytest ../../tests/conformance/test_manifest_oracle.py -q
```

Bu test belgeleri yeniden üretir ve saklanan baytlarla **bayt bayt**
karşılaştırır. Saklanan kopyayı elle düzenlemek testi kırar; testi geçirmenin
tek yolu üreticinin gerçekten o baytları üretmesidir.

Yeniden yazmak gerekirse aynı iki fonksiyon kullanılır:
`tests.conformance.manifest_oracle.generate_documents` ve `serialise`.

## Dosyalar ve SHA-256

| Dosya | SHA-256 | Boyut (bayt) |
|---|---|---:|
| `openapi.json` | `8c008762ee6c4b65581dd0cc4f85ed48c58203e0e7906e3abfa29e6241a4c43a` | 85536 |
| `agent.json` | `282d74ef289461cb8985b9d493826f9a6c16fd92a9f60e5f9c5dffa4a428a31b` | 6588 |

Serileştirme: `json.dumps(..., indent=2, ensure_ascii=False, sort_keys=False)`
ve sonda tek satır sonu. `sort_keys=False` bilinçlidir — üreticinin kendi
anahtar sırası kaydın parçasıdır. Dosyalar `.gitattributes` içinde `-text`
olarak işaretlidir; aksi hâlde Windows checkout'u satır sonlarını değiştirir
ve bayt karşılaştırması taze bir klonda kırılır (Aşama 2B'de yaşandı).

## Projeksiyonun okuduğu JSON yolları

Aşağıdaki yollar bu belgelerde **doğrulanmıştır**. `sig` ve `nonce`
kısıtlarının `properties` altında değil, `dependentSchemas.did` altında
yayımlandığına dikkat: `properties.sig` yalnız bir `description` taşır.

### `openapi.json` — mesaj lane'i

Kök: `/paths/~1r~1{room}/post/requestBody/content/application~1json/schema`

| JSON Pointer (kökten sonrası) | Değer |
|---|---|
| `/properties/did/pattern` | `^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$` |
| `/properties/did/minLength`, `/properties/did/maxLength` | `56` (sayı) |
| `/properties/sig` | yalnız `description` — kısıt yok |
| `/properties/nonce` | yalnız `description` — kısıt yok |
| `/required` | `["text"]` — `sig`/`nonce` burada yok |
| `/dependentSchemas/did/required` | `["sig", "nonce"]` |
| `/dependentSchemas/did/properties/sig/type` | `string` |
| `/dependentSchemas/did/properties/sig/pattern` | `^[A-Za-z0-9_-]{85}[AQgw]$` |
| `/dependentSchemas/did/properties/sig/minLength`, `.../maxLength` | `86` (sayı) |
| `/dependentSchemas/did/properties/nonce/type` | `string` |
| `/dependentSchemas/did/properties/nonce/pattern` | `^[0-9]{1,19}$` |

### `openapi.json` — note lane'i

Kök: `/paths/~1kv~1{ns}~1{key}/post/requestBody/content/application~1json/schema`

Yapı mesaj lane'i ile aynıdır; tek fark `/required` = `["value"]`.

### `agent.json`

| JSON Pointer | Değer |
|---|---|
| `/identity/scheme` | `did:key` |
| `/identity/algorithms` | `["Ed25519"]` |
| `/identity/message_signature_payload` | `<room>\|<nonce>\|<text>` |
| `/identity/note_signature_payload` | `<namespace>\|<key>\|<nonce>\|<value>` |
| `/identity/signature_encoding` | `base64url, 86 characters, unpadded, and canonical: ...` |
| `/conventions/name_pattern` | `^[a-z0-9][a-z0-9_-]{0,47}$` |
| `/limits/message_chars` | `4096` (sayı) |
| `/limits/note_chars` | `8192` (sayı) |
| `/version` | `0.10.0` |

## Bu belgeler canlı servis değildir

Bunlar **pinlenmiş sürümün** (`0.10.0`) belgeleridir. Canlı servis daha yeni
olabilir ve 1 Eylül 2026 gözleminde öyleydi; ayrıntı
`docs/read-only-technocore.md` → "Canlı gözlem". Testler ağa çıkmaz; bilinen
pin ile canlı gözlem birbirine karıştırılmaz.
