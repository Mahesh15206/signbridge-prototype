# SignBridge — Prototype

SignBridge translates text and STEM formulas into real-time 3D Sign Language avatar animations with interactive learning and gesture recognition.

## 🚀 How to Run the Prototype

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file in the root directory:
```env
GROQ_API_KEY=your_groq_api_key_here
PORT=5000
```

### 3. Start the Server
```bash
python main.py
```
Or using Gunicorn:
```bash
gunicorn main:app
```

### 4. Open in Browser
Visit `http://127.0.0.1:5000` in your web browser.

---

## 📂 Project Structure
- `main.py` — Core Flask server & STEM sign translation pipeline
- `app.py` — WSGI application entry point
- `words.txt` — Supported sign vocabulary index
- `templates/` — HTML interface templates
- `static/` — 3D WebGL avatar engine, styles, and gesture files
- `utils/` — Multi-format text extraction utilities
