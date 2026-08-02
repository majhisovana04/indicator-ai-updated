import requests
from bs4 import BeautifulSoup
import time

HEADERS = {"User-Agent": "Mozilla/5.0 (Phase-1-research-script)"}

def scrape_screener_index(index_path: str, total_pages: int = 20):
    """index_path: 'CNX500' for Nifty 500, '1005' for S&P BSE 500"""
    all_rows = []

    for page in range(1, total_pages + 1):
        url = f"https://www.screener.in/company/{index_path}/?page={page}#constituents"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        table = soup.find("table", class_="data-table")
        all_trs = table.find("tbody").find_all("tr")
        header_row, data_rows = all_trs[0], all_trs[1:]

        # Build {data-tooltip text: column index} from the header row —
        # robust to column reordering, unaffected by label wording changes.
        col_map = {}
        for i, th in enumerate(header_row.find_all("th")):
            tooltip = th.get("data-tooltip")
            if tooltip:
                col_map[tooltip] = i

        if page == 1:
            print("Detected metric columns:", list(col_map.keys()))
            if "Return on equity" not in col_map:
                print("[info] ROE not in free view, as expected — filled via yfinance separately")

        for row in data_rows:
            company_id = row.get("data-row-company-id")
            cells = row.find_all(["th", "td"])
            if not company_id or len(cells) <= max(col_map.values(), default=0):
                continue
                
            name_link = cells[1].find("a") if len(cells) > 1 else None

            # WE NO LONGER SCRAPE P/E HERE PER USER REQUEST
            all_rows.append({
                "company_id": company_id,
                "name": name_link.get_text(strip=True) if name_link else None,
                "symbol_href": name_link.get("href") if name_link else None,
                "roce": cells[col_map["Return on capital employed"]].get_text(strip=True) if "Return on capital employed" in col_map else None,
            })

        print(f"{index_path} page {page}/{total_pages}: {len(all_rows)} rows so far")
        time.sleep(2)

    return all_rows


if __name__ == "__main__":
    nifty500 = scrape_screener_index("CNX500")
    bse500 = scrape_screener_index("1005")

    from collections import OrderedDict
    
    combined = OrderedDict()
    for row in nifty500 + bse500:
        cid = row["company_id"]
        if cid not in combined:
            combined[cid] = row
                
    print(f"\nUnique companies after dedupe: {len(combined)}")
