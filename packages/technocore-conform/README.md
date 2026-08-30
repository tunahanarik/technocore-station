# technocore-conform

Technocore **uygunluk (conformance)** paketi — sweep, canonical string,
`did:key` türetimi, Ed25519 imzalama ve doğrulama.

> **Durum: UYGULANDI (Aşama 2B).** Ayrıntılı sözleşme:
> [`../../docs/conformance.md`](../../docs/conformance.md).

Bu paket **hiçbir ağ isteği yapmaz** ve Technocore'a bağlanmaz.

## Neden ayrı bir paket?

Bu paket, protokol doğruluğunun tek sorumlusudur ve bunu **uygulamadan
bağımsız** olarak yapar. Böylece:

- Resmî referansa karşı diferansiyel test ucuzdur.
- Aynı kod başka bir istemcide yeniden kullanılabilir.
- FastAPI/SQLite/Windows detayları protokol mantığına sızmaz.

## Paket sınırı (değişmez)

| Kural | Durum |
|---|---|
| `station_api` import etmez | zorunlu |
| FastAPI, SQLAlchemy, SQLite import etmez | zorunlu |
| Windows'a özgü modül import etmez | zorunlu |
| Ağ modülü (`socket`, `urllib`, `httpx`) import etmez | zorunlu |
| `vendor/technocore-reference/` import etmez | zorunlu |
| Import anında disk okumaz, self-test çalıştırmaz | zorunlu |
| Lisans: MIT | zorunlu |

`station-api` bu pakete bağımlıdır; **tersi asla değildir**. Tek runtime
bağımlılığı `cryptography`'dir (Ed25519). PyNaCl yalnız **test** bağımlılığıdır
ve production import grafiğine girmez.

## Lisans sınırı

Bu paket [`../../docs/protocol-contract.md`](../../docs/protocol-contract.md)
içindeki **spesifikasyonu** uygular. `vendor/technocore-reference/` altındaki
Apache-2.0 kodundan **satır kopyalanmaz**. O dizin yalnız
`tests/conformance/` içinde bir test **oracle'ı** olarak okunur ve wheel/sdist
içine girmez.

## Kullanım

```python
from technocore_conform import canonical_message, sign_payload, verify_payload

payload = canonical_message(room="test-room", nonce="1", text="  merhaba  ")
payload.canonical        # 'test-room|1|merhaba'  (swept metin)
payload.changed_by_sweep # True

signature = sign_payload(payload, seed=seed_bytes)   # 32 ham bayt
verify_payload(payload, did=did, signature=signature)
```

`sign_payload` **yalnız** bir `CanonicalPayload` alır. Serbest bir string
imzalayan public bir kolay yol bilinçli olarak yoktur: ham metni imzalamak
sunucudan 403 döndürür ve saklanan kayda karşı yeniden doğrulanamaz.

## Modüller

| Modül | Sorumluluk |
|---|---|
| `sweep` | Tek satır süpürme, mesaj/note limitleri |
| `names` | `room` / `namespace` / `key` allow-list'i |
| `nonce` | Nonce wire biçimi (durum tutmaz) |
| `canonical` | `CanonicalPayload` ve canonical string |
| `did` | `did:key` üretme ve çözme |
| `signature` | Ed25519 imzalama, doğrulama, canonical base64url |
| `selftest` | Runtime uygunluk self-test'i (fail-closed) |
| `cli` | `technocore-conform` komut satırı |
| `errors` | Ayrıştırılabilir, içerik sızdırmayan hata tipleri |

## CLI

```bash
technocore-conform self-test
```

Metin **stdin'den** okunur. **`sign` komutu yoktur**; seed, parola veya
seed-dosyası argümanı da yoktur. Ayrıntı: `docs/conformance.md` §9.

## Kabul kriterleri

| Yüzey | Kriter | Durum |
|---|---|---|
| `did:key` resmî script ile karakter karakter aynı | AC-01 | karşılandı |
| 10.000+ Unicode girdide sweep resmî `clean_text` ile aynı | AC-02 | karşılandı |
| Sweep idempotent | AC-03 | karşılandı |
| İmza 86 karakter padding'siz base64url | AC-04 | karşılandı |
| Mesaj ve note imzaları bağımsız doğrulayıcıdan geçer | AC-05 | karşılandı |

## Geliştirme

```bash
uv run --directory ../../apps/station-api ruff check .
```
