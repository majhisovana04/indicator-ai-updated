import requests
from datetime import date, timedelta
from app.market.hard_filters import SurveillanceDataLoader

class DailySurveillanceFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; XaneFunds-SurveillanceLoader/1.0)",
            "Referer": "https://www.nseindia.com/all-reports",
        })
        self._cookies_fetched = False

    def _fetch_nse_cookies(self):
        if not self._cookies_fetched:
            print("Fetching NSE session cookies...")
            try:
                self.session.get("https://www.nseindia.com", timeout=10)
                self.session.get("https://www.nseindia.com/all-reports", timeout=10)
                self._cookies_fetched = True
            except requests.exceptions.RequestException as e:
                print(f"Warning: Could not fetch NSE cookies: {e}")

    def _fetch_url_with_fallback(self, url_template: str, date_format: str, exchange: str, max_days_back: int = 5) -> str:
        """
        Tries to fetch the file for today. If 404, steps back one day at a time.
        Returns the raw CSV text.
        """
        if exchange == "NSE":
            self._fetch_nse_cookies()

        today = date.today()
        for i in range(max_days_back):
            check_date = today - timedelta(days=i)
            date_str = check_date.strftime(date_format)
            url = url_template.format(ddmmyy=date_str, ddmmyyyy=date_str)
            
            print(f"  Trying {exchange} file for {check_date.isoformat()} ({url})...")
            try:
                resp = self.session.get(url, timeout=10)
                if resp.status_code == 200:
                    # BSE returns HTTP 200 with an EMPTY body on unpublished/weekend dates
                    # instead of a 404. A real file is always at least a few hundred bytes
                    # (header row alone is >50 bytes). Treat 0-byte (or suspiciously tiny)
                    # responses as "not published yet" and fall back to the previous day.
                    MIN_VALID_BYTES = 50
                    if len(resp.content) < MIN_VALID_BYTES:
                        print(f"    -> Empty response ({len(resp.content)} bytes) — treating as not published yet.")
                    else:
                        print(f"    -> Success! ({len(resp.content)} bytes)")
                        return resp.text
                elif resp.status_code == 404:
                    print("    -> Not published yet (404).")
                else:
                    print(f"    -> Failed with status {resp.status_code}.")
            except requests.exceptions.RequestException as e:
                print(f"    -> Request failed: {e}")
                
        raise FileNotFoundError(f"Could not find a published {exchange} file in the last {max_days_back} days!")

    def fetch_esm(self) -> str:
        """Fetches the latest ESM file (static URL, no date rollback)."""
        url = SurveillanceDataLoader.ESM_URL
        print(f"  Trying ESM file ({url})...")
        try:
            self._fetch_nse_cookies()
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
            print(f"    -> Success! ({len(resp.content)} bytes)")
            return resp.text
        except requests.exceptions.RequestException as e:
            print(f"    -> ESM Request failed: {e}")
            raise FileNotFoundError("Could not fetch the latest ESM file.")

    def fetch_and_load(self) -> SurveillanceDataLoader:
        """
        Fetches all 5 files into memory and parses them into a SurveillanceDataLoader.
        """
        print("=== Fetching Surveillance Data ===")
        
        nse_text = self._fetch_url_with_fallback(
            SurveillanceDataLoader.NSE_DOWNLOAD_URL_TEMPLATE, "%d%m%y", "NSE"
        )
        
        bse_long_text = self._fetch_url_with_fallback(
            SurveillanceDataLoader.BSE_LONG_ASM_URL_TEMPLATE, "%d%m%Y", "BSE"
        )
        
        bse_short_text = self._fetch_url_with_fallback(
            SurveillanceDataLoader.BSE_SHORT_ASM_URL_TEMPLATE, "%d%m%Y", "BSE"
        )
        
        bse_gsm_text = self._fetch_url_with_fallback(
            SurveillanceDataLoader.BSE_GSM_URL_TEMPLATE, "%d%m%Y", "BSE"
        )
        
        esm_text = self.fetch_esm()
        
        print("\n=== Parsing Surveillance Data ===")
        loader = SurveillanceDataLoader()
        loader.load(nse_text, bse_long_text, bse_short_text, bse_gsm_text, esm_text)
        print("Data loaded successfully into memory.")
        
        return loader


if __name__ == "__main__":
    fetcher = DailySurveillanceFetcher()
    try:
        loader = fetcher.fetch_and_load()
        print(f"\nVerification:")
        print(f"  - NSE symbols loaded: {len(loader._nse_flags)}")
        print(f"  - BSE ISINs loaded:   {len(loader._bse_isin_flags)}")
    except Exception as e:
        print(f"\nFatal Error: {e}")
