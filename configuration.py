# ============================================================================
# IMPORTS AND CONFIGURATION
# ============================================================================
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

print("="*80)
print("MOMENTUM + LOW VOLATILITY STRATEGY - COMPLETE PIPELINE")
print("="*80)

INITIAL_CAPITAL           = 5000000
REBALANCE_DAYS            = 21
TOP_N_STOCKS              = 30
MIN_POSITIONS             = 15
MAX_POSITIONS             = 30
TRANSACTION_COST_PER_SIDE = 0.00268
ANNUAL_RISK_FREE_RATE     = 0.065
DAILY_RISK_FREE_RATE      = ANNUAL_RISK_FREE_RATE / 252

print(f"\nStrategy Configuration:")
print(f"  Initial Capital:       ₹{INITIAL_CAPITAL:,}")
print(f"  Rebalance Frequency:   {REBALANCE_DAYS} days (~monthly)")
print(f"  Portfolio Size:        {MIN_POSITIONS}-{MAX_POSITIONS} positions")
print(f"  Transaction Cost:      {TRANSACTION_COST_PER_SIDE*100:.3f}% per side")
print(f"  Risk-Free Rate:        {ANNUAL_RISK_FREE_RATE*100:.1f}% p.a.")
print(f"  Execution:             T+1 at (O+H+L+C)/4 ± costs")

# ============================================================================
# LOADING DATA
# ============================================================================
print("\n" + "="*80)
print("LOADING DATA")
print("="*80)

# ---- File paths ----
STOCKS_FILE  = "/kaggle/input/nse-prices-complete/nse_prices_complete.parquet"
INDEXES_FILE = "/kaggle/input/indexes/indexes.xlsx"

# ---- Load data ----
stocks_df  = pd.read_parquet(STOCKS_FILE)
indexes_df = pd.read_excel(INDEXES_FILE)

# ---- Ensure datetime ----
stocks_df['tradedate']  = pd.to_datetime(stocks_df['tradedate'])
indexes_df['tradedate'] = pd.to_datetime(indexes_df['tradedate'])

# ---- Sort properly ----
stocks_df  = stocks_df.sort_values(['fid', 'tradedate']).reset_index(drop=True)
indexes_df = indexes_df.sort_values(['index_name', 'tradedate']).reset_index(drop=True)

# ---- Extract NSE500 benchmark ----
nse500 = indexes_df[indexes_df['index_name'] == 'NSE500'][['tradedate', 'close']].copy()
nse500.columns = ['tradedate', 'nse500_close']
nse500 = nse500.sort_values('tradedate').reset_index(drop=True)

print(f"✓ Stock data:       {stocks_df.shape[0]:,} records, {stocks_df['fid'].nunique()} stocks")
print(f"  Date range:       {stocks_df['tradedate'].min().date()} to {stocks_df['tradedate'].max().date()}")
print(f"✓ NSE500 benchmark: {len(nse500)} records")
print(f"  Columns: {stocks_df.columns.tolist()}")