import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.ticker import FuncFormatter

def plot_scheme_trends(df, scheme_name, **kwargs):
    mask = (df['scheme_name'] == scheme_name)

    for key, value in kwargs.items():
        if key in df.columns:
            mask &= (df[key] == value)

    df_filtered = df[mask].groupby(['txn_mth_id']).agg(
        txn_price_mean=('txn_price_rm', 'mean'),
        txn_price_median=('txn_price_rm', 'median')
    ).reset_index().sort_values('txn_mth_id')
    
    # Check if data exists for the scheme
    if df_filtered.empty:
        print(f"No data found for scheme: {scheme_name}")
        return

    # 2. Setup the plot
    plt.figure(figsize=(12, 6))
    sns.set_style("whitegrid")
    
    # 3. Plotting
    sns.lineplot(data=df_filtered, x='txn_mth_id', y='txn_price_mean', marker='o', label='Mean Price')
    sns.lineplot(data=df_filtered, x='txn_mth_id', y='txn_price_median', marker='s', linestyle='--', label='Median Price')
    
    # 4. Formatter for Y-axis (thousands)
    def thousands_formatter(x, pos):
        return f'{x/1000:,.0f}k'
    
    plt.gca().yaxis.set_major_formatter(FuncFormatter(thousands_formatter))
    
    # 5. Formatting
    plt.xticks(rotation=45, ha='right')
    plt.title(f'Transaction Price Trends: {scheme_name}', fontsize=14)
    plt.xlabel('Transaction Month', fontsize=12)
    plt.ylabel('Price (in thousands RM)', fontsize=12)
    plt.legend()
    plt.tight_layout()
    
    plt.show()