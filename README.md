# PiyasaRadar

Borsa Istanbul (`.IS`) ve NYSE/NASDAQ sembollerini Yahoo Finance verisiyle izleyen PyQt5 masaustu uygulamasi.

## Ozellikler

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

## Veri ve tahmin notu

Veri kaynagi Yahoo Finance'in yfinance arayuzudur; gecikme, kota, sembol kapsamasi ve servis kesintileri olabilir. Tahmin modulu yatirim tavsiyesi degildir. Tahmin; son 60 gunun ortalama getirisi, volatilitesi, MACD yonu ve RSI degerini kullanan basit bir istatistiksel senaryodur, garanti edilen fiyat hedefi degildir.

Aylik temettu filtresi `monthly_dividend_payers` icinde son 370 gun icindeki farkli takvim aylarini sayar. Bir sembolun en az 12 ayda odeme kaydi varsa listelenir; veri kaynaginin temettu tarihleri bu sonucu etkileyebilir.
