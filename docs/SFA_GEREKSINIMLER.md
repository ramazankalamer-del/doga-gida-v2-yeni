# Doğa Gıda V2 — SFA gereksinimleri

Tarih: 2 Kasım 2026. Durum: kullanıcı talimatı ve kabul ölçütleri; bu belgenin varlığı özelliklerin uygulanmış olduğu anlamına gelmez.

## Bağlayıcı veri koruma kararı

- FastAPI ve SQLite altyapısı korunacak.
- Gerçek ürün kaynağı eski veritabanındaki **124 ürün**dür. V2'deki **5 örnek ürün gerçek ürün değildir** ve gerçek katalog, stok, ciro veya performansa karıştırılmayacak.
- İki mevcut veritabanında kayıt silinmeyecek, değiştirilmeyecek veya sıfırlanmayacak. Kaynak dosyalar korunacak; yedekler doğrulanacak.
- Kullanıcının son talimatı önceki birleştirme tercihini geçersiz kılar: **şu aşamada aktarım veya şema değişikliği yoktur**. Karşılaştırma, yedekleme, import/migration önerisi ve test planı sunulacak; kullanıcı onayı beklenecek.
- Veritabanları, yedekler, kullanıcı parolaları, oturumlar ve kurtarma bağlantıları GitHub'a yüklenmeyecek.
- Gerçek veri bulunmayan görseller açıkça demo işaretlenecek; eksik fiyat, fiziksel stok veya koli dönüşümü uydurulmayacak.

## 1. Sistem mimarisi

- SFA-01: Bilgisayarda modern yönetici paneli; telefonda mobil uyumlu pazarlamacı ekranı; depo ve sevkiyat ekranları.
- SFA-02: Ortak veritabanı/API, Türkçe arayüz, renkli grafikler ve rol bazlı ekranlar.
- SFA-03: Yetki denetimi API ve veri sorgusu seviyesinde zorunlu; düğmeyi gizlemek tek başına yeterli değil.
- Kabul: başka rolün/kişinin müşteri kimliğini doğrudan API'ye göndermek erişim sağlamaz.

## 2. Satış modeli — Pre-Sales

- SFA-04: Pazarlamacı sipariş alır; kontrollerden geçen sipariş depoya, ardından sevkiyata gider.
- SFA-05: İlk sürümde Van Sales yoktur.
- Kabul: sipariş, onay, hazırlama, sevkiyat ve teslim ayrı durumlardır; stok kontrolü ve rezervasyon/düşüm noktası açıkça tanımlanır.

## 3. Akıllı sipariş onayı

- SFA-06: Normal siparişler otomatik onaylanıp depoya iletilir.
- SFA-07: Kredi limiti aşımı, vadesi geçmiş borç, minimum fiyat altı satış veya yetki dışı özel iskonto yönetici onayı gerektirir. Bir siparişte birden fazla neden tutulabilir.
- SFA-08: Stok yetersizliğinde hazırlık durur ve stok kontrolü gerekir.
- SFA-09: Onay, ret ve düzeltmeler aktör, zaman, gerekçe ve önceki/sonraki değerlerle kaydedilir.
- Kabul: riskli sipariş onaylanmadan hazırlanamaz; eşzamanlı siparişler limiti veya stok rezervasyonunu aşamaz; onay anında risk yeniden kontrol edilir.

## 4. Müşteri yönetimi

- SFA-10: Her aktif müşteri tek bir pazarlamacıya atanır. Atamayı yalnızca yönetici değiştirir; tarihçe korunur.
- SFA-11: Pazarlamacı yeni müşteri oluşturabilir; yönetici onayına kadar müşteri pasiftir ve başlangıç kredi limiti **0 TL**'dir.
- SFA-12: Yönetici müşteri onayında kredi limiti belirler; limiti yalnızca yönetici değiştirebilir.
- SFA-13: Pazarlamacı limit artış talebi gönderebilir; karar ve eski/yeni limit saklanır.
- Kabul: onaysız/atanmamış müşteriyle saha satışı açılamaz; başka pazarlamacının ataması veya limiti değiştirilemez.

## 5. Cari hesap

- SFA-14: Pazarlamacı yalnızca yetkili müşterilerinin bakiye, kredi limiti, kullanılabilir limit, gecikmiş borç, fatura hareketi, tahsilat geçmişi ve ekstresini görebilir.
- SFA-15: Cari işlemler aynı işlem kimliğiyle tekrarlandığında ikinci kayıt oluşmaz.
- Kabul: sipariş/tahsilat/iade/iptal tutarları tutarlı; onay bekleyen sipariş riski, rezervasyon ve gerçekleşmiş cari borç birbirinden ayrılmıştır.
- Not: mevcut sipariş dökümü resmi fatura değildir. Fatura hareketi ile resmi e-belge entegrasyonunun kapsamı ayrı tanımlanacak.

## 6. Fiyatlandırma

- SFA-16: Liste ve minimum satış fiyatlarını yalnızca yönetici belirler.
- SFA-17: Pazarlamacı minimuma kadar fiyat değiştirebilir; minimum altı sipariş onaya düşer.
- SFA-18: Kampanya fiyatları, geçerlilik tarihleri ve yetkili özel iskonto sınırları tanımlanabilir; fiyat değişikliği geçmişi saklanır.
- SFA-19: Siparişteki fiyat/birim/iskonto ve hesaplama temeli saklanır; sonraki fiyat değişikliği geçmiş siparişi değiştirmez.
- Kabul: fiyatı tanımlanmamış ürün satılamaz. Eski 124 ürünün veritabanında fiyat alanı olmadığı için fiyatlar yönetici tarafından ayrıca doğrulanacak.

## 7. Sipariş türleri

- SFA-20: **Saha siparişi**, GPS ile doğrulanmış müşteri ziyareti sırasında oluşturulur.
- SFA-21: **Telefon siparişi**, pazarlamacı veya yetkili ofis personeli tarafından GPS olmadan oluşturulabilir.
- SFA-22: Telefon siparişi müşterinin bağlı olduğu pazarlamacının satış performansına yazılır; ziyaret performansına yazılmaz. Siparişi giren kullanıcı ayrıca saklanır.
- Kabul: giren kullanıcı, performans sahibi pazarlamacı, sipariş kanalı ve varsa ziyaret kimliği ayrı alanlardır.

## 8. GPS ziyaret sistemi

- SFA-23: Doğrulama mesafesi **100 metre**dir; konum doğruluğu ve koordinatlar saklanır.
- SFA-24: Pazarlamacı yalnızca kendi müşterisini ziyaret edebilir. Yönetici haftalık plan hazırlar; pazarlamacı günlük listeyi görür.
- SFA-25: Kendi müşterisine plan dışı ziyaret mümkündür; plan dışı ziyaret ayrı raporlanır.
- SFA-26: Başlangıç/bitiş zamanları ve doğrulama sonucu saklanır. Konumu doğrulanamayan ziyaret doğrulanmış sayılmaz.
- SFA-27: GPS yalnızca yetkili iş sürecinde kullanılır; sürekli arka plan takibi yapılmaz.
- Kabul: mesafe hesabı backend'de yapılır; istemciden gelen `verified=true` kabul edilmez. Güncel olmayan veya güvenilir olmayan konum doğrulama sağlamaz.
- Açık karar: kabul edilebilir GPS doğruluk yarıçapı, ölçüm yaşı ve cihaz sahteciliğine karşı uygulanabilir kontroller ayrıca tanımlanacak; 100 metre kuralı değiştirilmez.

## 9. Ziyaret bitirme sonuçları

1. Sipariş alındı.
2. Sipariş alınamadı — gerekçe zorunlu.
3. İşyeri kapalı.
4. Yetkili kişi yerinde yok.
5. Yalnızca tahsilat yapıldı.

- SFA-28: Sipariş alınamama gerekçeleri en az fiyat yüksekliği, müşteride stok bulunması, rakip ürün tercihi, ödeme sorunu ve ihtiyaç olmamasını kapsar.
- SFA-29: Aynı ziyarette sipariş ve tahsilat varsa her ikisi raporlanır; tek sonuç seçimi diğer işlemi kaybettirmez.
- Kabul: “sipariş alındı” bağlı geçerli sipariş olmadan; “yalnızca tahsilat” tahsilat olmadan kaydedilemez. İptaller performansta dikkate alınır.

## 10. Tahsilat yönetimi

| Yöntem | Doğrulama ve takip |
| --- | --- |
| Nakit | Kasaya teslim ve yetkili onayı |
| Kredi kartı / POS | Banka/POS işlem doğrulaması |
| Havale / EFT | Hesaba gelen tutarın doğrulanması |
| Çek | Teslim, vade ve tahsilat durumları |

- SFA-30: Sipariş ve tahsilat aynı ziyarette yapılabilir.
- SFA-31: Kaydedilmiş ve doğrulanmış tahsilatlar ayrı tutulur; doğrulama, ret, iptal ve teslim adımları denetlenir.
- SFA-32: Çift tahsilat/cari hareket engellenir; makbuz ve günlük pazarlamacı tahsilat raporu hazırlanır.
- Kabul: doğrulanmamış tahsilat doğrulanmış performansa yazılmaz; doğrulama tekrarı cari veya kasa/banka hareketini ikinci kez oluşturmaz.
- Açık karar: cari bakiyeye etki anı, kısmi doğrulama, çekin karşılıksız çıkması ve muhasebeleştirme politikası uygulamadan önce kesinleştirilecek.

## 11. Pazarlamacı hedefleri

- SFA-33: Yönetici kişi bazında koli satış, ciro, müşteri ziyareti, tahsilat ve aktif müşteri hedefi belirler.
- SFA-34: Kişi ve bölge bazında günlük, haftalık, aylık gerçekleşme raporlanır.
- SFA-35: İade, iptal ve doğrulanmamış tahsilat etkileri doğru ayrılır.
- Kabul: telefon siparişi ziyareti artırmaz; aynı müşteri aynı dönem için aktif müşteri ölçümünde mükerrer sayılmaz.
- Açık karar: koli/birim dönüşüm katsayıları, hedef dönem sınırları ve aktif müşteri tanımı yönetici tarafından onaylanacak. Ürün adından koli içi adet tahmin edilmeyecek.

## 12. Depo ve sevkiyat

- SFA-36: MERKEZ DEPO satılabilir, İADE DEPO kontrol/iade stoğudur.
- SFA-37: Sipariş onayı, stok kontrolü, toplama, sevkiyat hazırlama, teslim ve iade ayrı süreçlerdir.
- Kabul: onaysız sipariş toplanamaz; yetersiz stokta sevkiyat ilerlemez; tekrar işlem stoktan ikinci kez düşmez; iade stoğu kontrolsüz satılamaz.
- Açık karar: rezervasyon/düşüm anı, kısmi sevkiyat/teslim ve eksik teslim politikası.

## 13. Yönetici paneli

- SFA-38: Günlük/aylık satış, satılan koli, hedef gerçekleşmesi, pazarlamacı performansı, ziyaret oranı ve plan dışı ziyaretler.
- SFA-39: Bekleyen sipariş/müşteri onayları, tahsilat doğrulamaları, riskli müşteriler ve bölgesel satış analizi.
- SFA-40: Modern, mobil uyumlu ve grafiklerle desteklenen Türkçe tasarım. Demo ile gerçek veri açıkça ayrılır.
- Kabul: sayaçlar/çizimler aynı filtre, dönem ve yetki kapsamındaki backend toplamlarıyla uyuşur; eksik veri gerçek gerçekleşme gibi sunulmaz.

## 14. Güvenlik ve geliştirme

- SFA-41: Kontrollü, sürümlü migration; önce doğrulanmış yedek ve ayrı kopyada prova.
- SFA-42: Backend yetkilendirme; sipariş, tahsilat, fiyat, limit ve atama değişiklikleri için denetim kayıtları.
- SFA-43: GPS erişim sınırı; kullanıcı/rol değişikliğinde güncel erişim kontrolü; parolalar/oturumlar günlük veya Git içine yazılmaz.
- SFA-44: İş kuralları ve veri koruma için otomatik testler; eşzamanlılık, tekrar gönderme, geri alma, rol ve veri kapsamı senaryoları.
- Kabul: 124 gerçek ürün alan bazında korunur; ürün kodu mükerrerliği ve demo/gerçek veri karışması engellenir. Mevcut çalışma verileri test için değiştirilmez.

## Bağlı belgeler ve uygulama sırası

1. [Veritabanı karşılaştırması](SFA_VERITABANI_KARSILASTIRMA.md): doğrulanmış veri envanteri ve alan farkları.
2. [Aktarım ve test planı](SFA_AKTARIM_PLANI.md): yalnızca öneri; uygulama için kullanıcı onayı gerekir.
3. [Mevcut durum ve eksik modüller](SFA_MEVCUT_DURUM.md): talep ile mevcut kodun karşılaştırması.

Öncelik: veri koruma/ürün ayrımı → rol ve müşteri kapsamı → fiyat/limit/onay → GPS ve sipariş kanalı → tahsilat doğrulaması → depo/sevkiyat → hedefler ve panel. Bu sıralama uygulama önerisidir; veri aktarımı onayı yerine geçmez.
