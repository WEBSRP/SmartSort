"""Tiny native startup panel and existing-window activation helpers."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from src.gui.theme import DARK, LIGHT


class StartupSplash(QSplashScreen):
    """One static 300×104 panel: no timer, animation, external asset or delay."""

    def __init__(self, theme='system'):
        app = QApplication.instance()
        if theme == 'dark':
            colors = DARK
        elif theme == 'light':
            colors = LIGHT
        else:
            colors = DARK if app.palette().color(app.palette().ColorRole.Window).lightness() < 128 else LIGHT
        screen = app.primaryScreen()
        ratio = screen.devicePixelRatio() if screen else 1.0
        pixmap = QPixmap(round(300 * ratio), round(104 * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(colors['border']))
        painter.setBrush(QColor(colors['surface']))
        painter.drawRoundedRect(QRectF(.5, .5, 299, 103), 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors['tint']))
        painter.drawRoundedRect(QRectF(20, 30, 44, 44), 10, 10)
        font = QFont('DejaVu Sans', 18)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(colors['accent']))
        painter.drawText(QRectF(20, 30, 44, 44), Qt.AlignmentFlag.AlignCenter, 'S')
        font.setPointSize(13)
        painter.setFont(font)
        painter.setPen(QColor(colors['text']))
        painter.drawText(QRectF(80, 27, 204, 25), Qt.AlignmentFlag.AlignVCenter, 'SmartSort')
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(colors['muted']))
        painter.drawText(QRectF(80, 52, 204, 24), Qt.AlignmentFlag.AlignVCenter, 'Starting SmartSort…')
        painter.end()
        super().__init__(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAccessibleName('Starting SmartSort')
        self.setAccessibleDescription('Starting SmartSort…')

    def finish(self, window):
        # QSplashScreen.finish waits for exposure, which may never happen for a
        # hidden/tray window. Startup owns readiness; closing never adds a wait.
        self.close()


def activate_dashboard(window):
    """Restore the existing dashboard; focus policy is ultimately desktop-owned."""
    window.show_tab(0)
    window.showNormal()
    window.raise_()
    window.activateWindow()
