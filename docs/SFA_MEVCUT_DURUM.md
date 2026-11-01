# SFA — mevcut yazılım ve eksik modüller

İnceleme: 2 Kasım 2026; kod tabanı `50eceea2b5c05c80149fce99b8a700bcebbf9337`. Durumlar kod incelemesidir; yeni iş kurallarına uygunluk sertifikası değildir. Bu aşamada uygulama kodu veya mevcut veritabanları değiştirilmedi.

| Alan | Mevcut durum / kod kanıtı | SFA için eksik veya değişecek davranış |
| --- | --- | --- |
| Altyapı ve arayüz | FastAPI, SQLite, React/TypeScript; mobil düzen. `backend/main.py`, `frontend/src/main.tsx`, `style.css`. | Pazarlamacı, ofis, depo ve sevkiyat için ayrı yetkili iş akışları; güvenli çok cihazlı dağıtım. Localhost adresi telefondaki bilgisayara kendiliğinden erişim sağlamaz. |
| Roller | `auth.py`: `admin`, `staff`, `viewer`; backend oturum/CSRF/rol kontrolü. | Pazarlamacı, ofis, depo, sevkiyat yetkilerinin açık matrisi; eski staff hesaplarına sınırsız yeni hak vermeyen geçiş. |
| Müşteri kapsamı | `customers()` oturum açmış kullanıcıya tüm müşterileri döndürüyor. | Tek pazarlamacı ataması; tüm müşteri/cari/GPS/rota/iade uçlarında satır bazlı kapsam kontrolü. Doğrudan başka müşteri ID'si ile erişim engeli. |
| Müşteri onayı | `add_customer()` writer kullanıcıyla doğrudan kayıt açıyor. | Pasif/onay bekleyen müşteri; başlangıç limiti 0 TL; yönetici onayı ve atama/limit geçmişi; limit artış talebi. |
| Pre-Sales sipariş | `add_order()` fiyatı üründen alıyor, stok yeterliyse siparişi açıp hemen Merkez stoğundan düşüyor. | Risk/onay bekleme, onaylı depoya gönderim ve rezervasyon/düşüm anı. Mevcut erken stok düşümü yeni akış için doğrudan uygun kabul edilmeyecek. |
| Akıllı onay | Stok ve rol kontrolleri, sipariş aşama/iptal geçmişi mevcut. | Limit, gecikmiş borç, minimum fiyat ve yetki dışı iskonto nedenleri; yönetici onay/ret/düzeltme kuyruğu, yeniden değerlendirme ve denetim. |
| Fiyat | `products.price_cents`; `order_items.price_cents` ile geçmiş satış fiyatı korunuyor. Ürün oluşturma/düzenleme `auth.writer` ile yapılabiliyor. | Fiyat düzenleme yalnızca yönetici olmalı. Minimum fiyat, kampanya, iskonto yetkisi, fiyat geçmişi ve eksik fiyat nedeniyle satış engeli yok. |
| Gerçek katalog | V2'de 5 örnek; eski ayrı veritabanında 124 gerçek ürün. | Ürün kapsamı/menşei, tüm kaynak alanları, fiyat ve birim hazırlığı, güvenli import ve kalıcı kimlik eşlemesi. |
| Sipariş kanalı | Siparişi giren `created_by` tutuluyor; ayrı saha/telefon kanalı yok. | GPS doğrulanmış ziyarete bağlı saha; GPS'siz yetkili telefon siparişi; performans sahibi pazarlamacı ile giren kullanıcı ayrı saklanmalı. |
| GPS müşteri konumu | `CustomerLocation.tsx`, `location.ts`: koordinat ve cihaz konumu alma; doğruluk mesajı; müşteri haritası. | Sunucuda 100 metre doğrulaması; ziyaret koordinatı/doğruluk/ölçüm zamanı, başlangıç/bitiş ve erişim kapsamı. Müşterinin kaydedilmiş koordinatı ziyaret doğrulaması değildir. |
| Rota ve ziyaret | Çoklu gün, günlük liste/harita, elle sıra, ziyaret edildi/edilmedi, not/neden, tarihçe ve tekrar ziyaret listesi mevcut. | Planı yalnızca yönetici düzenlemeli; pazarlamacının kendi günlük planı; GPS doğrulanmış oturum ve plan dışı ziyaret sınıflaması. |
| Ziyaret sonucu | `VisitInput`, `VisitControls`: boolean durum; not ve serbest neden. | Beş zorunlu sonuç ve yapılandırılmış gerekçeler; sipariş/tahsilat ilişkileri; kanıtsız “sipariş alındı” sonucunu engelleme. |
| Cari ve ekstre | Bakiye, ekstre, vade listesi, tahsilat/iade/iptal bağlantıları var; işlem kimlikleri tekrar kayıtları engelliyor. | Kredi/kullanılabilir limit ve müşteri bazlı yetki; onay bekleyen riskin ayrılması; gerçek fatura hareketi kapsamı. Mevcut sipariş ekstresi resmi fatura değildir. |
| Tahsilat | Nakit, havale/EFT, kart; isteğe bağlı finans hesabıyla tek işlem; iptal bağlantısı mevcut. | Çek; kasaya teslim/onay, POS/EFT doğrulaması, kaydedilmiş/doğrulanmış ayrımı, doğrulama geçmişi, makbuz ve günlük pazarlamacı raporu. Kayıt şu anda bekleyen doğrulama olmadan bakiyeyi azaltıyor. |
| Depo/sevkiyat | Merkez/İade, kontrol onaylı transfer, stok girişi, sipariş aşamaları ve iadeler mevcut. | Depo/sevkiyat rolleri, onay bağımlılığı, rezervasyon, toplama ve teslimat iş kayıtları; kısmi/eksik teslim politikası. |
| Ticari iadeler | `commercial_returns.py`: miktar sınırı, aynı işlemde stok/bakiye, yönetici iptali; ekstre/vade/kâr yansımaları. | Pazarlamacı kapsamı, ziyaret/teslim bağlantısı ve SFA performans kuralları. Eski fiziksel iade kabulü ticari iade ile karıştırılmamalı. |
| Hedef ve performans | Günlük rota özeti ve genel toplamlar var. | Beş hedef tipi, pazarlamacı/bölge/dönem hedefleri, telefon/saha ayrımı ve doğrulanmış tahsilat performansı. |
| Dashboard | Günlük net satış, sipariş, tahsilat, müşteri, stok; vade, gider ve kâr raporları var. | Aylık grafikler, koli, hedef oranları, pazarlamacı/bölge, plan dışı ziyaretler, risk ve bekleyen üç onay kuyruğu. |
| Veri koruma | Özellik öncesi SQLite yedeği, işlem kilitleri, parolaların özetlenmesi ve oturum iptalleri mevcut. | Sürümlü migration defteri, kontrollü prova, alan bazında 124 ürün mutabakatı, geri dönüş provası ve gerçek/demo veri kapsamı. Başlangıç seed davranışı gerçek katalog kurulumunda kontrol edilmeli. |

## Öncelikli riskler

1. **Pazarlamacı veri kapsamı yok:** mevcut tüm müşteri listesi, cari, konum ve iş uçları SFA erişim modeli eklenmeden gerçek saha erişimine açılmamalı.
2. **Fiyat kaynakta yok:** 124 ürüne V2 örnek fiyatı atanamaz. Liste/minimum fiyat yöneticice doğrulanmadan gerçek satış açılamaz.
3. **Stok bilinmiyor:** eski hareket tablosunun boş olması fiziksel stoğun sıfır olduğunu kanıtlamaz. Açılış sayımı veya doğrulanmış kaynak gerekir.
4. **Birimler farklı:** koli/adet dönüşümü ve NUMERIC(14,3) miktar modeli V2'nin tam sayı adediyle aynı sayılmamalı.
5. **Erken muhasebeleştirme:** mevcut siparişin anında stok/cari etkisi ve tahsilatın anında bakiye etkisi yeni onay/doğrulama akışlarıyla yeniden tasarlanmalı; doğrudan davranış değiştirip eski işlemler yeniden işlenmemeli.
6. **Demo ayrımı yok:** örnek 5 ürüne bağlı alış, depo ve stok kayıtları var; bunları silmek veya gerçek ürünlere yeniden bağlamak veri kaybettirir.

## Önerilen aşamalar

| Aşama | Çıktı | Geçiş koşulu |
| --- | --- | --- |
| A — İnceleme | Değişmemiş kaynaklar, doğrulanmış yerel yedekler, alan farkları ve import/test planı | Bu aşamanın raporu kullanıcıya sunulur. |
| B — İzole prova | Ayrı V2 kopyasında sürümlü şema ve 124 ürün aktarımı; 5 örnek ayrı kapsamda | Kullanıcı onayı; 124/124 alan mutabakatı, tekrar çalıştırma ve geri dönüş testleri. |
| C — Temel SFA | Rol/kapsam, müşteri atama/onay/limit, gerçek/demo ayrımı, yönetici fiyatlandırması | Yetki ve veri kaybı testleri; fiyat/birim/stok eksiklerinin açık yönetimi. |
| D — İş akışı | Sipariş riski/onayı, GPS ziyareti, saha/telefon, tahsilat doğrulaması, depo/sevkiyat | Uçtan uca ve eşzamanlılık testleri; muhasebeleştirme politikasının onayı. |
| E — Analiz | Hedefler, makbuz, pazarlamacı/bölge raporları ve yeni dashboard | Doğrulanmış gerçek veriyle mutabakat; demo örneklerinin ayrılması. |

Bu tabloda B–E öneridir; mevcut inceleme onayı bunları yürütme izni değildir. Önce aktarım planının onayı beklenecek.
