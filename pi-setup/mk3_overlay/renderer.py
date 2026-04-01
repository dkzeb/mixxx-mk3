"""Qt overlay window and QPainter rendering for the MK3 widget system."""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QColor, QFont, QPen

from .widget import ActionItem, ToggleItem, InfoItem

# Color palette (matches MK3 skin aesthetic)
BG = QColor(0x0d, 0x0d, 0x1a)
TAB_BAR_BG = QColor(0x11, 0x11, 0x22)
TAB_ACTIVE = QColor(0xe6, 0x7e, 0x22)
TAB_INACTIVE = QColor(0x55, 0x55, 0x55)
ITEM_TEXT = QColor(0xaa, 0xaa, 0xaa)
ITEM_TEXT_HL = QColor(0xff, 0xff, 0xff)
ITEM_BG_HL = QColor(0x1a, 0x1a, 0x2e)
ACCENT = QColor(0xe6, 0x7e, 0x22)
INFO_TEXT = QColor(0x55, 0x55, 0x55)
TOGGLE_ON_BG = QColor(0xe6, 0x7e, 0x22)
TOGGLE_OFF_BG = QColor(0x33, 0x33, 0x33)
TOGGLE_ON_TEXT = QColor(0xff, 0xff, 0xff)
TOGGLE_OFF_TEXT = QColor(0x88, 0x88, 0x88)
CONFIRM_BG = QColor(0x2a, 0x1a, 0x1a)
CONFIRM_TEXT = QColor(0xe7, 0x4c, 0x3c)
CONFIRM_BORDER = QColor(0xe7, 0x4c, 0x3c)
CHEVRON_COLOR = QColor(0x55, 0x55, 0x55)
CHEVRON_HL = QColor(0xe6, 0x7e, 0x22)

TAB_HEIGHT = 28
ITEM_HEIGHT = 26
ACCENT_WIDTH = 3
TOGGLE_WIDTH = 50
CHEVRON_WIDTH = 40
PADDING_LEFT = 12
PADDING_RIGHT = 12


class OverlayWindow(QWidget):
    """Frameless Qt window that renders a widget's current page."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._widget = None
        self._font = QFont("Sans", 10)
        self._font_bold = QFont("Sans", 10)
        self._font_bold.setBold(True)
        self._font_small = QFont("Sans", 8)
        self._font_tab = QFont("Sans", 9)
        self._font_tab_bold = QFont("Sans", 9)
        self._font_tab_bold.setBold(True)

    def set_widget(self, widget):
        """Attach a widget and position/size the window."""
        self._widget = widget
        x, y, w, h = widget.position
        self.move(x, y)
        self.resize(w, h)

    def paintEvent(self, event):
        if not self._widget:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w = self.width()
        h = self.height()
        p.fillRect(0, 0, w, h, BG)
        self._paint_tabs(p, w)
        self._paint_items(p, w, h)
        p.end()

    def _paint_tabs(self, p, w):
        p.fillRect(0, 0, w, TAB_HEIGHT, TAB_BAR_BG)
        num_pages = len(self._widget.pages)
        if num_pages == 0:
            return
        tab_w = w // max(num_pages, 1)
        for i, page in enumerate(self._widget.pages):
            x = i * tab_w
            is_active = (i == self._widget.current_page)
            if is_active:
                p.setPen(TAB_ACTIVE)
                p.setFont(self._font_tab_bold)
                p.fillRect(x, TAB_HEIGHT - 2, tab_w, 2, TAB_ACTIVE)
            else:
                p.setPen(TAB_INACTIVE)
                p.setFont(self._font_tab)
            rect = QRect(x, 0, tab_w, TAB_HEIGHT)
            p.drawText(rect, Qt.AlignCenter, page.title)

    def _paint_items(self, p, w, h):
        page = self._widget.page
        y = TAB_HEIGHT
        for i, item in enumerate(page.items):
            is_hl = (i == self._widget.cursor)
            is_confirming = is_hl and self._widget.confirming
            item_rect = QRect(0, y, w, ITEM_HEIGHT)
            if is_confirming:
                self._paint_confirm_row(p, item_rect)
            elif is_hl:
                self._paint_highlighted_row(p, item_rect, item)
            else:
                self._paint_normal_row(p, item_rect, item)
            y += ITEM_HEIGHT

    def _paint_normal_row(self, p, rect, item):
        if isinstance(item, InfoItem):
            self._paint_info_row(p, rect, item, highlighted=False)
            return
        p.setFont(self._font)
        p.setPen(ITEM_TEXT)
        label_rect = QRect(rect.x() + PADDING_LEFT, rect.y(),
                           rect.width() - PADDING_LEFT - PADDING_RIGHT, rect.height())
        if isinstance(item, ToggleItem):
            label_rect.setWidth(label_rect.width() - TOGGLE_WIDTH)
            p.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, item.label)
            self._paint_toggle(p, rect, item.state)
        elif isinstance(item, ActionItem):
            label_rect.setWidth(label_rect.width() - CHEVRON_WIDTH)
            p.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, item.label)
            chev_rect = QRect(rect.right() - CHEVRON_WIDTH, rect.y(),
                              CHEVRON_WIDTH, rect.height())
            p.setPen(CHEVRON_COLOR)
            p.drawText(chev_rect, Qt.AlignCenter, "\u203a")

    def _paint_highlighted_row(self, p, rect, item):
        p.fillRect(rect, ITEM_BG_HL)
        p.fillRect(rect.x(), rect.y(), ACCENT_WIDTH, rect.height(), ACCENT)
        if isinstance(item, InfoItem):
            self._paint_info_row(p, rect, item, highlighted=True)
            return
        p.setFont(self._font_bold)
        p.setPen(ITEM_TEXT_HL)
        label_rect = QRect(rect.x() + PADDING_LEFT, rect.y(),
                           rect.width() - PADDING_LEFT - PADDING_RIGHT, rect.height())
        if isinstance(item, ToggleItem):
            label_rect.setWidth(label_rect.width() - TOGGLE_WIDTH)
            p.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, item.label)
            self._paint_toggle(p, rect, item.state)
        elif isinstance(item, ActionItem):
            label_rect.setWidth(label_rect.width() - CHEVRON_WIDTH)
            p.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, item.label)
            chev_rect = QRect(rect.right() - CHEVRON_WIDTH, rect.y(),
                              CHEVRON_WIDTH, rect.height())
            p.setPen(CHEVRON_HL)
            p.drawText(chev_rect, Qt.AlignCenter, "\u203a")

    def _paint_info_row(self, p, rect, item, highlighted=False):
        p.setFont(self._font)
        p.setPen(INFO_TEXT)
        label_rect = QRect(rect.x() + PADDING_LEFT, rect.y(),
                           rect.width() // 2 - PADDING_LEFT, rect.height())
        p.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, item.label)
        value = item.get_value()
        if value:
            value_rect = QRect(rect.width() // 2, rect.y(),
                               rect.width() // 2 - PADDING_RIGHT, rect.height())
            p.drawText(value_rect, Qt.AlignRight | Qt.AlignVCenter, value)

    def _paint_confirm_row(self, p, rect):
        p.fillRect(rect, CONFIRM_BG)
        p.fillRect(rect.x(), rect.y(), ACCENT_WIDTH, rect.height(), CONFIRM_BORDER)
        p.setFont(self._font_bold)
        p.setPen(CONFIRM_TEXT)
        text_rect = QRect(rect.x() + PADDING_LEFT, rect.y(),
                          rect.width() - PADDING_LEFT - PADDING_RIGHT, rect.height())
        p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter,
                   "Are you sure? Push to confirm")

    def _paint_toggle(self, p, rect, state):
        pill_w = 40
        pill_h = 16
        pill_x = rect.right() - TOGGLE_WIDTH + (TOGGLE_WIDTH - pill_w) // 2
        pill_y = rect.y() + (rect.height() - pill_h) // 2
        bg = TOGGLE_ON_BG if state else TOGGLE_OFF_BG
        text_color = TOGGLE_ON_TEXT if state else TOGGLE_OFF_TEXT
        text = "ON" if state else "OFF"
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(pill_x, pill_y, pill_w, pill_h, 8, 8)
        p.setPen(text_color)
        p.setFont(self._font_small)
        p.drawText(QRect(pill_x, pill_y, pill_w, pill_h), Qt.AlignCenter, text)
