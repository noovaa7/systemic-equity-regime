"""
SYSTEMATIC EQUITY REGIME MODEL
A quantitative momentum and low-volatility backtesting pipeline for the NSE500.
Features cash scaling, slippage modeling, and a 200-day moving average regime filter.
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

print("="*80)
print("MOMENTUM + LOW VOLATILITY STRATEGY - ENGINE ONLY")
print("="*80)

INITIAL_CAPITAL           = 5000000
REBALANCE_DAYS            = 21
TOP_N_STOCKS              = 30
MIN_POSITIONS             = 15
MAX_POSITIONS             = 30
TRANSACTION_COST_PER_SIDE = 0.00268
ANNUAL_RISK_FREE_RATE     = 0.065
DAILY_RISK_FREE_RATE      = ANNUAL_RISK_FREE_RATE / 252
BEAR_EQUITY_ALLOCATION    = 0.50
ENTRY_RANK                = 20 
HOLD_RANK                 = 40   

# ============================================================================
# 1. LOADING DATA
# ============================================================================
print("\nLoading Data...")
STOCKS_FILE  = "/kaggle/input/nse-prices-complete/nse_prices_complete.parquet"
INDEXES_FILE = "/kaggle/input/indexes/indexes.xlsx"

stocks_df  = pd.read_parquet(STOCKS_FILE)
indexes_df = pd.read_excel(INDEXES_FILE)

stocks_df['tradedate']  = pd.to_datetime(stocks_df['tradedate'])
indexes_df['tradedate'] = pd.to_datetime(indexes_df['tradedate'])
stocks_df  = stocks_df.sort_values(['fid', 'tradedate']).reset_index(drop=True)
indexes_df = indexes_df.sort_values(['index_name', 'tradedate']).reset_index(drop=True)

nse500 = indexes_df[indexes_df['index_name'] == 'NSE500'][['tradedate', 'close']].copy()
nse500.columns = ['tradedate', 'nse500_close']
nse500 = nse500.sort_values('tradedate').reset_index(drop=True)

# ============================================================================
# 2. FEATURE ENGINEERING & ALPHA SCORING
# ============================================================================
print("Calculating alpha features...")
stocks_df['ret_1d'] = stocks_df.groupby('fid')['close'].pct_change(1)
stocks_df['momentum_12_1'] = stocks_df.groupby('fid')['close'].transform(lambda x: x.pct_change(252) - x.pct_change(21))
stocks_df['vol_126d'] = stocks_df.groupby('fid')['ret_1d'].transform(lambda x: x.rolling(126, min_periods=60).std()) * np.sqrt(252)
stocks_df['avg_value_21d'] = stocks_df.groupby('fid')['traded_value'].transform(lambda x: x.rolling(21, min_periods=10).mean())

nse500['ma_200d'] = nse500['nse500_close'].rolling(200, min_periods=150).mean()
nse500['bull_regime'] = (nse500['nse500_close'] > nse500['ma_200d']).astype(int)

def calculate_score(df_day, current_date, bull_regime=1):
    df = df_day.copy()
    required = ['momentum_12_1', 'vol_126d', 'avg_value_21d', 'mcap']
    for col in required:
        if col not in df.columns: return pd.DataFrame()
        df = df[df[col].notna()].copy()

    if len(df) < 50: return pd.DataFrame()
    df = df[df['mcap'] > 0].copy().nlargest(500, 'mcap')
    df = df[df['avg_value_21d'] > df['avg_value_21d'].median()].copy()

    if len(df) < 30: return pd.DataFrame()
    
    def zscore(series): return (series - series.mean()) / series.std() if series.std() > 1e-6 else pd.Series(0, index=series.index)
    
    df['composite_score'] = 0.50 * zscore(df['momentum_12_1']) + 0.50 * zscore(-df['vol_126d'])
    df['rank'] = df['composite_score'].rank(ascending=False).astype(int)
    df['bull_regime'] = bull_regime
    return df[['fid', 'composite_score', 'rank', 'vol_126d', 'avg_value_21d', 'mcap', 'bull_regime']].copy()

# ============================================================================
# 3. PORTFOLIO MANAGER & BACKTEST ENGINE
# ============================================================================
class PortfolioManager:
    def __init__(self, initial_capital=INITIAL_CAPITAL):
        self.initial_capital = initial_capital
        self.cash            = float(initial_capital)
        self.holdings        = {} 

    def calculate_execution_price(self, row, side='buy'):
        base_price = (row['open'] + row['high'] + row['low'] + row['close']) / 4
        return base_price * (1 + TRANSACTION_COST_PER_SIDE) if side == 'buy' else base_price * (1 - TRANSACTION_COST_PER_SIDE)

    def get_current_portfolio_value(self, current_prices):
        value = self.cash
        for fid, shares in self.holdings.items():
            if fid in current_prices.index: value += shares * current_prices.loc[fid, 'close']
        return value

    def rebalance_portfolio(self, target_scores, next_day_prices, current_day_prices, n_stocks=30):
        if len(target_scores) == 0: return

        bull_regime = int(target_scores['bull_regime'].iloc[0])
        rank_lookup = target_scores.set_index('fid')['rank'].to_dict()
        current_held = set(self.holdings.keys())
        
        keep = {fid for fid in current_held if rank_lookup.get(fid, 9999) <= HOLD_RANK}
        candidates = target_scores[target_scores['rank'] <= ENTRY_RANK].sort_values('rank')

        new_entries = []
        for _, row in candidates.iterrows():
            if len(keep) + len(new_entries) >= n_stocks: break
            if row['fid'] not in keep: new_entries.append(row['fid'])

        target_fids = keep | set(new_entries)
        if len(target_fids) < n_stocks:
            for _, row in target_scores.sort_values('rank').iterrows():
                if len(target_fids) >= n_stocks: break
                target_fids.add(row['fid'])

        total_value = self.get_current_portfolio_value(current_day_prices)
        equity_allocation = total_value if bull_regime == 1 else total_value * BEAR_EQUITY_ALLOCATION
        target_value_map = {fid: (1.0 / len(target_fids)) * equity_allocation for fid in target_fids} if len(target_fids) > 0 else {}

        for fid in list(self.holdings.keys()):
            if fid not in target_fids:
                if fid in next_day_prices.index:
                    self.cash += self.holdings[fid] * self.calculate_execution_price(next_day_prices.loc[fid], 'sell')
                del self.holdings[fid]

        for fid, target_value in target_value_map.items():
            if fid not in next_day_prices.index: continue
            sell_price = self.calculate_execution_price(next_day_prices.loc[fid], 'sell')
            target_shares = int(target_value / sell_price)
            current_shares = self.holdings.get(fid, 0)
            if current_shares > target_shares:
                self.cash += (current_shares - target_shares) * sell_price
                if target_shares == 0: self.holdings.pop(fid, None)
                else: self.holdings[fid] = target_shares

        buys_needed = []
        for fid, target_value in target_value_map.items():
            if fid not in next_day_prices.index: continue
            buy_price = self.calculate_execution_price(next_day_prices.loc[fid], 'buy')
            shares_to_buy = int(target_value / buy_price) - self.holdings.get(fid, 0)
            if shares_to_buy > 0: buys_needed.append((fid, shares_to_buy, buy_price))

        total_buy_cost = sum(s * p for _, s, p in buys_needed)
        if total_buy_cost > 0:
            scale = min(1.0, self.cash / total_buy_cost)
            for fid, shares_to_buy, buy_price in buys_needed:
                scaled_shares = int(shares_to_buy * scale)
                if scaled_shares > 0:
                    self.holdings[fid] = self.holdings.get(fid, 0) + scaled_shares
                    self.cash -= scaled_shares * buy_price

    def liquidate_all(self, next_day_prices):
        for fid in list(self.holdings.keys()):
            if fid in next_day_prices.index:
                self.cash += self.holdings[fid] * self.calculate_execution_price(next_day_prices.loc[fid], 'sell')
            del self.holdings[fid]

def run_backtest(stocks_data, start_date, end_date):
    stocks_data = stocks_data[(stocks_data['tradedate'] >= start_date) & (stocks_data['tradedate'] <= end_date)].copy()
    trading_days = sorted(stocks_data['tradedate'].unique())[20:]
    
    regime_lookup = nse500.set_index('tradedate')['bull_regime'].to_dict()
    pm = PortfolioManager()
    
    results, last_rebalance_day = [], 0

    for i, current_date in enumerate(trading_days):
        day_data = stocks_data[stocks_data['tradedate'] == current_date]
        prices = day_data.set_index('fid')
        bull_regime = regime_lookup.get(current_date, 1)

        results.append({
            'date': current_date, 'portfolio_value': pm.get_current_portfolio_value(prices),
            'positions': len(pm.holdings), 'cash': pm.cash, 'bull_regime': bull_regime
        })

        if (i - last_rebalance_day >= REBALANCE_DAYS or i == 0) and i < len(trading_days) - 1:
            next_day_data = stocks_data[stocks_data['tradedate'] == trading_days[i + 1]]
            scores = calculate_score(day_data, current_date, bull_regime)
            
            if len(scores) > 0: pm.rebalance_portfolio(scores, next_day_data.set_index('fid'), prices, TOP_N_STOCKS)
            else: pm.liquidate_all(next_day_data.set_index('fid'))
            last_rebalance_day = i

    df = pd.DataFrame(results)
    df['returns'] = df['portfolio_value'].pct_change()
    return df

# ============================================================================
# 4. METRICS & TURNOVER
# ============================================================================
def calculate_performance_metrics(results_df, benchmark_df):
    perf_df = results_df.merge(benchmark_df, left_on='date', right_on='tradedate', how='left')
    perf_df['benchmark_value'] = (perf_df['nse500_close'].ffill() / perf_df['nse500_close'].ffill().iloc[0]) * INITIAL_CAPITAL
    perf_df['benchmark_returns'] = perf_df['benchmark_value'].pct_change()

    strat_cagr = (perf_df['portfolio_value'].iloc[-1] / INITIAL_CAPITAL) ** (252 / len(perf_df)) - 1
    bm_cagr = (perf_df['benchmark_value'].iloc[-1] / INITIAL_CAPITAL) ** (252 / len(perf_df)) - 1
    strat_vol = perf_df['returns'].std() * np.sqrt(252)
    bm_vol = perf_df['benchmark_returns'].std() * np.sqrt(252)

    return {
        'Strategy CAGR': f"{strat_cagr*100:.2f}%", 'Benchmark CAGR': f"{bm_cagr*100:.2f}%",
        'Strategy Volatility': f"{strat_vol*100:.2f}%", 'Benchmark Volatility': f"{bm_vol*100:.2f}%",
        'Sharpe Ratio': f"{(strat_cagr - ANNUAL_RISK_FREE_RATE) / strat_vol:.3f}"
    }, perf_df

def calculate_turnover(results_df, stocks_data):
    trading_days = sorted(results_df['date'].unique())
    rebalance_dates = [trading_days[i] for i in range(0, len(trading_days), REBALANCE_DAYS)]
    rebalance_data = stocks_data[stocks_data['tradedate'].isin(rebalance_dates)]
    regime_lookup = nse500.set_index('tradedate')['bull_regime'].to_dict()
    
    prev_portfolio, turnovers = set(), []

    for date in rebalance_dates:
        day_data = rebalance_data[rebalance_data['tradedate'] == date]
        if day_data.empty: continue
        scores = calculate_score(day_data, date, regime_lookup.get(date, 1))
        if scores.empty: continue

        rank_lookup = scores.set_index('fid')['rank'].to_dict()
        keep = {fid for fid in prev_portfolio if rank_lookup.get(fid, 9999) <= HOLD_RANK}
        candidates = scores[scores['rank'] <= ENTRY_RANK].sort_values('rank')
        
        new_entries = [row['fid'] for _, row in candidates.iterrows() if row['fid'] not in keep][:TOP_N_STOCKS - len(keep)]
        current_portfolio = keep | set(new_entries)

        if prev_portfolio:
            n = max(len(prev_portfolio), len(current_portfolio), 1)
            turnovers.append(max(len(prev_portfolio - current_portfolio), len(current_portfolio - prev_portfolio)) / n)
        prev_portfolio = current_portfolio

    return {'annualized_one_way_turnover': np.mean(turnovers) * (252 / REBALANCE_DAYS)} if turnovers else {}

# ============================================================================
# 5. EXECUTION
# ============================================================================
print("\nExecuting Full Backtest (2011-2020)...")
results_full = run_backtest(stocks_df, '2011-01-01', '2020-01-01')
nse500_full = nse500[(nse500['tradedate'] >= '2011-01-01') & (nse500['tradedate'] <= '2020-01-01')]

metrics_full, perf_full = calculate_performance_metrics(results_full, nse500_full)
turnover_stats = calculate_turnover(results_full, stocks_df)

print("\n--- PERFORMANCE SUMMARY ---")
for k, v in metrics_full.items(): print(f"{k}: {v}")
if turnover_stats: print(f"Annualized One-Way Turnover: {turnover_stats['annualized_one_way_turnover']*100:.1f}%")
print("Pipeline complete. Code executed successfully without visualizations.")