from datetime import datetime
import webbrowser

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QTabWidget, QTextBrowser, QTableWidgetItem, QVBoxLayout, QWidget,
)

from analysis.technical import forecast, indicators
from config import BIST_EXAMPLES, DEFAULT_SYMBOL, NEWS_LIMIT, REFRESH_SECONDS, US_SYMBOLS
from services.market_data import MarketDataService
from services.news import NewsService
from ui.widgets import ChartCanvas, ResultTable, Worker


THEME = """
QMainWindow, QWidget { background: #0f141b; color: #e9eef5; font-family: 'Segoe UI'; }
QLineEdit, QComboBox { background: #18212c; border: 1px solid #2b3645; border-radius: 6px; padding: 8px; color: #e9eef5; }
QPushButton { background: #2878d0; border: 0; border-radius: 6px; padding: 9px 15px; color: white; font-weight: 600; }
QPushButton:hover { background: #3d91ed; }
QTabWidget::pane, QGroupBox { border: 1px solid #2b3645; border-radius: 8px; margin-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #8fb9e6; }
QTableWidget { background: #141a22; alternate-background-color: #18212c; gridline-color: #2b3645; border: 0; }
QHeaderView::section { background: #1e2b3b; color: #b8c7d9; padding: 7px; border: 0; }
QTextBrowser { background: #141a22; border: 0; padding: 8px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.market = MarketDataService()
        self.news = NewsService()
        self.workers = []
        self.current_symbol = DEFAULT_SYMBOL
        self.setWindowTitle("PiyasaRadar | BIST & NYSE/NASDAQ")
        self.resize(1380, 860)
        self.setStyleSheet(THEME)
        self._build_ui()
        self._load_symbol(DEFAULT_SYMBOL)
        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self._load_symbol(self.symbol_input.text()))
        self.timer.start(REFRESH_SECONDS * 1000)

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        header = QHBoxLayout()
        title = QLabel("PiyasaRadar")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #58d68d;")
        header.addWidget(title)
        header.addSpacing(20)
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("Sembol: AAPL veya THYAO.IS")
        self.symbol_input.setText(DEFAULT_SYMBOL)
        self.symbol_input.returnPressed.connect(lambda: self._load_symbol(self.symbol_input.text()))
        header.addWidget(self.symbol_input, 1)
        refresh = QPushButton("Yenile")
        refresh.clicked.connect(lambda: self._load_symbol(self.symbol_input.text()))
        header.addWidget(refresh)
        self.status = QLabel("Hazır")
        self.status.setStyleSheet("color: #9aa7b8;")
        header.addWidget(self.status)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.dashboard_tab = self._build_dashboard()
        self.tabs.addTab(self.dashboard_tab, "Genel Bakış")
        self.tabs.addTab(self._build_dividend_tab(), "ABD Aylık Temettü")
        self.tabs.addTab(self._build_financial_tab(), "Finansallar")
        self.tabs.addTab(self._build_news_tab(), "Haber Akışı")
        layout.addWidget(self.tabs)
        self.setCentralWidget(root)

    def _build_dashboard(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.quote_label = QLabel("Veri yükleniyor...")
        self.quote_label.setStyleSheet("font-size: 22px; font-weight: 600; padding: 10px;")
        layout.addWidget(self.quote_label)
        splitter = QSplitter(Qt.Vertical)
        chart_group = QGroupBox("Fiyat ve Hareketli Ortalamalar")
        chart_layout = QVBoxLayout(chart_group)
        self.chart = ChartCanvas()
        chart_layout.addWidget(self.chart)
        splitter.addWidget(chart_group)
        lower = QSplitter(Qt.Horizontal)
        forecast_group = QGroupBox("İstatistiksel Öngörü (yatırım tavsiyesi değildir)")
        forecast_layout = QVBoxLayout(forecast_group)
        self.forecast_table = ResultTable()
        forecast_layout.addWidget(self.forecast_table)
        lower.addWidget(forecast_group)
        indicator_group = QGroupBox("Teknik Göstergeler")
        indicator_layout = QFormLayout(indicator_group)
        self.rsi_label = QLabel("-")
        self.macd_label = QLabel("-")
        self.sma_label = QLabel("-")
        indicator_layout.addRow("RSI(14)", self.rsi_label)
        indicator_layout.addRow("MACD", self.macd_label)
        indicator_layout.addRow("SMA20 / SMA50", self.sma_label)
        lower.addWidget(indicator_group)
        splitter.addWidget(lower)
        layout.addWidget(splitter, 1)
        return page

    def _build_dividend_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel("Son yaklaşık 12 ayda her ay temettü ödemesi görülen ABD sembolleri")
        layout.addWidget(intro)
        controls = QHBoxLayout()
        self.us_symbols = QLineEdit(", ".join(US_SYMBOLS))
        controls.addWidget(self.us_symbols, 1)
        button = QPushButton("Filtrele")
        button.clicked.connect(self._load_dividends)
        controls.addWidget(button)
        layout.addLayout(controls)
        self.dividend_table = ResultTable()
        layout.addWidget(self.dividend_table)
        return page

    def _build_financial_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.financial_tables = QTabWidget()
        layout.addWidget(self.financial_tables)
        return page

    def _build_news_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.news_browser = QTextBrowser()
        self.news_browser.setOpenExternalLinks(False)
        self.news_browser.anchorClicked.connect(lambda url: webbrowser.open(url.toString()))
        layout.addWidget(self.news_browser)
        return page

    def _run(self, function, success, *args):
        self.status.setText("Veri alınıyor...")
        worker = Worker(function, *args)
        self.workers.append(worker)
        worker.succeeded.connect(success)
        worker.failed.connect(self._show_error)
        worker.finished.connect(lambda: self.status.setText(f"Son güncelleme: {datetime.now():%H:%M:%S}"))
        worker.finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        worker.start()

    def _load_symbol(self, symbol):
        symbol = symbol.strip().upper()
        if not symbol:
            return
        self.current_symbol = symbol
        self._run(self._fetch_dashboard, self._present_dashboard, symbol)
        self._run(self.news.fetch, self._present_news, symbol, NEWS_LIMIT)
        self._run(self.market.financial_tables, self._present_financials, symbol)

    def _fetch_dashboard(self, symbol):
        history = self.market.history(symbol)
        return self.market.quote(symbol), indicators(history), forecast(history)

    def _present_dashboard(self, payload):
        quote, frame, predictions = payload
        color = "#58d68d" if quote["change"] >= 0 else "#ed6a5a"
        self.quote_label.setText(f"{quote['symbol']}   {quote['price']:.2f} {quote['currency']}   <span style='color:{color}'>{quote['change']:+.2f} ({quote['change_pct']:+.2f}%)</span>")
        self.chart.plot(frame)
        latest = frame.iloc[-1]
        self.rsi_label.setText(f"{latest['RSI']:.1f}")
        self.macd_label.setText(f"{latest['MACD']:.3f} / sinyal {latest['MACD_Signal']:.3f}")
        self.sma_label.setText(f"{latest['SMA20']:.2f} / {latest['SMA50']:.2f}")
        rows = [[item.horizon, f"{item.target_price:.2f}", f"{item.change_pct:+.2f}%", item.signal, item.confidence] for item in predictions]
        self.forecast_table.load_rows(rows, ["Vade", "Tahmini Fiyat", "Potansiyel", "Sinyal", "Güven"])

    def _present_news(self, articles):
        if not articles:
            self.news_browser.setText("Bu sembol için haber bulunamadı.")
            return
        html = "".join(f"<p><a href='{item['link']}'>{item['title']}</a><br><small>{item['published']}</small></p>" for item in articles)
        self.news_browser.setHtml(html)

    def _present_financials(self, tables):
        self.financial_tables.clear()
        for name, frame in tables.items():
            table = ResultTable()
            if frame.empty:
                table.setRowCount(1)
                table.setColumnCount(1)
                table.setItem(0, 0, QTableWidgetItem("Veri bulunamadı"))
            else:
                rows = [[index] + [value if value == value else "-" for value in row] for index, row in frame.head(30).iterrows()]
                table.load_rows(rows, ["Kalem"] + [str(column)[:10] for column in frame.columns])
            self.financial_tables.addTab(table, name)

    def _load_dividends(self):
        symbols = [item.strip().upper() for item in self.us_symbols.text().replace(";", ",").split(",") if item.strip()]
        self._run(self.market.monthly_dividend_payers, self._present_dividends, symbols)

    def _present_dividends(self, frame):
        rows = [[row["Sembol"], row["Şirket"], f"{float(row['Temettü Verimi']) * 100:.2f}%", row["Ödeme Sayısı"]] for _, row in frame.iterrows()]
        self.dividend_table.load_rows(rows, ["Sembol", "Şirket", "Temettü Verimi", "Ödeme Sayısı"])

    def _show_error(self, message):
        self.status.setText("Veri alınamadı")
        QMessageBox.warning(self, "Veri hatası", message)
