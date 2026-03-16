import pandas as pd
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from data_loader import load_dataset, load_from_bytes
from graph_builder import build_graph
from aml_detection import run_all_detectors

app = FastAPI(
    title="AML Detection API",
    description="Graph-based Anti-Money Laundering detection using IBM transaction data.",
    version="1.0.0",
)

templates = Jinja2Templates(directory="templates")


def _to_json_safe(obj):
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_json_safe(i) for i in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    try:
        import numpy as np
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
    except ImportError:
        pass
    return obj


def _load_or_raise():
    try:
        return load_dataset()
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Dataset not found. Place HI-Small_Trans.csv at: datasets/HI-Small_Trans.csv",
        )


def _build_stats(df, G):
    """Shared stats + chart data for both /stats and /upload."""
    buckets = pd.cut(df["amount"], bins=20)
    amount_dist = (
        df.groupby(buckets, observed=True)["amount"]
        .count()
        .reset_index(name="count")
    )
    return {
        "transactions": len(df),
        "unique_senders": int(df["from_account"].nunique()),
        "unique_receivers": int(df["to_account"].nunique()),
        "graph_nodes": G.number_of_nodes(),
        "graph_edges": G.number_of_edges(),
        "total_amount": round(float(df["amount"].sum()), 2),
        "avg_amount": round(float(df["amount"].mean()), 2),
        "max_amount": round(float(df["amount"].max()), 2),
        "known_laundering_tx": int(df["is_laundering"].sum()),
        "laundering_rate_pct": round(float(df["is_laundering"].mean()) * 100, 2),
        "payment_formats": df["payment_format"].value_counts().to_dict()
            if "payment_format" in df.columns else {},
        "amount_hist": {
            "x": [str(i) for i in amount_dist["amount"].tolist()],
            "y": amount_dist["count"].tolist(),
        },
    }


# ── Frontend ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── API ────────────────────────────────────────────────────────────────────────

@app.get("/stats", summary="Dataset and graph statistics")
async def stats():
    df = _load_or_raise()
    G = build_graph(df)
    return JSONResponse(_to_json_safe(_build_stats(df, G)))


@app.get("/analyze", summary="Run all AML detectors on the pre-loaded dataset")
async def analyze():
    df = _load_or_raise()
    G = build_graph(df)
    results = run_all_detectors(G, df)
    results["graph_stats"] = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "transactions": len(df),
        "known_laundering_tx": int(df["is_laundering"].sum()),
    }
    return JSONResponse(_to_json_safe(results))


@app.post("/upload", summary="Upload an IBM AML CSV and run detection")
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    data = await file.read()

    try:
        df = load_from_bytes(data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    G = build_graph(df)
    results = run_all_detectors(G, df)

    # Include full stats + charts so the frontend can render everything
    results["stats"] = _build_stats(df, G)
    return JSONResponse(_to_json_safe(results))
