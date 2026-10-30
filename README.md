# mag-veri — Pazar Analiz programının kendi veri servisi (DÜNYA)

Geoapify benzeri, **tamamen ücretsiz ve anahtarsız** işletme verisi — **bütün dünya**.
GitHub ayda iki kez (1'inde ve 15'inde) OpenStreetMap verisini (Geofabrik) kıta kıta indirir, işletmeleri ve
yer adlarını ayıklar, karelere bölüp **https://xfranerx53.github.io/mag-veri/** adresinde yayınlar.
Pazar Analiz programı tarama yaparken sadece çevredeki kareleri indirir.

Veri: © OpenStreetMap katkıda bulunanlar, ODbL lisansı (programda bu not gösterilir).

## Dosyalar
| Dosya | Görevi |
|---|---|
| `bolgeler.json` | Hangi bölgelerin (kıtaların) derleneceği. 8 bölge = bütün dünya. |
| `sektorler.json` | 49 sektörün (+ adı olan sanayi/depo binaları, sanayi alanları, adında "ambalaj/poşet" geçenler) OpenStreetMap etiket kuralları (programdaki listeyle aynı). |
| `build.py` | `bolge <kod>`: bir kıtayı indirir/ayıklar. `birlestir`: hepsini birleştirip `site/` üretir. |
| `.github/workflows/veri.yml` | Otomatik görev: 8 kıta aynı anda ayrı makinelerde, sonra birleştirme + yayın. |

## Nasıl çalışır
1. **liste** işi `bolgeler.json`'u okur.
2. **bolge** işleri: her kıta ayrı bir GitHub makinesinde aynı anda işlenir (Avrupa en uzunu, ~1-2 saat).
3. **yayinla** işi: parçaları birleştirir, kıta sınırında iki kez gelen işletmeleri siler, siteyi yayınlar.
   Bir kıta hata verirse diğerleri yine yayınlanır; sayfada "derlenemeyen bölge" yazar. Hiçbiri olmazsa eski veri kalır.

## Çıktı (yayınlanan dosyalar, `data/`)
- `dunya.json` — özet: toplam işletme, tarih, bölgeler
- `w/i/<blok>.json` — 4,8°'lik blok dizini: hangi karede kaç işletme var
- `w/t/<boy>/<kare>.json.gz` — işletmeler `[ad, sektör, enlem, boylam, telefon, web, adres, ilçe/il, osm_id, e-posta]`.
  Boş yerlerde büyük kare (1,6°), şehirlerde küçük kare (en küçük 0,1°) — bir karede en çok ~2000 işletme.
- `w/y/<kare>.json.gz` — 0,8°'lik karelerde il/ilçe/mahalle/köy adları (konumdan yer adı bulma)
- `w/s/<harf>.json.gz` — yer adı arama dizini (Türkçe/İngilizce/yerel adlarla: "Moskova", "Moscow", "Москва")
- Dosyalar sıkıştırılmıştır (.gz); program tarayıcıda açar. Böylece bütün dünya 1 GB sınırına sığar.

## Kurulum / güncelleme
1. Bu dosyaları depoya yükle (`build.py`, `bolgeler.json`, `sektorler.json`, `README.md`).
2. `.github/workflows/veri.yml` dosyasının içeriğini yenisiyle değiştir (kalem ✏️ → hepsini sil → yapıştır → Commit).
3. Eski `ulkeler.json` artık kullanılmıyor, silinebilir.
4. Actions → "Veri guncelle" → **Run workflow**. İlk dünya derlemesi ~2-3 saat.
5. Yeşil tik çıkınca https://xfranerx53.github.io/mag-veri/ sayfasında bölge tablosu görünür.

## Ücretsiz sınırlar (sıfır maliyet kuralı)
- GitHub Actions: public depolarda ücretsiz; tek iş en fazla 6 saat, aynı anda 20 iş.
- GitHub Pages: site başına **1 GB**, ayda ~100 GB trafik. `yayinla` işi kayıtlara toplam boyutu yazar.
- Geofabrik'e saygı: bütün dünya ~80 GB indirme olduğu için ayda 2 kez çalışır (haftalık değil).
- Avrupa bölgesi tek dosyada ~31 GB; makinenin diski yetmezse `bolgeler.json`'da Avrupa'yı parçalara ayır
  (örn. `europe/turkey`, `europe/germany`… adresleri download.geofabrik.de'de).

## Elle güncelleme
Actions → "Veri guncelle" → Run workflow.
