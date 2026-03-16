import networkx as nx
import pandas as pd


def build_graph(df: pd.DataFrame) -> nx.MultiDiGraph:
    """
    Build a directed multigraph from a transaction DataFrame.
    Uses MultiDiGraph so multiple transactions between the same
    account pair are preserved as distinct edges.
    """
    G = nx.from_pandas_edgelist(
        df,
        source="from_account",
        target="to_account",
        edge_attr=["amount", "timestamp", "payment_format", "is_laundering"],
        create_using=nx.MultiDiGraph(),
    )
    return G
