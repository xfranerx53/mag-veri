#!/usr/bin/env python3
"""MAG veri derleyici — DÜNYA sürümü (surum 2).

İki aşamada çalışır (GitHub Actions ikisini sırayla yapar):

  python3 build.py bolge <kod>   -> bolgeler.json'daki bir bölgeyi (kıta) Geofabrik'ten indirir,
                                     işletmeleri ve yer adlarını ayıklar, parca/<kod>/ altına
                                     4,8 derecelik bloklar halinde yazar. (Her bölge ayrı makinede, aynı anda.)
  python3 build.py birlestir     -> tüm bölge parçalarını birleştirir, kenarlardaki tekrarları siler,
                                     yayınlanacak site/ klasörünü üretir.

Yayın düzeni (site/data/):
  dunya.json                    özet (tarih, adet, bölgeler)
  w/i/<BI>_<BJ>.json            blok dizini: hangi karede kaç işletme var
  w/t/<s>/<i>_<j>.json.gz       işletmeler [ad, sektör, enlem, boylam, tel, web, adres, ilçe/il, osm_id, e-posta]
                                (kare boyu s x 0,1 derece; yoğun yerlerde küçük, boş yerlerde büyük kare)
  w/y/<i>_<j>.json.gz           0,8 derecelik karelerde yer adları [ad, tür, enlem, boylam, bağlı olduğu yer]
  w/s/<hex>.json.gz             yer adı arama dizini (adın ilk 2 harfine göre)

Veri: © OpenStreetMap katkıda bulunanlar, ODbL lisansı.
"""
import datetime, gzip, json, math, os, re, shutil, subprocess, sys, time, unicodedata, urllib.request

KOK = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(KOK, "site")
DATA = os.path.join(SITE, "data")
PARCA = os.path.join(KOK, "parca")
TMP = os.environ.get("TMPDIR_VERI", "/tmp/veri")

BLOK = 48          # blok = 48 x 0,1 = 4,8 derece
KOK_KARE = 16      # en büyük işletme karesi 1,6 derece
KARE_SINIR = 2000  # bir karede bundan fazla işletme varsa 4'e bölünür (en küçük 0,1 derece)
YER_KARE = 8       # yer adı kareleri 0,8 derece

FILTRE = [
    "nwr/shop", "nwr/craft", "nwr/office", "nwr/industrial", "nwr/man_made=works",
    "nwr/amenity=restaurant,fast_food,cafe,bar,pub,pharmacy,marketplace,fuel,ice_cream,"
    "clinic,dentist,hospital,doctors,veterinary,school,college,kindergarten,language_school,driving_school",
    "nwr/tourism=hotel,guest_house,motel,hostel",
    "nwr/building=industrial,factory,manufacture,warehouse", "wr/landuse=industrial",
    "n/place=city,town,village,suburb,neighbourhood,quarter",
]
YER_TURLERI = {"city", "town", "village", "suburb", "neighbourhood", "quarter"}
ISLETME_ANAHTAR = ("shop", "amenity", "craft", "office", "industrial", "man_made", "tourism", "building", "landuse")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def norm(s):
    """Arama için sadeleştirme. Programdaki normY() ile birebir aynı olmalı."""
    s = (s or "").replace("İ", "i").replace("I", "i").replace("ı", "i").lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c)[0] in "LN")


def onek_dosya(n):
    return "-".join(format(ord(c), "x") for c in n[:2])


def a10(x):
    return math.floor(x * 10)


def kurallar():
    sek = json.load(open(os.path.join(KOK, "sektorler.json"), encoding="utf-8"))
    kur = [(s["k"], [(k, re.compile(r, re.I if k == "name" else 0)) for k, r in s["osm"]], any(r == "." for _, r in s["osm"])) for s in sek]
    return [(k, kos) for k, kos, genel in sorted(kur, key=lambda x: x[2])]


def sinifla(tags, KUR):
    for k, kos in KUR:
        for anahtar, rx in kos:
            v = tags.get(anahtar)
            if v and rx.search(v):
                return k
    return "ozel"


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


def indir(url, hedef):
    for deneme in range(5):
        try:
            log("indiriliyor:", url)
            req = urllib.request.Request(url, headers={"User-Agent": "mag-veri-derleyici/2.0 (github.com/xfranerx53)"})
            with urllib.request.urlopen(req, timeout=300) as r, open(hedef, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 22)
            log("indirildi:", round(os.path.getsize(hedef) / 1e9, 2), "GB")
            return
        except Exception as e:
            log("indirme hatası:", e)
            time.sleep(60 * (deneme + 1))
    raise SystemExit("İndirilemedi: " + url)


def calistir(*arg):
    log("$", " ".join(arg))
    subprocess.run(arg, check=True)


def geojsonseq_uret(kod, url):
    test = os.environ.get("TEST_GEOJSONSEQ")
    if test:
        return test
    os.makedirs(TMP, exist_ok=True)
    pbf, poi, gj = (os.path.join(TMP, f"{kod}{s}") for s in (".osm.pbf", "-poi.osm.pbf", ".geojsonseq"))
    indir(url, pbf)
    calistir("osmium", "tags-filter", pbf, *FILTRE, "-o", poi, "--overwrite")
    os.remove(pbf)
    calistir("osmium", "export", poi, "-f", "geojsonseq", "-a", "type,id",
             "--geometry-types=point,polygon", "-x", "print_record_separator=false",
             "-o", gj, "--overwrite")
    os.remove(poi)
    return gj


def satirlar(gj):
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
            if m and (p.get("name") or "").strip():
                yield p, round(m[0], 5), round(m[1], 5)


# ---------------------------------------------------------------- 1. aşama: bölge
def bolge_isle(kod):
    KUR = kurallar()
    b = next(x for x in json.load(open(os.path.join(KOK, "bolgeler.json"), encoding="utf-8")) if x["kod"] == kod)
    log("==", b["ad"], "==")
    gj = geojsonseq_uret(kod, b["url"])

    # 1. geçiş: yer adları
    yerler = []
    for p, lat, lon in satirlar(gj):
        if p.get("place") in YER_TURLERI and p.get("@type", "node") == "node":
            ad = (p.get("name:tr") or p.get("name")).strip()
            alt = sorted({x.strip() for x in (p.get("name"), p.get("name:en"), p.get("int_name"), p.get("name:tr")) if x and x.strip() and x.strip() != ad})
            yerler.append([ad, p["place"], lat, lon, "", "|".join(alt)])
    log("yer adı:", len(yerler))

    sehir, ilce = {}, {}
    for y in yerler:
        k = (a10(y[2]), a10(y[3]))
        if y[1] == "city":
            sehir.setdefault(k, []).append(y)
        elif y[1] == "town":
            ilce.setdefault(k, []).append(y)

    def en_yakin(iz, lat, lon, cap):
        a, bb = a10(lat), a10(lon)
        eniyi, ed = None, 1e9
        for i in range(a - cap, a + cap + 1):
            for j in range(bb - cap, bb + cap + 1):
                for y in iz.get((i, j), ()):
                    d = (y[2] - lat) ** 2 + ((y[3] - lon) * math.cos(math.radians(lat))) ** 2
                    if d < ed:
                        eniyi, ed = y, d
        return eniyi

    onbellek = {}

    def bolge_adi(lat, lon, haric=""):
        k = (a10(lat), a10(lon))  # 0,1 derecelik karede bir kez hesapla (hız için)
        if k not in onbellek:
            c = (k[0] + .5) / 10, (k[1] + .5) / 10
            i, s = en_yakin(ilce, *c, 2), en_yakin(sehir, *c, 5)
            onbellek[k] = ((i or [""])[0], (s or [""])[0])
        return " / ".join(dict.fromkeys(x for x in onbellek[k] if x and x != haric))

    for y in yerler:
        if y[1] == "town":
            s = en_yakin(sehir, y[2], y[3], 5)
            y[4] = s[0] if s and s[0] != y[0] else ""
        elif y[1] != "city":
            y[4] = bolge_adi(y[2], y[3], y[0])

    hedef = os.path.join(PARCA, kod)
    shutil.rmtree(hedef, ignore_errors=True)
    os.makedirs(hedef)
    tampon, adet = {}, 0

    def yaz(lat, lon, satir, zorla=False):
        if satir is not None:
            k = f"{a10(lat) // BLOK}_{a10(lon) // BLOK}"
            tampon.setdefault(k, []).append(satir)
            if len(tampon[k]) < 5000 and not zorla:
                return
            ks = [k]
        else:
            ks = list(tampon)
        for k in ks:
            with open(os.path.join(hedef, k + ".jsonl"), "a", encoding="utf-8") as f:
                f.write("\n".join(tampon.pop(k)) + "\n")

    for y in yerler:
        yaz(y[2], y[3], json.dumps(y, ensure_ascii=False, separators=(",", ":")))

    # 2. geçiş: işletmeler
    for p, lat, lon in satirlar(gj):
        if p.get("place") or not any(k in p for k in ISLETME_ANAHTAR):
            continue
        sokak = " No:".join(x for x in (p.get("addr:street"), p.get("addr:housenumber")) if x)
        adres = ", ".join(x for x in (p.get("addr:neighbourhood") or p.get("addr:quarter") or p.get("addr:suburb"), sokak) if x)
        il = " / ".join(x for x in (p.get("addr:district"), p.get("addr:city") or p.get("addr:province")) if x) or bolge_adi(lat, lon)
        tel = p.get("phone") or p.get("contact:phone") or p.get("contact:mobile") or p.get("mobile") or ""
        web = p.get("website") or p.get("contact:website") or ""
        oid = (p.get("@type", "n")[:1]) + str(p.get("@id", ""))
        ep = (p.get("email") or p.get("contact:email") or "").split(";")[0].strip()
        r = [p["name"].strip(), sinifla(p, KUR), lat, lon, tel.split(";")[0].strip(), web.split(";")[0].strip(), adres, il, oid, ep]
        yaz(lat, lon, json.dumps(r, ensure_ascii=False, separators=(",", ":")))
        adet += 1
    yaz(0, 0, None)

    # blok dosyalarını sıkıştır (aktarım küçük olsun)
    for ad in os.listdir(hedef):
        yol = os.path.join(hedef, ad)
        with open(yol, "rb") as f, gzip.open(yol + ".gz", "wb", 6) as g:
            shutil.copyfileobj(f, g)
        os.remove(yol)
    with open(os.path.join(hedef, "_ozet.json"), "w", encoding="utf-8") as f:
        json.dump({"kod": kod, "ad": b["ad"], "adet": adet, "yer": len(yerler), "tarih": datetime.date.today().isoformat()}, f, ensure_ascii=False)
    if not os.environ.get("TEST_GEOJSONSEQ"):
        os.remove(gj)
    log(b["ad"], "bitti:", adet, "işletme,", len(yerler), "yer adı")


# ---------------------------------------------------------------- 2. aşama: birleştir
def gz_yaz(yol, veri):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "wb") as f:
        f.write(gzip.compress(json.dumps(veri, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9, mtime=0))


def kare_bol(s, i, j, recs, cikti):
    if s == 1 or len(recs) <= KARE_SINIR:
        cikti.append((s, i, j, recs))
        return
    h = s // 2
    alt = {}
    for r in recs:
        alt.setdefault((a10(r[2]) // h, a10(r[3]) // h), []).append(r)
    for (ii, jj), l in alt.items():
        kare_bol(h, ii, jj, l, cikti)


def birlestir():
    parcalar = sorted(d for d in os.listdir(PARCA) if os.path.isdir(os.path.join(PARCA, d))) if os.path.isdir(PARCA) else []
    ozet = []
    for d in parcalar:
        try:
            ozet.append(json.load(open(os.path.join(PARCA, d, "_ozet.json"), encoding="utf-8")))
        except OSError:
            log("UYARI: yarım kalmış bölge atlandı:", d)
    if not ozet:
        raise SystemExit("Hiç bölge verisi yok, yayın yapılmadı (eski veri yerinde kalır).")
    shutil.rmtree(DATA, ignore_errors=True)
    W = os.path.join(DATA, "w")
    os.makedirs(os.path.join(W, "i"))
    bloklar = sorted({ad[:-9] for o in ozet for ad in os.listdir(os.path.join(PARCA, o["kod"])) if ad.endswith(".jsonl.gz")})
    log("blok sayısı:", len(bloklar))
    arama_tmp = os.path.join(TMP, "arama")
    shutil.rmtree(arama_tmp, ignore_errors=True)
    os.makedirs(arama_tmp)
    arama, toplam, toplam_yer, dosya = {}, 0, 0, 0

    def arama_bosalt(hepsi=False):
        for k in [k for k, v in arama.items() if hepsi or len(v) > 5000]:
            with open(os.path.join(arama_tmp, k), "a", encoding="utf-8") as f:
                f.write("\n".join(arama.pop(k)) + "\n")

    for bk in bloklar:
        isletme, gor, yerler, ygor = [], set(), [], set()
        for o in ozet:
            yol = os.path.join(PARCA, o["kod"], bk + ".jsonl.gz")
            if not os.path.exists(yol):
                continue
            with gzip.open(yol, "rt", encoding="utf-8") as f:
                for satir in f:
                    if not satir.strip():
                        continue
                    r = json.loads(satir)
                    if len(r) >= 9:  # işletme (9-10 alan); yer adı 5-6 alan
                        if r[8] not in gor:  # bölge sınırında iki kez gelen işletme
                            gor.add(r[8])
                            isletme.append(r)
                    else:
                        k = (r[0], r[2], r[3])
                        if k not in ygor:
                            ygor.add(k)
                            yerler.append(r)
        # işletme kareleri (yoğun yerde küçük kare)
        kok = {}
        for r in isletme:
            kok.setdefault((a10(r[2]) // KOK_KARE, a10(r[3]) // KOK_KARE), []).append(r)
        cikti = []
        for (i, j), l in kok.items():
            kare_bol(KOK_KARE, i, j, l, cikti)
        dizin = {}
        for s, i, j, l in cikti:
            gz_yaz(os.path.join(W, "t", str(s), f"{i}_{j}.json.gz"), l)
            dizin[f"{s}/{i}_{j}"] = len(l)
            dosya += 1
        if dizin:
            with open(os.path.join(W, "i", bk + ".json"), "w") as f:
                json.dump({"t": dizin}, f, separators=(",", ":"))
            dosya += 1
        # yer adı kareleri + arama dizini
        yk = {}
        for y in yerler:
            yk.setdefault((a10(y[2]) // YER_KARE, a10(y[3]) // YER_KARE), []).append(y[:5])
            for isim in [y[0]] + [x for x in y[5].split("|") if x]:
                n = norm(isim)
                if len(n) >= 2:
                    arama.setdefault(onek_dosya(n), []).append(json.dumps(y[:5] + ([isim] if isim != y[0] else []), ensure_ascii=False, separators=(",", ":")))
        for (i, j), l in yk.items():
            gz_yaz(os.path.join(W, "y", f"{i}_{j}.json.gz"), l)
            dosya += 1
        arama_bosalt(True)
        toplam += len(isletme)
        toplam_yer += len(yerler)
    arama_bosalt(True)
    for ad in os.listdir(arama_tmp):
        with open(os.path.join(arama_tmp, ad), encoding="utf-8") as f:
            gz_yaz(os.path.join(W, "s", ad + ".json.gz"), [json.loads(x) for x in f if x.strip()])
        dosya += 1
    shutil.rmtree(arama_tmp, ignore_errors=True)

    tarih = min(o["tarih"] for o in ozet)
    dunya = {"surum": 2, "tarih": tarih, "adet": toplam, "yer": toplam_yer, "blok": BLOK, "yerKare": YER_KARE,
             "bolgeler": [{k: o[k] for k in ("kod", "ad", "adet", "tarih")} for o in ozet]}
    with open(os.path.join(DATA, "dunya.json"), "w", encoding="utf-8") as f:
        json.dump(dunya, f, ensure_ascii=False, indent=1)
    shutil.copy(os.path.join(KOK, "sektorler.json"), os.path.join(DATA, "sektorler.json"))  # program sektör kurallarını buradan okur
    eksik = [b["ad"] for b in json.load(open(os.path.join(KOK, "bolgeler.json"), encoding="utf-8")) if b["kod"] not in {o["kod"] for o in ozet}]
    sat = "".join(f"<tr><td>{o['ad']}</td><td>{o['adet']:,}</td><td>{o['tarih']}</td></tr>" for o in ozet)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MAG veri</title><style>body{{font:15px system-ui;margin:24px;max-width:700px}}td,th{{padding:4px 10px;border-bottom:1px solid #ddd;text-align:left}}</style>
<h2>MAG Pazar Analiz — dünya veri deposu</h2><p>Toplam <b>{toplam:,}</b> işletme, {toplam_yer:,} yer adı. Veri tarihi {tarih}.</p>
<table><tr><th>Bölge</th><th>İşletme</th><th>Veri tarihi</th></tr>{sat}</table>
{"<p style='color:#b42318'>Bu çalıştırmada derlenemeyen bölge: " + ", ".join(eksik) + "</p>" if eksik else ""}
<p style="color:#666">Veri: © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap katkıda bulunanlar</a>, ODbL lisansı.</p>""")
    boyut = sum(os.path.getsize(os.path.join(d, x)) for d, _, fs in os.walk(SITE) for x in fs)
    log(f"TOPLAM: {toplam:,} işletme, {toplam_yer:,} yer, {dosya:,} dosya, {round(boyut / 1e6, 1)} MB (GitHub Pages sınırı 1000 MB)")
    if eksik:
        log("UYARI: derlenemeyen bölgeler:", ", ".join(eksik))
    if boyut > 950e6:
        log("UYARI: 1 GB sınırına yaklaşıldı.")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "bolge":
        bolge_isle(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "birlestir":
        birlestir()
    elif len(sys.argv) >= 2 and sys.argv[1] == "liste":
        print(json.dumps([b["kod"] for b in json.load(open(os.path.join(KOK, "bolgeler.json"), encoding="utf-8"))]))
    else:
        print(__doc__)
