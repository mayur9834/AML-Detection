DATASET_PATH = "datasets/HI-Small_Trans.csv"
MAX_TRANSACTIONS = 20000

# Detection thresholds
FAN_OUT_THRESHOLD = 5
FAN_IN_THRESHOLD = 5
VELOCITY_THRESHOLD = 10
LAYERING_MIN_CHAIN_LENGTH = 3
LAYERING_CUTOFF_DEPTH = 4
CYCLE_MAX_LENGTH = 6
CYCLE_MAX_RESULTS = 100

# Only sample top-N high-degree nodes for layering search (performance)
LAYERING_SOURCE_SAMPLE = 50

# Structuring detection — transactions just below a reporting threshold
STRUCTURING_THRESHOLD = 10000    # e.g. $10,000 CTR reporting limit
STRUCTURING_MARGIN_PCT = 0.15    # flag transactions within 15% below threshold
STRUCTURING_MIN_COUNT = 3        # minimum just-below-threshold tx per account
