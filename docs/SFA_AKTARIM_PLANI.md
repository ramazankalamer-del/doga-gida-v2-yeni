# SFA — güvenli aktarım önerisi ve test planı

Tarih: 2 Kasım 2026. **Yalnızca plan; aktarım, migration, seed veya mevcut veri değişikliği yapılmadı. Kullanıcı onayı gerekiyor.**

## 1. Veri kaynakları ve ayrım kararı

- Gerçek katalog: eski SQLite `doga_gida_dev.db`, 124 ürün. Aynı katalog/depo/hareket içeriğine sahip üç yerel kopya bulundu; bunlar üç ayrı katalog gibi içe alınmayacak.
- Hedef mimari: mevcut FastAPI/V2 SQLite şemasının kontrollü geliştirilmesi.
- V2'nin 5 örnek ürünü ve bunlara bağlı kayıtlar korunacak, gerçek ürünlere dönüştürülmeyecek veya yeniden bağlanmayacak.
- Öneri: onaydan sonra önce **ayrı bir aday V2 dosyası**, doğrulanmış V2 yedeğinden oluşturulsun. Eski kaynak ve mevcut V2 dosyası değiştirilmesin. Adaydaki eski 5 ürün `demo`, ithal 124 ürün `real` kapsamıyla ayrı tutulsun. Fiziksel satır sayısı 129 olabilir; gerçek iş kataloğu ve iş raporları **124 gerçek ürün** üzerinden çalışmalıdır. 129 satırın tamamını gerçek ürün saymak kabul değildir.
- Demo ürünler ve ilişkili alış/stock/depo hareketleri demo ekranı/arşiv kapsamından görülebilir. Gerçek sipariş gerçek ürün, gerçek müşteri ve gerçek hesapla çalışmalı; kapsamlar arası işlem engellenmeli. Mevcut müşteri/tedarikçi/finans kayıtlarının menşei otomatik varsayılmamalı; ayrı envanter ve yönetici sınıflaması gerekir.

## 2. Yedekleme ve geri dönüş

İlk incelemede her iki kaynak yalnızca `mode=ro` bağlantıyla okundu. Uygulama başlatıcısı/`initialize()` çalıştırılmadı. SQLite journal modu `delete`; aktif WAL/journal bulunmadı. Okuma kilidi altında byte-byte kopya oluşturuldu.

- Yedekler proje kaynak klasörünün dışında, yerel `outputs/SFA-Yedekleri/<zaman>/` içinde.
- SHA-256 kaynak = yedek; tüm tablo satır sayıları/alan tanımları/veri parmak izleri eşit; `integrity_check=ok`; `foreign_key_check` ihlali 0.
- İşlem öncesi/sonrası kaynak dosya hash'i ve son değiştirme zamanı aynı.
- Yedek klasöründe deny-by-default Git ignore ve kullanıcı/SYSTEM/yerel yöneticilerle sınırlandırılmış Windows erişimi var. Kaynak depoya yalnızca belgeler eklenir; DB ve yerel doğrulama dosyası yüklenmez.
- İleride WAL/aktif yazım görülürse bu ham dosya kopyalama yöntemi kullanılmayacak; yazımlar kontrollü durdurulacak veya SQLite Backup API ile tutarlı snapshot alınıp ayrıca doğrulanacak.
- Prova geri dönüşü: aday bağlantısı kapatılır; yalnızca aday dosya yeni bir çalışma dosyasıyla değiştirilir. Kaynağın üzerine dosya yazılmaz. Canlı geçiş yapılacaksa ayrıca o anın yeni yedeği, veri değişikliği kontrolü ve açık kullanıcı onayı gerekir. Geçiş sonrası yeni işlem oluşmuşsa eski yedeği körlemesine geri yüklemek kabul değildir.

## 3. Şema hazırlığı — aday kopyada, onaydan sonra

1. Sürümlü `schema_migrations` kaydı, checksum ve uygulanma zamanı; tekrarlanabilir migration kontrolü.
2. Ürün menşei/kapsamı, kaynak sistem/ürün kimliği ve import partisi alanları; orijinal ID ile hedef ID için değişmez eşleme.
3. Kod, ad, barkod, birim/satış birimi/temel birim, kategori/alt kategori, KDV kodları, kaynak aktifliği ve kaynak tarihini kayıpsız tutacak alanlar.
4. Fiyatı **bilinmiyor** olarak temsil edebilen şema; liste/minimum/kampanya ve fiyat doğrulama durumunun ayrı yönetimi. V2'nin `price_cents NOT NULL` ve pozitif fiyat isteyen API'si uyarlanmadan import yapılmaz. Sahte 0 TL/örnek fiyatla bu zorunluluk aşılmaz; gerekirse aday kopyada foreign key ve indeksler korunarak kontrollü tablo dönüşümü yapılır.
5. Birimler/decimal miktar ve koli dönüşüm modeli. Kaynak `NUMERIC(14,3)` miktarları tam sayıya yuvarlanmaz. Stok bilinmiyorsa `opening_stock_verified=false` gibi açık hazırlık durumu ve satış engeli gerekir; bu gerçek sıfır stok beyanı değildir.
6. Otomatik demo seed gerçek veri kurulumu için kapatılır. Kopyadaki mevcut kayıtlar seed/migration nedeniyle yeniden oluşmamalı.
7. Şema yalnızca ayrı aday dosyada değiştirilir; her adımda tüm mevcut tablolar ve foreign key'ler doğrulanır.

## 4. Kod bazında mükerrerlik önleme

- Ürün kodu **metindir**. 67 baştaki sıfır aynen korunur; sayıya/Excel otomatik tipine çevrilmez.
- Orijinal kod ayrı ve aynen tutulur. Eşleştirme anahtarı için boşluk/büyük-küçük harf/Unicode kuralları belgelenir ve tutarlı uygulanır; veri üzerinde sessiz düzeltme yapılmaz.
- `normalized_product_code` için uygun UNIQUE kısıtı; ayrıca `(source_system, source_product_id)` ve `(source_system, source_product_code)` için kalıcı eşleme ve tekillik.
- Mevcut incelemede normalize kod mükerrerliği **0**, eski kod–V2 SKU çakışması **0**. Import anında tekrar kontrol edilir; bugünkü sonuç geleceğe garanti değildir.
- Aynı kaynak hash'i/partisi ikinci kez çalıştırılırsa yeni ürün, stok veya hareket eklenmez.
- Kod çakışması, aynı kodda farklı içerik veya değişmiş kaynakta sessiz `upsert/replace` yapılmaz. İşlem durur ve uyuşmazlık raporu üretilir; kaynak satır düşürülmez, kodun başına rastgele önek eklenmez.
- Kaynak ID 1–124 ile V2 ID 1–5 çakışır. Hedefte yeni ID atanabilir; orijinal ID eşleme tablosunda korunur. Eski sipariş/alış/depo foreign key'leri yeni gerçek ürünlere çevrilmez.

## 5. Kayıpsız aktarım adımları

1. Onaylı yedek/hash ve kaynak envanterini sabitle; source dosyaları salt okunur aç.
2. Aday V2 kopyasını oluştur; yeni alanları/migration defterini uygula; mevcut veri envanterini karşılaştır.
3. 124 ürünün her alanını doğrula; eksik fiyat, barkod, stok ve dönüşüm katsayısını eksik olarak raporla.
4. İşlem başlamadan bütün mükerrerlikleri ve veri sınırlarını denetle. Kod/ad/kategori kesilmez. Mevcut gerçek uzunluklar V2'nin bugünkü sınırlarında olsa da import doğrulaması bunu her çalıştırmada kontrol eder.
5. Tek transaction içinde 124 gerçek ürünü, import partisini ve ID eşlemelerini kaydet. Alanların orijinal değerlerini denetim için koru. Bir satırda hata varsa partiyi bütünüyle geri al.
6. İki depo `MERKEZ`/`IADE` koduyla eşlenir; mevcut V2 depoları ikinci kez oluşturulmaz. Kaynak depo metaverisi saklanır.
7. Kaynakta müşteri tablosu yok, `stock_movements=0`; olmayan müşteri/stok hareketi veya açılış hareketi uydurulmaz. Başka bir kaynakla stok açılışı gerekirse ayrı onaylı işlem yapılır.
8. Gerçek kapsamda 124, demo kapsamda 5 ürün ve bütün alan eşitlikleri doğrulanır; tüm mevcut V2 kayıtları/ilişkileri değişmeden kalmalıdır.
9. Prova raporu, farklılık listesi, test sonuçları ve geri dönüş kanıtı kullanıcıya sunulur. Uygulamanın mevcut DB bağlantısı otomatik değiştirilmez.

## 6. 124 ürün koruma test planı

| Test | Beklenen sonuç |
| --- | --- |
| T-01 Kaynak değişmezliği | İnceleme/prova öncesi-sonrası her iki orijinal DB SHA-256 ve değiştirme zamanı aynı; tek satır yazılmamış. |
| T-02 Yedek geri okuma | Yedek hash'i kaynakla aynı; tüm tablolar, satır sayıları ve alan parmak izleri aynı; integrity `ok`, FK ihlali 0. |
| T-03 Tam ürün mutabakatı | 124 kaynak ID'nin her biri tam bir kez hedef gerçek kayda eşlenmiş; eksik/fazla eşleme 0. |
| T-04 Alan mutabakatı | 124 ürünün 14 kaynak alanı, NULL/Unicode/tarih ve tüm birim/KDV kodları dahil birebir geri okunabilir. |
| T-05 Kod koruma | 67 baştaki sıfır korunmuş; boş/normalize mükerrer kod 0; eşleme kodu metin. |
| T-06 Demo ayrımı | 5 örnek ürün kendi ID ve ilişkileriyle demo kapsamda; gerçek katalog/performans 124 ürün; karışık kapsamlı sipariş reddedilmiş. |
| T-07 İlişkili eski veriler | V2'nin kullanıcı, müşteri, sipariş, alış, depo, stok ve finans kayıtları/bağlantıları birebir aynı; silinen kayıt 0. |
| T-08 İdempotency | Aynı import ikinci kez çalıştığında yeni ürün/hareket/parti etkisi 0; gerçek ürün sayısı 124. |
| T-09 Çakışma | Aynı normalize kodda farklı ürün veya değişmiş kaynak açık hata; sessiz üzerine yazma/satır atlama yok. |
| T-10 Atomiklik | 1., 62. veya 124. kayıtta yapay hata tüm partiyi geri alır; yarım aktarım/yarım eşleme yok. |
| T-11 Fiyat yokluğu | Hiçbir gerçek ürüne demo/sıfır fiyat atanıp satış açılamaz; yönetici fiyat doğrulaması gerekli. |
| T-12 Stok yokluğu | Boş hareket tablosu doğrulanmış fiziksel sıfır sayılmaz; sayım/onay olmadan gerçek satış açılmaz. |
| T-13 Birim/KDV | KL/KOL/AD/ADT orijinalleri ve 1/10/20/0 kodları kaybolmaz; koli dönüşümü veya vergi oranı tahmin edilmez. |
| T-14 Geri dönüş | Prova dosyası kullanılmaz hale getirilip yeni kopya üzerinden geri dönüş doğrulanır; orijinal dosyalara dokunulmaz. |
| T-15 Mevcut regresyonlar | Mevcut uygulamanın testleri yalnızca geçici DB'lerde; sipariş/tahsilat/iade/ekstre/rol akışları korunmuş. |
| T-16 Güvenlik | Pazarlamacı import/migration/fiyat tanımı çalıştıramaz; DB/yedek/oturum dosyası Git kapsamına giremez. |

**Şimdi gerçekleşen doğrulama:** T-01/T-02 kapsamında iki kaynağın byte hash'i, yedeklerin geri okunabilirliği, bütün tablo parmak izleri, integrity ve FK kontrolleri doğrulandı. Kod ve alan envanteri okundu. T-03–T-16'nın aktarım/uygulama bölümleri henüz yürütülmedi; onay sonrası ayrı kopyada uygulanacak testlerdir. “124 ürün aktarıldı” sonucu verilmedi.

## 7. Onay kapısı

Önerilen ilk onay yalnızca **ayrı bir deneme kopyasında migration/import geliştirme ve prova** içindir. Mevcut iki DB'yi değiştirme, demo ürün silme veya bağlantıyı canlı aday dosyaya yönlendirme yetkisi içermez. Başarılı prova raporundan sonra gerçek kullanıma geçiş için ayrıca onay istenir.
