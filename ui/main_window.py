from datetime import datetime
import json

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QSpinBox,
    QPushButton, QSplitter, QTabWidget,
    QTextBrowser, QTableWidgetItem, QVBoxLayout, QWidget,
)

from analysis.technical import forecast, indicators
from config import BASE_DIR, CACHE_DIR, DEFAULT_SYMBOL, DEFAULT_WATCHLIST, NEWS_LIMIT, REFRESH_SECONDS
from services.market_data import MarketDataService
from services.news import NewsService
from ui.widgets import ChartCanvas, ResultTable, Worker


THEME = """
QMainWindow, QWidget { background: #0b1118; color: #e9eef5; font-family: 'Segoe UI'; }
QLineEdit, QComboBox, QDoubleSpinBox { background: #121b26; border: 1px solid #29384a; border-radius: 4px; padding: 7px; color: #e9eef5; }
QPushButton { background: #2878d0; border: 0; border-radius: 4px; padding: 8px 13px; color: white; font-weight: 600; }
QPushButton:hover { background: #3d91ed; }
QPushButton:disabled { background: #1a2530; color: #5a6b7d; }
QGroupBox { background: #101821; border: 1px solid #29384a; border-radius: 5px; margin-top: 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #b8c7d9; }
QTableWidget { background: #141a22; alternate-background-color: #18212c; gridline-color: #2b3645; border: 0; }
QTableWidget::item:hover { background: #263b52; }
QTableWidget::item:selected { background: #1769aa; color: #ffffff; }
QHeaderView::section { background: #1e2b3b; color: #b8c7d9; padding: 7px; border: 0; }
QTextBrowser { background: #141a22; border: 0; padding: 8px; }
QSplitter::handle { background: #29384a; }
QTabWidget::pane { border: 1px solid #29384a; background: #0f171f; top: -1px; }
QTabBar::tab { background: #121b26; color: #9aa7b8; border: 1px solid #29384a; border-bottom: 0; padding: 9px 18px; min-width: 112px; }
QTabBar::tab:hover { background: #1b2b3b; color: #e9eef5; }
QTabBar::tab:selected { background: #1769aa; color: #ffffff; border-color: #3d91ed; font-weight: 700; }
QTabBar::tab:!selected { margin-top: 3px; }
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
        self.current_news = []
        self.dividend_rows = []
        self.favorites = self._load_favorites()
        self.simulation_history = []
        self.watchlist_rows = []
        self.active_requests = 0
        self.loading_step = 0
        self.dividend_loaded = False
        self.news_loaded_symbol = None
        self.financials_loaded_symbol = None
        self.setWindowTitle("PiyasaRadar | BIST & NYSE/NASDAQ")
        self.resize(1380, 860)
        self.setMinimumSize(1000, 650)
        try:
            self.setWindowIcon(QIcon(str(BASE_DIR / "icon.png")))
        except (OSError, TypeError):
            pass
        self.setStyleSheet(THEME)
        self._build_ui()
        QTimer.singleShot(150, lambda: self._load_symbol(DEFAULT_SYMBOL, load_watchlist=False))
        QTimer.singleShot(1800, self._refresh_watchlist)
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
        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setToolTip("Borsa listelerini ve seçili hisse verilerini yenile")
        self.refresh_button.clicked.connect(lambda: self._refresh_watchlist(self.refresh_button))
        header.addWidget(self.refresh_button)
        self.status = QLabel("Hazır")
        self.status.setStyleSheet("color: #9aa7b8;")
        header.addWidget(self.status)
        self.loading_label = QLabel()
        self.loading_label.setStyleSheet("color: #58d68d; font-weight: 600;")
        header.addWidget(self.loading_label)
        self.loading_timer = QTimer(self)
        self.loading_timer.timeout.connect(self._animate_loading)
        layout.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.dashboard_tab = self._build_dashboard()
        self.tabs.addTab(self.dashboard_tab, "Genel Bakış")
        self.tabs.setTabToolTip(0, "Seçilen hissenin fiyatı, grafiği ve teknik analizi")
        self.tabs.addTab(self._build_dividend_tab(), "ABD Temettüleri")
        self.tabs.setTabToolTip(1, "ABD hisselerinin temettü ödeme listesi")
        self.tabs.addTab(self._build_financial_tab(), "Finansallar")
        self.tabs.setTabToolTip(2, "Seçilen şirketin gelir, bilanço ve nakit akışı tabloları")
        self.tabs.addTab(self._build_news_tab(), "Haber Akışı")
        self.tabs.setTabToolTip(3, "Seçilen hisseyle ilgili güncel haberler")
        self.tabs.currentChanged.connect(self._on_tab_changed)
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
        self.load_lists_button = QPushButton("Listeleri yükle")
        self.load_lists_button.setToolTip("Borsa İstanbul ve ABD hisse listelerini yükle")
        self.load_lists_button.clicked.connect(lambda: self._refresh_watchlist(self.load_lists_button))
        left_layout.addWidget(self.load_lists_button)
        layout.addWidget(left_panel, 1)

        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(0, 0, 6, 0)
        self.quote_label = QLabel("Veri yükleniyor...")
        self.quote_label.setStyleSheet("font-size: 23px; font-weight: 700; padding: 4px 0;")
        center_layout.addWidget(self.quote_label)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setMaximumHeight(44)
        self.error_label.setStyleSheet("color: #ffb4ab; background: #3a1d24; padding: 6px; border-radius: 4px;")
        self.error_label.hide()
        center_layout.addWidget(self.error_label)
        self.recommendation_label = QLabel("Gerçek veriler yükleniyor...")
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setStyleSheet("color: #f5b041; padding: 3px 0;")
        center_layout.addWidget(self.recommendation_label)
        chart_group = QGroupBox("Fiyat ve Hareketli Ortalamalar")
        chart_layout = QVBoxLayout(chart_group)
        self.chart = ChartCanvas()
        chart_layout.addWidget(self.chart)
        center_layout.addWidget(chart_group, 1)
        forecast_group = QGroupBox("İstatistiksel Öngörü (yatırım tavsiyesi değildir)")
        forecast_layout = QVBoxLayout(forecast_group)
        self.forecast_table = ResultTable()
        self.forecast_table.fill_container()
        forecast_layout.addWidget(self.forecast_table)
        center_layout.addWidget(forecast_group, 1)

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
        self.test_buy_button.setToolTip("Seçilen hisse için sanal yatırım sonucunu hesapla")
        self.test_buy_button.setEnabled(False)
        self.test_buy_button.clicked.connect(self._calculate_test_buy)
        order_layout.addWidget(self.test_buy_button)
        self.test_result = QLabel("Bir hisse seçip tutar ve süre girin.")
        self.test_result.setWordWrap(True)
        self.test_result.setStyleSheet("color: #b8c7d9; padding-top: 8px;")
        order_layout.addWidget(self.test_result)
        order_layout.addWidget(QLabel("Simülasyon geçmişi"))
        self.simulation_table = ResultTable()
        self.simulation_table.setMaximumHeight(150)
        order_layout.addWidget(self.simulation_table)
        center_layout.addWidget(order_panel)

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
        center_layout.addWidget(indicator_group)
        layout.addWidget(center_panel, 3)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(us_panel, 1)
        layout.addWidget(right_panel, 1)
        return page

    def _build_market_panel(self, title, symbols, placeholder):
        panel = QGroupBox(title)
        layout = QVBoxLayout(panel)
        input_field = QLineEdit()
        input_field.setPlaceholderText(placeholder)
        input_field.setText(symbols)
        input_field.returnPressed.connect(self._refresh_watchlist)
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

    def _build_dividend_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel("ABD borsalarında temettü verimi pozitif olan hisseler")
        layout.addWidget(intro)
        controls = QHBoxLayout()
        self.dividend_search = QLineEdit()
        self.dividend_search.setPlaceholderText("Sembol veya şirket ara")
        controls.addWidget(self.dividend_search, 2)
        self.dividend_exchange = QComboBox()
        self.dividend_exchange.addItems(["Tüm ABD borsaları", "NASDAQ", "NYSE", "AMEX"])
        controls.addWidget(self.dividend_exchange)
        self.dividend_min_price = QDoubleSpinBox()
        self.dividend_min_price.setRange(0, 1000000)
        self.dividend_min_price.setPrefix("Min fiyat ")
        controls.addWidget(self.dividend_min_price)
        self.dividend_max_price = QDoubleSpinBox()
        self.dividend_max_price.setRange(0, 1000000)
        self.dividend_max_price.setValue(1000000)
        self.dividend_max_price.setPrefix("Max fiyat ")
        controls.addWidget(self.dividend_max_price)
        self.dividend_min_yield = QDoubleSpinBox()
        self.dividend_min_yield.setRange(0, 100)
        self.dividend_min_yield.setSuffix("% verim")
        controls.addWidget(self.dividend_min_yield)
        self.dividend_min_payments = QSpinBox()
        self.dividend_min_payments.setRange(0, 52)
        self.dividend_min_payments.setSuffix(" ödeme+")
        controls.addWidget(self.dividend_min_payments)
        self.dividend_filter_button = QPushButton("Filtrele")
        self.dividend_filter_button.clicked.connect(self._filter_dividends)
        controls.addWidget(self.dividend_filter_button)
        layout.addLayout(controls)
        self.dividend_table = ResultTable()
        self.dividend_table.cellClicked.connect(lambda row, _column: self._load_symbol(self.dividend_table.item(row, 0).text()))
        layout.addWidget(self.dividend_table)
        self.dividend_status = QLabel("Listeyi görmek için Temettü listesini yükle düğmesine basın.")
        layout.addWidget(self.dividend_status)
        self.dividend_load_button = QPushButton("Temettü listesini yükle")
        self.dividend_load_button.clicked.connect(self._load_dividend_universe)
        layout.addWidget(self.dividend_load_button)
        return page

    def _build_financial_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.financial_status = QLabel("Bir hisse seçildiğinde finansal tablolar burada yüklenir.")
        layout.addWidget(self.financial_status)
        self.financial_tables = QTabWidget()
        self.financial_empty_label = QLabel("Veri yok / Henüz yüklenmedi")
        self.financial_empty_label.setAlignment(Qt.AlignCenter)
        self.financial_empty_label.setStyleSheet("color: #9aa7b8; padding: 24px;")
        layout.addWidget(self.financial_tables)
        layout.addWidget(self.financial_empty_label)
        return page

    def _build_news_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        news_splitter = QSplitter(Qt.Vertical)
        self.news_browser = QTextBrowser()
        self.news_browser.setPlaceholderText("Bir hisse seçildiğinde haberler burada yüklenir.")
        self.news_browser.setOpenExternalLinks(False)
        self.news_browser.anchorClicked.connect(self._show_news_detail)
        news_splitter.addWidget(self.news_browser)
        self.news_detail = QTextBrowser()
        self.news_detail.setOpenExternalLinks(True)
        self.news_detail.setPlaceholderText("Detayını görmek için bir habere tıklayın.")
        news_splitter.addWidget(self.news_detail)
        layout.addWidget(news_splitter)
        return page

    def _run(self, function, success, *args, context="Veri", trigger=None):
        self._set_loading(True)
        self.active_requests += 1
        self.status.setText(f"{context} alınıyor...")
        if trigger is not None:
            trigger.setEnabled(False)
        worker = Worker(function, *args)
        worker.trigger = trigger
        self.workers.append(worker)
        worker.succeeded.connect(success)
        worker.failed.connect(self._show_error)
        worker.finished.connect(lambda: self._worker_finished(worker))
        worker.start()

    def _worker_finished(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        if getattr(worker, "trigger", None) is not None:
            worker.trigger.setEnabled(True)
        self.active_requests = max(0, self.active_requests - 1)
        if not self.active_requests:
            self._set_loading(False)
            self.status.setText(f"Son güncelleme: {datetime.now():%H:%M:%S}")

    def _set_loading(self, loading):
        if loading:
            self.loading_step = 0
            self.loading_label.show()
            self.loading_timer.start(300)
            self._animate_loading()
        else:
            self.loading_timer.stop()
            self.loading_label.clear()
            self.loading_label.hide()

    def _animate_loading(self):
        self.loading_step = (self.loading_step + 1) % 4
        self.loading_label.setText("Yükleniyor" + "." * self.loading_step)

    def _load_symbol(self, symbol, load_watchlist=True):
        symbol = symbol.strip().upper()
        if not symbol:
            return
        self.current_symbol = symbol
        self.news_loaded_symbol = None
        self.financials_loaded_symbol = None
        self._run(self._fetch_dashboard, self._present_dashboard, symbol, context="Genel bakış")
        if load_watchlist:
            self._load_context_for_current_tab()

    def _on_tab_changed(self, index):
        if index == 1 and not self.dividend_loaded:
            self._load_dividend_universe()
        elif index in {2, 3}:
            self._load_context_for_current_tab()

    def _load_context_for_current_tab(self):
        if not self.current_symbol:
            return
        if self.tabs.currentIndex() == 2 and self.financials_loaded_symbol != self.current_symbol:
            self.financials_loaded_symbol = self.current_symbol
            self._run(self.market.financial_tables, self._present_financials, self.current_symbol, context="Finansal tablolar")
        elif self.tabs.currentIndex() == 3 and self.news_loaded_symbol != self.current_symbol:
            self.news_loaded_symbol = self.current_symbol
            self._run(self.news.fetch, self._present_news, self.current_symbol, NEWS_LIMIT, context="Haberler")

    def _symbols_from_input(self):
        text = f"{self.bist_input.text()},{self.us_watchlist_input.text()}"
        symbols = [item.strip().upper() for item in text.replace(";", ",").split(",") if item.strip()]
        return list(dict.fromkeys(symbols))

    def _refresh_watchlist(self, trigger=None):
        symbols = self._symbols_from_input()
        if not symbols:
            self.status.setText("En az bir sembol girin")
            return
        self.watchlist = symbols
        self._run(self._fetch_watchlist, self._present_watchlist, symbols, context="Borsa listeleri", trigger=trigger)

    def _fetch_watchlist(self, symbols):
        rows = []
        for symbol in symbols:
            try:
                history = self.market.history(symbol)
                quote = self.market.quote(symbol)
                predictions = forecast(history)
                one_month = predictions[0]
                rows.append({
                    "symbol": quote["symbol"],
                    "price": quote["price"],
                    "currency": quote["currency"],
                    "change_pct": quote["change_pct"],
                    "forecast_pct": one_month.change_pct,
                    "signal": one_month.signal,
                    "confidence": one_month.confidence,
                })
            except Exception:
                continue
        return rows

    def _present_watchlist(self, rows):
        if not rows:
            self.recommendation_label.setText("Gösterilecek geçerli hisse bulunamadı.")
            return
        self.watchlist_rows = rows
        rows.sort(key=lambda row: row["forecast_pct"], reverse=True)
        table_rows = [
            ["★" if row["symbol"] in self.favorites else "☆", row["symbol"], f"{row['price']:.2f} {row['currency']}", f"{row['change_pct']:+.2f}%",
             f"{row['forecast_pct']:+.2f}%", row["signal"], row["confidence"]]
            for row in rows
        ]
        headers = ["Favori", "Sembol", "Son fiyat", "Günlük değişim", "1 ay senaryosu", "Sinyal", "Güven"]
        self.bist_table.load_rows([row for row in table_rows if row[1].endswith(".IS")], headers, color_columns=(3, 4))
        self.us_table.load_rows([row for row in table_rows if not row[1].endswith(".IS")], headers, color_columns=(3, 4))
        best = rows[0]
        self.recommendation_label.setText(
            f"Veriye dayalı 1 ay senaryosunda en yüksek tahmini getiri: {best['symbol']} "
            f"({best['forecast_pct']:+.2f}%, güven: {best['confidence']}). "
            "Bu bir garanti veya yatırım tavsiyesi değildir; geçmiş fiyat verisine dayalı istatistiksel tahmindir."
        )
        self._load_symbol(best["symbol"], load_watchlist=False)

    def _watchlist_row_clicked(self, row, column):
        table = self.sender()
        if column == 0:
            symbol_item = table.item(row, 1)
            if symbol_item:
                self._toggle_favorite(symbol_item.text())
            return
        symbol_item = table.item(row, 1)
        if symbol_item:
            self._load_symbol(symbol_item.text())

    def _fetch_dashboard(self, symbol):
        history = self.market.history(symbol)
        return self.market.quote(symbol), indicators(history), forecast(history), self.market.dividend_info(symbol)

    def _present_dashboard(self, payload):
        quote, frame, predictions, dividend = payload
        self.current_quote = quote
        self.current_predictions = predictions
        self.current_dividend = dividend
        self.error_label.hide()
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
        rows = []
        for item in predictions:
            action, usage = self._scenario_action(item)
            rows.append([item.horizon, f"{item.target_price:.2f}", f"{item.change_pct:+.2f}%", item.signal, item.confidence, action, usage])
        self.forecast_table.load_rows(rows, ["Vade", "Tahmini Fiyat", "Potansiyel", "Sinyal", "Güven", "Aksiyon", "Kullanım"], color_columns=(2,))
        self.forecast_table.fill_container()
        self.test_months.clear()
        for item in predictions:
            action, _usage = self._scenario_action(item)
            months = int(item.horizon.split()[0])
            self.test_months.addItem(f"{item.horizon} - {action}", months)

    def _scenario_action(self, prediction):
        if prediction.signal == "Asiri alim" or prediction.change_pct <= -5:
            return "SAT / AZALT", "Yeni alım yerine riski azaltmayı değerlendir."
        if prediction.signal == "Asiri satim" and prediction.change_pct > 0:
            return "AL / KADEMELİ", "Toparlanma senaryosu; küçük ve kademeli pozisyon düşün."
        if prediction.change_pct >= 5 and prediction.signal == "Pozitif":
            return "AL / DEĞERLENDİR", "Pozitif momentum; stop-loss ve portföy riskini izle."
        return "BEKLE / İZLE", "Sinyaller net değil; yeni veriyi ve fiyat hareketini bekle."

    def _calculate_test_buy(self):
        if not self.current_quote or not self.current_predictions:
            return
        self.test_buy_button.setEnabled(False)
        QTimer.singleShot(0, lambda: self.test_buy_button.setEnabled(True))
        selected_months = self.test_months.currentData()
        selected = next(item for item in self.current_predictions if item.horizon.startswith(str(selected_months)))
        action, usage = self._scenario_action(selected)
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
            f"Vade aksiyonu: <b>{action}</b><br>"
            f"Kullanım: {usage}<br>"
            f"Son 12 ay ödeme sayısı: {self.current_dividend['payment_count']}<br><br>"
            "Geçmiş veriye dayalı senaryodur, garanti edilmiş kazanç değildir."
        )
        self.simulation_history.insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"),
            "symbol": self.current_quote["symbol"],
            "horizon": f"{selected_months} ay",
            "return": f"{total_pct:+.2f}%",
            "amount": f"{total_profit:+.2f} {currency}",
        })
        self.simulation_history = self.simulation_history[:10]
        self.simulation_table.load_rows(
            [[item["time"], item["symbol"], item["horizon"], item["return"], item["amount"]] for item in self.simulation_history],
            ["Saat", "Sembol", "Vade", "Değişim", "Sonuç"],
        )

    def _favorites_path(self):
        return CACHE_DIR / "favorites.json"

    def _load_favorites(self):
        try:
            return set(json.loads(self._favorites_path().read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return set()

    def _save_favorites(self):
        try:
            self._favorites_path().write_text(json.dumps(sorted(self.favorites)), encoding="utf-8")
        except OSError:
            self.status.setText("Favoriler kaydedilemedi")

    def _toggle_favorite(self, symbol):
        if symbol in self.favorites:
            self.favorites.remove(symbol)
        else:
            self.favorites.add(symbol)
        self._save_favorites()
        self._present_watchlist(self.watchlist_rows)

    def _present_news(self, articles):
        self.current_news = articles
        if not articles:
            self.news_browser.setText("Bu sembol için haber bulunamadı.")
            return
        html = "".join(
            f"<article style='padding:8px;border-bottom:1px solid #29384a;'>"
            f"<a href='{item['link']}'><b>{item['title']}</b></a><br>"
            f"<small>{item.get('source', 'Yahoo Finance')} | {item['published']}</small><br>"
            f"<span>{item.get('summary', '')}</span></article>"
            for item in articles
        )
        self.news_browser.setHtml(html)

    def _show_news_detail(self, url):
        link = url.toString()
        article = next((item for item in self.current_news if item.get("link") == link), None)
        if not article:
            return
        self.news_detail.setHtml(
            f"<h2>{article['title']}</h2>"
            f"<p><small>{article.get('source', 'Yahoo Finance')} | {article['published']}</small></p>"
            f"<p>{article.get('summary', 'Detay bulunamadı.')}</p>"
            f"<p><a href='{article['link']}'>Kaynak haberi aç</a></p>"
        )

    def _present_financials(self, tables):
        self.financial_status.setText(f"{self.current_symbol} finansal tabloları")
        self.financial_tables.clear()
        self.financial_empty_label.setVisible(not tables)
        for name, frame in tables.items():
            table = ResultTable()
            if frame.empty:
                table.load_rows([], ["Kalem"])
            else:
                rows = [[index] + [value if value == value else "-" for value in row] for index, row in frame.head(30).iterrows()]
                table.load_rows(rows, ["Kalem"] + [str(column)[:10] for column in frame.columns])
            self.financial_tables.addTab(table, name)
        self.financial_empty_label.setVisible(not tables)

    def _load_dividend_universe(self):
        self.dividend_status.setText("Temettü hisseleri yükleniyor...")
        self._run(
            self.market.dividend_universe,
            self._present_dividend_universe,
            context="Temettü listesi",
            trigger=self.dividend_load_button,
        )

    def _present_dividend_universe(self, rows):
        self.dividend_rows = rows
        self.dividend_loaded = True
        self.dividend_status.setText(f"{len(rows)} temettü hissesi yüklendi. Filtreleri kullanabilirsiniz.")
        self._filter_dividends()

    def _filter_dividends(self):
        if not hasattr(self, "dividend_table"):
            return
        needle = self.dividend_search.text().strip().upper()
        exchange = self.dividend_exchange.currentText()
        filtered = [
            row for row in self.dividend_rows
            if (not needle or needle in row["symbol"] or needle in row["name"].upper())
            and (exchange == "Tüm ABD borsaları" or exchange in row["exchange"].upper())
            and self.dividend_min_price.value() <= row["price"] <= self.dividend_max_price.value()
            and row["yield_pct"] >= self.dividend_min_yield.value()
            and row["payment_count"] >= self.dividend_min_payments.value()
        ]
        self.dividend_table.load_rows(
            [[row["symbol"], row["name"][:30], row["exchange"], f"{row['price']:.2f}", f"{row['yield_pct']:.2f}%", f"{row['annual_dividend']:.2f}", row["payment_count"]] for row in filtered],
            ["Sembol", "Şirket", "Borsa", "Fiyat", "Temettü verimi", "Yıllık temettü", "Son 12 ay ödeme"],
        )

    def _show_error(self, message):
        self.status.setText("Veri alınamadı")
        self.error_label.setText(f"Veri alınamadı: {message}")
        self.error_label.show()
        QTimer.singleShot(8000, self.error_label.hide)
        if hasattr(self, "dividend_status") and self.tabs.currentIndex() == 1:
            self.dividend_status.setText("Veri alınamadı. Yeniden denemek için listeyi tekrar yükleyin.")

    def closeEvent(self, event):
        for worker in self.workers:
            worker.requestInterruption()
            worker.quit()
            worker.wait(1500)
        event.accept()
