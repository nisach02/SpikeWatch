import sys
import asyncio
import requests
import websockets
import json
import threading

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QVBoxLayout, QWidget,
    QLabel, QLineEdit, QPushButton, QComboBox, QHBoxLayout
)
from PyQt5.QtCore import pyqtSignal, QObject


class SignalEmitter(QObject):
    log_signal = pyqtSignal(str)


class PriceSpikeApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🚨 Binance Futures Spike Monitor")
        self.setGeometry(200, 200, 1000, 650)

        self.signals = SignalEmitter()
        self.signals.log_signal.connect(self.append_log)

        # Layout components
        self.text_box = QTextEdit()
        self.text_box.setReadOnly(True)

        self.percent_input = QLineEdit("5")
        self.timeframe_select = QComboBox()
        self.timeframe_select.addItems(["1m", "3m", "5m"])

        self.start_button = QPushButton("Start Monitoring")
        self.start_button.clicked.connect(self.start_monitoring)

        # Layout setup
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("Threshold (%)"))
        controls_layout.addWidget(self.percent_input)
        controls_layout.addWidget(QLabel("Timeframe"))
        controls_layout.addWidget(self.timeframe_select)
        controls_layout.addWidget(self.start_button)

        layout = QVBoxLayout()
        layout.addLayout(controls_layout)
        layout.addWidget(self.text_box)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # For stopping and restarting threads
        self.monitor_thread = None

    def append_log(self, message):
        self.text_box.append(message)

    def get_usdt_futures_symbols(self):
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url)
        symbols = []
        for s in response.json()['symbols']:
            if s['quoteAsset'] == 'USDT' and s['contractType'] == 'PERPETUAL' and s['status'] == 'TRADING':
                symbols.append(s['symbol'].lower())
        return symbols

    def start_monitoring(self):
        threshold = float(self.percent_input.text())
        timeframe = self.timeframe_select.currentText()

        self.append_log(f"⚙️ Starting monitoring with threshold: {threshold}% and timeframe: {timeframe}")
        if self.monitor_thread is not None:
            self.append_log("🔁 Restarting monitoring...")

        self.monitor_thread = threading.Thread(
            target=self.start_async_monitoring, args=(threshold, timeframe), daemon=True
        )
        self.monitor_thread.start()

    def start_async_monitoring(self, threshold, timeframe):
        symbols = self.get_usdt_futures_symbols()
        self.signals.log_signal.emit(f"✅ Tracking {len(symbols)} USDT perpetual futures pairs...\n")
        asyncio.run(self.monitor_price_jumps(symbols, threshold, timeframe))

    async def monitor_price_jumps(self, symbols, threshold, timeframe):
        streams = '/'.join([f"{s}@kline_{timeframe}" for s in symbols])
        uri = f"wss://fstream.binance.com/stream?streams={streams}"

        try:
            async with websockets.connect(uri, max_size=None) as ws:
                self.signals.log_signal.emit("🟢 Connected to Binance Futures WebSocket.\n")

                while True:
                    try:
                        msg = await ws.recv()
                        data = json.loads(msg)

                        if 'data' in data:
                            kline = data['data']['k']
                            symbol = kline['s']
                            is_closed = kline['x']

                            if is_closed:
                                open_price = float(kline['o'])
                                close_price = float(kline['c'])
                                percent_change = ((close_price - open_price) / open_price) * 100

                                if percent_change >= threshold:
                                    alert = f"🚨 {symbol} | {timeframe}: {percent_change:.2f}% | O: {open_price}, C: {close_price}"
                                    self.signals.log_signal.emit(alert)
                    except Exception as e:
                        self.signals.log_signal.emit(f"❌ Error: {str(e)}")
                        await asyncio.sleep(5)
        except Exception as e:
            self.signals.log_signal.emit(f"❌ WebSocket connection failed: {str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PriceSpikeApp()
    window.show()
    sys.exit(app.exec_())
