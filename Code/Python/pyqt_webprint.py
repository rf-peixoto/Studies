# pip install PyQt5==5.15.7 PyQtWebEngine==5.15.7

import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QTimer, QUrl, Qt
from PyQt5.QtGui import QImage, QPainter

def capture_webpage(url, output_file):
    app = QApplication(sys.argv)

    # Create a QWebEngineView and load the webpage
    web = QWebEngineView()

    # Show the widget off-screen to ensure it initializes properly
    web.show()
    web.resize(1024, 768)  # Set a default size

    web.loadFinished.connect(lambda ok: on_load_finished(ok, web, output_file))
    web.load(QUrl(url))

    # Start the event loop
    app.exec_()

def on_load_finished(ok, web, output_file):
    if ok:
        # Give the page time to render dynamic content
        QTimer.singleShot(1000, lambda: render_page(web, output_file))
    else:
        print("Failed to load the web page.")
        QApplication.quit()

def render_page(web, output_file):
    # Ensure the widget is updated
    web.page().runJavaScript("document.body.scrollHeight;", lambda height: render_callback(height, web, output_file))

def render_callback(height, web, output_file):
    # Resize the widget to the full page height
    height = int(height)
    web.resize(web.width(), height)

    # Process events to update the widget
    QApplication.processEvents()

    # Render the page into an image
    image = QImage(web.size(), QImage.Format_ARGB32)
    image.fill(Qt.transparent)

    painter = QPainter(image)
    web.render(painter)
    painter.end()

    # Save the image
    image.save(output_file)
    print(f"Screenshot saved to {output_file}")
    QApplication.quit()

if __name__ == '__main__':
    url = 'https://www.duckduckgo.com'  # Replace with your target URL

    # Set the output file path to save in the current directory
    current_directory = os.getcwd()
    output_file = os.path.join(current_directory, 'screenshot.png')
    print(f"Saving screenshot to: {output_file}")

    capture_webpage(url, output_file)
