# PiyasaRadar

Borsa Istanbul (`.IS`) ve NYSE/NASDAQ sembollerini Yahoo Finance verisiyle izleyen PyQt5 masaustu uygulamasi.

## Ozellikler

- Birden fazla hisseyi izleme listesine ekleme, satira tiklayarak secilen hissenin grafigini ve gunluk degisimini goruntuleme
- Gercek Yahoo Finance verilerinden hesaplanan 1 aylik senaryo siralamasi ve tahmini getiri gostergesi
- Borsa Istanbul ve ABD hisselerini ayri panellerde izleme
- Yahoo Finance tarayicisindan Borsa Istanbul ve ABD borsalarinin dinamik hisse evrenini listeleme
- Secilen hissenin bulundugu piyasadaki diger hisselerle fiyat, gunluk degisim ve hacim karsilastirmasi
- Secilen hisse icin butce, 1/3/6 aylik vade ve son 12 aydaki gercek temettu odemelerine dayali Test Alisi hesaplamasi
- Canli fiyat, degisim yuzdesi ve 60 saniyelik otomatik yenileme
- Hareketli ortalamalar, RSI(14), MACD ve fiyat grafigi
- 1, 3 ve 6 aylik, gecmis getirilerden uretilen aciklanabilir istatistiksel tahmin
- ABD sembolleri icin son yaklasik 12 ayda her ay temettu odemesi gorulenleri listeleme
- Yahoo Finance RSS haber akisi
- Gelir tablosu, bilanco ve nakit akisinin tablo gorunumu
- Ag hatalarinda QMessageBox ile kullaniciya bildirim

## Kurulum

Python 3.10 veya daha yeni bir surum onerilir.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

Linux/macOS icin sanal ortam etkinlestirme komutu `.venv/bin/activate` olur.

## Sembol kullanimi

- ABD: `AAPL`, `MSFT`, `O`, `MAIN`
- Borsa Istanbul: `THYAO.IS`, `ASELS.IS`, `BIMAS.IS`

Genel Bakis sekmesinde BIST ve ABD hisse evrenleri Yahoo Finance tarayicisindan otomatik yuklenir. Liste icindeki arama alanina sembol veya sirket adi yazarak filtreleyebilirsiniz. Bir satira tikladiginizda secilen hissenin grafigi, gunluk yukselis/dusus orani, teknik gostergeleri, tahmin tablosu ve sag tarafta ayni piyasadaki hisselerle karsilastirmasi gosterilir. Bu veriler ve tahminler kesin kazanc veya yatirim tavsiyesi degildir.

## Veri ve tahmin notu

Veri kaynagi Yahoo Finance'in yfinance arayuzudur; gecikme, kota, sembol kapsamasi ve servis kesintileri olabilir. Tahmin modulu yatirim tavsiyesi degildir. Tahmin; son 60 gunun ortalama getirisi, volatilitesi, MACD yonu ve RSI degerini kullanan basit bir istatistiksel senaryodur, garanti edilen fiyat hedefi degildir.

Aylik temettu filtresi `monthly_dividend_payers` icinde son 370 gun icindeki farkli takvim aylarini sayar. Bir sembolun en az 12 ayda odeme kaydi varsa listelenir; veri kaynaginin temettu tarihleri bu sonucu etkileyebilir.
