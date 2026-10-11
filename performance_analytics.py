# ============================================================================
# PERFORMANCE METRICS & TURNOVER
# ============================================================================
print("\n" + "="*80)
print("PERFORMANCE METRICS")
print("="*80)

def calculate_performance_metrics(results_df, benchmark_df,
                                   initial_capital=INITIAL_CAPITAL):

    results_df   = results_df.copy()
    benchmark_df = benchmark_df.copy()
    results_df['date']        = pd.to_datetime(results_df['date'])
    benchmark_df['tradedate'] = pd.to_datetime(benchmark_df['tradedate'])

    perf_df = results_df.merge(
        benchmark_df, left_on='date', right_on='tradedate', how='left'
    )
    perf_df['nse500_close']      = perf_df['nse500_close'].ffill()
    perf_df['benchmark_value']   = (
        perf_df['nse500_close'] / perf_df['nse500_close'].iloc[0]
    ) * initial_capital
    perf_df['benchmark_returns'] = perf_df['benchmark_value'].pct_change()

    n_years = len(perf_df) / 252

    strat_total  = (perf_df['portfolio_value'].iloc[-1] / initial_capital) - 1
    strat_cagr   = (1 + strat_total) ** (1 / n_years) - 1
    strat_rets   = perf_df['returns'].dropna()
    strat_vol    = strat_rets.std() * np.sqrt(252)
    strat_sharpe = (strat_cagr - ANNUAL_RISK_FREE_RATE) / strat_vol 
    rolling_max  = perf_df['portfolio_value'].expanding().max()
    strat_dd     = ((perf_df['portfolio_value'] - rolling_max) / rolling_max).min()

    bm_total  = (perf_df['benchmark_value'].iloc[-1] / initial_capital) - 1
    bm_cagr   = (1 + bm_total) ** (1 / n_years) - 1
    bm_rets   = perf_df['benchmark_returns'].dropna()
    bm_vol    = bm_rets.std() * np.sqrt(252)
    bm_sharpe = (bm_cagr - ANNUAL_RISK_FREE_RATE) / bm_vol  
    bm_max    = perf_df['benchmark_value'].expanding().max()
    bm_dd     = ((perf_df['benchmark_value'] - bm_max) / bm_max).min()

    merged_rets    = pd.DataFrame({
        'strat': perf_df['returns'],
        'bm':    perf_df['benchmark_returns']
    }).dropna()
    active_rets    = merged_rets['strat'] - merged_rets['bm']
    tracking_error = active_rets.std() * np.sqrt(252)
    info_ratio     = (
        (strat_cagr - bm_cagr) / tracking_error if tracking_error > 0 else 0
    )

    up_days      = merged_rets['bm'] > 0
    down_days    = merged_rets['bm'] < 0
    up_capture   = (
        merged_rets.loc[up_days,   'strat'].mean() /
        merged_rets.loc[up_days,   'bm'].mean()
        if merged_rets.loc[up_days, 'bm'].mean() != 0 else 0
    )
    down_capture = (
        merged_rets.loc[down_days, 'strat'].mean() /
        merged_rets.loc[down_days, 'bm'].mean()
        if merged_rets.loc[down_days, 'bm'].mean() != 0 else 0
    )

    metrics = {
        'Strategy': {
            'Total Return': f"{strat_total*100:.2f}%",
            'CAGR':         f"{strat_cagr*100:.2f}%",
            'Volatility':   f"{strat_vol*100:.2f}%",
            'Sharpe Ratio': f"{strat_sharpe:.3f}",
            'Max Drawdown': f"{strat_dd*100:.2f}%",
        },
        'Benchmark (NSE500)': {
            'Total Return': f"{bm_total*100:.2f}%",
            'CAGR':         f"{bm_cagr*100:.2f}%",
            'Volatility':   f"{bm_vol*100:.2f}%",
            'Sharpe Ratio': f"{bm_sharpe:.3f}",
            'Max Drawdown': f"{bm_dd*100:.2f}%",
        },
        'Relative': {
            'Alpha (CAGR)':      f"{(strat_cagr - bm_cagr)*100:.2f}%",
            'Information Ratio': f"{info_ratio:.3f}",
            'Up Capture':        f"{up_capture*100:.2f}%",
            'Down Capture':      f"{down_capture*100:.2f}%",
            'Tracking Error':    f"{tracking_error*100:.2f}%",
        }
    }

    return metrics, perf_df

def calculate_rolling_metrics(perf_df, windows=[252, 756, 1260]):
    results = {}
    for window in windows:
        yrs  = window / 252
        s_r  = (1 + perf_df['returns']).rolling(window).apply(
            lambda x: x.prod() ** (252 / window) - 1, raw=True
        )
        bm_r = (1 + perf_df['benchmark_returns']).rolling(window).apply(
            lambda x: x.prod() ** (252 / window) - 1, raw=True
        )
        out  = (s_r - bm_r) * 100
        results[f'{int(yrs)}Y'] = {
            'Average Outperformance': f"{out.mean():.2f}%",
            'Worst Underperformance': f"{out.min():.2f}%",
            'Best Outperformance':    f"{out.max():.2f}%",
            'Periods Analyzed':       out.notna().sum()
        }
    return results

def calculate_turnover(results_df, stocks_data, rebalance_days=REBALANCE_DAYS):
    """Simulates rank buffer rule to compute accurate turnover."""
    trading_days    = sorted(results_df['date'].unique())
    rebalance_dates = [trading_days[i] for i in range(0, len(trading_days), rebalance_days)]
    rebalance_stocks_data = stocks_data[stocks_data['tradedate'].isin(rebalance_dates)]
    regime_lookup_local = nse500.set_index('tradedate')['bull_regime'].to_dict()
    prev_portfolio      = set()
    turnovers           = []
    trade_log           = []

    for date in rebalance_dates:
        day_data = rebalance_stocks_data[rebalance_stocks_data['tradedate'] == date].copy()
        if len(day_data) == 0:
            continue
        bull_regime_val = regime_lookup_local.get(date, 1)
        scores = calculate_score(day_data, date, bull_regime=bull_regime_val)
        if len(scores) == 0:
            continue

        rank_lookup = scores.set_index('fid')['rank'].to_dict()
        keep = {fid for fid in prev_portfolio if rank_lookup.get(fid, 9999) <= HOLD_RANK}
        candidates = scores[scores['rank'] <= ENTRY_RANK].sort_values('rank')
        
        new_entries = []
        for _, row in candidates.iterrows():
            if len(keep) + len(new_entries) >= TOP_N_STOCKS:
                break
            if row['fid'] not in keep:
                new_entries.append(row['fid'])

        current_portfolio = keep | set(new_entries)

        if len(current_portfolio) < TOP_N_STOCKS:
            for _, row in scores.sort_values('rank').iterrows():
                if len(current_portfolio) >= TOP_N_STOCKS:
                    break
                current_portfolio.add(row['fid'])

        if len(prev_portfolio) > 0:
            exits   = prev_portfolio - current_portfolio
            entries = current_portfolio - prev_portfolio
            n       = max(len(prev_portfolio), len(current_portfolio), 1)
            one_way = max(len(exits), len(entries)) / n
            turnovers.append(one_way)

            trade_log.append({
                'date':         date,
                'regime':       'BULL' if bull_regime_val == 1 else 'BEAR',
                'positions':    len(current_portfolio),
                'entries':      len(entries),
                'exits':        len(exits),
                'one_way_turn': f"{one_way*100:.1f}%"
            })
        prev_portfolio = current_portfolio

    if len(turnovers) == 0:
        return {}, pd.DataFrame()

    avg_per_rebalance  = np.mean(turnovers)
    rebalances_per_yr  = 252 / rebalance_days
    annualized_one_way = avg_per_rebalance * rebalances_per_yr

    stats = {
        'avg_turnover_per_rebalance':  avg_per_rebalance,
        'rebalances_per_year':         rebalances_per_yr,
        'annualized_one_way_turnover': annualized_one_way,
        'annualized_round_trip':       annualized_one_way * 2,
        'total_rebalances_analyzed':   len(turnovers),
        'implied_annual_cost_drag':    annualized_one_way * 2 * TRANSACTION_COST_PER_SIDE * 100
    }
    return stats, pd.DataFrame(trade_log)

# ============================================================================
# EXECUTE FULL BACKTEST (2011-2020)
# ============================================================================
results_full = run_backtest(
    stocks_df,
    start_date='2011-01-01',
    end_date='2020-01-01',
    initial_capital=INITIAL_CAPITAL
)

nse500_full = nse500[
    (nse500['tradedate'] >= '2011-01-01') &
    (nse500['tradedate'] <= '2020-01-01')
].copy()

metrics_full, perf_full = calculate_performance_metrics(results_full, nse500_full)
rolling_metrics = calculate_rolling_metrics(perf_full)
turnover_stats, trade_log_df = calculate_turnover(results_full, stocks_df)