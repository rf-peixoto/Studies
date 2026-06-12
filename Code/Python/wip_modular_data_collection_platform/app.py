"""Entry point.

    python app.py            # development server on http://127.0.0.1:5000
    gunicorn 'app:app'       # production (behind an HTTPS reverse proxy)
"""
from core import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
