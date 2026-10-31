# Doğa Gıda V2

Türkçe ve mobil uyumlu React + TypeScript yönetim paneli; FastAPI ve SQLite backend.
Bu ilk sürüm yalnızca örnek veriler içerir. Kimlik doğrulama henüz eklenmediğinden gerçek müşteri verileriyle veya herkese açık canlı ortamda kullanılmamalıdır.

## Özellikler

- İstanbul saatine göre günlük satış, sipariş ve tahsilat özeti
- Toplam müşteri, stok ve kritik stok göstergeleri
- Son siparişler (örnek kayıtlar)
- Müşteri listeleme, arama ve ekleme
- Ürün listeleme, arama ve ekleme; benzersiz ürün kodu kontrolü
- SQLite üzerinde kalıcı kayıtlar; para tutarları veritabanında kuruş olarak saklanır
- Form doğrulama, yüklenme ve hata durumları

Sipariş ve tahsilat oluşturma, kullanıcı girişi, yetkilendirme, çevrimdışı çalışma ve muhasebe entegrasyonu bu sürümün kapsamına dahil değildir. Mobil testler Chromium telefon ekranı benzetimidir; gerçek Android/iPhone cihaz testi yapılmamıştır.

## Gereksinimler

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

Uçtan uca testler için ayrı bir backend terminalinde (normal sunucu 8000 portunda çalışmamalı):

```bash
cd backend
DATABASE_PATH=/tmp/doga-e2e.db ../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Diğer terminalde:

```bash
cd frontend
npm run test:e2e
```

Test yapılandırması `/usr/bin/chromium` kullanır. Farklı kurulumda `CHROMIUM_PATH` ile Chromium çalıştırılabilir dosyasını belirtin. Testler yalnızca ayrı test veritabanına örnek müşteri ve ürün ekler. Masaüstü (1440×1000) ve mobil (390×844) boyutlarında listeleme, ekleme, arama, yeniden yükleme sonrası kalıcılık ve yatay taşma kontrol edilir. Ekran görüntüleri `/tmp/doga-desktop.png` ve `/tmp/doga-mobile.png` olarak alınır.

## Proje yapısı

```text
backend/main.py                FastAPI, SQLite, örnek veri ve API uçları
backend/requirements.txt       Python bağımlılıkları
backend/tests/test_api.py      API ve veri doğrulama testleri
frontend/src/main.tsx          React ekranları ve formlar
frontend/src/style.css         Mobil uyumlu tasarım
frontend/vite.config.ts        Geliştirme sunucusu ve API proxy
frontend/tsconfig.json         TypeScript ayarları
frontend/playwright.config.ts  Tarayıcı test ayarları
frontend/tests/app.spec.ts     Masaüstü ve mobil test akışları
frontend/package-lock.json     Kilitli JavaScript bağımlılıkları
```

## Doğrulanan sonuçlar

- TypeScript kontrolü ve Vite derlemesi başarılı.
- 5 backend testi başarılı.
- 2 Chromium uçtan uca testi başarılı (masaüstü ve mobil).
- Backend testlerinde bağımlılık kaynaklı bir AnyIO kullanım dışı bırakma uyarısı var; test hatası değil.

Bu sonuçlar mevcut geliştirme ortamına aittir; canlı dağıtım veya gerçek cihaz doğrulaması anlamına gelmez.
