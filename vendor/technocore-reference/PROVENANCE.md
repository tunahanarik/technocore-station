# Vendor provenance — `technocore-reference`

Bu dizin **resmî FLOP Labs kaynak kodunun pinlenmiş bir kopyasıdır**. Yalnızca
test oracle'ı olarak kullanılır. Ürün runtime paketine girmez.

## Kaynak

| Alan | Değer |
|---|---|
| Repo URL | https://github.com/flop-labs/technocore-chat |
| Branch | `main` |
| Pinlenmiş commit SHA | `7707cb63ebf638e8ef0cf59d1364818b9fef7d24` |
| Commit tarihi (UTC) | 2026-08-30T11:04:44Z |
| Alınma tarihi (UTC) | 2026-08-30 |
| Alınma yöntemi | `https://raw.githubusercontent.com/flop-labs/technocore-chat/<SHA>/<path>` |
| Upstream lisans | Apache License 2.0 |
| Upstream telif | Copyright 2026 FLOP Labs |

Commit permalink:
<https://github.com/flop-labs/technocore-chat/tree/7707cb63ebf638e8ef0cf59d1364818b9fef7d24>

## Alınan dosyalar ve SHA-256

| Dosya | SHA-256 | Boyut (bayt) |
|---|---|---:|
| `LICENSE` | `9a199b2f98908456e0714c49a9d0ae7b01d43eb85c0005a040a974db5faa982a` | 11340 |
| `NOTICE` | `526c7eb0e9086a44125bab1455a58225e097c2980f32b05de377a1ea25c02563` | 182 |
| `scripts/sign.py` | `667e3d6cf48301d1b43f44c9b328d73ec1dbf413ddc89fcb740baf86f6406c15` | 7846 |
| `src/store.py` | `91decc7120befaae5c08b7bb7670d1c70dfe60a502605a43a2916043ece86314` | 119110 |

Makine-okunabilir liste: [`SHA256SUMS`](SHA256SUMS).

Doğrulama:

```bash
cd vendor/technocore-reference && sha256sum -c SHA256SUMS
```

## Değişmezler

1. **Bu dosyalar değiştirilmez.** Formatlanmaz, lint'lenmez, yeniden yazılmaz.
   Upstream'den birebir alınmıştır.
2. **Vendor kodu uygulama runtime paketine girmez.** `station-api` ve
   `station-web` bu dizinden import etmez. Yalnızca `tests/conformance/`
   altındaki diferansiyel testler bu dosyaları okur.
3. **Apache-2.0 satırları MIT kodumuza kopyalanmaz.** `technocore-conform`
   paketi spesifikasyonu bağımsız olarak uygular; upstream implementation
   satırları taşınmaz.
4. **Upstream `LICENSE` ve `NOTICE` korunur.** Kök `NOTICE` dosyası lisans
   haritasında bu dizini Apache-2.0 olarak işaretler.
5. **Commit SHA sabittir.** Yükseltme ayrı ve açık bir karar adımıdır; bu
   dosya ve `SHA256SUMS` birlikte güncellenir.

## Neden bu dosyalar?

| Dosya | Test oracle rolü |
|---|---|
| `scripts/sign.py` | `did:key` türetimi, canonical string ve Ed25519 imza biçiminin resmî referansı (AC-01, AC-04, AC-05) |
| `src/store.py` | `clean_text` Unicode sweep davranışının resmî referansı (AC-02, AC-03) |

Bu dosyalarda gözlenen canonical sözleşme (Aşama 2B'de test edilecek):

```text
message:  <room>|<nonce>|<text-after-sweep>
note:     <ns>|<key>|<nonce>|<value-after-sweep>
```

> Not: `scripts/sign.py` içindeki "passphrase → SHA-256 → seed" yolu
> **Station'da uygulanmaz**. Künye §8.3 paroladan seed türetmeyi açıkça
> yasaklar. Station yalnız `secrets.token_bytes(32)` veya kullanıcının
> 64-hex seed'ini kullanır.
