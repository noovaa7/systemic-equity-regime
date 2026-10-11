# ============================================================================
# FEATURE ENGINEERING 
# ============================================================================
print("\n" + "="*80)
print("FEATURE ENGINEERING")
print("="*80)

# Sort once
stocks_df = stocks_df.sort_values(['fid', 'tradedate']).reset_index(drop=True)

# ── Returns ───────────────────────────────────────────────────────────────────
print("  1/4 Returns & Momentum...")
stocks_df['ret_1d'] = stocks_df.groupby('fid')['close'].pct_change(1)

# ──Single transform───────────────────────────────────────────────────────────────────
stocks_df['momentum_12_1'] = stocks_df.groupby('fid')['close'].transform(
    lambda x: x.pct_change(252) - x.pct_change(21)
)

# ── Volatility ────────────────────────────────────────────────────────────────
print("  2/4 Volatility...")
stocks_df['vol_126d'] = (
    stocks_df.groupby('fid')['ret_1d']
    .transform(lambda x: x.rolling(126, min_periods=60).std()) * np.sqrt(252)
)

# ── Liquidity ─────────────────────────────────────────────────────────────────
print("  3/4 Liquidity...")
stocks_df['avg_value_21d'] = (
    stocks_df.groupby('fid')['traded_value']
    .transform(lambda x: x.rolling(21, min_periods=10).mean())
)

# ── Benchmark 200-day MA ────────────────────────────────────────────────
print("  4/4 Benchmark 200-day MA (regime filter)...")
nse500 = nse500.sort_values('tradedate').reset_index(drop=True)
nse500['ma_200d'] = nse500['nse500_close'].rolling(200, min_periods=150).mean()
nse500['bull_regime'] = (nse500['nse500_close'] > nse500['ma_200d']).astype(int)

# ── Integrity checks ──────────────────────────────────────────────────────────
momentum_nan_pct = stocks_df['momentum_12_1'].isna().mean() * 100
vol_nan_pct      = stocks_df['vol_126d'].isna().mean() * 100
ma_nan_pct       = nse500['ma_200d'].isna().mean() * 100

print(f"\n✓ Feature engineering complete")
print(f"  momentum_12_1 NaN:  {momentum_nan_pct:.1f}%  (expected ~25-30%)")
print(f"  vol_126d NaN:       {vol_nan_pct:.1f}%  (expected ~15-20%)")
print(f"  ma_200d NaN:        {ma_nan_pct:.1f}%  (expected first ~200 rows only)")
print(f"  Bull regime days:   {nse500['bull_regime'].mean()*100:.1f}% of history")

assert momentum_nan_pct < 50, "momentum_12_1 NaN% too high"
assert vol_nan_pct      < 40, "vol_126d NaN% too high"
print("  Integrity checks passed ✓")

# ============================================================================
# MOMENTUM + LOW VOLATILITY SCORING 
# ============================================================================
print("\n" + "="*80)
print("MOMENTUM + LOW VOLATILITY SCORING (50/50, RANK BUFFER)")
print("="*80)

ENTRY_RANK = 20 
HOLD_RANK  = 40   

def calculate_score(df_day, current_date, bull_regime=1):
    """
    Flat 50/50 two-factor model. Returns full ranked universe.
    Rank buffer (entry=20, hold=40) applied in PortfolioManager.
    """
    df = df_day.copy()

    required = ['momentum_12_1', 'vol_126d', 'avg_value_21d', 'mcap']
    for col in required:
        if col not in df.columns:
            print(f"  WARNING: '{col}' missing on {current_date} — skipping rebalance")
            return pd.DataFrame()
        df = df[df[col].notna()].copy()

    if len(df) < 50:
        return pd.DataFrame()

    # Universe: top 500 by mcap
    df = df[df['mcap'] > 0].copy()
    df = df.nlargest(500, 'mcap').copy()

    if len(df) < 30:
        return pd.DataFrame()

    # Liquidity filter
    liq_median = df['avg_value_21d'].median()
    df = df[df['avg_value_21d'] > liq_median].copy()

    if len(df) < 30:
        return pd.DataFrame()

    # Cross-sectional z-score
    def zscore(series):
        std = series.std()
        if std < 1e-6:
            return pd.Series(0, index=series.index)
        return (series - series.mean()) / std

    df['z_momentum'] = zscore(df['momentum_12_1'])
    df['z_lowvol']   = zscore(-df['vol_126d'])

    # Flat 50/50 weights
    df['composite_score'] = 0.50 * df['z_momentum'] + 0.50 * df['z_lowvol']

    # Rank all stocks
    df['rank']        = df['composite_score'].rank(ascending=False).astype(int)
    df['bull_regime'] = bull_regime

    # Return ALL ranked stocks
    return df[['fid', 'composite_score', 'rank', 'vol_126d',
               'avg_value_21d', 'mcap', 'bull_regime']].copy()