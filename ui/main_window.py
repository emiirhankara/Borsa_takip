from datetime import datetime
import webbrowser

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPushButton, QSplitter, QTabWidget, QTextBrowser, QTableWidgetItem, QVBoxLayout, QWidget,
)

from analysis.technical import forecast, indicators
from config import BIST_EXAMPLES, DEFAULT_SYMBOL, DEFAULT_WATCHLIST, NEWS_LIMIT, REFRESH_SECONDS, US_SYMBOLS
from services.market_data import MarketDataService
from services.news import NewsService
from ui.widgets import ChartCanvas, ResultTable, Worker


THEME = """
QMainWindow, QWidget { background: #0b1118; color: #e9eef5; font-family: 'Segoe UI'; }
QLineEdit, QComboBox, QDoubleSpinBox { background: #121b26; border: 1px solid #29384a; border-radius: 4px; padding: 7px; color: #e9eef5; }
QPushButton { background: #2878d0; border: 0; border-radius: 4px; padding: 8px 13px; color: white; font-weight: 600; }
QPushButton:hover { background: #3d91ed; }
QGroupBox { background: #101821; border: 1px solid #29384a; border-radius: 5px; margin-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #b8c7d9; }
QTableWidget { background: #141a22; alternate-background-color: #18212c; gridline-color: #2b3645; border: 0; }
QHeaderView::section { background: #1e2b3b; color: #b8c7d9; padding: 7px; border: 0; }
QTextBrowser { background: #141a22; border: 0; padding: 8px; }
QSplitter::handle { background: #29384a; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.market = MarketDataService()
        self.news = NewsService()
        self.workers = []
        self.current_symbol = DEFAULT_SYMBOL
        self.watchlist = list(DEFAULT_WATCHLIST)
        self.current_quote = None
        self.current_predictions = []
        self.current_dividend = {"annual_per_share": 0.0, "payment_count": 0}
        self.market_rows = {"BIST": [], "US": []}
        self.setWindowTitle("PiyasaRadar | BIST & NYSE/NASDAQ")
        self.resize(1380, 860)
        self.setStyleSheet(THEME)
        self._build_ui()
        QTimer.singleShot(250, self._refresh_watchlist)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_watchlist)
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
        refresh.clicked.connect(self._refresh_watchlist)
        header.addWidget(refresh)
        self.status = QLabel("Hazır")
        self.status.setStyleSheet("color: #9aa7b8;")
        header.addWidget(self.status)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.dashboard_tab = self._build_dashboard()
        self.tabs.addTab(self.dashboard_tab, "Genel Bakış")
        self.tabs.addTab(self._build_financial_tab(), "Finansallar")
        self.tabs.addTab(self._build_news_tab(), "Haber Akışı")
        layout.addWidget(self.tabs)
        self.setCentralWidget(root)

    def _build_dashboard(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 6, 0)
        self.bist_table, bist_panel = self._build_market_panel(
            "Borsa İstanbul", ", ".join(symbol for symbol in self.watchlist if symbol.endswith(".IS")), "THYAO.IS, ASELS.IS, BIMAS.IS"
        )
        self.us_table, us_panel = self._build_market_panel(
            "ABD Borsaları", ", ".join(symbol for symbol in self.watchlist if not symbol.endswith(".IS")), "AAPL, MSFT, JNJ"
        )
        left_layout.addWidget(bist_panel, 1)
        load_lists = QPushButton("Listeleri yükle")
        load_lists.clicked.connect(self._refresh_watchlist)
        left_layout.addWidget(load_lists)
        layout.addWidget(left_panel, 1)

        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 6, 0)
        self.quote_label = QLabel("Veri yükleniyor...")
        self.quote_label.setStyleSheet("font-size: 23px; font-weight: 700; padding: 4px 0;")
        center_layout.addWidget(self.quote_label)
        self.recommendation_label = QLabel("BIST ve ABD piyasalarının tüm listesi yükleniyor...")
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setStyleSheet("color: #f5b041; padding: 3px 0;")
        center_layout.addWidget(self.recommendation_label)
        chart_group = QGroupBox("Fiyat ve Hareketli Ortalamalar")
        chart_layout = QVBoxLayout(chart_group)
        self.chart = ChartCanvas()
        chart_layout.addWidget(self.chart)
        center_layout.addWidget(chart_group, 1)
        lower = QSplitter(Qt.Vertical)
        forecast_group = QGroupBox("İstatistiksel Öngörü (yatırım tavsiyesi değildir)")
        forecast_layout = QVBoxLayout(forecast_group)
        self.forecast_table = ResultTable()
        self.forecast_table.fill_container()
        forecast_layout.addWidget(self.forecast_table)
        lower.addWidget(forecast_group)
        indicator_group = QGroupBox("Teknik Göstergeler")
        indicator_layout = QHBoxLayout(indicator_group)
        self.rsi_label = QLabel("-")
        self.macd_label = QLabel("-")
        self.sma_label = QLabel("-")
        indicator_layout.addWidget(QLabel("RSI(14)"))
        indicator_layout.addWidget(self.rsi_label)
        indicator_layout.addWidget(QLabel("MACD"))
        indicator_layout.addWidget(self.macd_label)
        indicator_layout.addWidget(QLabel("SMA20 / SMA50"))
        indicator_layout.addWidget(self.sma_label)
        lower.addWidget(indicator_group)
        center_layout.addWidget(lower, 1)
        layout.addWidget(center_panel, 3)

        order_panel = QGroupBox("Test Alışı")
        order_layout = QVBoxLayout(order_panel)
        order_layout.addWidget(QLabel("Sanal yatırım tutarı"))
        self.test_budget = QDoubleSpinBox()
        self.test_budget.setRange(1, 1000000000)
        self.test_budget.setValue(10000)
        self.test_budget.setDecimals(2)
        order_layout.addWidget(self.test_budget)
        order_layout.addWidget(QLabel("Elde tutma süresi"))
        self.test_months = QComboBox()
        self.test_months.addItem("1 ay", 1)
        self.test_months.addItem("3 ay", 3)
        self.test_months.addItem("6 ay", 6)
        order_layout.addWidget(self.test_months)
        self.test_buy_button = QPushButton("Hesapla")
        self.test_buy_button.setEnabled(False)
        self.test_buy_button.clicked.connect(self._calculate_test_buy)
        order_layout.addWidget(self.test_buy_button)
        self.test_result = QLabel("Bir hisse seçip tutar ve süre girin.")
        self.test_result.setWordWrap(True)
        self.test_result.setStyleSheet("color: #b8c7d9; padding-top: 8px;")
        order_layout.addWidget(self.test_result)
        order_layout.addStretch()
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(us_panel, 1)
        comparison_panel = QGroupBox("Diğer hisselerle karşılaştırma")
        comparison_layout = QVBoxLayout(comparison_panel)
        self.comparison_table = ResultTable()
        comparison_layout.addWidget(self.comparison_table)
        right_layout.addWidget(comparison_panel, 1)
        right_layout.addWidget(order_panel, 1)
        layout.addWidget(right_panel, 1)
        return page

    def _build_market_panel(self, title, symbols, placeholder):
        panel = QGroupBox(title)
        layout = QVBoxLayout(panel)
        input_field = QLineEdit()
        input_field.setPlaceholderText(f"{placeholder} | tüm liste otomatik gelir")
        input_field.returnPressed.connect(lambda: self._filter_market_table(title, input_field.text()))
        layout.addWidget(input_field)
        table = ResultTable()
        table.setSelectionBehavior(table.SelectRows)
        table.setEditTriggers(table.NoEditTriggers)
        table.cellClicked.connect(self._watchlist_row_clicked)
        layout.addWidget(table)
        if title.startswith("Borsa"):
            self.bist_input = input_field
        else:
            self.us_watchlist_input = input_field
        return table, panel

    def _filter_market_table(self, title, text):
        market = "BIST" if title.startswith("Borsa") else "US"
        needle = text.strip().upper()
        rows = self.market_rows[market]
        if needle:
            rows = [row for row in rows if needle in row["symbol"] or needle in row["name"].upper()]
        self._load_market_table(self.bist_table if market == "BIST" else self.us_table, rows)

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

    def _load_symbol(self, symbol, load_watchlist=True):
        symbol = symbol.strip().upper()
        if not symbol:
            return
        self.current_symbol = symbol
        self._run(self._fetch_dashboard, self._present_dashboard, symbol)
        self._run(self.news.fetch, self._present_news, symbol, NEWS_LIMIT)
        self._run(self.market.financial_tables, self._present_financials, symbol)

    def _refresh_watchlist(self):
        self._run(self._fetch_market_universes, self._present_market_universes)

    def _fetch_market_universes(self):
        return {"BIST": self.market.screener_quotes("BIST"), "US": self.market.screener_quotes("US")}

    def _present_market_universes(self, markets):
        self.market_rows = markets
        bist_rows = markets["BIST"]
        us_rows = markets["US"]
        if not bist_rows and not us_rows:
            self.recommendation_label.setText("Piyasa listesi alınamadı.")
            return
        self._load_market_table(self.bist_table, bist_rows)
        self._load_market_table(self.us_table, us_rows)
        best = max(bist_rows + us_rows, key=lambda row: row["change_pct"])
        self.recommendation_label.setText(
            f"Gerçek zamanlı piyasa taraması: {len(bist_rows)} BIST, {len(us_rows)} ABD hissesi. "
            f"Günün en yüksek hareketi: {best['symbol']} ({best['change_pct']:+.2f}%). "
            "Bir hisse seçerek ayrıntılı grafik ve tahminini açın."
        )
        if bist_rows:
            self._load_symbol(bist_rows[0]["symbol"], load_watchlist=False)

    def _load_market_table(self, table, rows):
        table_rows = [
            [row["symbol"], row["name"][:24], f"{row['price']:.2f} {row['currency']}", f"{row['change_pct']:+.2f}%", f"{row['volume']:,}"]
            for row in rows
        ]
        table.load_rows(table_rows, ["Sembol", "Şirket", "Fiyat", "Günlük", "Hacim"])

    def _watchlist_row_clicked(self, row, _column):
        table = self.sender()
        symbol_item = table.item(row, 0)
        if symbol_item:
            self._load_symbol(symbol_item.text(), load_watchlist=False)

    def _fetch_dashboard(self, symbol):
        history = self.market.history(symbol)
        return self.market.quote(symbol), indicators(history), forecast(history), self.market.dividend_info(symbol)

    def _present_dashboard(self, payload):
        quote, frame, predictions, dividend = payload
        self.current_quote = quote
        self.current_predictions = predictions
        self.current_dividend = dividend
        self.test_buy_button.setEnabled(True)
        self.test_budget.setSuffix(f" {quote['currency']}")
        self.test_result.setText("Tutar ve süreyi seçip Hesapla düğmesine basın.")
        color = "#58d68d" if quote["change"] >= 0 else "#ed6a5a"
        self.quote_label.setText(f"{quote['symbol']}   {quote['price']:.2f} {quote['currency']}   <span style='color:{color}'>{quote['change']:+.2f} ({quote['change_pct']:+.2f}%)</span>")
        self.chart.plot(frame)
        latest = frame.iloc[-1]
        self.rsi_label.setText(f"{latest['RSI']:.1f}")
        self.macd_label.setText(f"{latest['MACD']:.3f} / sinyal {latest['MACD_Signal']:.3f}")
        self.sma_label.setText(f"{latest['SMA20']:.2f} / {latest['SMA50']:.2f}")
        rows = [[item.horizon, f"{item.target_price:.2f}", f"{item.change_pct:+.2f}%", item.signal, item.confidence] for item in predictions]
        self.forecast_table.load_rows(rows, ["Vade", "Tahmini Fiyat", "Potansiyel", "Sinyal", "Güven"])
        self.forecast_table.fill_container()
        self._present_comparison(quote["symbol"])

    def _present_comparison(self, symbol):
        market = "BIST" if symbol.endswith(".IS") else "US"
        rows = self.market_rows.get(market, [])
        selected = next((row for row in rows if row["symbol"] == symbol), None)
        peers = sorted(rows, key=lambda row: row["change_pct"], reverse=True)[:5]
        if selected and selected not in peers:
            peers.append(selected)
        self.comparison_table.load_rows(
            [[row["symbol"], f"{row['price']:.2f}", f"{row['change_pct']:+.2f}%", f"{row['volume']:,}"] for row in peers],
            ["Sembol", "Fiyat", "Günlük", "Hacim"],
        )

    def _calculate_test_buy(self):
        if not self.current_quote or not self.current_predictions:
            return
        selected_months = self.test_months.currentData()
        selected = next(item for item in self.current_predictions if item.horizon.startswith(str(selected_months)))
        budget = self.test_budget.value()
        shares = budget / self.current_quote["price"]
        price_profit = budget * selected.change_pct / 100
        dividend_per_share = self.current_dividend["annual_per_share"] * selected_months / 12
        dividend_profit = shares * dividend_per_share
        total_profit = price_profit + dividend_profit
        total_pct = total_profit / budget * 100
        currency = self.current_quote["currency"]
        self.test_result.setText(
            f"<b>{self.current_quote['symbol']}</b><br>"
            f"Alınabilecek miktar: {shares:.4f} hisse<br>"
            f"Fiyat senaryosu: {price_profit:+.2f} {currency} ({selected.change_pct:+.2f}%)<br>"
            f"Tahmini temettü: {dividend_profit:+.2f} {currency}<br>"
            f"Toplam değişim: <b>{total_profit:+.2f} {currency} ({total_pct:+.2f}%)</b><br>"
            f"Son 12 ay ödeme sayısı: {self.current_dividend['payment_count']}<br><br>"
            "Geçmiş veriye dayalı senaryodur, garanti edilmiş kazanç değildir."
        )

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
        self.quote_label.setText(f"<span style='color:#ed6a5a'>Veri alınamadı:</span> {message}")

    def closeEvent(self, event):
        for worker in self.workers:
            worker.requestInterruption()
            worker.quit()
            worker.wait(1500)
        event.accept()
