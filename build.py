#!/usr/bin/env python3
"""MAG veri derleyici.

ulkeler.json'daki her ülke için OpenStreetMap verisini (Geofabrik) indirir,
işletmeleri ve yer adlarını ayıklar, ~11 km'lik karelere bölüp site/data/
altına küçük JSON dosyaları olarak yazar. GitHub Actions haftada bir çalıştırır.

Veri: © OpenStreetMap katkıda bulunanlar, ODbL lisansı.
"""
import json, math, os, re, shutil, subprocess, sys, time, urllib.request, datetime

KOK = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(KOK, "site")
DATA = os.path.join(SITE, "data")
TMP = os.environ.get("TMPDIR_VERI", "/tmp/veri")
KARE = 0.1  # derece (~11 km); uygulama meta.json'dan okur

# osmium tags-filter ifadeleri: sadece işimize yarayan nesneler
FILTRE = [
    "nwr/shop", "nwr/craft", "nwr/office", "nwr/industrial", "nwr/man_made=works",
    "nwr/amenity=restaurant,fast_food,cafe,bar,pub,pharmacy,marketplace,fuel,ice_cream,"
    "clinic,dentist,hospital,doctors,veterinary,school,college,kindergarten,language_school,driving_school",
    "nwr/tourism=hotel,guest_house,motel,hostel",
    "n/place=city,town,village,suburb,neighbourhood,quarter,hamlet",
]
YER_TURLERI = {"city", "town", "village", "suburb", "neighbourhood", "quarter", "hamlet"}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def kurallar():
    sek = json.load(open(os.path.join(KOK, "sektorler.json"), encoding="utf-8"))
    kur = [(s["k"], [(k, re.compile(r)) for k, r in s["osm"]], any(r == "." for _, r in s["osm"])) for s in sek]
    # "her değer" (.) kuralları en sona: önce özel kurallar (örn. depo) eşleşsin
    return [(k, kos) for k, kos, genel in sorted(kur, key=lambda x: x[2])]


def sinifla(tags, KUR):
    for k, kos in KUR:
        for anahtar, rx in kos:
            v = tags.get(anahtar)
            if v and rx.search(v):
                return k
    return "ozel"  # tanımlı sektöre girmeyen ama işletme olan yer (isimle aranabilir)


def merkez(geom):
    t, c = geom.get("type"), geom.get("coordinates")
    if not c:
        return None
    if t == "Point":
        return c[1], c[0]
    if t == "Polygon":
        ring = c[0]
    elif t == "MultiPolygon":
        ring = c[0][0]
    elif t == "LineString":
        ring = c
    else:
        return None
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    if not pts:
        return None
    return sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts)


def kare(lat, lon):
    return f"{math.floor(lat / KARE)}_{math.floor(lon / KARE)}"


def indir(url, hedef):
    for deneme in range(4):
        try:
            log("indiriliyor:", url)
            req = urllib.request.Request(url, headers={"User-Agent": "mag-veri-derleyici/1.0 (github.com/xfranerx53)"})
            with urllib.request.urlopen(req, timeout=120) as r, open(hedef, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            log("indirildi:", round(os.path.getsize(hedef) / 1e6), "MB")
            return
        except Exception as e:
            log("indirme hatası:", e)
            time.sleep(30 * (deneme + 1))
    raise SystemExit("İndirilemedi: " + url)


def calistir(*arg):
    log("$", " ".join(arg))
    subprocess.run(arg, check=True)


def geojsonseq_uret(cc, url):
    """pbf indir -> filtrele -> GeoJSON satırları. Test için TEST_GEOJSONSEQ ortam değişkeni verilebilir."""
    test = os.environ.get("TEST_GEOJSONSEQ")
    if test:
        return test
    os.makedirs(TMP, exist_ok=True)
    pbf, poi, gj = (os.path.join(TMP, f"{cc}{s}") for s in (".osm.pbf", "-poi.osm.pbf", ".geojsonseq"))
    indir(url, pbf)
    calistir("osmium", "tags-filter", pbf, *FILTRE, "-o", poi, "--overwrite")
    os.remove(pbf)
    calistir("osmium", "export", poi, "-f", "geojsonseq", "-a", "type,id",
             "--geometry-types=point,polygon", "-x", "print_record_separator=false",
             "-o", gj, "--overwrite")
    os.remove(poi)
    return gj


def en_yakin(izgara, lat, lon, cap=1):
    a, b = math.floor(lat / KARE), math.floor(lon / KARE)
    eniyi, ed = None, 1e9
    for i in range(a - cap, a + cap + 1):
        for j in range(b - cap, b + cap + 1):
            for y in izgara.get((i, j), ()):
                d = (y[2] - lat) ** 2 + ((y[3] - lon) * math.cos(math.radians(lat))) ** 2
                if d < ed:
                    eniyi, ed = y, d
    return eniyi


def ulke_isle(u, KUR):
    cc, ad = u["cc"], u["ad"]
    log("==", ad, "==")
    gj = geojsonseq_uret(cc, u["url"])
    isletme, yerler = [], []
    with open(gj, encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip().lstrip("\x1e")
            if not satir:
                continue
            try:
                ft = json.loads(satir)
            except ValueError:
                continue
            p = ft.get("properties") or {}
            m = merkez(ft.get("geometry") or {})
            ad_ = (p.get("name") or "").strip()
            if not m or not ad_:
                continue
            lat, lon = round(m[0], 5), round(m[1], 5)
            yer = p.get("place")
            if yer in YER_TURLERI and p.get("@type", "node") == "node":
                yerler.append([ad_, yer, lat, lon, ""])
                continue
            if not any(k in p for k in ("shop", "amenity", "craft", "office", "industrial", "man_made", "tourism")):
                continue
            sokak = " No:".join(x for x in (p.get("addr:street"), p.get("addr:housenumber")) if x)
            adres = ", ".join(x for x in (p.get("addr:neighbourhood") or p.get("addr:quarter") or p.get("addr:suburb"), sokak) if x)
            il = " / ".join(x for x in (p.get("addr:district"), p.get("addr:city") or p.get("addr:province")) if x)
            tel = p.get("phone") or p.get("contact:phone") or p.get("contact:mobile") or p.get("mobile") or ""
            web = p.get("website") or p.get("contact:website") or ""
            oid = (p.get("@type", "n")[:1]) + str(p.get("@id", ""))
            isletme.append([ad_, sinifla(p, KUR), lat, lon, tel.split(";")[0].strip(), web.split(";")[0].strip(), adres, il, oid])
    log("işletme:", len(isletme), "yer adı:", len(yerler))

    # yer adlarına bağlı olduğu şehri/ilçeyi ekle, adres eksik işletmelere en yakın ilçe/şehir adını yaz
    sehir_iz, ilce_iz = {}, {}
    for y in yerler:
        key = (math.floor(y[2] / KARE), math.floor(y[3] / KARE))
        if y[1] == "city":
            sehir_iz.setdefault(key, []).append(y)
        if y[1] == "town":
            ilce_iz.setdefault(key, []).append(y)

    def bolge(lat, lon, haric=""):
        ilce = en_yakin(ilce_iz, lat, lon, 2)
        sehir = en_yakin(sehir_iz, lat, lon, 5)
        return " / ".join(dict.fromkeys(x for x in ((ilce or [""])[0], (sehir or [""])[0]) if x and x != haric))

    for y in yerler:
        if y[1] == "town":
            s = en_yakin(sehir_iz, y[2], y[3], 5)
            y[4] = s[0] if s and s[0] != y[0] else ""
        elif y[1] != "city":
            y[4] = bolge(y[2], y[3], y[0])
    for r in isletme:
        if not r[7]:
            r[7] = bolge(r[2], r[3])

    # karelere böl ve yaz
    hedef = os.path.join(DATA, cc)
    shutil.rmtree(hedef, ignore_errors=True)
    os.makedirs(os.path.join(hedef, "t"))
    kareler = {}
    for r in isletme:
        kareler.setdefault(kare(r[2], r[3]), []).append(r)
    for k, lst in kareler.items():
        with open(os.path.join(hedef, "t", k + ".json"), "w", encoding="utf-8") as f:
            json.dump(lst, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(hedef, "yerler.json"), "w", encoding="utf-8") as f:
        json.dump(yerler, f, ensure_ascii=False, separators=(",", ":"))
    tum = [(r[2], r[3]) for r in isletme] + [(y[2], y[3]) for y in yerler]
    bbox = [min(a for a, _ in tum), min(b for _, b in tum), max(a for a, _ in tum), max(b for _, b in tum)] if tum else [0, 0, 0, 0]
    tarih = datetime.date.today().isoformat()
    meta = {"cc": cc, "ad": ad, "tarih": tarih, "adet": len(isletme), "yer": len(yerler), "kare": KARE,
            "bbox": [round(x, 4) for x in bbox], "tiles": {k: len(v) for k, v in kareler.items()}}
    with open(os.path.join(hedef, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, separators=(",", ":"))
    if not os.environ.get("TEST_GEOJSONSEQ"):
        try:
            os.remove(gj)
        except OSError:
            pass
    boyut = sum(os.path.getsize(os.path.join(d, x)) for d, _, fs in os.walk(hedef) for x in fs)
    log(ad, "bitti:", len(kareler), "kare,", round(boyut / 1e6, 1), "MB")
    return {"cc": cc, "ad": ad, "tarih": tarih, "adet": len(isletme), "bbox": meta["bbox"]}


def main():
    KUR = kurallar()
    os.makedirs(DATA, exist_ok=True)
    ulkeler = json.load(open(os.path.join(KOK, "ulkeler.json"), encoding="utf-8"))
    sadece = os.environ.get("SADECE")  # örn. SADECE=tr
    ozet = []
    for u in ulkeler:
        if sadece and u["cc"] not in sadece.split(","):
            continue
        ozet.append(ulke_isle(u, KUR))
    with open(os.path.join(DATA, "ulkeler.json"), "w", encoding="utf-8") as f:
        json.dump(ozet, f, ensure_ascii=False, indent=1)
    satirlar = "".join(f"<tr><td>{o['ad']}</td><td>{o['adet']:,}</td><td>{o['tarih']}</td></tr>" for o in ozet)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MAG veri</title><style>body{{font:15px system-ui;margin:24px;max-width:700px}}td,th{{padding:4px 10px;border-bottom:1px solid #ddd;text-align:left}}</style>
<h2>MAG Pazar Analiz — veri deposu</h2><p>Bu adres Pazar Analiz programının kullandığı işletme verisini barındırır.</p>
<table><tr><th>Ülke</th><th>İşletme</th><th>Veri tarihi</th></tr>{satirlar}</table>
<p style="color:#666">Veri: © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap katkıda bulunanlar</a>, ODbL lisansı.</p>""")
    boyut = sum(os.path.getsize(os.path.join(d, x)) for d, _, fs in os.walk(SITE) for x in fs)
    log("TOPLAM site boyutu:", round(boyut / 1e6, 1), "MB (GitHub Pages sınırı 1000 MB)")
    if boyut > 950e6:
        log("UYARI: 1 GB sınırına yaklaşıldı. Ülkeleri ikinci bir veri deposuna bölmek gerekiyor.")


if __name__ == "__main__":
    main()
