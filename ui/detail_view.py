"""Stock detail view widget for PiyasaRadar."""
# pyrefly: ignore [missing-import]
from PyQt5.QtCore import Qt, pyqtSignal
# pyrefly: ignore [missing-import]
from PyQt5.QtGui import QColor, QBrush
# pyrefly: ignore [missing-import]
from PyQt5.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QTabWidget, QTextBrowser, QVBoxLayout, QWidget
)

from ui.widgets import ChartCanvas, ResultTable, EmptyStateWidget


class IndicatorCard(QFrame):
    """Small card widget for displaying a technical indicator."""
    def __init__(self, label_text: str, value_text: str, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setStyleSheet("QFrame { background: #0f171f; border: 1px solid #29384a; border-radius: 4px; padding: 10px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        
        self.label = QLabel(label_text)
        self.label.setStyleSheet("font-size: 11px; color: #9aa7b8; font-weight: 500;")
        self.value = QLabel(value_text)
        self.value.setStyleSheet("font-size: 16px; color: #e9eef5; font-weight: 600;")
        
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addStretch()


class StockDetailView(QWidget):
    """Detailed view for a single stock with chart, indicators, forecast, and trading simulation."""
    
    back_clicked = pyqtSignal()  # Signal emitted when "Back" button clicked
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
    
    def _build_ui(self):
        """Build the detail view UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        
        # Header: Back button, symbol, price, change
        header = QHBoxLayout()
        self.back_button = QPushButton("< Listeye dön")
        self.back_button.setMaximumWidth(120)
        self.back_button.clicked.connect(self.back_clicked.emit)
        header.addWidget(self.back_button)
        
        self.quote_label = QLabel("Veri yükleniyor...")
        self.quote_label.setStyleSheet("font-size: 22px; font-weight: 700; padding: 4px 0;")
        header.addWidget(self.quote_label, 1)
        
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setMaximumHeight(44)
        self.error_label.setStyleSheet("color: #ffb4ab; background: #3a1d24; padding: 6px; border-radius: 4px;")
        self.error_label.hide()
        
        layout.addLayout(header)
        layout.addWidget(self.error_label)
        
        # Main content tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        
        # Overview tab
        overview_page = self._build_overview_tab()
        self.tabs.addTab(overview_page, "Genel Bakış")
        
        # Financial tab
        self.financial_tables = QTabWidget()
        self.financial_empty_label = EmptyStateWidget("📄", "Henüz veri yok", "Bir hisse seçildiğinde finansal tablolar burada yüklenir.")
        financial_page = QWidget()
        financial_layout = QVBoxLayout(financial_page)
        financial_layout.addWidget(self.financial_tables)
        financial_layout.addWidget(self.financial_empty_label)
        self.tabs.addTab(financial_page, "Finansallar")
        
        # News tab
        self.news_browser = QTextBrowser()
        self.news_browser.setPlaceholderText("Bir hisse seçildiğinde haberler burada yüklenir.")
        self.news_browser.setOpenExternalLinks(False)
        # Signal connection is handled in main_window.py
        
        news_page = QWidget()
        news_layout = QVBoxLayout(news_page)
        news_layout.addWidget(self.news_browser, 1)
        
        self.news_detail = QTextBrowser()
        self.news_detail.setOpenExternalLinks(True)
        self.news_detail.setPlaceholderText("Detayını görmek için bir habere tıklayın.")
        news_layout.addWidget(self.news_detail, 1)
        self.tabs.addTab(news_page, "Haber Akışı")
        
        layout.addWidget(self.tabs, 1)
    
    def _build_overview_tab(self) -> QWidget:
        """Build the overview tab with chart, indicators, forecast, and test trading."""
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Left side: Chart and forecast
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 6, 0)
        
        chart_group = QGroupBox("Fiyat ve Hareketli Ortalamalar")
        chart_layout = QVBoxLayout(chart_group)
        self.chart = ChartCanvas()
        chart_layout.addWidget(self.chart)
        left_layout.addWidget(chart_group, 2)
        
        # Technical indicators - card style
        indicators_group = QGroupBox("Teknik Göstergeler")
        indicators_layout = QHBoxLayout(indicators_group)
        
        self.rsi_card = IndicatorCard("RSI(14)", "-")
        self.macd_card = IndicatorCard("MACD", "-")
        self.sma_card = IndicatorCard("SMA20/50", "-")
        
        indicators_layout.addWidget(self.rsi_card)
        indicators_layout.addWidget(self.macd_card)
        indicators_layout.addWidget(self.sma_card)
        left_layout.addWidget(indicators_group)
        
        forecast_group = QGroupBox("İstatistiksel Öngörü (yatırım tavsiyesi değildir)")
        forecast_layout = QVBoxLayout(forecast_group)
        self.forecast_table = ResultTable(empty_icon="📈", empty_title="Henüz tahmin yok", empty_subtitle="Seçili hissenin tahminleri burada listelenir")
        self.forecast_table.fill_container()
        forecast_layout.addWidget(self.forecast_table)
        left_layout.addWidget(forecast_group, 2)
        
        layout.addWidget(left_panel, 3)
        
        # Right side: Geopolitical, Test trading
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.geopolitical_label = QLabel("Jeopolitik risk verisi yükleniyor...")
        self.geopolitical_label.setWordWrap(True)
        self.geopolitical_label.setStyleSheet("color: #b8c7d9; background: #18212c; padding: 7px; border-radius: 4px;")
        right_layout.addWidget(self.geopolitical_label)
        
        # Dividend info
        dividend_group = QGroupBox("Temettü Bilgisi")
        dividend_layout = QVBoxLayout(dividend_group)
        self.dividend_label = QLabel("Yükleniyor...")
        self.dividend_label.setWordWrap(True)
        dividend_layout.addWidget(self.dividend_label)
        right_layout.addWidget(dividend_group)
        
        # Test trading
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
        order_layout.addWidget(self.test_buy_button)
        self.test_result = QLabel("Bir hisse seçip tutar ve süre girin.")
        self.test_result.setWordWrap(True)
        self.test_result.setStyleSheet("color: #b8c7d9; padding-top: 8px;")
        order_layout.addWidget(self.test_result)
        order_layout.addWidget(QLabel("Simülasyon geçmişi"))
        self.simulation_table = ResultTable(empty_icon="📊", empty_title="İşlem geçmişi boş", empty_subtitle="Hesapla butonuna basarak test yapın")
        self.simulation_table.setMaximumHeight(150)
        order_layout.addWidget(self.simulation_table)
        right_layout.addWidget(order_panel)
        
        right_layout.addStretch()
        layout.addWidget(right_panel, 1)
        
        return page
    
    def set_loading(self, message: str = "Yükleniyor..."):
        """Show loading state."""
        self.quote_label.setText(message)
        self.error_label.hide()
    
    def set_error(self, message: str):
        """Show error state."""
        self.error_label.setText(f"Veri alınamadı: {message}")
        self.error_label.show()
