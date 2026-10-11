# ============================================================================
# PORTFOLIO MANAGER 
# ============================================================================
print("\n" + "="*80)
print("PORTFOLIO MANAGER (RANK BUFFER + DELISTED FIX)")
print("="*80)

BEAR_EQUITY_ALLOCATION = 0.50

class PortfolioManager:

    def __init__(self, initial_capital=INITIAL_CAPITAL):
        self.initial_capital = initial_capital
        self.cash            = float(initial_capital)
        self.holdings        = {} 

    def calculate_execution_price(self, row, side='buy'):
        """T+1 execution at (O+H+L+C)/4 ± transaction costs."""
        base_price = (row['open'] + row['high'] + row['low'] + row['close']) / 4
        if side == 'buy':
            return base_price * (1 + TRANSACTION_COST_PER_SIDE)
        return base_price * (1 - TRANSACTION_COST_PER_SIDE)

    def get_current_portfolio_value(self, current_prices):
        """NAV marked at day T close. No look-ahead."""
        value = self.cash
        for fid, shares in self.holdings.items():
            if fid in current_prices.index:
                value += shares * current_prices.loc[fid, 'close']
        return value

    def rebalance_portfolio(self, target_scores, next_day_prices,
                            current_day_prices, n_stocks=30):

        if len(target_scores) == 0:
            return

        bull_regime = int(target_scores['bull_regime'].iloc[0])

        # ── RANK BUFFER: build target portfolio ───────────────────────────────
        rank_lookup  = target_scores.set_index('fid')['rank'].to_dict()
        current_held = set(self.holdings.keys())
        
        keep = {fid for fid in current_held
                if rank_lookup.get(fid, 9999) <= HOLD_RANK}

        candidates = target_scores[
            target_scores['rank'] <= ENTRY_RANK
        ].sort_values('rank')

        new_entries = []
        for _, row in candidates.iterrows():
            if len(keep) + len(new_entries) >= n_stocks:
                break
            if row['fid'] not in keep:
                new_entries.append(row['fid'])

        target_fids = keep | set(new_entries)

        if len(target_fids) < n_stocks:
            for _, row in target_scores.sort_values('rank').iterrows():
                if len(target_fids) >= n_stocks:
                    break
                target_fids.add(row['fid'])

        # ── Equity allocation ─────────────────────────────────────────────────
        total_value = self.cash
        for fid, shares in self.holdings.items():
            if fid in current_day_prices.index:
                total_value += shares * current_day_prices.loc[fid, 'close']

        if bull_regime == 1:
            equity_allocation = total_value
        else:
            equity_allocation = total_value * BEAR_EQUITY_ALLOCATION

        n        = len(target_fids)
        equal_wt = 1.0 / n if n > 0 else 0
        target_value_map = {fid: equal_wt * equity_allocation
                            for fid in target_fids}

        # ── SELL ─────────────────────────────
        for fid in list(self.holdings.keys()):
            if fid not in target_fids:
                shares = self.holdings[fid]

                if fid in next_day_prices.index:
                    sell_price  = self.calculate_execution_price(
                        next_day_prices.loc[fid], side='sell'
                    )
                    self.cash  += shares * sell_price
                elif fid in current_day_prices.index:
                    sell_price  = current_day_prices.loc[fid, 'close']
                    self.cash  += shares * sell_price
                else:
                    pass
                del self.holdings[fid]

        # ── SELL DOWN: trim overweight positions ──────────────────────────────
        for fid, target_value in target_value_map.items():
            if fid not in next_day_prices.index:
                continue
            sell_price     = self.calculate_execution_price(
                next_day_prices.loc[fid], side='sell'
            )
            target_shares  = int(target_value / sell_price)
            current_shares = self.holdings.get(fid, 0)
            if current_shares > target_shares:
                diff = current_shares - target_shares
                self.cash += diff * sell_price
                if target_shares == 0:
                    self.holdings.pop(fid, None)
                else:
                    self.holdings[fid] = target_shares

        # ── BUY: build up underweight positions ───────────────────────────────
        buys_needed = []

        for fid, target_value in target_value_map.items():
            if fid not in next_day_prices.index:
                continue
            buy_price      = self.calculate_execution_price(
                next_day_prices.loc[fid], side='buy'
            )
            target_shares  = int(target_value / buy_price)
            current_shares = self.holdings.get(fid, 0)
            shares_to_buy  = target_shares - current_shares
            if shares_to_buy > 0:
                buys_needed.append((fid, shares_to_buy, buy_price))

        total_buy_cost = sum(s * p for _, s, p in buys_needed)

        if total_buy_cost > 0:
            scale = min(1.0, self.cash / total_buy_cost)
            for fid, shares_to_buy, buy_price in buys_needed:
                scaled_shares = int(shares_to_buy * scale)
                if scaled_shares > 0:
                    cost = scaled_shares * buy_price
                    self.holdings[fid] = self.holdings.get(fid, 0) + scaled_shares
                    self.cash         -= cost

    def liquidate_all(self, next_day_prices):
        """Exit all positions at T+1 avg price minus costs."""
        for fid in list(self.holdings.keys()):
            if fid in next_day_prices.index:
                shares     = self.holdings[fid]
                sell_price = self.calculate_execution_price(
                    next_day_prices.loc[fid], side='sell'
                )
                self.cash += shares * sell_price
            del self.holdings[fid]

# ============================================================================
# BACKTEST ENGINE
# ============================================================================
print("\n" + "="*80)
print("BACKTEST ENGINE")
print("="*80)

WARMUP_DAYS = 20 

def run_backtest(stocks_data, start_date, end_date,
                 initial_capital=INITIAL_CAPITAL):

    stocks_data = stocks_data[
        (stocks_data['tradedate'] >= start_date) &
        (stocks_data['tradedate'] <= end_date)
    ].copy()

    trading_days = sorted(stocks_data['tradedate'].unique())
    trading_days = trading_days[WARMUP_DAYS:]

    if len(trading_days) == 0:
        raise ValueError("No trading days after warmup. Dataset too short.")

    regime_lookup = nse500.set_index('tradedate')['bull_regime'].to_dict()

    pm                 = PortfolioManager(initial_capital=initial_capital)
    portfolio_values   = []
    dates              = []
    position_counts    = []
    cash_levels        = []
    regime_log         = []
    last_rebalance_day = 0

    for i, current_date in enumerate(trading_days):

        current_day_data = stocks_data[
            stocks_data['tradedate'] == current_date
        ].copy()

        current_prices = current_day_data.set_index('fid')[
            ['close', 'open', 'high', 'low']
        ]

        portfolio_value = pm.get_current_portfolio_value(current_prices)
        portfolio_values.append(portfolio_value)
        dates.append(current_date)
        position_counts.append(len(pm.holdings))
        cash_levels.append(pm.cash)

        bull_regime = regime_lookup.get(current_date, 1)
        regime_log.append(bull_regime)

        should_rebalance = (
            (i - last_rebalance_day >= REBALANCE_DAYS) or (i == 0)
        )

        if should_rebalance and i < len(trading_days) - 1:
            scores = calculate_score(current_day_data, current_date,
                                     bull_regime=bull_regime)

            next_date       = trading_days[i + 1]
            next_day_data   = stocks_data[
                stocks_data['tradedate'] == next_date
            ].copy()
            next_day_prices = next_day_data.set_index('fid')[
                ['close', 'open', 'high', 'low']
            ]

            if len(scores) > 0:
                pm.rebalance_portfolio(
                    target_scores      = scores,
                    next_day_prices    = next_day_prices,
                    current_day_prices = current_prices,
                    n_stocks           = TOP_N_STOCKS
                )
            else:
                pm.liquidate_all(next_day_prices)

            last_rebalance_day = i

    results_df = pd.DataFrame({
        'date':            dates,
        'portfolio_value': portfolio_values,
        'positions':       position_counts,
        'cash':            cash_levels,
        'bull_regime':     regime_log
    })
    results_df['returns'] = results_df['portfolio_value'].pct_change()
    return results_df