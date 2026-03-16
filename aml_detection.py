import networkx as nx
import pandas as pd
from config import (
    FAN_OUT_THRESHOLD,
    FAN_IN_THRESHOLD,
    VELOCITY_THRESHOLD,
    LAYERING_MIN_CHAIN_LENGTH,
    LAYERING_CUTOFF_DEPTH,
    LAYERING_SOURCE_SAMPLE,
    CYCLE_MAX_LENGTH,
    CYCLE_MAX_RESULTS,
)


def detect_fan_out(G, threshold=FAN_OUT_THRESHOLD):
    """Accounts sending money to many different receivers (smurfing / dispersal)."""
    return [
        {"account": n, "out_degree": G.out_degree(n)}
        for n in G.nodes()
        if G.out_degree(n) > threshold
    ]


def detect_fan_in(G, threshold=FAN_IN_THRESHOLD):
    """Accounts receiving money from many different senders (aggregation)."""
    return [
        {"account": n, "in_degree": G.in_degree(n)}
        for n in G.nodes()
        if G.in_degree(n) > threshold
    ]


def detect_circular_transactions(G):
    """
    Detect short cycles in the graph (money going in circles).
    Only searches within strongly connected components to keep runtime bounded.
    Deduplicates cycles by sorted tuple.
    """
    seen = set()
    cycles = []

    # Convert to DiGraph for simple_cycles (works on MultiDiGraph too but DiGraph is faster)
    simple_G = nx.DiGraph(G)

    for scc in nx.strongly_connected_components(simple_G):
        if len(scc) < 2:
            continue
        sub = simple_G.subgraph(scc)
        for cycle in nx.simple_cycles(sub):
            if len(cycle) > CYCLE_MAX_LENGTH:
                continue
            key = tuple(sorted(cycle))
            if key not in seen:
                seen.add(key)
                cycles.append(cycle)
            if len(cycles) >= CYCLE_MAX_RESULTS:
                return cycles

    return cycles


def detect_layering_chains(G):
    """
    Detect long chains of sequential transactions (layering / placement obscuration).
    Only traces paths from the top LAYERING_SOURCE_SAMPLE nodes by out-degree
    to keep runtime tractable on large graphs.
    """
    # Pick highest out-degree nodes as likely chain starts
    top_sources = sorted(G.nodes(), key=lambda n: G.out_degree(n), reverse=True)
    top_sources = top_sources[:LAYERING_SOURCE_SAMPLE]

    chains = []
    simple_G = nx.DiGraph(G)

    for source in top_sources:
        # single_source_shortest_path returns {target: path} via BFS — O(V+E) per source
        paths = nx.single_source_shortest_path(simple_G, source, cutoff=LAYERING_CUTOFF_DEPTH)
        for target, path in paths.items():
            if len(path) >= LAYERING_MIN_CHAIN_LENGTH + 1:  # path length = nodes, chain = edges
                chains.append(path)

    return chains[:200]


def detect_velocity(df, threshold=VELOCITY_THRESHOLD):
    """
    Accounts with an unusually high number of outgoing transactions
    within any rolling 24-hour window.
    """
    suspicious = []
    grouped = df.sort_values("timestamp").groupby("from_account")

    for account, group in grouped:
        timestamps = group["timestamp"].dropna().sort_values().reset_index(drop=True)
        if len(timestamps) < threshold:
            continue
        # Two-pointer sliding window — O(n) per account
        window = pd.Timedelta(hours=24)
        left = 0
        max_count = 0
        for right in range(len(timestamps)):
            while timestamps[right] - timestamps[left] >= window:
                left += 1
            max_count = max(max_count, right - left + 1)
        if max_count > threshold:
            suspicious.append({"account": account, "max_tx_per_24h": int(max_count)})

    return suspicious


def run_all_detectors(G, df):
    """Run all AML detectors and return a combined results dict."""
    return {
        "fan_out": detect_fan_out(G),
        "fan_in": detect_fan_in(G),
        "circular_transactions": detect_circular_transactions(G),
        "layering_chains": detect_layering_chains(G),
        "velocity": detect_velocity(df),
    }
