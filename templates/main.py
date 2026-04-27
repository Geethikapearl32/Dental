import threading
import webview
from app import app

def run_flask():
    app.run(port=5000, debug=False)

if __name__ == '__main__':
    # Start Flask in background
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    # Open app in desktop window (NO browser)
    webview.create_window(
        "Dental Clinic Software",
        "http://127.0.0.1:5000",
        width=1200,
        height=800
    )

    webview.start()