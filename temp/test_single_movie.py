import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote_plus

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def test_parsing():
    # Use the query that we know contains the list
    url = "https://search.naver.com/search.naver?where=nexearch&query=최근+영화"
    print(f"Fetching {url}...")
    
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Selectors from the main script
    links = soup.select('a.this_text._text') + soup.select('.title_box .name') + soup.select('a.tit_area')
    
    print(f"Found {len(links)} links. Searching for '몬스타엑스'...")
    
    for i, link in enumerate(links):
        visible_text = link.get_text(strip=True)
        if "몬스타엑스" in visible_text:
            print(f"\n--- Target Found: Link {i+1} ---")
            href = link.get('href')
            print(f"  Visible Text: '{visible_text}'")
            print(f"  Raw Href: '{href}'")
            
            if href and 'query=' in href:
                try:
                    after_query = href.split('query=', 1)[1]
                    raw_value = after_query.split('&', 1)[0]
                    print(f"  Raw query param value: '{raw_value}'")
                    
                    decoded_title = unquote_plus(raw_value)
                    print(f"  Decoded Title: '{decoded_title}'")
                except Exception as e:
                    print(f"  Error parsing: {e}")
            else:
                 print("  No 'query=' in href")
            break
    else:
        print("Target '몬스타엑스' not found in this query result.")

if __name__ == "__main__":
    test_parsing()
