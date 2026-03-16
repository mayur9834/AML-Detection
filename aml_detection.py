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
    STRUCTURING_THRESHOLD,
    STRUCTURING_MARGIN_PCT,
    STRUCTURING_MIN_COUNT,
)


def detect_fan_out(G, threshold=FAN_OUT_THRESHOLD):
    """Accounts sending money to many different receivers (smurfing / dispersal).
    Now includes total outgoing volume for amount-weighted risk."""
    results = []
    for n in G.nodes():
        out_deg = G.out_degree(n)
        if out_deg > threshold:
            total_out = sum(
                d.get("amount", 0) for _, _, d in G.out_edges(n, data=True)
            )
            results.append({
                "account": n,
                "out_degree": out_deg,
                "total_amount": round(float(total_out), 2),
            })
    return results


def detect_fan_in(G, threshold=FAN_IN_THRESHOLD):
    """Accounts receiving money from many different senders (aggregation).
    Now includes total incoming volume for amount-weighted risk."""
    results = []
    for n in G.nodes():
        in_deg = G.in_degree(n)
        if in_deg > threshold:
            total_in = sum(
                d.get("amount", 0) for _, _, d in G.in_edges(n, data=True)
            )
            results.append({
                "account": n,
                "in_degree": in_deg,
                "total_amount": round(float(total_in), 2),
            })
    return results


def detect_circular_transactions(G):
    """Detect short cycles in the graph (money going in circles).
    Now annotates each cycle with total value flowing through it."""
    seen = set()
    cycles = []

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
                # Sum amounts along cycle edges
                cycle_amount = 0.0
                for i in range(len(cycle)):
                    u, v = cycle[i], cycle[(i + 1) % len(cycle)]
                    if G.has_edge(u, v):
                        for _, ed in G[u][v].items():
                            cycle_amount += ed.get("amount", 0)
                cycles.append({
                    "accounts": cycle,
                    "length": len(cycle),
                    "total_amount": round(cycle_amount, 2),
                })
            if len(cycles) >= CYCLE_MAX_RESULTS:
                return cycles

    return cycles


def detect_layering_chains(G):
    """Detect long chains of sequential transactions (layering).
    Now annotates chains with min/max/total amounts along the path."""
    top_sources = sorted(G.nodes(), key=lambda n: G.out_degree(n), reverse=True)
    top_sources = top_sources[:LAYERING_SOURCE_SAMPLE]

    chains = []
    simple_G = nx.DiGraph(G)

    for source in top_sources:
        paths = nx.single_source_shortest_path(simple_G, source, cutoff=LAYERING_CUTOFF_DEPTH)
        for target, path in paths.items():
            if len(path) >= LAYERING_MIN_CHAIN_LENGTH + 1:
                # Sum amounts along chain edges
                amounts = []
                for i in range(len(path) - 1):
                    u, v = path[i], path[i + 1]
                    edge_sum = 0.0
                    if G.has_edge(u, v):
                        for _, ed in G[u][v].items():
                            edge_sum += ed.get("amount", 0)
                    amounts.append(edge_sum)
                chains.append({
                    "path": path,
                    "hops": len(path) - 1,
                    "total_amount": round(sum(amounts), 2),
                    "min_hop_amount": round(min(amounts) if amounts else 0, 2),
                    "max_hop_amount": round(max(amounts) if amounts else 0, 2),
                })

    return chains[:200]


def detect_velocity(df, threshold=VELOCITY_THRESHOLD):
    """Accounts with high outgoing transaction frequency within 24h windows.
    Now includes total and max single-transaction amounts in the peak window."""
    suspicious = []
    grouped = df.sort_values("timestamp").groupby("from_account")

    for account, group in grouped:
        sorted_group = group.sort_values("timestamp").dropna(subset=["timestamp"])
        timestamps = sorted_group["timestamp"].reset_index(drop=True)
        amounts = sorted_group["amount"].reset_index(drop=True)
        if len(timestamps) < threshold:
            continue
        window = pd.Timedelta(hours=24)
        left = 0
        max_count = 0
        best_left = 0
        best_right = 0
        for right in range(len(timestamps)):
            while timestamps[right] - timestamps[left] >= window:
                left += 1
            count = right - left + 1
            if count > max_count:
                max_count = count
                best_left = left
                best_right = right
        if max_count > threshold:
            window_amounts = amounts[best_left:best_right + 1]
            suspicious.append({
                "account": account,
                "max_tx_per_24h": int(max_count),
                "window_total_amount": round(float(window_amounts.sum()), 2),
                "window_max_single": round(float(window_amounts.max()), 2),
            })

    return suspicious


def detect_structuring(df, threshold=STRUCTURING_THRESHOLD,
                       margin_pct=STRUCTURING_MARGIN_PCT,
                       min_count=STRUCTURING_MIN_COUNT):
    """Detect structuring — multiple transactions just below a reporting threshold.
    Classic AML pattern where launderers split amounts to avoid CTR filings."""
    lower_bound = threshold * (1 - margin_pct)

    # Find transactions in the just-below-threshold band
    just_below = df[(df["amount"] >= lower_bound) & (df["amount"] < threshold)]

    if just_below.empty:
        return []

    # Group by sender and count how many just-below-threshold transactions they have
    grouped = just_below.groupby("from_account").agg(
        count=("amount", "size"),
        total_amount=("amount", "sum"),
        avg_amount=("amount", "mean"),
        min_amount=("amount", "min"),
        max_amount=("amount", "max"),
    ).reset_index()

    flagged = grouped[grouped["count"] >= min_count]

    return [
        {
            "account": row["from_account"],
            "count": int(row["count"]),
            "total_amount": round(float(row["total_amount"]), 2),
            "avg_amount": round(float(row["avg_amount"]), 2),
            "range": f"${round(float(row['min_amount']),2):,.2f} – ${round(float(row['max_amount']),2):,.2f}",
            "threshold": threshold,
        }
        for _, row in flagged.iterrows()
    ]


def evaluate_ground_truth(G, df, detectors_result):
    """Compare detector flags against ground truth is_laundering labels.
    Returns precision, recall, F1 per detector and overall."""
    # Build set of accounts involved in known laundering transactions
    laundering_tx = df[df["is_laundering"] == 1]
    if laundering_tx.empty:
        return None

    gt_accounts = set(laundering_tx["from_account"]) | set(laundering_tx["to_account"])

    metrics = {}

    # Extract flagged accounts from each detector
    detector_accounts = {
        "fan_out": {r["account"] for r in detectors_result.get("fan_out", [])},
        "fan_in": {r["account"] for r in detectors_result.get("fan_in", [])},
        "circular": set(),
        "velocity": {r["account"] for r in detectors_result.get("velocity", [])},
        "layering": set(),
        "structuring": {r["account"] for r in detectors_result.get("structuring", [])},
    }

    # Circular: collect all accounts from cycles
    for c in detectors_result.get("circular_transactions", []):
        accounts = c.get("accounts", c) if isinstance(c, dict) else c
        detector_accounts["circular"].update(accounts)

    # Layering: collect all accounts in chains
    for c in detectors_result.get("layering_chains", []):
        path = c.get("path", c) if isinstance(c, dict) else c
        detector_accounts["layering"].update(path)

    # Per-detector metrics
    all_flagged = set()
    for name, flagged in detector_accounts.items():
        all_flagged |= flagged
        tp = len(flagged & gt_accounts)
        fp = len(flagged - gt_accounts)
        fn = len(gt_accounts - flagged)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        metrics[name] = {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "flagged_count": len(flagged),
        }

    # Overall (union of all detectors)
    tp = len(all_flagged & gt_accounts)
    fp = len(all_flagged - gt_accounts)
    fn = len(gt_accounts - all_flagged)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    metrics["overall"] = {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "flagged_count": len(all_flagged),
        "ground_truth_count": len(gt_accounts),
    }

    return metrics


def build_suspicious_subgraph(G, detectors_result, max_nodes=150):
    """Build a subgraph of flagged accounts + their direct neighbors for visualization.
    Returns nodes and edges as JSON-serializable lists."""
    # Collect all flagged accounts
    flagged = set()
    for r in detectors_result.get("fan_out", []):
        flagged.add(r["account"])
    for r in detectors_result.get("fan_in", []):
        flagged.add(r["account"])
    for r in detectors_result.get("velocity", []):
        flagged.add(r["account"])
    for r in detectors_result.get("structuring", []):
        flagged.add(r["account"])
    for c in detectors_result.get("circular_transactions", []):
        accounts = c.get("accounts", c) if isinstance(c, dict) else c
        flagged.update(accounts)
    for c in detectors_result.get("layering_chains", []):
        path = c.get("path", c) if isinstance(c, dict) else c
        flagged.update(path)

    if not flagged:
        return {"nodes": [], "edges": []}

    # Determine which detectors flagged each account
    flag_map = {}
    for r in detectors_result.get("fan_out", []):
        flag_map.setdefault(r["account"], set()).add("fan_out")
    for r in detectors_result.get("fan_in", []):
        flag_map.setdefault(r["account"], set()).add("fan_in")
    for r in detectors_result.get("velocity", []):
        flag_map.setdefault(r["account"], set()).add("velocity")
    for r in detectors_result.get("structuring", []):
        flag_map.setdefault(r["account"], set()).add("structuring")
    for c in detectors_result.get("circular_transactions", []):
        accounts = c.get("accounts", c) if isinstance(c, dict) else c
        for a in accounts:
            flag_map.setdefault(a, set()).add("circular")
    for c in detectors_result.get("layering_chains", []):
        path = c.get("path", c) if isinstance(c, dict) else c
        for a in path:
            flag_map.setdefault(a, set()).add("layering")

    # Limit to top nodes by number of flags, then add 1-hop neighbors
    sorted_flagged = sorted(flagged, key=lambda n: len(flag_map.get(n, set())), reverse=True)
    core_nodes = set(sorted_flagged[:max_nodes // 2])
    subgraph_nodes = set(core_nodes)
    for n in core_nodes:
        if n in G:
            for neighbor in list(G.successors(n))[:5] + list(G.predecessors(n))[:5]:
                subgraph_nodes.add(neighbor)
                if len(subgraph_nodes) >= max_nodes:
                    break
        if len(subgraph_nodes) >= max_nodes:
            break

    # Build edges between subgraph nodes
    sub = G.subgraph(subgraph_nodes)
    nodes_list = []
    for n in sub.nodes():
        flags = sorted(flag_map.get(n, set()))
        nodes_list.append({
            "id": str(n),
            "flagged": n in flagged,
            "flags": flags,
            "flag_count": len(flags),
            "in_degree": sub.in_degree(n),
            "out_degree": sub.out_degree(n),
        })

    edges_list = []
    seen_edges = set()
    for u, v, d in sub.edges(data=True):
        key = (str(u), str(v))
        if key not in seen_edges:
            seen_edges.add(key)
            # Sum all parallel edges
            total = sum(ed.get("amount", 0) for _, ed in G[u][v].items())
            edge_count = G.number_of_edges(u, v)
            edges_list.append({
                "source": str(u),
                "target": str(v),
                "amount": round(float(total), 2),
                "count": edge_count,
            })

    return {"nodes": nodes_list, "edges": edges_list}


def run_all_detectors(G, df):
    """Run all AML detectors and return a combined results dict."""
    results = {
        "fan_out": detect_fan_out(G),
        "fan_in": detect_fan_in(G),
        "circular_transactions": detect_circular_transactions(G),
        "layering_chains": detect_layering_chains(G),
        "velocity": detect_velocity(df),
        "structuring": detect_structuring(df),
    }

    # Ground truth evaluation
    evaluation = evaluate_ground_truth(G, df, results)
    if evaluation:
        results["ground_truth_evaluation"] = evaluation

    # Suspicious subgraph for network visualization
    results["suspicious_subgraph"] = build_suspicious_subgraph(G, results)

    return results
