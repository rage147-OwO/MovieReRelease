import requests
from bs4 import BeautifulSoup
import json

class Web:
    KOBIS_API_KEY = "4de78bd8b0c7014328be1b70d3f44192"
    KAKAO_API_KEY = "2115eff7e535351cff2abc63d0611315"

    @classmethod
    def search_movie(cls, movie_name):
        """ 영화진흥위원회 API를 이용해 영화 정보를 가져옴 """
        url = f"http://kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieList.json?key={cls.KOBIS_API_KEY}&movieNm={movie_name}"
        response = requests.get(url)
        data = response.json()

        if not data.get("movieListResult") or not data["movieListResult"]["movieList"]:
            return None

        movie = data["movieListResult"]["movieList"][0]  # 첫 번째 검색 결과 반환
        return {
            "movie_name": movie["movieNm"],
            "release_date": movie.get("openDt", "정보 없음"),
            "genre": movie.get("genreAlt", "정보 없음"),
            "nation": movie.get("nationAlt", "정보 없음")
        }

    @classmethod
    def get_movie_image(cls, movie_name):
        """ 카카오 이미지 검색 API를 이용해 영화 포스터 가져오기 """
        url = "https://dapi.kakao.com/v2/search/image"
        headers = {"Authorization": f"KakaoAK {cls.KAKAO_API_KEY}"}
        params = {"query": f"{movie_name} 영화 포스터", "size": 1}

        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        if not data.get("documents"):
            return "이미지를 찾을 수 없습니다."

        return data["documents"][0]["image_url"]

    @classmethod
    def get_movie_details(cls, movie_name):
        """ 영화 이름으로 개봉일, 장르, 국가, 포스터 이미지를 가져옴 """
        movie_info = cls.search_movie(movie_name)
        if not movie_info:
            return {"error": "영화 정보를 찾을 수 없습니다."}

        movie_info["poster_url"] = cls.get_movie_image(movie_name)
        return movie_info

    @staticmethod
    def get_movie_schedule(theater_name):
        """ 네이버 검색을 이용해 특정 영화관의 상영 시간을 크롤링 """

        url = f"https://search.naver.com/search.naver?where=nexearch&sm=top_hty&query={theater_name}+영화시간표"

        response = requests.get(url)
        soup = BeautifulSoup(response.content, "html.parser")

        # 네이버 검색 결과에서 영화 스케줄 정보를 포함하는 div 찾기
        schedule_div = soup.select_one("div.list_tbl_box")
        if not schedule_div:
            return {"error": "해당 영화관의 상영 정보를 찾을 수 없습니다."}

        tbody = schedule_div.find("tbody", class_="_wrap_time_table")
        if not tbody:
            return {"error": "시간표 데이터를 찾을 수 없습니다."}

        data = []
        for row in tbody.find_all("tr"):
            movie_name = row.find("th", scope="row").find("a").get_text()
            row_data = row.find_all("td")
            time_list = [td.find("span", class_="time_info").get_text() for td in row_data]

            data.append({
                "movie_name": movie_name,
                "time_list": time_list
            })

        return data
    
    @staticmethod
    def getMovieList():
        # API URL
        url = "https://m.search.naver.com/p/csearch/content/qapirender.nhn?_callback=현재상영영화_q&key=MovieAPIforPList&pkid=68&where=nexearch&start=0&display=2&so=s1.dsc&q=%ED%98%84%EC%9E%AC%EC%83%81%EC%98%81%EC%98%81%ED%99%94"

        # 요청 보내기
        response = requests.get(url)

        # 영화 정보를 담을 리스트
        movies = []

        # 영화 정보 파싱을 위한 함수
        def parsingByStartAndEndWord(startWord, endWord, text):
            startIndex = text.find(startWord) + len(startWord)
            endIndex = text[startIndex:].find(endWord) + startIndex
            return text[startIndex:endIndex], text[endIndex:]

        # 응답 상태 코드 확인
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            total = soup.text.find('total')
            url = url.replace('display=2', 'display=' + str(total))
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            # 영화 리스트 파싱
            movie_elements = soup.text.split(r'<\/a>\n \n \n \n ')[1:]
            # 영화 데이터 처리
            for movie_element in movie_elements:
                movie_data = {}
                # 영화 이름 파싱
                endIndex = movie_element.find(r'<\/a>\n <\/div>\n <\/div>\n \n \n ')
                movie_data['name'] = movie_element[:endIndex]
                movie_element = movie_element[endIndex:]
                # 영화 카테고리 파싱
                movie_data['category'], movie_element = parsingByStartAndEndWord(r'<\/a>\n <\/div>\n <\/div>\n \n \n 개요<\/dt>\n ', r'<\/dd>\n ', movie_element)
                # 영화 상영시간 파싱
                movie_data['play_time'], movie_element = parsingByStartAndEndWord(r'<\/dd>\n ', r'<\/dd>\n ', movie_element)
                # 영화 개봉일 파싱
                movie_data['release_date'], movie_element = parsingByStartAndEndWord(r'<\/dd>\n <\/dl>\n \n\n 개봉<\/dt>\n ', r'<\/dd>\n ', movie_element)
                if movie_data['release_date'].startswith('n'):
                    movie_data['release_date'] = movie_data['release_date'][2:]
                # 영화 평점 파싱
                movie_data['rating'], movie_element = parsingByStartAndEndWord(r'<\/dd>\n 평점<\/span><\/dt>\n <\/i>', r'<\/span><\/dd>\n ', movie_element)
                # 이미지 URL 파싱
                image_urls = str(soup).split(r"src='")
                for image_url in image_urls[1:]:
                    url = image_url.replace(r"amp;", "")
                    endIndex = url.find(r"width=")
                    movie_data['image_url'] = url[2:endIndex-4]
                    break  # 첫 번째 이미지만 추가
                # 영화 데이터를 리스트에 추가
                movies.append(movie_data)
        return movies







if __name__ == "__main__":

    # 영화 목록 가져오기
    movies = Web.getMovieList()
    print("🎬 현재 상영 중인 영화 목록")
    for movie in movies:
        print(f"영화 제목: {movie['name']}")
        print(f"장르: {movie['category']}")
        print(f"상영 시간: {movie['play_time']}")
        print(f"개봉일: {movie['release_date']}")
        print(f"평점: {movie['rating']}")
        print(f"포스터 이미지 URL: {movie['image_url']}")
        print("-" * 30)

        
    # 영화 정보 및 포스터 검색
    movie_name = "에이리언: 로물루스"
    movie_details = Web.get_movie_details(movie_name)

    if "error" in movie_details:
        print(movie_details["error"])
    else:
        print("🎬 영화 정보")
        print("영화 제목:", movie_details["movie_name"])
        print("개봉일:", movie_details["release_date"])
        print("장르:", movie_details["genre"])
        print("국가:", movie_details["nation"])
        print("포스터 이미지 URL:", movie_details["poster_url"])
    # 특정 영화관의 상영 스케줄 검색
    theater_name = "롯데시네마 평촌"
    movie_schedule = Web.get_movie_schedule(theater_name)

    print("🎥 영화관 상영 스케줄")
    if "error" in movie_schedule:
        print(movie_schedule["error"])
    else:
        for movie in movie_schedule:
            print(f"영화: {movie['movie_name']}")
            print(f"상영 시간: {', '.join(movie['time_list'])}")
            print("-" * 30)

