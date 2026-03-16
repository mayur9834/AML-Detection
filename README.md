# AML Detection Dashboard

A graph-based Anti-Money Laundering (AML) detection system built with FastAPI, NetworkX, and Plotly. It models financial transactions as a directed graph and applies multiple pattern-detection algorithms to flag suspicious accounts and transaction flows.

---

## What It Does

Financial transactions are represented as a **directed multigraph** — accounts are nodes, transactions are edges. This structure makes it possible to detect laundering patterns that are invisible in a flat table:

| Detector | Pattern | How It Works |
|---|---|---|
| **Fan-Out** | Smurfing / Dispersal | Accounts sending to many unique receivers (high out-degree) |
| **Fan-In** | Aggregation | Accounts receiving from many unique senders (high in-degree) |
| **Circular** | Round-tripping | Short cycles where money flows back to the origin |
| **Layering** | Chain obscuration | Long multi-hop paths used to hide the money trail |
| **Velocity** | Rapid transactions | Accounts making many transactions within a 24-hour window |

---

## Demo

![Dashboard Overview](https://i.imgur.com/placeholder.png)

> Default view loads automatically. Click **Run Analysis** to execute all detectors. Upload any IBM-format CSV to see a full separate analysis for that file.

---

## Dataset

This project uses the **IBM Transactions for Anti-Money Laundering (AML)** dataset — specifically the `HI-Small_Trans.csv` file (High Illicit ratio, Small accounts pattern).

- Download from Kaggle: https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml
- Place the file at: `datasets/HI-Small_Trans.csv`

**CSV columns used:**

| Column | Description |
|---|---|
| `Timestamp` | Transaction date/time (`YYYY/MM/DD HH:MM`) |
| `From Bank` + `Account` | Sender (combined into unique ID) |
| `To Bank` + `Account` | Receiver (combined into unique ID) |
| `Amount Paid` | Transaction value |
| `Payment Format` | Wire / Cheque / ACH / etc. |
| `Is Laundering` | Ground truth label (0 = clean, 1 = suspicious) |

---

## Project Structure

```
credit-risk/
├── main.py              # FastAPI app — endpoints and frontend serving
├── config.py            # Thresholds and dataset path
├── data_loader.py       # CSV loading and column normalisation
├── graph_builder.py     # Builds NetworkX MultiDiGraph from DataFrame
├── aml_detection.py     # All five AML detectors + run_all_detectors()
├── templates/
│   └── index.html       # Single-page dashboard (Bootstrap + Plotly.js)
├── datasets/
│   └── HI-Small_Trans.csv   ← place dataset here (not included)
└── requirements.txt
```

---

## Setup

**1. Clone the repository**
```bash
git clone https://github.com/mayur9834/aml-detection.git
cd aml-detection
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Add the dataset**

Download `HI-Small_Trans.csv` from the Kaggle link above and place it at:
```
datasets/HI-Small_Trans.csv
```

**5. Run the server**
```bash
uvicorn main:app --port 8000 --reload
```

Open **http://localhost:8000** in your browser.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Dashboard frontend |
| `GET` | `/stats` | Dataset statistics + chart data |
| `GET` | `/analyze` | Run all AML detectors on the pre-loaded dataset |
| `POST` | `/upload` | Upload any IBM-format CSV and get full analysis |
| `GET` | `/docs` | Interactive Swagger API documentation |

---

## How the Graph Is Built

Each row in the CSV becomes a directed edge in a `MultiDiGraph`:

```
Account A ──$1,249 (Wire)──► Account B
Account B ──$800   (ACH)───► Account C
Account C ──$500   (Wire)──► Account A   ← cycle detected
```

`MultiDiGraph` is used (not plain `DiGraph`) so that multiple transactions between the same account pair are each preserved as a separate edge — important for velocity and circular detection.

Account IDs are constructed as `BankCode_AccountNumber` to ensure global uniqueness across banks:
```
Bank 11, Account 8000ABC → node "11_8000ABC"
```

---

## Detection Thresholds

All thresholds are configurable in `config.py`:

```python
FAN_OUT_THRESHOLD       = 5   # out-degree to flag as fan-out
FAN_IN_THRESHOLD        = 5   # in-degree to flag as fan-in
VELOCITY_THRESHOLD      = 10  # max transactions per 24h window
LAYERING_MIN_CHAIN_LENGTH = 3 # minimum hops to flag as layering
LAYERING_CUTOFF_DEPTH   = 4   # BFS depth for layering search
CYCLE_MAX_LENGTH        = 6   # maximum cycle length to report
MAX_TRANSACTIONS        = 20000  # rows loaded from dataset
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| Graph engine | NetworkX |
| Data processing | Pandas |
| Frontend | HTML, Bootstrap 5, Plotly.js |
| Templating | Jinja2 |

---

## License

This project is for educational and research purposes. The IBM AML dataset is subject to its own Kaggle license.
