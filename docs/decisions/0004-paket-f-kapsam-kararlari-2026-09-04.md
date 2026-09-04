# ADR-0004 — Paket F kapsam kararları (4 Eylül 2026)

Durum: **kabul edildi** · Bağlam: uçtan uca prompt §10, künye Aşama 6

Paket F öncesi keşif yedi karar boşluğu ve bir belge tutarsızlığı çıkardı.
ADR-0001/0002/0003 gibi bu da künyeye üstündür (çelişkide ek geçerli) ve
**hiçbir güvenlik değişmezini gevşetmez**.

## 1. "Modül" ne demek — registry kaydı, dosya taşıma değil

**Keşif bulgusu:** `Proje 0` kod tabanında **hiç yok**. `apps/` ve
`packages/` altında `Proje 0` / `project_0` / `ProjectZero` için sıfır
eşleşme; ne bir `project` tablosu, ne bir bölüm kimliği, ne "tamamlandı"
işareti. Künye §7.2 m.8 bugün karşılanmamış.

Yol haritası "Proje 0 modül sınırına taşınmış" diyor; görevin kendisi ise
"**mevcut kayıt kimlikleri ve migration geçmişi bozulmasın**" diyor. Bu iki
cümle gerilimde ve keşif fiziksel taşımanın bedelini saydı: en az altı test
kırılır (`OUTBOUND_CLIENT_MODULES` `technocore/` dizinini **adıyla**
pinliyor, `test_write_gate.py` modül yollarını literal kullanıyor, üç yerde
`collect_route_paths` route kümesini denetliyor), ve karşılığında hiçbir
davranış kazanılmaz.

**Karar:** "Modül" = **derleme zamanında sabit bir registry kaydı**. Sorumlu
kod yerinde kalır; registry ona işaret eder. Proje 0 **taşınmaz**, registry'de
temsil edilir. Bu, deponun kendi yerleşik kalıbıdır: `sections.ts`,
`sources.py`/`write_targets.py`/`evidence_targets.py` ve `write_gate.py`'nin
hepsi "kayıt tek yerde, sahibi dağınık" biçiminde çalışır.

Yeni bir Python paketi **yalnız yeni görev kodu için** açılır
(`station_api/tasks/`). Diskten kullanıcı tanımlı plugin/import yükleme
**yoktur** ve bunu bir test sabitler.

## 2. Güvenilir çekirdek yeniden kullanılır, kopyalanmaz

Çekirdek bugün somut olarak beş nesnedir ve hepsi `app.py:create_app()`
içinde **tek örnek** kurulur: `conformance`, `technocore`,
`identity_service`, `evidence`, `compose`.

**Karar:** Görev servisi bağımlılıklarını constructor'dan alır — hiçbirini
kendi yaratmaz (`ComposeService`'in kalıbı). Üç kopyalama riski açıkça
yasaklanır:

- **Yeni HTTP istemcisi YOK.** `OUTBOUND_CLIENT_MODULES` üç modülde kilitli
  ve yorumu açık: "Dördüncü bir giriş, dördüncü bir giden yüzey demektir."
- **İkinci vault/signer yığını YOK.** ADR-0003 §6'daki ayrım geçerli: yalnız
  `dpapi.protect/unprotect`, `windows_acl`, `strict_json` ve `_atomic_write`
  **kalıbı** yeniden kullanılır.
- **İkinci gate YOK.** Görev kapısı `write_gate.evaluate()`'in **saf
  fonksiyon** kalıbını izler; o gate kopyalanmaz, yanına konur.

## 3. Dokuz durum tanımlanır; kaçının bugün **üretilebildiği** açıkça yazılır

Promptun saydığı dokuz durum (`suggested`, `awaiting_approval`, `running`,
`paused`, `blocked`, `failed`, `review_needed`, `ready_to_publish`,
`published`) tanımlanır ve **açık bir `ALLOWED_TRANSITIONS` tablosu** yazılır
— depoda bugün açık geçiş tablosu yok, doğrulama DB kısıtlarına ve
"başarısızlıkta ileri değil iptale git" kalıbına dağılmış durumda. Geçiş
saf bir fonksiyondur ve backend doğrular.

**Fakat dürüstlük gerektiren kısım:** dokuzunun hepsi bu sürümde
üretilebilir değil. `suggested` bir öneri üreticisi ister (H1);
`running`/`paused` bir yürütücü ister (H2). Bugün gerçekten türeyebilenler:
`awaiting_approval`, `blocked`, `failed`, `review_needed`,
`ready_to_publish`, `published`.

**Karar:** Üretici olmayan durumlar tanımlı kalır ama **hiçbir kod yolu
onları üretemez**, ve bunu bir test sabitler. Böylece gelecekteki bir paket
o durumu açarken **bilinçli** bir değişiklik yapmak zorunda kalır.
`CheckState.NOT_IMPLEMENTED`'ın "yapılmamış olan asla geçmiş sayılmaz"
kuralıyla aynı ruh: erişilemez bir durum, sessizce erişilebilirmiş gibi
durmaz.

## 4. Dört alan asla toplanmaz

Görev başarısı, test sonucu, kullanıcı kabulü ve public paylaşım **dört
ayrı alandır** ve tek bir boolean'a indirgenmez — `EvidenceRecord`'un dört
güven seviyesi kalıbı birebir uygulanır.

**Public paylaşım alanı bu pakette daima boştur.** Dış paylaşım H3'ün
(Proof Workspace) konusudur ve orada ayrı, tek kullanımlık bir onay ister.
F yalnız alanı açar; doldurmaz.

Bir durumun `ready_to_publish`'e geçmesi **gerçek kanıttan** türer: her
check kendi kanıtına (evidence kaydı, test sonucu kaydı, kullanıcı onay
kaydı) işaret eder ve **eksik check `NOT_IMPLEMENTED` raporlar, `PASSED`
değil**. "Sonuç dosyasının varlığı tek başına başarı değildir" kuralının
deponun kendi emsalleri var: `test_frontend_bundle.py` build çıktısının
varlığını yalnız başına bırakmıyor, `test_the_storage_scanner_would_catch_a_real_violation`
denetleyiciyi denetliyor, ve Paket E'nin koruması mutasyonla doğrulanıyor.

## 5. Deduplication: kaynak kimliği + içerik sürümü

`domain_digest(b"technocore-station/task-source/v1", source_id,
content_sha256)` → `source_version_id`. Görev bu kimliğe bağlanır; içerik
değişince kimlik değişir ve **eski kanıt eşleşmez**.

Bu, `verdict_id`'nin fail-closed okumasının birebir uygulamasıdır:
"herhangi bir yeni kontrol, aynı protokolü değişmemiş bulsa bile yeni bir
kimlik üretir". Kaynak kimliği registry enum'undan gelir, çağıranın verdiği
serbest string'ten değil (`OfficialSourceSnapshot.source_id` kalıbı).

## 6. Restart uzlaştırması — okur, yazmaz

**Keşif bulgusu:** `WriteOutcomeValue.IN_FLIGHT` yazılıyor ama **hiçbir
startup hook'u onu okumuyor**; `app.py`'de `lifespan`/`on_event` yok. Yani
çökmüş bir gönderim sonsuza dek `in_flight` kalıyor.

**Karar:** F bir **salt-okuma** başlangıç taraması ekler: yarım kalmış
kayıtlar kullanıcıya görünür olur. Hiçbir otomatik dış yazma, hiçbir
otomatik devam yoktur. Devam kararı kullanıcınındır ve gönderim anındaki
kontroller yeniden koşar. Bu, ADR-0003 §4'ün daralmasıyla aynı biçimdir:
"uzlaştırma = yakalama denenebilir, yeniden gönder değil".

## 7. Bütçe bu pakette yok

Gereksinim "devam kararı onay/**bütçe**/izinlerle uzlaştırılsın" diyor ama
depoda bütçe kavramı yok (`budget` yalnız HTTP timeout bütçesi olarak
geçiyor). Yürütme planı bütçe/izin sınırını **H2**'ye, harcama bağlamını
**G**'ye koyuyor.

**Karar:** F bütçe alanı **açmaz** ve bütçe varmış gibi davranmaz. Bu yarım
gereksinim G/H2'ye **görünür şekilde** ertelenir — sessizce düşürülmez.
Onay ve izin yarısı F'de karşılanır.

## 8. Şemalar `schemas.py`'de kalır

**Keşif tuzağı:** `tests/security/test_no_secret_fields.py`'nin üç testi de
`vars(schemas)` ile **yalnız `station_api/schemas.py`'yi** tarıyor. Paket F
Pydantic modellerini yeni bir modüle koyarsa bu üç koruma **sessizce kapsam
dışı kalır** — sızıntı değil ama koruma kaybı, ve tam da bu projenin
yakalamak istediği türden bir sessiz gerileme.

**Karar:** Görev şemaları `schemas.py`'de kalır. Alternatif olarak testler
genişletilebilir; genişletme kabul edilir, **daraltma edilmez** (INV-06).

## 9. Görevler bölümü kapalı kalır

`sections.ts`'in kendi kuralı: "bir özellikmiş gibi davranan boş bir bölüm,
bu uygulamanın göstermeyi reddettiği tam olarak şeydir."

**Karar:** `work-scan`, `tasks` ve `activity` `ready: false` kalır. F bir
temel paketidir; görünür bir görev yüzeyi H1/H2'nindir. Yeni HeroUI bileşeni
de eklenmez (küme 11'de kilitli).

## 10. `docs/architecture.md` gerçekle uzlaştırılır

Belge hâlâ "Durum: Aşama 2 — Conformance, Technocore istemcisi ve Evidence
katmanları henüz **yoktur**" diyor. Üçü de var ve merge edilmiş durumda.
Paket F bir modül sınırı paketi olduğu için mimari belgesinin yanlış olması
kabul edilemez; güncellenir.

## 11. Değişmeyenler

Yeni bağımlılık yok. Yeni giden istemci yok. Yeni HeroUI bileşeni yok.
Migration `0007` (`down_revision = "0006"`), tek head korunur; mevcut tablo
adları ve kayıt kimlikleri **değişmez**. Gerçek servise istek yok. İnsan
güvenlik incelemesi ertelenmiş kalan risktir (ADR-0001 §5).
