# technocore-conform

Technocore **uygunluk (conformance)** paketi — sweep, canonical string,
`did:key` türetimi, Ed25519 imzalama ve doğrulama.

> **Durum: PLACEHOLDER.** Aşama 1'de yalnız **paket sınırı** kurulmuştur.
> Sweep, DID veya imza kodu **henüz yazılmamıştır**; Aşama 2B'de yazılacaktır.

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
| `vendor/technocore-reference/` import etmez | zorunlu |
| Lisans: MIT | zorunlu |

`station-api` bu pakete bağımlıdır; **tersi asla değildir**. Bağımlılık
`apps/station-api/pyproject.toml` içinde `[tool.uv.sources]` ile path
bağımlılığı olarak tanımlıdır.

## Lisans sınırı

Bu paket `docs/protocol-contract.md` içindeki **spesifikasyonu** uygular.
`vendor/technocore-reference/` altındaki Apache-2.0 kodundan **satır
kopyalanmaz**. O dizin yalnız `tests/conformance/` içinde bir test
**oracle'ı** olarak okunur.

## Aşama 2B kapsamı

| Yüzey | Kabul kriteri |
|---|---|
| Unicode sweep (Cc, Cf, Cs, Co, Zl, Zp -> boşluk, sonra trim) | AC-02, AC-03 |
| Mesaj canonical: `room` + `nonce` + `swept_text` | AC-05 |
| Note canonical: `namespace` + `key` + `nonce` + `swept_value` | AC-05 |
| `did:key` base58btc/multicodec üretme ve çözme | AC-01 |
| Ed25519 imzalama, padding'siz base64url (86 karakter) | AC-04 |
| Bağımsız doğrulayıcı | AC-05 |
| CLI yüzeyi | — |

Aşama 2B'de eklenecek tek runtime bağımlılığı: `cryptography` (Ed25519).
