# ============================================================================
# VISUALIZATIONS
# ============================================================================
print("\n" + "="*80)
print("VISUALIZATIONS")
print("="*80)

def shade_bear_periods(ax, results_df):
    label_added = False
    df = results_df.copy()
    in_bear    = False
    bear_start = None
    for _, row in df.iterrows():
        if row['bull_regime'] == 0 and not in_bear:
            bear_start = row['date']
            in_bear    = True
        elif row['bull_regime'] == 1 and in_bear:
            lbl = 'Bear Regime (50% cash)' if not label_added else '_nolegend_'
            ax.axvspan(bear_start, row['date'], alpha=0.15, color='red', label=lbl)
            label_added = True
            in_bear     = False
    if in_bear:
        lbl = 'Bear Regime (50% cash)' if not label_added else '_nolegend_'
        ax.axvspan(bear_start, df['date'].iloc[-1], alpha=0.15, color='red', label=lbl)


# ── DASHBOARD 1: MAIN 4-PANEL STRATEGY DASHBOARD ──────────────────────────────
fig1, axes = plt.subplots(4, 1, figsize=(14, 22))
fig1.suptitle('Strategy Dashboard (2011–2020)\nMomentum + Low Volatility | NSE500 Universe', fontsize=14, fontweight='bold')

# Panel 1: NAV Curve
ax = axes[0]
ax.plot(perf_full['date'], perf_full['portfolio_value'], color='#1f77b4', linewidth=1.5, label='Strategy NAV')
ax.plot(perf_full['date'], perf_full['benchmark_value'], color='#ff7f0e', linewidth=1.5, linestyle='--', label='NSE500 NAV')
shade_bear_periods(ax, results_full)
ax.set_title('NAV Curve — Strategy vs NSE500 Benchmark', fontsize=11)
ax.set_ylabel('Portfolio Value (₹)')
ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'₹{x/1e6:.1f}M'))
ax.legend(loc='upper left', fontsize=9)
ax.grid(True, alpha=0.3)
ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
ax.xaxis.set_major_locator(mdates.YearLocator())

# Panel 2: Drawdown Curve
ax = axes[1]
strat_max = perf_full['portfolio_value'].expanding().max()
strat_dd  = ((perf_full['portfolio_value'] - strat_max) / strat_max) * 100
bm_max    = perf_full['benchmark_value'].expanding().max()
bm_dd     = ((perf_full['benchmark_value'] - bm_max) / bm_max) * 100
ax.fill_between(perf_full['date'], strat_dd, 0, alpha=0.4, color='#1f77b4', label=f'Strategy (max DD: {strat_dd.min():.2f}%)')
ax.plot(perf_full['date'], bm_dd, color='#ff7f0e', linewidth=1.0, linestyle='--', label=f'NSE500 (max DD: {bm_dd.min():.2f}%)')
ax.axhline(0, color='black', linewidth=0.5)
shade_bear_periods(ax, results_full)
ax.set_title('Drawdown Curve — Strategy vs NSE500 Benchmark', fontsize=11)
ax.set_ylabel('Drawdown (%)')
ax.legend(loc='lower left', fontsize=9)
ax.grid(True, alpha=0.3)

# Panel 3: Position Count & Cash
ax = axes[2]
ax.plot(results_full['date'], results_full['positions'], color='#2ca02c', linewidth=1.2, label='Positions Held')
ax.axhline(y=TOP_N_STOCKS, color='gray', linestyle='--', linewidth=1.0, label=f'Target ({TOP_N_STOCKS})')
ax.fill_between(results_full['date'], results_full['cash'] / results_full['portfolio_value'] * MAX_POSITIONS, 0, alpha=0.2, color='orange', label='Cash Weight (scaled)')
shade_bear_periods(ax, results_full)
ax.set_title('Position Count & Cash Level Over Time', fontsize=11)
ax.set_ylabel('Number of Positions')
ax.set_ylim(0, MAX_POSITIONS + 10)
ax.legend(loc='upper right', fontsize=9)
ax.grid(True, alpha=0.3)

# Panel 4: Rolling 1Y Outperformance
ax = axes[3]
s_r = (1 + perf_full['returns']).rolling(252).apply(lambda x: x.prod() ** (252/252) - 1, raw=True)
bm_r = (1 + perf_full['benchmark_returns']).rolling(252).apply(lambda x: x.prod() ** (252/252) - 1, raw=True)
rolling_1y = (s_r - bm_r) * 100
ax.fill_between(perf_full['date'], rolling_1y, 0, where=(rolling_1y >= 0), alpha=0.6, color='#2ca02c', label='Outperformance')
ax.fill_between(perf_full['date'], rolling_1y, 0, where=(rolling_1y < 0),  alpha=0.6, color='#d62728', label='Underperformance')
ax.axhline(y=0, color='black', linewidth=0.8)
shade_bear_periods(ax, results_full)
ax.set_title('Rolling 1-Year Outperformance vs NSE500 (%)', fontsize=11)
ax.set_ylabel('Outperformance (%)')
ax.legend(loc='upper left', fontsize=9)
ax.grid(True, alpha=0.3)

plt.tight_layout(rect=[0, 0, 1, 0.97])
plt.savefig('strategy_dashboard_2011_2020.png', dpi=150, bbox_inches='tight')
plt.show()

# ── BULL REGIME ──
merged_regime = perf_full.merge(results_full[['date', 'bull_regime']], on='date', how='left')
bull_df = merged_regime[merged_regime['bull_regime'] == 1].copy().reset_index(drop=True)

fig2, axes2 = plt.subplots(3, 2, figsize=(16, 18))
fig2.suptitle('Bull Regime Performance Breakdown (2011–2020)\nNSE500 above 200-day MA — Strategy 100% invested', fontsize=13, fontweight='bold')

# Row 1, Col 1: NAV Curve — bull days
ax = axes2[0, 0]
ax.plot(bull_df['date'], bull_df['portfolio_value'], color='#1f77b4', linewidth=1.5, label='Strategy NAV')
ax.plot(bull_df['date'], bull_df['benchmark_value'], color='#ff7f0e', linewidth=1.5, linestyle='--', label='NSE500 NAV')
ax.set_title('NAV Curve — Bull Days Only', fontsize=11)
ax.set_ylabel('Portfolio Value (₹)')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# Row 1, Col 2: Drawdown Curve — bull days
ax = axes2[0, 1]
bull_s_max = bull_df['portfolio_value'].expanding().max()
bull_s_dd  = ((bull_df['portfolio_value'] - bull_s_max) / bull_s_max) * 100
bull_b_max = bull_df['benchmark_value'].expanding().max()
bull_b_dd  = ((bull_df['benchmark_value'] - bull_b_max) / bull_b_max) * 100
ax.fill_between(bull_df['date'], bull_s_dd, 0, alpha=0.4, color='#1f77b4', label=f'Strategy (max: {bull_s_dd.min():.2f}%)')
ax.plot(bull_df['date'], bull_b_dd, color='#ff7f0e', linewidth=1.0, linestyle='--', label=f'NSE500 (max: {bull_b_dd.min():.2f}%)')
ax.axhline(0, color='black', linewidth=0.5)
ax.set_title('Drawdown Curve — Bull Days Only', fontsize=11)
ax.set_ylabel('Drawdown (%)')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# Row 2, Col 1: Cumulative return — bull days
ax = axes2[1, 0]
bull_s_cum = (1 + bull_df['returns'].fillna(0)).cumprod()
bull_b_cum = (1 + bull_df['benchmark_returns'].fillna(0)).cumprod()
ax.plot(bull_df['date'], (bull_s_cum - 1) * 100, color='#1f77b4', linewidth=1.5, label='Strategy')
ax.plot(bull_df['date'], (bull_b_cum - 1) * 100, color='#ff7f0e', linewidth=1.5, linestyle='--', label='NSE500')
ax.set_title('Cumulative Return — Bull Days Only', fontsize=11)
ax.set_ylabel('Cumulative Return (%)')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# Row 2, Col 2: Daily return distribution — bull
ax = axes2[1, 1]
bull_mr = pd.DataFrame({'Strategy': bull_df['returns'].dropna() * 100, 'NSE500': bull_df['benchmark_returns'].dropna() * 100})
ax.hist(bull_mr['Strategy'], bins=60, alpha=0.6, color='#1f77b4', label='Strategy')
ax.hist(bull_mr['NSE500'],   bins=60, alpha=0.6, color='#ff7f0e', label='NSE500')
ax.axvline(bull_mr['Strategy'].mean(), color='#1f77b4', linestyle='--', linewidth=1.5)
ax.axvline(bull_mr['NSE500'].mean(),   color='#ff7f0e', linestyle='--', linewidth=1.5)
ax.set_title('Daily Return Distribution — Bull Days', fontsize=11)
ax.set_xlabel('Daily Return (%)')
ax.set_ylabel('Frequency')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

# Row 3, Col 1: Rolling 3M active return — bull
ax = axes2[2, 0]
bull_active     = bull_df['returns'].fillna(0) - bull_df['benchmark_returns'].fillna(0)
rolling_3m_bull = bull_active.rolling(63).mean() * 252 * 100
ax.fill_between(bull_df['date'], rolling_3m_bull, 0, where=(rolling_3m_bull >= 0), alpha=0.6, color='#2ca02c', label='Outperform')
ax.fill_between(bull_df['date'], rolling_3m_bull, 0, where=(rolling_3m_bull < 0),  alpha=0.6, color='#d62728', label='Underperform')
ax.axhline(0, color='black', linewidth=0.8)
ax.set_title('Rolling 3M Annualised Active Return — Bull Days', fontsize=11)
ax.set_ylabel('Active Return (% ann.)')
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)

# Row 3, Col 2: Scatter — bull
ax = axes2[2, 1]
common_bull = pd.DataFrame({'bm': bull_df['benchmark_returns'].dropna() * 100, 'st': bull_df['returns'].dropna() * 100}).dropna()
ax.scatter(common_bull['bm'], common_bull['st'], alpha=0.3, s=8, color='#1f77b4')
lims = [min(common_bull['bm'].min(), common_bull['st'].min()), max(common_bull['bm'].max(), common_bull['st'].max())]
ax.plot(lims, lims, 'k--', linewidth=0.8, label='1:1 line')
m, b = np.polyfit(common_bull['bm'], common_bull['st'], 1)
xfit = np.linspace(common_bull['bm'].min(), common_bull['bm'].max(), 100)
ax.plot(xfit, m * xfit + b, color='red', linewidth=1.2, label=f'Beta={m:.2f}, Alpha/day={b:.4f}%')
ax.set_title('Strategy vs Benchmark Returns — Bull Days', fontsize=11)
ax.set_xlabel('Benchmark Return (%)')
ax.set_ylabel('Strategy Return (%)')
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)

plt.tight_layout(rect=[0, 0, 1, 0.95])
plt.savefig('regime_bull_breakdown.png', dpi=150, bbox_inches='tight')
plt.show()