# config.py

# ===== Биржа =====
EXCHANGE = "okx"       # bybit / okx
API_KEY = "e08cd9d4-39ec-41f2-8b77-1e7d26d5edc7"
API_SECRET = "E3A8156DD5B06AE004EDFEB83AB405BF"

# ===== Telegram =====
TELEGRAM_BOT_TOKEN = "8390507219:AAEa_sWTg5VajSsbgxiYZOOHoCUz_2D4oOU"
TELEGRAM_CHAT_ID = "@tredd001bot"

# ===== Настройки стратегии =====
TOP_N = 50                     # сколько монет сканировать
TIMEFRAMES = ["15m","1h"]      # короткий и длинный таймфрейм
MIN_CONFIDENCE = 65            # минимальная уверенность для сигнала
SIGNAL_COOLDOWN_HOURS = 6      # сколько часов ждать до повторного сигнала
PRICE_RESEND_THRESHOLD_PCT = 1.5  # минимальное изменение цены для повторного сигнала

# ===== Режим теста =====
PAPER_MODE = True              # True = только консоль, не отправляет в Telegram
SCAN_INTERVAL = 300            # интервал сканирования в секундах
