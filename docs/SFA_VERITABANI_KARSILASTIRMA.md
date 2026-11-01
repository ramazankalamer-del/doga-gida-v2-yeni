# SFA — veritabanı karşılaştırması

İnceleme: 2 Kasım 2026. Bu dosya tablo/alan envanteri ve bulguları içerir; **aktarım veya şema değişikliği yapılmadı**. Kaynak bağlantıları salt okunur açıldı; uygulama başlatılmadı.

## Kaynaklar ve doğrulama

| Özellik | Eski gerçek katalog | Mevcut V2 |
| --- | --- | --- |
| Dosya etiketi | `doga_gida_yeni_paket/.../backend/doga_gida_dev.db` | `work/doga-gida-v2-yeni/smoke.db` |
| Tablo sayısı | 3 | 35 |
| Ürün | **124 gerçek** | **5 örnek** |
| Depo | 2: MERKEZ / IADE | Kodlarla uygulama içinde tanımlı; ayrı warehouses tablosu yok |
| Müşteri | Tablo yok | 4 |
| Stok hareketi | Tablo var, **0 kayıt** | 3 |
| Alış | Tablo yok | 1 alış, 1 satır |
| Depo işlemi | Eski hareket tablosu boş | 1 warehouse_actions kaydı |
| Sipariş | Tablo yok | 4; ürün satırı 0 |
| Tahsilat | Tablo yok | 1 |
| Bütünlük | integrity_check=ok; FK ihlali 0 | integrity_check=ok; FK ihlali 0 |

V2 örnek ürünlerine bağlı sonradan girilmiş alış/depo/stock kayıtları bulundu. Örnek ürünler gelişigüzel silinemez veya gerçek ürüne yeniden bağlanamaz. Kullanıcı ve diğer mevcut kayıtların tamamı korunmalıdır.

Üç ayrı yerel 124 ürünlü kopyanın products, warehouses ve stock_movements içerik parmak izleri aynı çıktı. Doğrulanmış inceleme kaynağı indirilen `doga_gida_yeni_paket` kopyasıdır; üçü birden içe alınırsa mükerrer katalog oluşur.

## Ürün alan eşlemesi

| Eski alan | Mevcut V2 karşılığı | Aktarım için gerekli yaklaşım |
| --- | --- | --- |
| id | products.id | Aynı ID ile üzerine yazılmaz; kaynak ID → yeni hedef ID eşlemesi korunur. |
| code | sku | Metin ve baştaki sıfırlar korunur; normalize eşleştirme anahtarı ve UNIQUE denetimi. |
| name | name | Aynen korunur; kesilmez. |
| barcode | Yok | Nullable yeni alan; boş barkod üretilmez. |
| unit | Yok | Orijinal birim aynen korunur. |
| sales_unit | Yok | Satış birimi ayrı saklanır. |
| base_unit | Yok | Temel birim ayrı; doğrulanmış dönüşüm katsayısı ayrıca gerekir. |
| category | category | Orijinal değer ve NULL durumu korunur; zorunluluk farkı migration ile ele alınır. |
| subcategory | Yok | Nullable yeni alan. |
| sales_vat_code | Yok | Kod aynen korunur; doğrulanmadan vergi oranı sayılmaz. |
| purchase_vat_code | Yok | Alış KDV kodu ayrı korunur. |
| source_status | Yok | Orijinal kaynak durum metni korunur. |
| is_active | Yok | Kaynak aktifliği ile satışa hazır/fiyatlı olma ayrı durumlar olmalı. |
| created_at | Yok | Orijinal tarih/metin korunur; kaynakta olmayan saat dilimi varsayılmaz. |

**Eski products tablosu 14 alan içeriyor; fiyat alanı yok.** V2 fiyatı `price_cents INTEGER NOT NULL` olarak tutuyor ve ürün API’si pozitif fiyat istiyor. Mevcut ürünler üzerine yazmadan veya sahte fiyat üretmeden fiyat-bilinmiyor durumunu destekleyecek kontrollü şema/API hazırlığı gerekiyor.

| V2 ek alanı | Eski kaynakta var mı? | Sonuç |
| --- | --- | --- |
| price_cents | Yok | Yönetici fiyat belirlemeden gerçek satış açılamaz. |
| stock / return_stock | Ürün üzerinde yok; hareketler boş | Fiziksel açılış stoğu bilinmiyor; 0 olduğu varsayılamaz. |
| min_stock | Yok | Yönetici stok politikası gerekir; örnek eşik gerçek değer sayılmaz. |
| version | Yok | Hedefte eşzamanlılık alanı olarak yönetilir; kaynak verisi değildir. |

## Kod, birim ve veri kalitesi

- Gerçek ürün: 124; boş kod: 0; boş ad: 0.
- Baştaki sıfır içeren kod: **67**; normalize kod mükerrerliği: **0**; V2 örnek SKU çakışması: **0**.
 - Kaynak ID 1–124; V2 örnek ID 1–5 ile çakışır. Ürün kodunun çakışmaması ID’lerin aynı kullanılabileceği anlamına gelmez.
- Tüm 124 kaynak ürün aktif; barkod dolu ürün sayısı 0.
- Birim ve satış birimi: KL=102, KOL=5, AD=10, ADT=7. Temel birim: KL=102, ADT=12, AD=10.
- Satış ve alış KDV kodları: 1→67 ürün, 10→49 ürün, 20→5 ürün, 0→3 ürün. Bunlar kaynak kodlarıdır; oran/istisna karşılığı ayrıca doğrulanmalı.
- 17 kategori. Mevcut en uzun kod 20, ad 45, kategori 14, alt kategori 12 karakter; bugünkü 124 kaydın uzunlukları V2 kod/ad/kategori üst sınırlarını aşmıyor. Kaynak şema sınırları farklı olduğundan genel import yine kontrol etmelidir.
- Kodları trim/büyük harf normalizasyonu bu örnekte yeni çakışma oluşturmuyor; orijinal metinler yine korunmalı.

## Stok ve hareket modeli farkı

- Eski hareket miktarı `NUMERIC(14,3)`; V2 miktarı tam sayı. Ondalıklı miktar olursa yuvarlama/kesme kabul değil.
- Eski iki depo gerçek kaynak kayıtlarıdır. V2’de `MERKEZ` ve `IADE` kodları vardır; depolar kodla eşlenmeli, ikinci kez oluşturulmamalı.
- Eski stock_movements tablosu boş. Başlangıç stoğu veya başka kaynaktaki hareketlerin tamlığı hakkında sonuç çıkarılamaz. Bu yalnızca incelenen dosyanın durumudur.
- V2 stokları ve alış/depo işlemleri 5 örnek ürüne bağlıdır; gerçek ürünlerin açılış stoğu gibi kullanılamaz.

## Yedek doğrulama özeti

Yedek dosyaları depo dışındaki yerel `outputs/SFA-Yedekleri/2026-11-02_01-20-39/` klasöründedir. Tam yerel kaynak/yedek yolları ve alan/parmak izi kanıtları yalnızca yerel `dogrulama.json` dosyasında tutulur; GitHub’a yüklenmez.

| Kaynak | Kaynak ve yedek SHA-256 | Sonuç |
| --- | --- | --- |
| Eski | `7056af5e415907cd05467319484183eea772f44ef5887e56ed484c6322109d7a` | Byte eşit; tüm tablolar eşit; integrity ok; FK 0; kaynak değişmedi |
| V2 | `d38a02455caf5ec5cfaab8627e1d31987c17cc7a7fb222c59282290befaeb4d1` | Byte eşit; tüm tablolar eşit; integrity ok; FK 0; kaynak değişmedi |

## Tam tablo ve alan envanteri

Aşağıdaki sayımlar inceleme anının yerel fotoğrafıdır. Ürün adları, müşteri bilgileri, parola özetleri ve oturum değerleri bu belgeye aktarılmadı. `NOT NULL`, varsayılan ve PK bilgileri yerel doğrulama raporunda ayrıca bulunur.

### Eski veritabanı

| Tablo | Kayıt | Alanlar (SQLite tipi) |
| --- | ---: | --- |
| `products` | 124 | `id INTEGER PK`; `code VARCHAR(50)`; `name VARCHAR(200)`; `barcode VARCHAR(80)`; `unit VARCHAR(20)`; `sales_unit VARCHAR(20)`; `base_unit VARCHAR(20)`; `category VARCHAR(80)`; `subcategory VARCHAR(100)`; `sales_vat_code INTEGER`; `purchase_vat_code INTEGER`; `source_status VARCHAR(30)`; `is_active BOOLEAN`; `created_at DATETIME` |
| `stock_movements` | 0 | `id INTEGER PK`; `warehouse_id INTEGER`; `product_id INTEGER`; `movement_type VARCHAR(30)`; `quantity_delta NUMERIC(14, 3)`; `reference_no VARCHAR(80)`; `transfer_group VARCHAR(36)`; `note TEXT`; `created_at DATETIME` |
| `warehouses` | 2 | `id INTEGER PK`; `code VARCHAR(30)`; `name VARCHAR(100)`; `warehouse_type VARCHAR(20)`; `is_active BOOLEAN`; `created_at DATETIME` |

### V2 veritabanı

| Tablo | Kayıt | Alanlar (SQLite tipi) |
| --- | ---: | --- |
| `collection_cancellations` | 0 | `collection_id INTEGER PK`; `user_id INTEGER`; `reason TEXT`; `cancelled_at TEXT` |
| `collection_finance_links` | 0 | `collection_id INTEGER PK`; `entry_id INTEGER` |
| `collections` | 1 | `id INTEGER PK`; `amount_cents INTEGER`; `date TEXT`; `customer_id INTEGER`; `request_id TEXT`; `created_by INTEGER`; `method TEXT`; `note TEXT`; `created_at TEXT` |
| `commercial_return_cancellations` | 0 | `return_id INTEGER PK`; `reason TEXT`; `user_id INTEGER`; `cancelled_at TEXT` |
| `commercial_return_items` | 0 | `return_id INTEGER PK`; `product_id INTEGER PK`; `name TEXT`; `sku TEXT`; `quantity INTEGER`; `price_cents INTEGER`; `cost_cents INTEGER` |
| `commercial_returns` | 0 | `id INTEGER PK`; `kind TEXT`; `order_id INTEGER`; `purchase_id INTEGER`; `warehouse TEXT`; `date TEXT`; `amount_cents INTEGER`; `note TEXT`; `request_id TEXT`; `payload TEXT`; `created_by INTEGER`; `created_at TEXT` |
| `customer_route_days` | 0 | `customer_id INTEGER PK`; `weekday INTEGER PK` |
| `customer_visit_events` | 0 | `id INTEGER PK`; `customer_id INTEGER`; `visit_date TEXT`; `visited INTEGER`; `version INTEGER`; `updated_by INTEGER`; `updated_at TEXT`; `note TEXT`; `reason TEXT` |
| `customer_visits` | 0 | `customer_id INTEGER PK`; `visit_date TEXT PK`; `visited INTEGER`; `version INTEGER`; `updated_by INTEGER`; `updated_at TEXT`; `note TEXT`; `reason TEXT` |
| `customers` | 4 | `id INTEGER PK`; `name TEXT`; `contact TEXT`; `phone TEXT`; `district TEXT`; `version INTEGER`; `latitude REAL`; `longitude REAL` |
| `finance_accounts` | 0 | `id INTEGER PK`; `name TEXT`; `kind TEXT`; `opening_cents INTEGER`; `request_id TEXT`; `created_by INTEGER`; `created_at TEXT` |
| `finance_cancellations` | 0 | `entry_id INTEGER PK`; `reason TEXT`; `user_id INTEGER`; `cancelled_at TEXT` |
| `finance_entries` | 0 | `id INTEGER PK`; `account_id INTEGER`; `kind TEXT`; `amount_cents INTEGER`; `date TEXT`; `category TEXT`; `note TEXT`; `request_id TEXT`; `created_by INTEGER`; `created_at TEXT` |
| `finance_transfers` | 0 | `id INTEGER PK`; `request_id TEXT`; `source_account_id INTEGER`; `target_account_id INTEGER`; `amount_cents INTEGER`; `date TEXT`; `note TEXT`; `created_by INTEGER`; `created_at TEXT`; `source_entry_id INTEGER`; `target_entry_id INTEGER` |
| `login_attempts` | 2 | `bucket TEXT PK`; `failures INTEGER`; `until INTEGER` |
| `order_cancellations` | 0 | `order_id INTEGER PK`; `user_id INTEGER`; `reason TEXT`; `cancelled_at TEXT` |
| `order_due_events` | 0 | `order_id INTEGER PK`; `version INTEGER PK`; `previous_date TEXT`; `new_date TEXT`; `user_id INTEGER`; `changed_at TEXT` |
| `order_items` | 0 | `id INTEGER PK`; `order_id INTEGER`; `product_id INTEGER`; `name TEXT`; `sku TEXT`; `quantity INTEGER`; `price_cents INTEGER` |
| `order_status_events` | 4 | `id INTEGER PK`; `order_id INTEGER`; `user_id INTEGER`; `request_id TEXT`; `from_status TEXT`; `to_status TEXT`; `changed_at TEXT` |
| `orders` | 4 | `id INTEGER PK`; `customer_id INTEGER`; `amount_cents INTEGER`; `status TEXT`; `date TEXT`; `request_id TEXT`; `created_by INTEGER`; `due_date TEXT`; `due_version INTEGER` |
| `products` | 5 | `id INTEGER PK`; `name TEXT`; `sku TEXT`; `category TEXT`; `price_cents INTEGER`; `stock INTEGER`; `min_stock INTEGER`; `version INTEGER`; `return_stock INTEGER` |
| `purchase_cancellations` | 0 | `purchase_id INTEGER PK`; `reason TEXT`; `user_id INTEGER`; `cancelled_at TEXT` |
| `purchase_items` | 1 | `purchase_id INTEGER PK`; `product_id INTEGER PK`; `name TEXT`; `sku TEXT`; `quantity INTEGER`; `unit_cost_cents INTEGER` |
| `purchases` | 1 | `id INTEGER PK`; `supplier_id INTEGER`; `date TEXT`; `due_date TEXT`; `amount_cents INTEGER`; `note TEXT`; `request_id TEXT`; `payload TEXT`; `created_by INTEGER`; `created_at TEXT` |
| `route_order_positions` | 0 | `scope_id INTEGER PK`; `customer_id INTEGER PK`; `position INTEGER` |
| `route_order_versions` | 0 | `scope_id INTEGER PK`; `version INTEGER`; `updated_by INTEGER`; `updated_at TEXT` |
| `sale_cost_snapshots` | 0 | `order_item_id INTEGER PK`; `unit_cost_cents INTEGER`; `purchase_id INTEGER` |
| `seed_version` | 1 | `version INTEGER PK` |
| `sessions` | 2 | `token_hash TEXT PK`; `user_id INTEGER`; `csrf TEXT`; `expires INTEGER` |
| `stock_movements` | 3 | `id INTEGER PK`; `product_id INTEGER`; `name TEXT`; `sku TEXT`; `kind TEXT`; `quantity INTEGER`; `before_stock INTEGER`; `after_stock INTEGER`; `user_id INTEGER`; `order_id INTEGER`; `request_id TEXT`; `note TEXT`; `created_at TEXT`; `warehouse TEXT`; `action_id TEXT` |
| `stock_tracking` | 5 | `product_id INTEGER PK`; `opening_stock INTEGER`; `tracked_since TEXT` |
| `supplier_payments` | 0 | `id INTEGER PK`; `supplier_id INTEGER`; `date TEXT`; `amount_cents INTEGER`; `note TEXT`; `request_id TEXT`; `created_by INTEGER`; `finance_entry_id INTEGER` |
| `suppliers` | 1 | `id INTEGER PK`; `name TEXT`; `contact TEXT`; `phone TEXT`; `note TEXT`; `version INTEGER`; `request_id TEXT`; `updated_by INTEGER`; `updated_at TEXT` |
| `users` | 1 | `id INTEGER PK`; `username TEXT`; `password_hash TEXT`; `role TEXT`; `active INTEGER` |
| `warehouse_actions` | 1 | `request_id TEXT PK`; `kind TEXT`; `product_id INTEGER`; `quantity INTEGER`; `source TEXT`; `target TEXT`; `note TEXT`; `user_id INTEGER`; `created_at TEXT` |

## Sonuç

Kaynak katalog 124 gerçek üründür; mevcut V2’nin 5 örnek ürünü ayrı tutulmalıdır. Kopyada prova, alan bazında mutabakat, tekrar çalıştırma ve geri dönüş testleri için [aktarımı planı](SFA_AKTARIM_PLANI.md) hazırlanmıştır. Bu belgenin hazırlanması aktarım onayı değildir.
