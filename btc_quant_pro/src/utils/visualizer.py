import matplotlib.pyplot as plt
import pandas as pd

class Visualizer:
    """Handles plotting of strategy results."""
    
    @staticmethod
    def plot_price_action(df: pd.DataFrame, trendlines: dict, title="Price Action with Trendlines"):
        plt.figure(figsize=(14, 8))
        plt.plot(df.index, df['Close'], color='gray', alpha=0.5, label='Close Price')
        
        # Plot Bullish Lines
        for line in trendlines['bullish_support']:
            plt.plot([line[0], line[2]], [line[1], line[3]], color='green', linewidth=1.5, alpha=0.8)
        for line in trendlines['bullish_resistance']:
            plt.plot([line[0], line[2]], [line[1], line[3]], color='lime', linestyle='--', linewidth=1, alpha=0.6)
            
        # Plot Bearish Lines
        for line in trendlines['bearish_resistance']:
            plt.plot([line[0], line[2]], [line[1], line[3]], color='red', linewidth=1.5, alpha=0.8)
        for line in trendlines['bearish_support']:
            plt.plot([line[0], line[2]], [line[1], line[3]], color='orange', linestyle='--', linewidth=1, alpha=0.6)

        plt.title(title)
        plt.legend(['Price', 'Bullish Support (HL)', 'Bullish Resistance (HH)', 'Bearish Resistance (LH)', 'Bearish Support (LL)'])
        plt.grid(True, alpha=0.3)
        plt.show()

    @staticmethod
    def plot_portfolio(df_map: dict, combined_df: pd.DataFrame, title="BTC Multi-Strategy Portfolio"):
        plt.figure(figsize=(14, 7))
        
        # Plot Individual Strategies
        for label, df in df_map.items():
            plt.plot(df.index, df['Cumulative_Returns'], label=f'{label} Strategy', alpha=0.6, linestyle='--')
            
        # Plot Combined Portfolio
        plt.plot(combined_df.index, combined_df['Portfolio_Cumulative_Returns'], 
                 label='Combined Portfolio', linewidth=2.5, color='black')
        
        plt.title(title, fontsize=14)
        plt.xlabel('Date')
        plt.ylabel('Cumulative Returns')
        plt.legend()
        plt.grid(True, which='both', linestyle='--', alpha=0.5)
        plt.tight_layout()
        plt.show()
