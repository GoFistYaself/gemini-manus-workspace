        # 7. Execute Strategy
        try:
            # print(f"DEBUG: [{self.symbol}] Entering Strategy. Signal: {final_signal}, Pos: {self.wallet.position_size}")
            self._execute_strategy(current_price, atr_15m, final_signal, final_score)
        except Exception as e:
            import traceback
            logging.error(f"Error in {self.symbol}_LIVE: {e}\n{traceback.format_exc()}")
            print(f"  !!! ERROR IN {self.symbol} STRATEGY: {e}")

    def _execute_strategy(self, price, atr, signal, score):
        try:
            w = self.wallet
            # print(f"DEBUG: [{self.symbol}] Inside _execute_strategy. Signal: {signal}")
            
            # Aggressive Demo Mode: Skip Whipsaw protection
            current_risk_pct = self.risk_per_trade

            # Manage Existing Position
            if w.position_size != 0:
                # --- SAFETY CHECK (v5.1.2) ---
                if w.entry_price is None or w.stop_loss is None:
                    print(f"  [ERROR] Corrupt position for {self.symbol} (NULL state). Closing for safety.")
                    w.position_size = 0.0
                    return

                # --- PROFESSIONAL: DYNAMIC TRAILING STOP ---
                # Lock in profits as price moves in our favor, trailing by 0.5x ATR
                trail_dist = atr * 0.5
                if w.position_size > 0:
                    new_sl = price - trail_dist
                    if new_sl > w.stop_loss and price > w.entry_price + (atr * 0.3):
                        w.stop_loss = new_sl
                        print(f"  [INSTITUTIONAL] Trailing Stop updated to {new_sl:.8f} for {self.symbol}")
                elif w.position_size < 0:
                    new_sl = price + trail_dist
                    if new_sl < w.stop_loss and price < w.entry_price - (atr * 0.3):
                        w.stop_loss = new_sl
                        print(f"  [INSTITUTIONAL] Trailing Stop updated to {new_sl:.8f} for {self.symbol}")

                # Check Stop Loss
                if w.position_size > 0 and price < w.stop_loss:
                    if w.close_position(price, "STOP LOSS"):
                        self.fortress.report_trade("CLOSE (SL)", self.symbol, price, w.position_size)
                        self.shadow.record_event("TRADE_CLOSE", {"reason": "STOP_LOSS", "price": price, "pnl": w.last_pnl})
                    return
                elif w.position_size < 0 and price > w.stop_loss:
                    if w.close_position(price, "STOP LOSS"):
                        self.fortress.report_trade("CLOSE (SL)", self.symbol, price, w.position_size)
                        self.shadow.record_event("TRADE_CLOSE", {"reason": "STOP_LOSS", "price": price, "pnl": w.last_pnl})
                    return
                
                # Check Take Profit
                if w.take_profit > 0:
                    if w.position_size > 0 and price > w.take_profit:
                        if w.close_position(price, "TAKE PROFIT"):
                            self.fortress.report_trade("CLOSE (TP)", self.symbol, price, w.position_size)
                            self.shadow.record_event("TRADE_CLOSE", {"reason": "TAKE_PROFIT", "price": price, "pnl": w.last_pnl})
                        return
                    elif w.position_size < 0 and price < w.take_profit:
                        if w.close_position(price, "TAKE PROFIT"):
                            self.fortress.report_trade("CLOSE (TP)", self.symbol, price, w.position_size)
                            self.shadow.record_event("TRADE_CLOSE", {"reason": "TAKE_PROFIT", "price": price, "pnl": w.last_pnl})
                        return
                
                # Trailing Stop Logic (Walking up the profit)
                trail_dist = atr * 0.5 # Walk with 0.5 ATR distance
                if w.position_size > 0 and price > w.entry_price + (atr * 1.5):
                    new_sl = price - trail_dist
                    if new_sl > w.stop_loss: w.stop_loss = new_sl
                elif w.position_size < 0 and price < w.entry_price - (atr * 1.5):
                    new_sl = price + trail_dist
                    if new_sl < w.stop_loss: w.stop_loss = new_sl
                        
                if (w.position_size > 0 and signal == -1) or (w.position_size < 0 and signal == 1):
                    if w.close_position(price, "Reverse Signal"):
                        self.fortress.report_trade("CLOSE (Reverse)", self.symbol, price, w.position_size)

            # Entry Logic (v5.5 - DUST DEFIANCE)
            # Allow entry if no position exists OR if the current position is just 'dust' (< $10)
            is_dust = abs(w.position_size * price) < 10.0
            if (w.position_size == 0 or is_dust) and signal != 0:
                # 1. Calculate Stop Loss Distance
                sl_dist = atr * self.sl_mult
                
                # 2. Calculate Position Size based on Risk
                risk_amt = w.equity * current_risk_pct
                size_risk = risk_amt / sl_dist if sl_dist > 0 else 0
                
                # 3. Apply Spot Market Cap (Coinbase One)
                # We allocate a max of 25% of total equity to any single trade to leave room for other assets
                max_spend = w.equity * 0.25 
                
                # Boost spend for high conviction
                if abs(score) >= 3.0: max_spend = w.equity * 0.50
                
                max_size_spot = max_spend / price
                final_size = min(size_risk, max_size_spot)
                leverage_cap = 1.0 # Spot market
                
                # MINIMUM SIZE ENFORCEMENT ($10 USD roughly)
                min_size = 10.0 / price 
                if final_size < min_size:
                    final_size = min_size
                    print(f"  [ADJUST] Small account; bumping size to minimum ${10.0:.2f}")

                if signal == -1: final_size = -final_size
                
                sl_price = price - sl_dist if signal == 1 else price + sl_dist
                tp_price = price + (atr * self.tp_mult) if signal == 1 else price - (atr * self.tp_mult)
                
                # --- NEW: FIBONACCI EXTENSION TP (v3.4) ---
                if signal == 1: 
                    # Detect pivots and get targets
                    df_with_pivots = AdvancedPatterns.detect_fib_pivots(self.buffers['15m'])
                    fib = AdvancedPatterns.get_fib_targets(df_with_pivots)
                    if fib and fib['target_161'] > price:
                        old_tp = tp_price
                        tp_price = fib['target_161']
                        print(f"  [FIB SNIPER] Target Upgraded for {self.symbol}: ${old_tp:.2f} -> ${tp_price:.2f} (1.618 Ext)")

                if w.open_position(price, final_size, sl_price, tp_price, leverage_cap):
                    self.fortress.report_trade("OPEN", self.symbol, price, final_size)
                    self.shadow.record_event("TRADE_OPEN", {
                        "asset": self.symbol,
                        "price": price,
                        "size": final_size,
                        "sl": sl_price,
                        "tp": tp_price,
                        "leverage": leverage_cap,
                        "score": score
                    })
        except Exception as e:
            import traceback
            logging.error(f"Error in {self.symbol}_STRATEGY: {e}\n{traceback.format_exc()}")
            print(f"  !!! ERROR IN {self.symbol} STRATEGY: {e}")
