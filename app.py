# Render deployment entry point — imports Flask app from main.py
from main import app

if __name__ == "__main__":
    app.run()
