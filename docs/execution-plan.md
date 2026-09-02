# Uçtan uca yürütme planı

> Kaynak: `Technocore-Uctan-Uca-Claude-Promptu.md` (2 Eylül 2026, kullanıcı
> tarafından verildi). Bu dosya ve [`execution-state.json`](execution-state.json)
> her compaction/resume sonrasında **gerçek Git/GitHub durumuyla birlikte**
> okunur. Kayıt ile gerçek durum çelişirse Git/GitHub kanıtı esastır.

## Görev tanımı

Technocore Station'ı A→J paketleri boyunca uygulamak; her paket için otomatik
test + bağımsız inceleme + PR + **normal merge**, sonra kendiliğinden sıradaki
pakete geçiş. Hedef durum: `CODE_COMPLETE_USER_ACCEPTANCE_PENDING`.
Manuel tarayıcı QA, görsel inceleme ve gerçek kullanıcı testi **kullanıcıya
bırakılmıştır** ve bu döngüde yapılmaz.

## Paketler

| Paket | İçerik | Kabul ölçütü (özet) |
|---|---|---|
| A | Başlangıç, kapsam eki (ADR), yürütme kaydı, tekrarlanabilir CI | Baseline yeşil; CI PR üzerinde gerçekten çalışıyor ve **fail edebildiği** negatif örnekle kanıtlı |
| B | Aşama 3.1 son kapanış | 12 yeni sınır türü × 2 lane önce mevcut kodda üretilir, sonra yapısal çözümle kapanır; eski 16+22 korunur |
| C | Dashboard kabuğu ve hata sözleşmesi | Sol menü (9 bölüm), `docs/ui-action-map.md`, hata/loading/timeout sözleşmesi; component testleri |
| D | Composer & Participation | Onay→imza→ayrı gönderim onayı; transaction'lı monoton nonce; `outcome_unknown`; canlı yazma yok |
| E | Evidence & Audit | Exact yakalama, 4 güven seviyesi, ayrı DPAPI zarfında HMAC, onaylı deterministik export |
| F | Proje/görev modülü temeli | Compile-time registry, durum makineleri, kanıt-türevli durumlar |
| G | OpenCode Go bağlantısı | DPAPI'de credential, katalogdan model listesi, 3 protokol adapter'ı, redaction; gerçek harcama yok |
| H1 | Work Scan | Kapalı salt-okuma kaynak registry'si, kaynak+başarı koşullu öneriler; Kibble doğrulanamazsa "destek doğrulanamadı" |
| H2 | Agent çalışma ortamı + Activity Desk | Tipli state machine, şemalı araçlar, bütçe/izin sınırı, izolasyon yoksa `execution_unavailable` |
| H3 | Proof Workspace | Artifact+hash+test kanıtı+eksikler; dış paylaşım ayrı tek kullanımlık onay |
| I | Windows paketleme | ADR'li paketleyici seçimi, izole doğrulama, SHA-256, unsigned uyarısı |
| J | Bütünleşik inceleme, temizlik, kılavuz | `docs/kullanim-kilavuzu.md`, `docs/kullanici-kabul-listesi.md`, tam suite son head'de |

Büyük paketler anlamlı alt PR'lara bölünebilir (kontrolsüz dev PR yok; satır
başına PR de yok). D ile E arasında uygulama gerçek kullanıma hazır ilan
edilmez; gönderim işlevi E tamamlanana kadar üretim akışında kapalı kalır.

## Değişmez sınırlar (her pakette geçerli)

- Gerçek DID/kasa/recovery/parola/veri dizini okunmaz, değiştirilmez, istenmez.
- Kullanıcı auth dosyalarından anahtar çıkarılmaz; gerçek anahtar bu oturuma istenmez.
- Technocore'a canlı write/claim/attestation yok; testler geçici `STATION_DATA_DIR` + TEST-ONLY kimlik.
- Gerçek LLM inference harcaması yok; provider'lar fixture/mock ile test edilir.
- Tag/release/deploy/ödeme yok; branch protection aşılmaz; PR #7 ve eski PR'lara dokunulmaz.
- Güvenlik testleri silinmez/skip edilmez/gevşetilmez.
- Squash/rebase/force yok; yalnız normal merge commit; feature branch'ler korunur.
- AI incelemesi "insan güvenlik incelemesi" diye adlandırılmaz; insan incelemesinin
  ertelendiği kalan risk olarak her raporda görünür.

## Döngü kuralları

- Aşama durumları: `planned → implementing → testing → reviewing →
  ready_to_merge → merged` ve `blocked`.
- Aynı kök nedende en fazla **3** sonuçsuz düzeltme turu; sonra `blocked` +
  kayıt. Yeniden deneme yeni aşama adıyla gizlenmez.
- Merge'den hemen önce head/base SHA, check'ler ve review thread'leri yeniden
  kontrol edilir; kod değiştiyse eski test/review yeni head'e onay sayılmaz.
- Her merge sonrası: ebeveyn sayısı, local/origin/GitHub HEAD eşitliği, temiz
  ağaç doğrulanır ve `execution-state.json` güncellenir.
- Aşama raporları `docs/verification/` altına konur (sır içermez).
