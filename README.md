# Miner Dashboard (Raspberry Pi)

Stabilny i deterministyczny dashboard do monitorowania koparek Bitaxe,
uruchamiany lokalnie na Raspberry Pi (Raspbian).

Projekt powstał z myślą o:
- pełnej kontroli lokalnej (LAN),
- braku zależności od zewnętrznych API (CoinGecko, mempool itp.),
- stabilnym działaniu 24/7,
- czytelnej wizualizacji stanu koparek.

---

## 🚀 Features

- Flask + Gunicorn (backend)
- Worker w Pythonie (zbieranie danych z koparek)
- Web dashboard (LAN)
- Deterministyczna animacja „coin rain” oparta wyłącznie o wzrost shares
- Brak fetchy zewnętrznych (offline-safe)
- Jedna pętla odświeżania (co 10 sekund)
- Konfiguracja przez plik `config.yaml`

---

## 🧱 Architektura

- Backend: Flask + Gunicorn
- Worker: `worker.py`
- Baza danych: SQLite
- Frontend: Vanilla JS + CSS
- Środowisko: Python venv

---

## 📂 Struktura projektu

miner-dashboard/

├── app/

│ ├── static/

│ │ ├── app.js

│ │ └── styles.css

│ └── templates/

│ ├── base.html

│ ├── dashboard.html

│ └── dashboard_pro.html

├── worker.py

├── wsgi.py

├── config.example.yaml

├── requirements.txt

├── README.md

└── .gitignore

---

## ⚙️ Instalacja (Raspberry Pi)

```bash
git clone https://github.com/TheSagittarius2305/miner-dashboard.git
cd miner-dashboard

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
cp config.example.yaml config.yaml
Uzupełnij config.yaml swoimi danymi koparek.

▶️ Uruchomienie
bash
Skopiuj kod
.venv/bin/gunicorn -b 0.0.0.0:8000 wsgi:app --workers 1 --threads 4 --timeout 60
bash
Skopiuj kod
.venv/bin/python worker.py
Dashboard dostępny w przeglądarce:

cpp
Skopiuj kod
http://<IP_RASPBERRY>:8000
🪙 Coin Rain – jak działa
Animacja pojawia się tylko gdy wzrasta shares_accepted

Brak losowości czasowej

Brak limitu monet – 1:1 względem nowych shares

Jedno odświeżenie = jedna decyzja

🔒 Bezpieczeństwo
config.yaml nie jest wersjonowany

Brak tokenów API w repozytorium

Projekt przeznaczony do użytku lokalnego (LAN)

📝 Uwagi
Projekt nastawiony na stabilność, nie eksperymenty

Idealny do pracy ciągłej 24/7 na Raspberry Pi

Kod celowo prosty i czytelny

