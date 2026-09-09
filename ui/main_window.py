from datetime import datetime
import json
from concurrent.futures import ThreadPoolExecutor
    
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QSpinBox, QStackedWidget,
    QPushButton, QSplitter, QTabWidget,
    QTextBrowser, QTableWidgetItem, QVBoxLayout, QWidget,
)

from analysis.geopolitical import assess_news
from analysis.technical import forecast, indicators
from config import BASE_DIR, CACHE_DIR, DEFAULT_SYMBOL, DEFAULT_WATCHLIST, NEWS_LIMIT, REFRESH_SECONDS, BIST_POPULAR, US_POPULAR
from services.market_data import MarketDataService
from services.news import NewsService
from ui.detail_view import StockDetailView
from ui.widgets import ChartCanvas, ResultTable, Worker, EmptyStateWidget


THEME = """
QMainWindow, QWidget { background: #0b1118; color: #e9eef5; font-family: 'Segoe UI'; }
QLineEdit, QComboBox, QDoubleSpinBox { background: #121b26; border: 1px solid #29384a; border-radius: 4px; padding: 7px; color: #e9eef5; }
QPushButton { background: #2878d0; border: 0; border-radius: 4px; padding: 8px 13px; color: white; font-weight: 600; }
QPushButton:hover { background: #3d91ed; }
QPushButton:disabled { background: #1a2530; color: #5a6b7d; }
QGroupBox { background: #101821; border: 1px solid #29384a; border-top: 3px solid #2878d0; border-radius: 5px; margin-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; color: #b8c7d9; font-weight: 600; }
QTableWidget { background: #141a22; alternate-background-color: #18212c; gridline-color: #2b3645; border: 0; }
QTableWidget::item:hover { background: #263b52; }
QTableWidget::item:selected { background: #1769aa; color: #ffffff; }
QHeaderView::section { background: #1e2b3b; color: #b8c7d9; padding: 7px; border: 0; }
QTextBrowser { background: #141a22; border: 0; padding: 8px; }
QSplitter::handle { background: #29384a; }
QSplitter::handle:hover { background: #3d91ed; }
QSplitter::handle:horizontal { width: 4px; }
QSplitter::handle:vertical { height: 4px; }
QTabWidget::pane { border: 1px solid #29384a; background: #0f171f; top: -1px; }
QTabBar::tab { background: #121b26; color: #9aa7b8; border: 1px solid #29384a; border-bottom: 0; padding: 11px 20px; min-width: 112px; font-weight: 500; }
QTabBar::tab:hover { background: #1b2b3b; color: #e9eef5; }
QTabBar::tab:selected { background: #1769aa; color: #ffffff; border-color: #3d91ed; font-weight: 700; }
QTabBar::tab:!selected { margin-top: 3px; }
"""


def add_search_icon(line_edit: QLineEdit):
    """Add a subtle search icon inside the leading position of a QLineEdit."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    font = painter.font()
    font.setPointSize(9)
    painter.setFont(font)
    painter.setPen(QColor("#7a8897"))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "🔍")
    painter.end()
    line_edit.addAction(QIcon(pixmap), QLineEdit.LeadingPosition)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.market = MarketDataService()
        self.news = NewsService()
        self.workers = []
        self.active_tasks = {}
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
        # Don't auto-load DEFAULT_SYMBOL - let user click "Listeleri yükle" or select a stock
        # QTimer.singleShot(150, lambda: self._load_symbol(DEFAULT_SYMBOL, load_watchlist=False))
        # Auto-refresh only on dashboard tab (index 0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_watchlist_if_visible)
        self.timer.start(REFRESH_SECONDS * 1000)

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # TOP HEADER: Logo + Symbol Input + Refresh Button
        header_top = QHBoxLayout()
        title = QLabel("PiyasaRadar")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #58d68d;")
        header_top.addWidget(title)
        header_top.addSpacing(20)
        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("Sembol: AAPL veya THYAO.IS")
        self.symbol_input.setText(DEFAULT_SYMBOL)
        self.symbol_input.returnPressed.connect(lambda: self._load_symbol(self.symbol_input.text()))
        add_search_icon(self.symbol_input)
        header_top.addWidget(self.symbol_input, 1)
        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setToolTip("Borsa listelerini ve seçili hisse verilerini yenile")
        self.refresh_button.clicked.connect(lambda: self._refresh_watchlist(self.refresh_button))
        header_top.addWidget(self.refresh_button)
        layout.addLayout(header_top)
        
        # STATUS BAR: Unified status display (28px height, hidden when idle)
        self.status_bar_frame = QFrame()
        self.status_bar_frame.setStyleSheet(
            "QFrame { background: #101821; border: 1px solid #1e2b3b; border-radius: 4px; }"
        )
        self.status_bar_frame.setFixedHeight(28)
        status_layout = QHBoxLayout(self.status_bar_frame)
        status_layout.setContentsMargins(10, 0, 10, 0)
        status_layout.setSpacing(6)
        
        self.status_icon = QLabel("⏳")
        self.status_icon.setStyleSheet("font-size: 13px; color: #58d68d;")
        self.status_icon.hide()
        status_layout.addWidget(self.status_icon)
        
        self.status = QLabel("")
        self.status.setStyleSheet("color: #9aa7b8; font-size: 12px; font-weight: 500;")
        status_layout.addWidget(self.status, 1)
        layout.addWidget(self.status_bar_frame)
        
        self.status_bar_frame.hide()  # Hide when no active operations

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
        """Build dashboard with QStackedWidget for watchlist/detail view switching."""
        # Create the stacked widget to switch between watchlist and detail views
        stacked = QStackedWidget()
        
        # Index 0: Watchlist view (BIST | US split)
        watchlist_view = self._build_watchlist_view()
        stacked.addWidget(watchlist_view)
        
        # Index 1: Detail view
        self.detail_view = StockDetailView()
        self.detail_view.back_clicked.connect(lambda: stacked.setCurrentIndex(0))
        self.detail_view.test_buy_button.clicked.connect(self._calculate_test_buy)
        self.detail_view.news_browser.anchorClicked.connect(self._show_news_detail)
        stacked.addWidget(self.detail_view)
        
        # Start with watchlist view
        stacked.setCurrentIndex(0)
        
        return stacked
    
    def _build_watchlist_view(self) -> QWidget:
        """Build the watchlist view with BIST and US markets split 50/50."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Top recommendation labels
        self.recommendation_label = QLabel("Gerçek veriler yükleniyor...")
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setStyleSheet("color: #f5b041; padding: 4px 0; font-weight: 500;")
        layout.addWidget(self.recommendation_label)
        
        self.geopolitical_label = QLabel("Jeopolitik risk verisi yükleniyor...")
        self.geopolitical_label.setWordWrap(True)
        self.geopolitical_label.setStyleSheet("color: #b8c7d9; background: #101821; border: 1px solid #29384a; padding: 8px; border-radius: 4px;")
        layout.addWidget(self.geopolitical_label)
        
        # Create a horizontal splitter to divide BIST and US panels
        splitter = QSplitter(Qt.Horizontal)
        
        # Left panel: Borsa İstanbul
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.bist_table, bist_panel = self._build_market_panel(
            "Borsa İstanbul", ", ".join(BIST_POPULAR), "THYAO.IS, ASELS.IS, BIMAS.IS, TUPRS.IS, GARAN.IS...", is_bist=True
        )
        left_layout.addWidget(bist_panel, 1)
        splitter.addWidget(left_panel)
        
        # Right panel: ABD Borsaları
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.us_table, us_panel = self._build_market_panel(
            "ABD Borsaları", ", ".join(US_POPULAR), "AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA...", is_bist=False
        )
        right_layout.addWidget(us_panel, 1)
        splitter.addWidget(right_panel)
        
        # Set equal sizes for both panels (50/50)
        splitter.setSizes([1, 1])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        
        layout.addWidget(splitter, 1)
        
        # Centered refresh button below both market panels
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 6, 0, 4)
        btn_layout.addStretch()
        self.load_lists_button = QPushButton("🔄 Listeleri Güncelle")
        self.load_lists_button.setToolTip("Borsa İstanbul ve ABD hisse listelerini güncelle")
        self.load_lists_button.setFixedWidth(220)
        self.load_lists_button.setFixedHeight(36)
        self.load_lists_button.clicked.connect(lambda: self._refresh_watchlist(self.load_lists_button))
        btn_layout.addWidget(self.load_lists_button)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        return page

    def _build_market_panel(self, title, symbols, placeholder, is_bist=True):
        flag_title = ("🇹🇷 " if is_bist else "🇺🇸 ") + title
        
        panel = QGroupBox(flag_title)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 16, 10, 10)
        layout.setSpacing(8)
        
        input_field = QLineEdit()
        input_field.setPlaceholderText(placeholder)
        input_field.setText(symbols)
        input_field.returnPressed.connect(self._refresh_watchlist)
        add_search_icon(input_field)
        layout.addWidget(input_field)
        
        table = ResultTable(empty_icon="📊", empty_title="Henüz veri yok", empty_subtitle="Listeleri yükle butonuna basarak başlayın")
        table.setSelectionBehavior(table.SelectRows)
        table.setEditTriggers(table.NoEditTriggers)
        table.cellClicked.connect(self._watchlist_row_clicked)
        layout.addWidget(table)
        if is_bist:
            self.bist_input = input_field
        else:
            self.us_watchlist_input = input_field
        return table, panel

    def _build_dividend_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        intro = QLabel("ABD borsalarında temettü verimi pozitif olan hisseler")
        intro.setStyleSheet("color: #b8c7d9; font-size: 12px; padding: 8px; background: #101821; border-radius: 4px;")
        layout.addWidget(intro)
        
        # Filters in a group box
        filter_group = QGroupBox("Filtreler")
        controls = QHBoxLayout(filter_group)
        controls.setSpacing(10)
        controls.setContentsMargins(10, 16, 10, 10)
        
        # Search
        search_layout = QVBoxLayout()
        search_label = QLabel("Ara")
        search_label.setStyleSheet("font-size: 11px; color: #9aa7b8; font-weight: 500;")
        self.dividend_search = QLineEdit()
        self.dividend_search.setPlaceholderText("Sembol veya şirket")
        self.dividend_search.setMinimumWidth(150)
        add_search_icon(self.dividend_search)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.dividend_search)
        controls.addLayout(search_layout, 2)
        
        # Exchange
        exchange_layout = QVBoxLayout()
        exchange_label = QLabel("Borsa")
        exchange_label.setStyleSheet("font-size: 11px; color: #9aa7b8; font-weight: 500;")
        self.dividend_exchange = QComboBox()
        self.dividend_exchange.addItems(["Tüm ABD borsaları", "NASDAQ", "NYSE", "AMEX"])
        self.dividend_exchange.setMinimumWidth(150)
        exchange_layout.addWidget(exchange_label)
        exchange_layout.addWidget(self.dividend_exchange)
        controls.addLayout(exchange_layout)
        
        # Min price
        min_price_layout = QVBoxLayout()
        min_price_label = QLabel("Min Fiyat")
        min_price_label.setStyleSheet("font-size: 11px; color: #9aa7b8; font-weight: 500;")
        self.dividend_min_price = QDoubleSpinBox()
        self.dividend_min_price.setRange(0, 1000000)
        self.dividend_min_price.setMinimumWidth(130)
        self.dividend_min_price.setSuffix(" $")
        min_price_layout.addWidget(min_price_label)
        min_price_layout.addWidget(self.dividend_min_price)
        controls.addLayout(min_price_layout)
        
        # Max price
        max_price_layout = QVBoxLayout()
        max_price_label = QLabel("Max Fiyat")
        max_price_label.setStyleSheet("font-size: 11px; color: #9aa7b8; font-weight: 500;")
        self.dividend_max_price = QDoubleSpinBox()
        self.dividend_max_price.setRange(0, 1000000)
        self.dividend_max_price.setValue(1000000)
        self.dividend_max_price.setMinimumWidth(130)
        self.dividend_max_price.setSuffix(" $")
        max_price_layout.addWidget(max_price_label)
        max_price_layout.addWidget(self.dividend_max_price)
        controls.addLayout(max_price_layout)
        
        # Min yield
        yield_layout = QVBoxLayout()
        yield_label = QLabel("Min Verim")
        yield_label.setStyleSheet("font-size: 11px; color: #9aa7b8; font-weight: 500;")
        self.dividend_min_yield = QDoubleSpinBox()
        self.dividend_min_yield.setRange(0, 100)
        self.dividend_min_yield.setMinimumWidth(130)
        self.dividend_min_yield.setSuffix(" %")
        yield_layout.addWidget(yield_label)
        yield_layout.addWidget(self.dividend_min_yield)
        controls.addLayout(yield_layout)
        
        # Min payments
        payments_layout = QVBoxLayout()
        payments_label = QLabel("Min Ödeme")
        payments_label.setStyleSheet("font-size: 11px; color: #9aa7b8; font-weight: 500;")
        self.dividend_min_payments = QSpinBox()
        self.dividend_min_payments.setRange(0, 52)
        self.dividend_min_payments.setMinimumWidth(130)
        self.dividend_min_payments.setSuffix(" /yıl")
        payments_layout.addWidget(payments_label)
        payments_layout.addWidget(self.dividend_min_payments)
        controls.addLayout(payments_layout)
        
        # Filter button
        filter_btn_layout = QVBoxLayout()
        filter_btn_layout.addStretch()
        self.dividend_filter_button = QPushButton("Filtrele")
        self.dividend_filter_button.setMinimumWidth(90)
        self.dividend_filter_button.clicked.connect(self._filter_dividends)
        filter_btn_layout.addWidget(self.dividend_filter_button)
        controls.addLayout(filter_btn_layout)
        
        layout.addWidget(filter_group)
        
        self.dividend_table = ResultTable(empty_icon="💰", empty_title="Henüz veri yok", empty_subtitle="Temettü listesini yükle butonuna basarak başlayın")
        self.dividend_table.cellClicked.connect(lambda row, _column: self._load_symbol(self.dividend_table.item(row, 0).text()))
        layout.addWidget(self.dividend_table, 1)
        
        self.dividend_status = QLabel("Listeyi görmek için Temettü listesini yükle düğmesine basın.")
        self.dividend_status.setStyleSheet("color: #9aa7b8; font-size: 12px; padding: 8px; background: #101821; border: 1px solid #29384a; border-radius: 4px;")
        layout.addWidget(self.dividend_status)
        
        self.dividend_load_button = QPushButton("Temettü listesini yükle")
        self.dividend_load_button.setMinimumHeight(36)
        self.dividend_load_button.clicked.connect(self._load_dividend_universe)
        layout.addWidget(self.dividend_load_button)
        
        return page

    def _build_financial_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Guiding empty state
        self.financial_empty_state = EmptyStateWidget(
            "📄",
            "Hisse Finansalları ve Bilançolar",
            "Bir hissenin gelir tablosunu, bilançosunu ve nakit akışını incelemek için Genel Bakış listesinden ilgili hisseye tıklayın.\nFinansal veriler doğrudan hissenin detay sayfasında sunulmaktadır."
        )
        layout.addWidget(self.financial_empty_state, 1)
        return page

    def _build_news_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # Top Info bar
        info_frame = QFrame()
        info_frame.setStyleSheet("QFrame { background: #101821; border: 1px solid #29384a; border-radius: 4px; }")
        info_layout = QHBoxLayout(info_frame)
        info_layout.setContentsMargins(12, 8, 12, 8)
        self.news_status = QLabel("📰 Güncel Piyasa ve Hisse Haber Akışı")
        self.news_status.setStyleSheet("color: #b8c7d9; font-size: 12px; font-weight: 500;")
        info_layout.addWidget(self.news_status)
        layout.addWidget(info_frame)
        
        # Empty state
        self.news_empty_state = EmptyStateWidget("📰", "Henüz haber yüklenmedi", "Bir hisse seçildiğinde güncel haberler burada listelenir.")
        layout.addWidget(self.news_empty_state, 1)
        
        # Splitter container - Horizontal Blog + Reader Layout
        self.news_splitter = QSplitter(Qt.Horizontal)
        self.news_splitter.setStyleSheet(
            "QSplitter::handle { background: #29384a; width: 4px; } "
            "QSplitter::handle:hover { background: #3d91ed; }"
        )
        
        self.news_browser = QTextBrowser()
        self.news_browser.setPlaceholderText("Bir hisse seçildiğinde haberler burada yüklenir.")
        self.news_browser.setOpenExternalLinks(False)
        self.news_browser.anchorClicked.connect(self._show_news_detail)
        self.news_splitter.addWidget(self.news_browser)
        
        self.news_detail = QTextBrowser()
        self.news_detail.setOpenExternalLinks(True)
        self.news_detail.setPlaceholderText("Detayını görmek için soldaki haberlerden birine tıklayın.")
        self.news_splitter.addWidget(self.news_detail)
        
        self.news_splitter.setSizes([650, 450])
        self.news_splitter.hide()
        layout.addWidget(self.news_splitter, 1)
        
        return page

    def _run(self, function, success, *args, context="Veri", trigger=None):
        if trigger is not None:
            trigger.setEnabled(False)
        worker = Worker(function, *args)
        worker.trigger = trigger
        self.workers.append(worker)
        self.active_tasks[worker] = context
        self._update_status_bar()
        worker.succeeded.connect(success)
        worker.failed.connect(self._show_error)
        worker.finished.connect(lambda: self._worker_finished(worker))
        worker.start()

    def _worker_finished(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        if worker in self.active_tasks:
            del self.active_tasks[worker]
        if getattr(worker, "trigger", None) is not None:
            worker.trigger.setEnabled(True)
        self._update_status_bar()

    def _update_status_bar(self):
        if self.active_tasks:
            messages = list(dict.fromkeys(f"{ctx} alınıyor..." for ctx in self.active_tasks.values()))
            text = " • ".join(messages)
            self.status.setText(text)
            self.status_icon.show()
            self.status_bar_frame.show()
        else:
            self.status.setText("")
            self.status_icon.hide()
            self.status_bar_frame.hide()

    def _load_symbol(self, symbol, load_watchlist=True, show_detail=False):
        symbol = symbol.strip().upper()
        if not symbol:
            return
        self.current_symbol = symbol
        self.news_loaded_symbol = None
        self.financials_loaded_symbol = None
        
        # Show detail view if requested
        if show_detail:
            stacked = self.tabs.widget(0)  # Get the stacked widget from dashboard tab
            if isinstance(stacked, QStackedWidget):
                stacked.setCurrentIndex(1)  # Switch to detail view
                self.detail_view.set_loading("Hisse verileri yükleniyor...")
        
        self._run(self._fetch_dashboard, self._present_dashboard, symbol, context="Genel bakış")
        if load_watchlist:
            self._load_context_for_current_tab()

    def _on_tab_changed(self, index):
        if index == 1 and not self.dividend_loaded:
            self._load_dividend_universe()
        elif index == 3:
            self._load_context_for_current_tab()

    def _load_context_for_current_tab(self):
        if not self.current_symbol:
            return
        if self.tabs.currentIndex() == 3 and self.news_loaded_symbol != self.current_symbol:
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

    def _refresh_watchlist_if_visible(self):
        """Only refresh watchlist if Dashboard tab (index 0) is currently active."""
        if self.tabs.currentIndex() == 0:
            self._refresh_watchlist()

    def _fetch_watchlist(self, symbols):
        """Fetch data for multiple symbols in parallel using ThreadPoolExecutor."""
        def fetch_symbol_data(symbol):
            try:
                history = self.market.history(symbol)
                quote = self.market.quote(symbol)
                predictions = forecast(history)
                one_month = predictions[0]
                return {
                    "symbol": quote["symbol"],
                    "price": quote["price"],
                    "currency": quote["currency"],
                    "change_pct": quote["change_pct"],
                    "forecast_pct": one_month.change_pct,
                    "signal": one_month.signal,
                    "confidence": one_month.confidence,
                }
            except Exception:
                return None
        
        rows = []
        # Parallelize with up to 16 workers to fetch multiple symbols concurrently
        with ThreadPoolExecutor(max_workers=16) as executor:
            results = executor.map(fetch_symbol_data, symbols)
            for result in results:
                if result is not None:
                    rows.append(result)
        
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
        # Don't auto-load the best symbol - let user choose which one to view

    def _watchlist_row_clicked(self, row, column):
        table = self.sender()
        if column == 0:
            # Favorite toggle
            symbol_item = table.item(row, 1)
            if symbol_item:
                self._toggle_favorite(symbol_item.text())
            return
        # Load stock detail
        symbol_item = table.item(row, 1)
        if symbol_item:
            self._load_symbol(symbol_item.text(), load_watchlist=False, show_detail=True)

    def _fetch_dashboard(self, symbol):
        history = self.market.history(symbol)
        try:
            articles = self.news.fetch(symbol, NEWS_LIMIT)
        except RuntimeError:
            articles = []
        return self.market.quote(symbol), indicators(history), forecast(history), self.market.dividend_info(symbol), articles

    def _present_dashboard(self, payload):
        """Update the detail view with dashboard data."""
        quote, frame, predictions, dividend, articles = payload
        self.current_quote = quote
        self.current_predictions = predictions
        self.current_dividend = dividend
        self.current_news = articles
        self.detail_view.error_label.hide()
        self.detail_view.test_buy_button.setEnabled(True)
        self.detail_view.test_budget.setSuffix(f" {quote['currency']}")
        self.detail_view.test_result.setText("Tutar ve süreyi seçip Hesapla düğmesine basın.")
        color = "#58d68d" if quote["change"] >= 0 else "#ed6a5a"
        self.detail_view.quote_label.setText(
            f"{quote['symbol']}   {quote['price']:.2f} {quote['currency']}   "
            f"<span style='color:{color}'>{quote['change']:+.2f} ({quote['change_pct']:+.2f}%)</span>"
        )
        self.detail_view.chart.plot(frame)
        latest = frame.iloc[-1]
        self.detail_view.rsi_card.value.setText(f"{latest['RSI']:.1f}")
        self.detail_view.macd_card.value.setText(f"{latest['MACD']:.3f}")
        self.detail_view.sma_card.value.setText(f"{latest['SMA20']:.2f}/{latest['SMA50']:.2f}")
        
        # Forecast table
        rows = []
        for item in predictions:
            action, usage = self._scenario_action(item)
            rows.append([item.horizon, f"{item.target_price:.2f}", f"{item.change_pct:+.2f}%", item.signal, item.confidence, action, usage])
        self.detail_view.forecast_table.load_rows(rows, ["Vade", "Tahmini Fiyat", "Potansiyel", "Sinyal", "Güven", "Aksiyon", "Kullanım"], color_columns=(2,))
        self.detail_view.forecast_table.fill_container()
        
        # Test months combo
        self.detail_view.test_months.clear()
        for item in predictions:
            action, _usage = self._scenario_action(item)
            months = int(item.horizon.split()[0])
            self.detail_view.test_months.addItem(f"{item.horizon} - {action}", months)
        
        # Geopolitical
        geopolitical = assess_news(articles)
        topics = ", ".join(geopolitical.matched_topics) if geopolitical.matched_topics else "belirgin konu yok"
        self.detail_view.geopolitical_label.setText(
            f"Jeopolitik senaryo: <b>Yükseliş %{geopolitical.up_probability}</b> | "
            f"<b>Düşüş %{geopolitical.down_probability}</b> | Risk: {geopolitical.risk_level}<br>"
            f"{geopolitical.summary} Konular: {topics}. "
            "Bu oranlar haber başlıklarından üretilen yaklaşık göstergelerdir; yatırım tavsiyesi değildir."
        )
        
        # Dividend info
        self.detail_view.dividend_label.setText(
            f"Yıllık hisse başı temettü: {dividend['annual_per_share']:.2f} {quote['currency']}<br>"
            f"Son 12 ay ödeme sayısı: {dividend['payment_count']}"
        )
        
        # News - will be presented separately
        # Recommendation for watchlist
        if self.watchlist_rows:
            for row in self.watchlist_rows:
                if row["symbol"] == quote["symbol"]:
                    self.recommendation_label.setText(
                        f"Veriye dayalı 1 ay senaryosunda tahmini getiri: {quote['symbol']} "
                        f"({row['forecast_pct']:+.2f}%, güven: {row['confidence']}). "
                        "Bu bir garanti veya yatırım tavsiyesi değildir; geçmiş fiyat verisine dayalı istatistiksel tahmindir."
                    )
                    break

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
            self.news_status.setText(f"{self.current_symbol} için haber bulunamadı.")
            self.news_splitter.hide()
            self.news_empty_state.show()
            if hasattr(self, "detail_view"):
                self.detail_view.news_browser.setText("Bu sembol için haber bulunamadı.")
            return

        self.news_status.setText(f"📰 {self.current_symbol} Güncel Blog ve Haber Akışı ({len(articles)} haber)")
        
        cards_html = []
        for i, item in enumerate(articles):
            source = item.get("source", "Finans Haber")
            date_str = item.get("published", "")
            title = item.get("title", "")
            summary = item.get("summary", "")
            link = item.get("link", "#")
            badge_color = "#1e3a5f" if i % 2 == 0 else "#2a2238"
            badge_text_color = "#5dade2" if i % 2 == 0 else "#bb86fc"
            badge_name = "PİYASA HABERİ" if i % 2 == 0 else "GELİŞME"

            card = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 12px; background-color: #121c27; border: 1px solid #233446; border-radius: 6px;">
                <tr>
                    <td style="padding: 12px 14px;">
                        <table width="100%" cellpadding="0" cellspacing="0">
                            <tr>
                                <td>
                                    <span style="background-color: {badge_color}; color: {badge_text_color}; font-size: 10px; font-weight: bold; padding: 2px 6px;">{badge_name}</span>
                                    &nbsp;
                                    <span style="background-color: #1a2736; color: #8fa0b5; font-size: 11px; padding: 2px 6px;">📰 {source}</span>
                                </td>
                                <td align="right">
                                    <span style="color: #65778a; font-size: 11px;">📅 {date_str}</span>
                                </td>
                            </tr>
                        </table>
                        <div style="margin-top: 8px; margin-bottom: 6px;">
                            <a href="{link}" style="text-decoration: none; color: #58d68d; font-size: 13px; font-weight: bold;">
                                {title}
                            </a>
                        </div>
                        <div style="color: #b0c0d0; font-size: 12px; line-height: 1.4; margin-bottom: 8px;">
                            {summary}
                        </div>
                        <div align="right">
                            <a href="{link}" style="text-decoration: none; color: #3d91ed; font-size: 11px; font-weight: bold;">
                                Haberi Oku ➔
                            </a>
                        </div>
                    </td>
                </tr>
            </table>
            """
            cards_html.append(card)

        full_html = f"""
        <div style="padding: 4px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            {"".join(cards_html)}
        </div>
        """
        self.news_browser.setHtml(full_html)
        self.news_empty_state.hide()
        self.news_splitter.show()
        if hasattr(self, "detail_view"):
            self.detail_view.news_browser.setHtml(full_html)

    def _show_news_detail(self, url):
        link = url.toString()
        article = next((item for item in self.current_news if item.get("link") == link), None)
        if not article:
            return
        source = article.get("source", "Haber Kaynağı")
        published = article.get("published", "")
        title = article.get("title", "")
        summary = article.get("summary", "Detay bulunamadı.")
        
        detail_html = f"""
        <div style="padding: 16px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0d151e; color: #d0dbe5;">
            <div style="margin-bottom: 12px;">
                <span style="background-color: #1e3a5f; color: #5dade2; font-size: 11px; font-weight: bold; padding: 3px 8px;">HABER DETAYI</span>
                &nbsp;
                <span style="background-color: #1a2736; color: #9aa7b8; font-size: 11px; padding: 3px 8px;">🏛️ {source}</span>
                &nbsp;
                <span style="color: #768b9e; font-size: 11px;">🕒 {published}</span>
            </div>
            
            <h2 style="color: #ffffff; font-size: 16px; font-weight: bold; line-height: 1.3; margin-top: 0; margin-bottom: 12px; border-bottom: 1px solid #233446; padding-bottom: 10px;">
                {title}
            </h2>
            
            <div style="font-size: 13px; line-height: 1.6; color: #c4d4e3; margin-bottom: 20px; background-color: #121c27; padding: 14px; border: 1px solid #223347; border-radius: 4px;">
                <p style="margin: 0;">{summary}</p>
            </div>
            
            <div style="margin-top: 20px; padding-top: 10px; border-top: 1px solid #1c2b3a;">
                <p style="font-size: 12px; color: #8fa0b5; margin-bottom: 10px;">Haberi orijinal web sitesinde okumak için aşağıdaki bağlantıya tıklayabilirsiniz:</p>
                <table cellpadding="0" cellspacing="0">
                    <tr>
                        <td style="background-color: #2878d0; padding: 8px 16px; border-radius: 4px;">
                            <a href="{article['link']}" style="color: #ffffff; text-decoration: none; font-weight: bold; font-size: 12px;">
                                🌐 Orijinal Kaynakta Aç ({source}) ↗
                            </a>
                        </td>
                    </tr>
                </table>
            </div>
        </div>
        """
        self.news_detail.setHtml(detail_html)
        if hasattr(self, "detail_view"):
            self.detail_view.news_detail.setHtml(detail_html)

    def _present_financials(self, tables):
        # Update detail view financial tab only (main window financial tab guides user to select a stock)
        if hasattr(self, "detail_view"):
            self.detail_view.financial_tables.clear()
            self.detail_view.financial_empty_label.setVisible(not tables)
            if tables:
                for name, frame in tables.items():
                    table = ResultTable()
                    if frame.empty:
                        table.load_rows([], ["Kalem"])
                    else:
                        rows = [[index] + [value if value == value else "-" for value in row] for index, row in frame.head(30).iterrows()]
                        table.load_rows(rows, ["Kalem"] + [str(column)[:10] for column in frame.columns])
                    self.detail_view.financial_tables.addTab(table, name)

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
        
        # Show error in detail view if it's currently visible
        stacked = self.tabs.widget(0)
        if isinstance(stacked, QStackedWidget) and stacked.currentIndex() == 1:
            self.detail_view.set_error(message)
        
        # Show error for dividend tab if active
        if self.tabs.currentIndex() == 1 and hasattr(self, "dividend_status"):
            self.dividend_status.setText("Veri alınamadı. Yeniden denemek için listeyi tekrar yükleyin.")

    def closeEvent(self, event):
        for worker in self.workers:
            worker.requestInterruption()
            worker.quit()
            worker.wait(1500)
        event.accept()
