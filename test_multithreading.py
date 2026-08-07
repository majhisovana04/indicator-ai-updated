import sys
import time
import concurrent.futures
from market_service.app.market.upstox_client import UpstoxClient

# Test configuration
TOTAL_STOCKS_TO_TEST = 50
WORKERS = 5
DELAY_SECONDS = 0.2

# Just a sample of 50 well-known stocks to test the API rate limit
TEST_SYMBOLS = [
    "NSE:RELIANCE", "NSE:TCS", "NSE:HDFCBANK", "NSE:INFY", "NSE:ICICIBANK",
    "NSE:HUL", "NSE:ITC", "NSE:SBIN", "NSE:BHARTIARTL", "NSE:KOTAKBANK",
    "NSE:LT", "NSE:AXISBANK", "NSE:ASIANPAINT", "NSE:MARUTI", "NSE:SUNPHARMA",
    "NSE:TITAN", "NSE:TATASTEEL", "NSE:BAJFINANCE", "NSE:WIPRO", "NSE:ULTRACEMCO",
    "NSE:HCLTECH", "NSE:ONGC", "NSE:NTPC", "NSE:POWERGRID", "NSE:JSWSTEEL",
    
    "BSE:RELIANCE", "BSE:TCS", "BSE:HDFCBANK", "BSE:INFY", "BSE:ICICIBANK",
    "BSE:HUL", "BSE:ITC", "BSE:SBIN", "BSE:BHARTIARTL", "BSE:KOTAKBANK",
    "BSE:LT", "BSE:AXISBANK", "BSE:ASIANPAINT", "BSE:MARUTI", "BSE:SUNPHARMA",
    "BSE:TITAN", "BSE:TATASTEEL", "BSE:BAJFINANCE", "BSE:WIPRO", "BSE:ULTRACEMCO",
    "BSE:HCLTECH", "BSE:ONGC", "BSE:NTPC", "BSE:POWERGRID", "BSE:JSWSTEEL"
]

def process_symbol(client, sym, i, total):
    print(f"  [{i}/{total}] Fetching {sym}...")
    try:
        # Fetch OHLC data just like the real pipeline does
        df_ohlc = client.fetch_ohlc(sym, days=180)
        
        # Polite delay to respect rate limit
        time.sleep(DELAY_SECONDS)
        
        if df_ohlc.empty:
            return (sym, "Failed (Empty Data)")
        return (sym, f"Success ({len(df_ohlc)} rows)")
        
    except Exception as e:
        # If rate limit is hit, Upstox will throw an exception
        print(f"  [ERROR] Upstox rate limit or fetch error for {sym}: {e}", file=sys.stderr)
        time.sleep(DELAY_SECONDS)
        return (sym, f"Error: {str(e)}")

def run_test():
    print("=" * 60)
    print("🚀 STARTING MULTI-THREADING RATE LIMIT TEST")
    print(f"  Total Stocks: {TOTAL_STOCKS_TO_TEST}")
    print(f"  Workers: {WORKERS}")
    print(f"  Delay: {DELAY_SECONDS}s")
    print("=" * 60)
    
    client = UpstoxClient()
    start_time = time.time()
    
    results = []
    
    # Launch multi-threaded executor
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = [
            executor.submit(process_symbol, client, sym, i+1, TOTAL_STOCKS_TO_TEST)
            for i, sym in enumerate(TEST_SYMBOLS)
        ]
        
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    end_time = time.time()
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE")
    print(f"  Time taken: {end_time - start_time:.2f} seconds")
    
    success_count = sum(1 for r in results if "Success" in r[1])
    error_count = sum(1 for r in results if "Error" in r[1])
    
    print(f"  Successes: {success_count}/{TOTAL_STOCKS_TO_TEST}")
    print(f"  Errors (Rate Limits): {error_count}/{TOTAL_STOCKS_TO_TEST}")
    print("=" * 60)

if __name__ == "__main__":
    run_test()
