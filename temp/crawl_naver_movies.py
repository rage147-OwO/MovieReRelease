import requests
from bs4 import BeautifulSoup
import time
import random
import psycopg2

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def save_to_db(movies):
    """
    Saves the list of movie dictionaries to the PostgreSQL database.
    """
    if not movies:
        print("No data to save.")
        return

    try:
        # Connect to the database based on Docker settings
        conn = psycopg2.connect(
            dbname="moviedb",
            user="myuser",
            password="mypassword",
            host="localhost",
            port="5432"
        )
        cur = conn.cursor()
        
        # Create table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                id SERIAL PRIMARY KEY,
                title TEXT UNIQUE NOT NULL,
                poster TEXT,
                genre_info TEXT,
                release_date TEXT,
                rating TEXT,
                audience TEXT,
                grade TEXT,
                crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Insert data
        print(f"Saving {len(movies)} movies to database...")
        for movie in movies:
            cur.execute("""
                INSERT INTO movies (title, poster, genre_info, release_date, rating, audience, grade)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (title) 
                DO UPDATE SET
                    poster = EXCLUDED.poster,
                    genre_info = EXCLUDED.genre_info,
                    release_date = EXCLUDED.release_date,
                    rating = EXCLUDED.rating,
                    audience = EXCLUDED.audience,
                    grade = EXCLUDED.grade,
                    crawled_at = CURRENT_TIMESTAMP;
            """, (
                movie.get('title'),
                movie.get('poster'),
                movie.get('genre_info'),
                movie.get('release_date'),
                movie.get('rating'),
                movie.get('audience'),
                movie.get('grade')
            ))
            
        conn.commit()
        cur.close()
        conn.close()
        print("Successfully saved data to database.")

    except Exception as e:
        print(f"Database error: {e}")

def get_movie_details(title):
    """
    Searches for a specific movie and extracts detailed information.
    """
    search_url = f"https://search.naver.com/search.naver?where=nexearch&query={title}"
    try:
        response = requests.get(search_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        detail = {'title': title}
        
        # Try to find the specific movie info box
        # This is heuristics-based as the layout might differ
        
        # Refine Title from Detail Page (if available)
        # Search for a strong title usually at the top of the movie info card
        detail_title_elem = soup.select_one('.cm_top_wrap .title_area strong.title') or soup.select_one('.cs_common_module .title_area strong')
        if detail_title_elem:
           detail['title'] = detail_title_elem.get_text(strip=True)
        
        # Poster
        # Usually in div.detail_info > a > img or similar, or just first img_box
        poster_img = soup.select_one('a.thumb._item img') or soup.select_one('.detail_info img') or soup.select_one('a.img_box img')
        if poster_img:
            detail['poster'] = poster_img.get('src')
            
        # Info Group (Genre, Country, Runtime, Release)
        # Often in dl.info definitions
        info_groups = soup.select('.info_group')
        for group in info_groups:
            dt = group.select_one('dt')
            dd = group.select_one('dd')
            if dt and dd:
                label = dt.get_text(strip=True)
                value = dd.get_text(strip=True)
                
                if '개요' in label:
                    detail['genre_info'] = value
                elif '개봉' in label:
                    detail['release_date'] = value
                elif '평점' in label:
                    detail['rating'] = value
                elif '관객' in label:
                    detail['audience'] = value
                elif '등급' in label:
                    detail['grade'] = value

            
        return detail

    except Exception as e:
        print(f"  Error fetching details for {title}: {e}")
        return {'title': title, 'error': str(e)}

def get_current_movies():
    # Naver Search doesn't provide a single "Show All" page for movies anymore.
    # To maximize the list (approaching the user's observed 30), we aggregate from multiple related queries.
    queries = [
        "현재상영영화",
        "최근 영화",
        "박스오피스",
        "개봉예정영화" # Optional, but might include some that are technically "out" but showing
    ]
    
    unique_movies = {}
    
    print("Finding movies from multiple sources...")
    
    for query in queries:
        print(f"Scanning query: '{query}'...")
        base_url = f"https://search.naver.com/search.naver?where=nexearch&query={query}"
        
        # Try a couple of 'start' pages just in case specific queries respond to it (unlikely for embedded lists but worth a shot)
        for start in [1]: 
            url = f"{base_url}&start={start}"
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                # Broaden selectors to capture different list styles
                # 'this_text _text' is common
                # 'name' inside 'data_area' for some lists
                links = soup.select('a.this_text._text') + soup.select('.title_box .name') + soup.select('a.tit_area') # Box office uses different sometimes
                
                found_on_page = 0
                for link in links:
                    # Priority 1: Extract from href query param (most reliable for full title)
                    href = link.get('href')
                    title_from_url = None
                    if href and 'query=' in href:
                         try:
                             from urllib.parse import unquote_plus
                             # href usually looks like: ?where=nexearch&query=%...&...
                             # Split by 'query=' and take the part after it
                             after_query = href.split('query=', 1)[1]
                             # Split by '&' to stop at the next param
                             raw_value = after_query.split('&', 1)[0]
                             
                             # Decode percent-encoding (handling + as space)
                             title_from_url = unquote_plus(raw_value)
                         except Exception:
                             pass
                    
                    # Priority 2: Title attribute
                    # Priority 3: Visible text
                    visible_text = link.get_text(strip=True)
                    title_attr = link.get('title')
                    
                    raw_title = title_from_url or title_attr or visible_text
                    
                    # Clean title if it ends with ... (fallback cleaning)
                    if raw_title and raw_title.endswith('...'):
                        raw_title = raw_title[:-3].strip()
                        
                    title = raw_title
                    
                    if title and title not in unique_movies:
                        # Filter out obviously non-movie text if selectors are too broad
                        if len(title) > 1: 
                            unique_movies[title] = None 
                            found_on_page += 1
                
                print(f"  Found {found_on_page} items.")
                time.sleep(random.uniform(0.5, 1.0))
                
            except Exception as e:
                print(f"  Error scanning {query}: {e}")

    print(f"\nFound {len(unique_movies)} unique titles. Fetching details...")
    
    results = []
    for title in unique_movies.keys():
        print(f"Fetching details for: {title}")
        details = get_movie_details(title)
        results.append(details)
        time.sleep(random.uniform(0.5, 1.0))
        
    print("\n=== Crawled Movie Data ===")
    for movie in results:
        print(movie)
        
    print("\n=== Saving to Database ===")
    save_to_db(results)

if __name__ == "__main__":
    get_current_movies()
