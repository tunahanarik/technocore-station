# ADR-0006 — Tarayıcı QA kapsama alındı (4 Eylül 2026)

Durum: **kabul edildi** · Yetki: kullanıcının 4 Eylül 2026 tarihli açık talimatı

## Neyi tersine çeviriyor

ADR-0001 §4 ve uçtan uca promptun §7.2'si tarayıcı QA'sını bu döngüde
**yasaklıyordu**: "Tarayıcı açıp tıklama turu yapma; Playwright/Selenium/
Cypress ile yeni browser QA … çalıştırma. Bütün manuel kabul maddelerini
kullanıcı kılavuzuna taşı."

Kullanıcı 4 Eylül 2026'da bunu açıkça değiştirdi: *"playwright ve chrome dev
pluginlerini … yükle ve ui testlerini de yap"*.

**Karar:** Tarayıcı tabanlı UI testleri kapsama alınır. Bu, önceki kararın
sessiz bir ihlali değil, kullanıcının yetkisiyle yapılmış **kayıtlı bir
tersine çevirmedir**. Paket C/D/E/F raporlarındaki "tarayıcı QA yok, ADR-0001
m.4" cümleleri geçmişte doğruydu ve öyle kalır; bu tarihten sonrası için
geçerli değildir.

## Kapsam ve sınırlar

1. **Ekleme, değiştirme değil.** Mevcut Vitest/jsdom bileşen testleri
   korunur ve silinmez. Tarayıcı testleri onların yerine geçmez; jsdom'da
   kanıtlanamayan şeyleri kanıtlar: gerçek odak sırası, gerçek klavye
   gezinmesi, `URL.createObjectURL` ile indirme yolu, gerçek
   `Content-Disposition` gidiş-dönüşü, CSP altında HeroUI/React Aria inline
   style hash'i (risk A1-R1).
2. **Gerçek dış ağ yok.** Testler yerel backend'e karşı koşar; geçici
   `STATION_DATA_DIR` kullanılır. `technocore.chat` ve `opencode.ai`'ye
   hiçbir istek gitmez. Suite'in autouse ağ kesicisi backend tarafında
   yürürlükte kalır.
3. **Gerçek kimlik materyali yok.** TEST-ONLY fixture'lar; gerçek DID, seed,
   vault parolası, recovery dosyası veya gerçek API anahtarı kullanılmaz.
   Lobby hiçbir testte hedef olamaz.
4. **Gerçek harcama yok.** OpenCode akışları sahte transport veya sahte
   backend yanıtlarıyla sürülür.
5. **Yeni bağımlılık kuralı aynen geçerli:** gerekçe + lisans yazılır,
   `README.md` bağımlılık tablosuna satır eklenir, lockfile güncellenir.
6. **CI kararı ayrıca verilir.** Tarayıcı testleri CI'a eklenecekse indirilen
   tarayıcı sürümü pinlenir ve iş süresi/kararlılığı gözetilir; kararsız
   (flaky) bir test yeşil sayılmaz ve gizlenmez.

## Değişmeyenler

Bu ADR hiçbir güvenlik değişmezini gevşetmez. INV-01…09 aynen geçerlidir.
Tarayıcı testlerinin varlığı **insan güvenlik incelemesinin** yerine geçmez;
o hâlâ ertelenmiş kalan risktir (ADR-0001 §5). Bir tarayıcı testinin geçmesi
"gerçek kullanıcı kabulü" anlamına gelmez — kabul kullanıcınındır (Paket J).
