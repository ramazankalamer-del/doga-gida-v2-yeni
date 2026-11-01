# Doğa Gıda V2

Türkçe ve mobil uyumlu React + TypeScript yönetim paneli; FastAPI ve SQLite backend.
Bu ilk sürüm yalnızca örnek veriler içerir. Bu aşamada kullanıcı girişi ve sunucuda rol kontrolü eklendi. Canlı dağıtım henüz doğrulanmadı; geliştirme ve testlerde yalnızca örnek veri kullanın.

## Özellikler

### Müşteri kartı kısayolları, ekstre ve rota günleri

Müşteri listesi, kayıt düzenleme kartı ve haritada seçilen müşteri üzerinde
**Hesap ekstresi**, **Satış yap**, **Tahsilat al** ve **Rota günü** kısayolları
bulunur. Satış ve tahsilat kısayolları mevcut formları seçilen müşteriyle açar;
düğmeye basmak tek başına kayıt oluşturmaz. Satış mevcut sipariş akışını
kullanır (Merkez stoğu kayıt anında düşer); fatura kesmez. Tahsilat para çekmez,
yalnızca kayıt tutar. Kartta kaydedilmemiş değişiklikler bu kısayollarla uygulanmaz.

Ekstre salt okunurdur; admin, staff ve viewer erişebilir. Tarih aralığına göre
devir bakiyesi, dönem borç/alacak toplamları, dönem sonu ve güncel hesap bakiyesi
ayrı gösterilir. Siparişler borç, tahsilatlar alacak; sipariş iptalleri alacak,
tahsilat iptalleri borç ters hareketidir. İptaller kayıt tarihindeki asıl hareketi
silmez; iptal tarihindeki ters hareketle dengelenir. İptal tarihi İstanbul gününe
çevrilir. Aynı gün hareketleri sipariş, tahsilat, sipariş iptali ve tahsilat iptali
sırasıyla; kendi içinde kayıt numarasıyla gösterilir. Saat sırası iddia edilmez.
Para hesapları kuruş cinsinden tamsayıdır. Müşteriye bağlı olmayan eski
tahsilatlar ekstreye eklenmez. İptal tarihi eksik eski iptal edilmiş siparişler
etkisiz satır olarak açıklanır; yapay iptal tarihi oluşturulmaz.

Rota günü seçiminde Pazartesi–Pazar arasından birden fazla gün seçilebilir;
**Günleri temizle** ve ardından Kaydet ziyaret günlerini kaldırır, müşteriyi silmez.
Rota günleri müşteri kartının sürümüne bağlıdır: eski kartla yazma 409 ile
reddedilir. GPS veya diğer kart alanları bu kısayoldan değişmez. Eski istemciler
rota günlerini göndermediğinde mevcut günler korunur. Admin/staff günleri
değiştirebilir; viewer günleri ve ekstreyi görür, satış/tahsilat/rota yazma
düğmelerini kullanamaz. Şema geçişi önce SQLite yedeği alır. Gün seçimi ziyaret
planıdır; otomatik rota optimizasyonu veya bildirim oluşturmaz.

API: `GET /api/customers/{id}/statement?start_date=2026-10-01&end_date=2026-10-31`
ve `POST /api/customers/{id}/route-days` (`route_days`: 1–7 arası benzersiz günler,
`expected_version`: güncel müşteri sürümü). Geçersiz tarihler/günler reddedilir.

### Müşteri GPS konumu

**Müşteri haritası** menüsü GPS kaydı bulunan müşterileri etkileşimli haritada
gösterir. Firma, yetkili veya ilçe araması ile GPS kayıtlı/konum eksik filtreleri
hem listeye hem haritadaki noktalara uygulanır. Konumu olmayan müşteriye sahte
bir nokta atanmaz. Aynı koordinattaki müşteriler tek işarette gruplanır;
açılan listeden her biri ayrı seçilebilir. İşaret veya listedeki müşteri seçilince
bilgiler ve yetkili kullanıcı için kart düzenleme düğmesi gösterilir. Salt okunur
kullanıcı haritayı ve bilgileri görebilir, kart düzenleyemez. GPS değişikliği veya
silme sonrasında harita güncellenir. **Tüm konumları göster** filtreleri kaldırıp
haritayı kayıtlı noktaların tamamına döndürür.

Harita Leaflet 1.9.4 ile tarayıcıda çizilir; müşteri adları ve telefonlar harita
servisine gönderilmez. Görüntülenen bölgenin harita görselleri OpenStreetMap'ten
yüklenir; internet gerekir. Atıf harita üzerinde görünür. Görseller yüklenemezse
uyarı ve tekrar deneme düğmesi gösterilir; müşteri listesi kullanılabilir.
Toplu/çevrimdışı harita indirme ve rota optimizasyonu eklenmemiştir.
Tile sağlayıcısı gerektiğinde derleme sırasında `VITE_MAP_TILE_URL` ile
değiştirilebilir; farklı sağlayıcının atıf gereksinimleri ayrıca ayarlanmalıdır.
Üretim trafiği için sağlayıcının kapasite/kullanım politikasını değerlendirin:
https://operations.osmfoundation.org/policies/tiles/ .

Harita veri filtreleri ve nokta gruplama kontrolleri:
`cd frontend` ardından `node --experimental-strip-types --test tests/customerMap.test.mjs`.

Müşteri ekleme/düzenleme formunda isteğe bağlı enlem (-90–90) ve boylam
(-180–180) alanları bulunur. İki alan birlikte doldurulur. **GPS bilgisini
temizle** iki alanı boşaltır; silme veya değişiklik **Kaydet** ile uygulanır.
Müşteri silinmez. Listedeki **Haritada aç** bağlantısı kayıtlı noktayı
OpenStreetMap'te açar; seçilen koordinatlar bu bağlantı ile dış servise gönderilir.
Müşteri haritası ekranı ayrıca görüntülenen bölgenin harita görsellerini yükler.
**Konumumu al** düğmesi müşterinin yanındayken cihazın güncel konumunu
tek sefer alır (tarayıcı izni gerekir). Koordinatları ve yaklaşık doğruluğu
gösterir; kaydetmeden önce kontrol edilebilir. Konum aranırken Kaydet devre
dışıdır. İzin reddi, desteklenmeyen tarayıcı, konum bulunamaması ve zaman aşımı
durumlarında elle giriş mümkündür; mevcut GPS silinmez. Arka planda takip yoktur.
Gerçek cihazın GPS doğruluğu donanım ve ortama bağlıdır.

API JSON sayıları veya iki alan için birlikte `null` kabul eder. Geçersiz,
eksik eş, boolean, NaN/sonsuz veya sınır dışı koordinatlar reddedilir.
Güncellemede iki alan da gönderilmezse mevcut GPS korunur; eski istemciler
diğer müşteri bilgilerini düzenlerken konumu yanlışlıkla silmez. Koordinatlar
diğer müşteri alanlarıyla birlikte sürüm kontrolü, rol ve CSRF korumasına tabidir.
Eski kayıtlar boş konumla korunur; geçiş öncesinde veritabanı yedeği alınır.

### Merkez ve İade depoları

**Depolar ve stok hareketleri** ekranı Merkez Depo ve İade Deposu stoklarını
ürün bazında ayrı gösterir. Mevcut `products.stock` alanı Merkez Depo'nun
satılabilir stoğudur; yeni `return_stock` alanı kontrol bekleyen iade stoğudur.
Eski stoklar, kullanıcılar, siparişler ve hareketler korunur. Şema geçişinden
önce mevcut veritabanının tutarlı yedeği veritabanının yanındaki `backups/`
klasörüne alınır. Eski hareketler Merkez Depo'ya atanır; İade Deposu sıfırdan
başlar ve sahte geçmiş oluşturulmaz. Yeniden başlatma stokları sıfırlamaz.

- **Stok girişi ekle:** Merkez Depo'ya teslimat ekler.
- **İade kabul et:** fiziksel ürünü yalnızca İade Deposu'na ekler. Sipariş,
  tahsilat ve müşteri bakiyesi değişmez; bu işlem muhasebesel iade değildir.
- **Depolar arası transfer:** İade → Merkez yönünde kontrol ve satışa uygunluk
  onayı gerekir. Merkez → İade yönü ürünü kontrole ayırır.
- Siparişler sadece Merkez stoğunu kullanır. Bekleyen siparişin iptali de
  Merkez stoğunu geri ekler. Ürün düzenleme ekranındaki stok düzeltmesi
  sadece Merkez'i değiştirir; İade stoğu korunur.

Transferin iki bacağı tek SQLite işleminde kaydedilir; fiziksel toplam değişmez.
Yetersiz kaynak veya depo başına 10.000.000 adet sınırı aşıldığında işlem
tamamen reddedilir. İstek kimlikleri tekrar kaydı önler; değiştirilmiş bir
istekle aynı kimlik kullanılırsa 409 döner. Yönetici ve personel yazabilir;
salt okunur kullanıcı iki depoyu ve geçmişi görebilir. API, CSRF ve yazma
kilidi altında güncel rol kontrolünü uygular.

API: `GET /api/warehouses`, `POST /api/warehouse-returns`,
`POST /api/warehouse-transfers`. Bu aşama seri/lot, son kullanma tarihi,
hurdaya ayırma ve müşteri/siparişe bağlı mali iade içermez.

- İstanbul saatine göre günlük satış, sipariş ve tahsilat özeti
- Toplam müşteri, stok ve kritik stok göstergeleri
- Sipariş oluşturma, ürün satırları, sunucuda tutar hesaplama ve otomatik stok düşümü
- Sipariş listesi ve son sipariş özeti
- Müşteri listeleme, arama ve ekleme
- Ürün listeleme, arama ve ekleme; benzersiz ürün kodu kontrolü
- SQLite üzerinde kalıcı kayıtlar; para tutarları veritabanında kuruş olarak saklanır
- Form doğrulama, yüklenme ve hata durumları

Çevrimdışı çalışma ve muhasebe entegrasyonu bu sürümün kapsamına dahil değildir. Mobil testler Chromium telefon ekranı benzetimidir; gerçek Android/iPhone cihaz testi yapılmamıştır.

## Gereksinimler

### Windows'ta kolay açılış

Proje klasöründeki **BASLAT.bat** dosyasını çift tıklayın. Python 3.12+ gerekir.
İlk kaynak kurulumunda Node.js 22.12+ ve internet bağlantısı da gerekir.
Başlatıcı sanal ortamı ve bağımlılıkları hazırlar; derlenmiş arayüz yoksa
`npm ci` ve `npm run build` çalıştırır. İlk yönetici yoksa kullanıcı adı
ve gizli parola ister. Ardından tarayıcıyı açar. Pencere açık kalmalıdır;
kapatmak için Ctrl+C kullanın.

8000 portu doluysa mevcut işlemi kapatmadan 8010–8020 arasından boş port seçer;
doğru adres terminalde yazılır. Her açılışta mevcut V2 SQLite dosyasının
tutarlı yedeği `yedekler/` içine alınır. Yerel HTTP oturumu için
`COOKIE_SECURE=0` yalnızca bu başlatıcının alt sürecine uygulanır;
sunucu yalnızca `127.0.0.1` adresini dinler.

Kaynakları güncelledikten sonra `python baslat.py --rebuild` çalıştırın.
İsteğe bağlı `--port 8015` ve `--no-browser` seçenekleri vardır.
Bu depo V2 veritabanını (`backend/data/doga.db`) kullanır; eski
`doga_gida_dev.db` dosyasını bunun üzerine kopyalamayın. Eski paketin
verilerini V2'ye aktarma ayrı bir işlemdir.

Arayüz derlenmeden backend elle başlatılırsa ana sayfa artık 404 yerine
kurulum adımlarını gösterir (HTTP 503); `/api/health` ve `/docs` çalışır.

Python 3.12+ ve Node.js 22.12+ (bu ortamda Python 3.12 ve Node.js 24 kullanıldı).
Aşağıdaki komutları proje kökünde çalıştırın:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
cd frontend
npm ci
npm run build
cd ..
```

## Uygulamayı çalıştırma

Derlenmiş arayüz ve API aynı sunucudan sunulur:

```bash
source .venv/bin/activate
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Kendi bilgisayarınızda tarayıcıdan `http://localhost:8000` adresini açın.
API dokümantasyonu: `http://localhost:8000/docs`.
Bulut ortamında bu adres kendi bilgisayarınızı göstermez; varsa ortamın port yönlendirmesini kullanın.
Telefonla yerel ağ testi için bilgisayarınızın yerel IP adresini ve 8000 portunu kullanabilirsiniz; telefon aynı ağa bağlı olmalıdır.

Varsayılan SQLite dosyası `backend/data/doga.db` konumunda ilk açılışta oluşturulur. Yeniden başlatma verileri silmez ve örnek verileri tekrar eklemez. Örnek siparişler ilk veritabanı oluşturma gününe aittir; sonraki gün günlük satışın sıfır olması beklenir. İsteğe bağlı `DATABASE_PATH` değişkeniyle başka bir dosya seçilebilir. Gerçek veri veya veritabanı dosyasını Git'e eklemeyin.

## Geliştirme modu

İlk terminalde backend'i yukarıdaki gibi başlatın. İkinci terminalde:

```bash
cd frontend
npm run dev
```

Vite varsayılan olarak 5173 portunda açılır. `/api` istekleri 8000 portundaki backend'e yönlendirilir.

## Testler

Backend testleri geçici ve birbirinden bağımsız SQLite veritabanları kullanır:

```bash
cd backend
../.venv/bin/python -m pytest -q
```

Arayüz derleme ve TypeScript kontrolü:

```bash
cd frontend
npm run build
```

Uçtan uca testler geçici, ayrı bir veritabanı ve yalnızca test hesapları oluşturur. 8001 portu boş olmalıdır; test sunucusu otomatik başlatılır, mevcut sunucu tekrar kullanılmaz.

```powershell
cd frontend
npx playwright install chromium
npm run test:e2e
```

Linux/macOS için `E2E_SERVER_COMMAND="../.venv/bin/python ../backend/e2e_server.py"` ayarlayın.
Varsayılan Playwright Chromium kullanılır; alternatif olarak `CHROMIUM_PATH` belirtilebilir.
Masaüstü ve mobil boyutlarda giriş, salt okunur rol, çıkış, kullanıcı yönetimi, müşteri/ürün ekleme, arama, sipariş oluşturma, yetersiz stok, kalıcılık ve yatay taşma denetlenir. Test sunucusu 8001 portunu kullanır; 8000 portundaki normal uygulamaya ve hesabınıza dokunulmaz. Ekran görüntüleri Playwright test çıktılarındadır.

## Proje yapısı

```text
backend/main.py                FastAPI, SQLite, örnek veri ve API uçları
backend/requirements.txt       Python bağımlılıkları
backend/tests/test_api.py      API ve veri doğrulama testleri
backend/tests/test_users.py    Kullanıcı yönetimi API testleri
backend/tests/test_user_rules.py Kullanıcı yönetimi iş kuralı testleri
frontend/src/UserManagement.tsx Yönetici kullanıcı ekranı
frontend/src/main.tsx          React ekranları ve formlar
frontend/src/style.css         Mobil uyumlu tasarım
frontend/vite.config.ts        Geliştirme sunucusu ve API proxy
frontend/tsconfig.json         TypeScript ayarları
frontend/playwright.config.ts  Tarayıcı test ayarları
frontend/tests/app.spec.ts     Masaüstü ve mobil test akışları
frontend/package-lock.json     Kilitli JavaScript bağımlılıkları
```

## Giriş, roller ve kullanıcı yönetimi

| Rol | Panel ve listeler | Müşteri/ürün ekleme |
| --- | --- | --- |
| admin (Yönetici) | Evet | Evet |
| staff (Personel) | Evet | Evet |
| viewer (Salt okunur) | Evet | Hayır |

Yönetici menüsündeki **Kullanıcılar** ekranında kullanıcı listeleme, oluşturma, rol değiştirme ve aktif/pasif durumu yönetilir. Personel ve salt okunur hesaplar bu ekrana ve API uçlarına erişemez. Herkese açık kayıt yoktur. İlk yönetici aşağıdaki yerel komutla oluşturulur; bundan sonra yeni hesaplar yönetici ekranından açılabilir. Veritabanındaki rol ve aktiflik her istekte yeniden okunur.

Yönetici kendi rolünü veya aktifliğini değiştiremez; son aktif yöneticinin yetkileri kaldırılamaz. Rol veya aktiflik değişikliği hedef hesabın bütün oturumlarını iptal eder. Pasif kullanıcı giriş yapamaz; yeniden aktifleştirilirse mevcut parolasıyla giriş yapabilir. Kullanıcı listesi ve oluşturma yanıtlarında parola özetleri ve oturum bilgileri bulunmaz. İşlemler CSRF ve sunucuda yönetici kontrolüyle korunur. Eşzamanlı yazmalarda yetki, veritabanı yazma kilidi alındıktan sonra yeniden kontrol edilir.

**Windows PowerShell kurulumu ve ilk kullanıcı:**

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd backend
../.venv/Scripts/python.exe manage_user.py yonetici --role admin
# Parola gizli istemle iki kez sorulur; 12–128 karakter gerekir.
# Yerel HTTP geliştirmesinde:
$env:COOKIE_SECURE = "0"
../.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Diğer roller için komutta `--role staff` veya `--role viewer` kullanın. Varsayılan hesap/parola ve imzalama anahtarı yoktur. Linux/macOS üzerinde `.venv/bin/python` kullanılır.

Parolalar rastgele tuzla scrypt (N=32768, r=8, p=3) kullanılarak özetlenir. Rastgele oturum belirtecinin yalnızca SHA-256 özeti SQLite'ta tutulur. Oturum 8 saat sonra sona erer; yeniden giriş belirteci yeniler, çıkış mevcut oturumu sunucudan siler. Çerez HttpOnly, SameSite=Strict ve varsayılan olarak Secure'dur. HTTP için `COOKIE_SECURE=0` yalnızca yerel geliştirmede kullanılmalıdır; HTTPS dağıtımında bu ayarı kaldırın. Oturum bilgileri localStorage'a yazılmaz. Yazma işlemlerinde CSRF belirteci, girişte özel başlık gerekir; CORS açılmamıştır. API yanıtları önbelleğe alınmaz.

Kullanıcı adı ve bağlantı IP'si başına 15 dakikada 5 başarısız girişten sonra 429 döner. Proxy arkasında istemci IP'si yalnızca güvenilir proxy yapılandırmasıyla kullanılmalıdır. Bu aşamada parola sıfırlama, MFA ve merkezi denetim kaydı yoktur; HTTPS ve dağıtım yapılandırması ayrıca doğrulanmalıdır.

Mevcut müşteri/ürün tabloları ve örnek veri ekleme davranışı korunur. Yeni kimlik tabloları `CREATE TABLE IF NOT EXISTS` ile eklenir; testler geçici veritabanları kullanır.

## Doğrulama

- API: `cd backend; ../.venv/Scripts/python.exe -m pytest -q --basetemp=../test-temp`
- İş kuralları (HTTP sunucusu gerektirmez): `cd backend; ../.venv/Scripts/python.exe -m pytest tests/test_user_rules.py -q --basetemp=../test-temp-rules`
- Arayüz: `cd frontend; npm run build`
- Tarayıcı: `cd frontend; npm run test:e2e`

Güncel çalıştırma sonuçları teslim notunda belirtilir. Mobil testler Chromium telefon ekranı benzetimidir; gerçek cihaz veya canlı ortam testi değildir.

## Sipariş oluşturma ve stok — ikinci iş aşaması

Menüde **Siparişler → Sipariş oluştur** seçin. Müşteriyi ve en fazla 50 farklı ürün satırını seçip adetleri girin. Yönetici ve personel sipariş oluşturabilir; salt okunur hesap yalnızca listeyi görüntüler.

Birim fiyatlar ve kesin toplam sunucudaki güncel ürün kayıtlarından alınır. Tutarlar kuruş olarak hesaplanır ve saklanır. Kaydedilen siparişin ürün adı, kodu, birim fiyatı ve miktarı saklanır. Sipariş `Bekliyor` durumunda oluşturulur; stok o anda düşer ve panel özeti güncellenir.

Stok yetmezse, müşteri/ürün yoksa veya herhangi bir satır geçersizse sipariş ve stok değişiklikleri birlikte iptal edilir. SQLite yazma kilidi altında yapılan kontrol, son ürünün eşzamanlı iki siparişe satılmasını önler. Form her yeni siparişte bir istek kimliği oluşturur; aynı kimlikle aynı isteğin tekrarı önceki siparişi döndürür ve stoktan yeniden düşmez. Aynı kimliğin farklı bilgilerle kullanılması 409 hatası verir.

Mevcut sipariş kayıtları korunur; eski örnek siparişlere geriye dönük stok düşümü yapılmaz. Eski kayıtlarda ürün detayı olmadığı belirtilir. Şema geçişi eksik sütunları ve ürün satırları tablosunu ekler; müşteri ve ürün kayıtlarını silmez. Mevcut SQLite veritabanını kullanmaya devam edebilirsiniz.

Bu aşamada ürün bazında kısmi iade, sipariş düzenleme, iskonto ve KDV ayrıştırma eklenmedi. Bekleyen siparişlerin tamamı aşağıdaki iptal akışıyla geri alınabilir. Gösterilen tutar mevcut ürün fiyatlarının toplamıdır; fatura düzenlenmez.

## Bekleyen sipariş iptali ve stok iadesi

**Siparişler** listesindeki uygun siparişin **İptal et** düğmesine basın. İptal nedenini (3–500 karakter) girip onaylayın. Onaydan önce **Vazgeç** veya **Kapat** ile işlemi bırakabilirsiniz. Yönetici ve personel iptal yapabilir; salt okunur hesap yapamaz.

Yalnızca Bekliyor durumundaki ve ürün satırları kayıtlı siparişler iptal edilir. Hazırlanıyor, Dağıtımda ve Teslim edildi durumları bu aşamada iptale kapalıdır. Ürün satırı olmayan eski örnek siparişlerde hatalı stok iadesini önlemek için iptal engellenir.

İptal edilen sipariş silinmez; tutarı ve ürün satırları korunur, durumu İptal edildi olur. Neden, İstanbul saat dilimindeki zaman ve işlemi yapan kullanıcının kimliği veritabanına kaydedilir. Siparişin tamamındaki miktarlar stoklara bir kez geri eklenir. İptal edilenler günlük satış ve iptal edilmemiş sipariş sayısından çıkarılır; son siparişlerde durumuyla birlikte görünür. Tahsilat kaydı değiştirilmez.

Stok iadesi, durum değişikliği ve iptal kaydı aynı SQLite işlemi içinde, yazma kilidi altında yapılır. Tekrarlanan/eşzamanlı iptal ikinci kez stok eklemez; ilk iptal kaydı döner. Ürün yoksa veya stok üst sınırı aşılacaksa hiçbir değişiklik yapılmaz. İptal edilmiş siparişin eski oluşturma isteğini tekrar göndermek de yeni satış oluşturmaz.

Kısmi iade, teslim edilmiş ürün iadesi, iptali geri alma ve tahsilat iadesi bu aşamanın kapsamı dışındadır. Tahsilatı bulunan bir siparişin iptali müşterinin hesabında alacak oluşturabilir; otomatik para iadesi yapılmaz.

## Tahsilat kaydı ve müşteri bakiyesi

**Tahsilat ve bakiyeler → Tahsilat ekle** yoluyla müşteri, tutar, yöntem (Nakit, Havale/EFT, Kart) ve isteğe bağlı açıklama girilir. Yönetici ve personel kayıt ekleyebilir; salt okunur hesap liste ve bakiyeleri görüntüler. Bu ekran bir kayıt aracıdır; karttan/bankadan ödeme çekmez.

Tutar 0,01–10.000.000 TL arasında, en fazla iki ondalık basamakla kabul edilir ve kuruş cinsinden tam sayı olarak saklanır. Tarih sunucuda bugünün İstanbul tarihi olarak atanır; ayrıca zaman ve işlemi yapan kullanıcı kaydedilir. Aynı istek kimliğiyle aynı tahsilat tekrar gönderilirse önceki kayıt döner; ikinci kayıt oluşmaz. Aynı kimlikle farklı müşteri/tutar/yöntem/açıklama reddedilir. Kontroller ve kayıt SQLite yazma kilidi altında yapılır; kullanıcının aktifliği ve rolü yeniden kontrol edilir.

**Müşteri bakiyesi = müşterinin tüm iptal edilmemiş siparişleri − müşteriye bağlı iptal edilmemiş tahsilatları.** Tarih filtresi uygulanmaz; günlük panelde ise yalnızca o günün toplamı gösterilir. Pozitif bakiye müşterinin borcu, negatif bakiye müşterinin alacağı, sıfır ise kapalı hesap olarak gösterilir. Avans/fazla tahsilat kaydedilebilir. Sipariş iptali tahsilat kaydını silmez veya para iadesi yapmaz; gerekirse müşteri alacağı oluşur.

Eski örnek tahsilatın müşteri bilgisi yoktur. Bu kayıt silinmez veya rastgele bir müşteriye atanmaz; listede müşterisiz eski kayıt olarak görünür. Kendi tarihindeki genel tahsilat toplamına dahildir, müşteri bakiyelerinden düşülmez. Bu nedenle tüm müşterilerin tahsilat toplamı ile eski müşterisiz kayıtları içeren genel toplam farklı olabilir. Ekranda bu durum açıklanır.

Yeni müşteriler sıfır bakiyeyle başlar. Sipariş ve tahsilat toplamları ayrı ayrı hesaplanır; birden çok kayıt toplamların katlanmasına yol açmaz. Müşteriye göre filtre tahsilat listesini ve bakiye tablosunu birlikte süzer.

Bu aşamada açılış bakiyesi, eski tahsilatları müşteriye eşleştirme, geriye dönük tarih, tahsilat düzenleme/para iadesi, banka entegrasyonu veya muhasebe fişi eklenmedi. Güncelleme mevcut kayıtları koruyarak tahsilat tablosuna isteğe bağlı müşteri ve kayıt bilgisi sütunlarını ekler.

## Müşteri ve ürün düzenleme

Müşteriler veya Ürünler ve stok listesindeki kaydın **Düzenle** düğmesine basın. Mevcut bilgiler forma gelir; değişikliklerden sonra **Kaydet** seçin. Yönetici ve personel düzenleyebilir; salt okunur kullanıcıda düğme görünmez ve sunucu isteği reddeder. Kayıt silme eklenmedi.

Müşterinin firma adı, yetkilisi, telefonu ve bölgesi; ürünün adı, kodu, kategorisi, fiyatı, stok adedi ve kritik stok eşiği düzenlenebilir. Ürün kodunun benzersizliği ve mevcut alan doğrulamaları korunur. Stok alanına işlem sonrası toplam adet yazılır; girilen sayı stoğa eklenen miktar değildir. Bu işlem manuel stok düzeltmesidir; takip başladıktan sonra fark, hareket geçmişine kaydedilir.

Her kayıt bir sürüm taşır. İki kullanıcı aynı kaydı açarsa ilk başarılı güncelleme sürümü artırır; ikinci eski form 409 hatasıyla reddedilir. Sipariş oluşturma ve iptal/stok iadesi de ürünün sürümünü artırır. Böylece eski bir ürün formu yeni stok hareketinin üzerine yazamaz. **Güncel listeyi yükle** düğmesi formu kapatır ve listeyi yeniler; sonra Düzenle ile güncel kayıt yeniden açılır. Hatalı güncelleme veya mükerrer kodda kayıt değişmez.

Ürün fiyatı/adı/kodu değişikliği eski sipariş satırlarında saklanan bilgileri değiştirmez; yeni sipariş güncel bilgileri kullanır. Müşteri kimliği değişmediği için sipariş ve tahsilat bağlantıları, kayıt sayıları ve bakiye tutarları korunur. Müşteri adı güncellenirse ilişkili listelerde güncel adı görünür.

Şema geçişi mevcut müşteri ve ürün tablolarına varsayılanı sıfır olan sürüm sütunu ekler; mevcut satırları silmez veya yeniden oluşturmaz. API güncellemesi POST /api/customers/{id} ve POST /api/products/{id} uçlarında, bütün form alanları ve listeden alınan expected_version ile yapılır. Yazma kilidi altında güncel rol ve sürüm yeniden kontrol edilir.

## Tahsilat iptali ve bakiye düzeltmesi

**Tahsilat ve bakiyeler** ekranında müşteriyle ilişkili yeni tahsilatın **İptal et** düğmesi yalnızca yöneticilere görünür. Müşteri ve tutarı kontrol edin, 3–500 karakterlik nedeni girip **Tahsilat iptalini onayla** seçin. Onaydan önce Vazgeç/Kapat/Escape ile çıkılabilir. Personel tahsilat eklemeye devam edebilir, iptal yapamaz; salt okunur kullanıcılar kayıt ekleyemez veya iptal edemez.

İptal gerçek para iadesi değildir. Kayıt silinmez; asıl tutar, tarih, yöntem ve açıklama korunur. Neden, İstanbul saat dilimindeki iptal zamanı ve işlemi yapan kullanıcı kimliği ayrı iptal kaydında saklanır. Listede İptal edildi durumu, neden ve üzeri çizili tutar görünür; yeniden iptal düğmesi gösterilmez.

İptal edilmiş tahsilatlar müşteri tahsilat toplamından çıkarılır; bakiye buna göre yeniden hesaplanır. Avans/alacak bakiyesi de doğru yönde düzelir. Günlük panel tahsilatın kendi tarihindeki geçerli kayıtları toplar: bugünkü kayıt iptal edilirse bugünün toplamı azalır; geçmiş tarihli kayıt iptal edilirse bugünün toplamı değişmez. Siparişler, satış toplamı ve stok değişmez.

İptal yazma kilidi altında ve güncel yönetici yetkisi yeniden kontrol edilerek yapılır. Tahsilat başına tek iptal kaydı vardır. Tekrarlanan/eşzamanlı istekler ilk iptali döndürür; bakiye ikinci kez değiştirilmez ve ilk neden/zaman korunur. Eski oluşturma isteğini tekrar göndermek iptal edilmiş tahsilatı tekrar etkinleştirmez.

Müşteri veya oluşturma detayı olmayan eski örnek tahsilatlar bu aşamada iptale kapalıdır. Eski kayıtlar aynen korunur. Kısmi tahsilat iptali, iptali geri alma, tahsilat düzenleme ve banka/kart para iadesi bu aşamada yoktur. Yeni iptal tablosu mevcut verileri silmeden oluşturulur.

## Sipariş hazırlık, dağıtım ve teslim aşamaları

**Siparişler** listesindeki sıradaki aşama düğmesini kullanın: **Hazırlığa al → Dağıtıma çıkar → Teslim edildi olarak işaretle**. Her işlemde sipariş/müşteri ve eski/yeni aşama gösterilir; **Aşamayı onayla** ile kaydedilir. Onay öncesinde Vazgeç/Kapat/Escape ile çıkılabilir. Yönetici ve personel ilerletebilir; salt okunur kullanıcılar yalnızca durumu/geçmişi görüntüler.

İzin verilen sıra **Bekliyor → Hazırlanıyor → Dağıtımda → Teslim edildi** şeklindedir. Aşama atlama, geriye alma veya teslim/iptal edilmiş siparişi yeniden ilerletme reddedilir. Bekleyen siparişlerin önceki iptal kuralları korunur; hazırlığa alınan sipariş artık bu akıştan iptal edilemez. Teslim aşaması yalnızca uygulama içi kayıttır; teslim imzası, belge veya harici taşıyıcı işlemi oluşturmaz.

Stok sipariş oluşturulurken düşmüştür. Aşama değişikliği tekrar stok düşmez, ürün sürümünü değiştirmez; sipariş tutarı, müşteri bakiyesi, satış ve tahsilat toplamları değişmez. Panelin son siparişler bölümünde güncel durum görünür.

Her başarılı geçişte önceki/yeni durum, İstanbul saat dilimindeki zaman ve işlemi yapan kullanıcı kaydedilir. Satırdaki **Aşama geçmişi** açılarak görülebilir. Eski örnek siparişler mevcut aşamalarından ilerletilebilir; geçmişleri geriye dönük uydurulmaz, yalnızca yeni işlemler kaydedilir.

İstek kimliği aynı geçişin yeniden/eşzamanlı gönderilmesini tek kayda indirger. Aynı kimlikle farklı işlem reddedilir. İki kullanıcı aynı eski durumdan farklı isteklerle ilerlemeye çalışırsa biri başarılı olur, diğeri güncel listeyi yüklemeye yönlendirilir. Yazma kilidi altında kullanıcı rolü ve mevcut durum yeniden kontrol edilir. İptal ile hazırlığa alma eşzamanlı olduğunda yalnızca biri uygulanır. Aynı eski isteğin daha sonraki bir aşamada tekrar gönderimi güncel siparişi döndürür; siparişi geriye almaz veya tekrar ilerletmez.

Bu aşamada geri geçiş, toplu durum değiştirme, dağıtımdaki/teslim edilmiş sipariş iadesi veya teslim belgesi eklenmedi.

## Stok girişleri ve hareket geçmişi

Menüde **Stok hareketleri → Stok girişi ekle** seçin. Ürün, eklenecek pozitif tam adet ve 3–300 karakterlik açıklama girilir. Girilen miktar mevcut stoğa eklenir; toplam stok 10.000.000 adedi geçemez. Yönetici ve personel giriş yapabilir, salt okunur kullanıcı yalnızca görüntüler. Bu kayıt satın alma faturası veya tedarikçi borcu oluşturmaz.

Ürüne göre filtre hem stok özetini hem hareket listesini süzer. Güncel stok, takip başlangıç stoğu ve kayıtlı hareketlerin net değişimi birlikte gösterilir. **Güncel stok = takip başlangıç stoğu + kayıtlı net hareket** kuralı geçerlidir. İlk güncellemede mevcut stoklar başlangıç kabul edilir; geçmiş siparişleri yeniden işleyerek stok değiştirilmez ve eski hareketler uydurulmaz.

Takip başladıktan sonra yeni ürünün pozitif açılış stoğu, stok girişi, sipariş çıkışı, sipariş iptal iadesi ve ürün düzenleme ekranından yapılan stok düzeltmesi kaydedilir. Her harekette ürün adı/kodu o andaki haliyle, miktar farkı, önceki/sonraki stok, İstanbul saatinde zaman, kullanıcı, açıklama ve varsa sipariş numarası bulunur. Sıfır stokla ürün açılması veya yalnızca fiyat/ad değişikliği miktar hareketi üretmez. Aşama ilerletme ve tahsilat işlemleri stok hareketi oluşturmaz.

Ürünler ve stok ekranındaki stok alanı hâlâ işlem sonrası toplam adettir; örneğin 10'dan 7'ye düzeltme -3 hareketi üretir. Stok girişi ekranındaki 7 ise mevcut stoğa +7 ekler. Manuel düzeltme hareketinde açıklama kaynağı ürün düzenleme ekranı olarak saklanır; ayrı neden alanı bu aşamada eklenmedi.

Stok ve hareket kaydı aynı SQLite işlemi içinde yazılır; hareket kaydı hatasında stok değişikliği geri alınır. Giriş, ürün sürümünü artırır ve eski düzenleme formlarının üzerine yazmasını engeller. Tekrarlanan/eşzamanlı aynı giriş tek hareket oluşturur; farklı girişlerin miktarları kaybolmadan toplanır. Sipariş ve iptal tekrarları hareketi ikinci kez üretmez.

Hareket kayıtlarını düzenleme/silme, stok girişini iptal etme, depo/parti/son kullanma tarihi takibi, tedarikçi hesabı ve geçmişe dönük hareket oluşturma bu aşamada yoktur. Başlangıç kaydı mevcut stok durumudur; geçmiş bir fiziksel teslimatı temsil etmez.


## Günlük rota

Menüde **Günlük rota** seçin. Ekran İstanbul saatine göre bugünün haftalık ziyaret planıyla açılır. Pazartesi–Pazar düğmeleri müşteri sayısını gösterir; gün seçimi hem listeyi hem haritayı süzer. Birden fazla rota günü olan müşteri ilgili günlerin her birinde görünür. **Bugünün rotası** güncel güne döner.

Arama ve GPS filtresi seçili gün içinde çalışır. GPS bilgisi eksik müşteriler listede kalır; uydurma konum işaretlenmez. **Günü atanmayan müşteriler** görünümünden müşteri seçip **Rota günü** kısayoluyla ziyaret günleri belirlenebilir. Kaydedilen değişiklikler listeye ve gün sayılarına yansır. Seçilen müşteri için hesap ekstresi ve yetkili kullanıcıların satış, tahsilat, rota günü ve kart düzenleme işlemleri kullanılabilir.

Bu ekran haftalık ziyaret planını gösterir; yol tarifi, otomatik durak sıralaması veya ziyaret tamamlama kaydı üretmez. Rota, harita ve cihaz konumu için 18 ön yüz birim testi bulunur.

## Günlük ziyaret takibi

Günlük rota ekranında **Ziyaret tarihi → Tarihi göster** ile tarih seçilir. Gün düğmeleri seçili tarihin haftasında gezinir; **Bugünün rotası** İstanbul takvimine göre bugüne döner. Müşteri seçilerek **Ziyaret edildi** işaretlenebilir veya **Ziyaret edilmedi** ile geri alınabilir. Sayaç ve ziyaret filtresi seçili müşteri kapsamına uygulanır; arama ve GPS filtresiyle birlikte listeyi ve haritayı süzer. Henüz kaydı olmayan müşteri ziyaret edilmedi kabul edilir.

Ziyaret durumu müşteri ve kesin takvim tarihi bazında ortak şirket kaydıdır, kullanıcıya özel değildir. Başka haftaya taşınmaz. Geçmiş tarih kayıtları görüntülenebilir ve yetkili kullanıcılarca düzeltilebilir; gelecek tarihe kayıt engellenir. Geçmiş günün müşteri listesi güncel haftalık plana göre oluşturulur; geçmiş planın anlık kopyası tutulmaz. Rota günleri sonradan değişse de eski ziyaret kayıtları veritabanında korunur.

Yönetici ve personel durumu değiştirebilir, salt okunur kullanıcı görüntüler. Son kaydı yapan kullanıcı ve İstanbul saati gösterilir. Her değişiklik ayrıca olay kaydında tutulur. Ziyaret sürümü eşzamanlı eski bir güncellemenin üzerine yazmayı engeller; çakışmada **Ziyaretleri yenile** seçilir. Ziyaret yazımı ve olay kaydı tek veritabanı işlemidir; satış, tahsilat ve stok değiştirilmez. Eski veritabanı ilk güncellemeden önce yedeklenir.

## Ziyaret notu ve edilememe nedeni

Günlük rotada tarih ve müşteri seçip **Müşteri ziyaret durumu**, **Ziyaret notu** (en fazla 1000 karakter) ve ziyaret edilmedi için **Ziyaret edilememe nedeni** (en fazla 300 karakter) alanlarını doldurun; **Ziyaret kaydını kaydet** seçin. Açıklamalar isteğe bağlıdır; boş kaydetmek alanı temizler. Durum ve metinler aynı kayıt içinde saklanır. Ziyaret edildi seçildiğinde edilememe nedeni temizlenir, ziyaret notu korunur.

Notlar müşteri/tarih bazındadır. Son değiştiren kullanıcı ve saat gösterilir; her değişikliğin açıklama anlık kopyası olay kaydında korunur. Salt okunur kullanıcılar açıklamaları görebilir fakat değiştiremez. Eski istemciler açıklama göndermeden durum güncellediğinde mevcut notlar korunur; ziyaret edildi durumuna geçiş her zaman edilememe nedenini temizler. Eski kayıtların açıklamaları boş başlatılır ve güncellemeden önce veritabanı yedeklenir.

## Müşteri ziyaret geçmişi

Müşteri listesinde, müşteri kartında veya harita/rota müşteri bilgisinde **Ziyaret geçmişi** seçin. Her kayıtlı tarihin son durumu; ziyaret notu, edilememe nedeni, son kaydı yapan kişi ve İstanbul saatinde kayıt zamanı ile yeniden eskiye gösterilir. Aynı gündeki tüm düzeltmeler ayrı ziyaret olarak sayılmaz. Hiç kayıt girilmemiş günler geçmişe eklenmez.

Başlangıç/bitiş tarihleri isteğe bağlıdır, sınır günler dahildir. Alanları boş bırakıp **Geçmişi göster** seçmek tüm tarihleri gösterir. Liste 50 kayıtlık sayfalara ayrılır; sayaçlar seçili tarih aralığının tamamını kapsar. Ekran tüm oturum açmış roller için salt okunurdur; kayıt veya müşteri kartındaki kaydedilmemiş bilgileri değiştirmez.

## Günlük rota özeti

Günlük rota ekranındaki özet; seçili tarihin gününe güncel planda atanmış müşterilerin sayısını, ziyaret edilen/kalan sayılarını, satış ve tahsilat toplamlarını gösterir. **Günü atanmayan müşteriler** seçildiğinde yalnızca gün atanmamış müşteriler kapsanır. Arama, GPS ve ziyaret filtresi özet toplamlarını değiştirmez. **Özeti yenile** sunucudan güncel toplamı alır; ziyaret kaydı ve rota değişiklikleri özeti yeniden yükler.

Satış, seçili tarihte oluşturulan ve halen geçerli olan siparişlerin kuruş bazında toplamıdır; bekleyen siparişler de dahildir. İptal edilen sipariş ve tahsilatlar, farklı tarihli işlemler, rota dışı müşteriler ve müşteriye bağlanmamış eski tahsilatlar dahil edilmez. İptal daha sonra yapılsa da işlem özgün gün toplamından çıkarılır; bu özet dönem muhasebe ekstresi değildir. Satış/tahsilat kaydı otomatik ziyaret oluşturmaz. Geçmiş tarihler güncel rota planına göre hesaplanır. Özet salt okunurdur, tüm oturum açmış roller görüntüleyebilir.
