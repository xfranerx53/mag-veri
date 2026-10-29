# mag-veri — Pazar Analiz programının kendi veri servisi

Geoapify benzeri, **tamamen ücretsiz ve anahtarsız** işletme verisi.
GitHub her pazartesi OpenStreetMap verisini (Geofabrik) indirir, işletmeleri ve yer adlarını ayıklar,
~11 km'lik karelere bölüp **https://xfranerx53.github.io/mag-veri/** adresinde yayınlar.
Pazar Analiz programı tarama yaparken sadece çevredeki kareleri indirir ve arar.

Veri: © OpenStreetMap katkıda bulunanlar, ODbL lisansı (programda bu not gösterilir).

## Dosyalar
| Dosya | Görevi |
|---|---|
| `ulkeler.json` | Hangi ülkelerin derleneceği. **Yeni ülke = yeni satır.** |
| `sektorler.json` | 49 sektörün OpenStreetMap etiket kuralları (programdaki listeyle aynı). |
| `build.py` | Veriyi indirir, ayıklar, karelere böler, `site/` klasörüne yazar. |
| `.github/workflows/veri.yml` | Haftalık otomatik görev + GitHub Pages yayını. |

## Çıktı (yayınlanan dosyalar)
- `data/ulkeler.json` — ülke listesi (ad, sınır kutusu, işletme sayısı, veri tarihi)
- `data/<ülke>/meta.json` — kare boyutu ve hangi karede kaç işletme olduğu
- `data/<ülke>/t/<enlem>_<boylam>.json` — o karedeki işletmeler: `[ad, sektör, enlem, boylam, telefon, web, adres, ilçe/il, osm_id]`
- `data/<ülke>/yerler.json` — il, ilçe, mahalle, köy adları (adres / semt arama için)

## Kurulum (bir kez)
1. GitHub'da yeni **public** depo: `mag-veri`.
2. `build.py`, `ulkeler.json`, `sektorler.json`, `README.md` dosyalarını yükle.
3. **Add file → Create new file** → dosya adı: `.github/workflows/veri.yml` → içeriği yapıştır → Commit.
4. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
5. **Actions** sekmesi → "Veri guncelle" → **Run workflow**. İlk çalıştırma ~15-40 dk.
6. Yeşil tik çıkınca https://xfranerx53.github.io/mag-veri/ açılır ve ülke tablosu görünür.

## Yeni ülke eklemek
`ulkeler.json`'a satır ekle (indirme adresleri: https://download.geofabrik.de):
```json
[
 {"cc": "tr", "ad": "Türkiye", "url": "https://download.geofabrik.de/europe/turkey-latest.osm.pbf"},
 {"cc": "az", "ad": "Azerbaycan", "url": "https://download.geofabrik.de/asia/azerbaijan-latest.osm.pbf"}
]
```
Kaydedince görev kendiliğinden çalışır; program yeni ülkeyi otomatik tanır.

## Ücretsiz sınırlar (sıfır maliyet kuralı)
- GitHub Actions: public depolarda ücretsiz; tek çalıştırma en fazla 6 saat.
- GitHub Pages: site başına **1 GB**, ayda ~100 GB trafik. Görev her çalıştığında toplam boyutu kayıtlara yazar.
- 1 GB'a yaklaşınca: ikinci bir depo (`mag-veri-2`) açılır, bazı ülkeler oraya taşınır; programda Ayarlar → "Veri adresi" ile bağlanır.
- Almanya, Fransa gibi çok büyük ülkeler Geofabrik'te eyalet/bölge parçaları olarak eklenmeli (tek dosya çok büyük).

## Elle güncelleme
Actions → "Veri guncelle" → Run workflow.
