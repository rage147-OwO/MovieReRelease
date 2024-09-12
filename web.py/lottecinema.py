import requests
from bs4 import BeautifulSoup
import numpy as np


class Web:
    @classmethod
    def search_movie(cls, movie_name):
        # HTTP Get Request
        url = "http://kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieList.json?key=4de78bd8b0c7014328be1b70d3f44192"
        # 변수 movieNm에 영화 제목
        url = url + "&movieNm=" + movie_name
        response = requests.get(url)
        data = response.json()
        return data
    @staticmethod
    def get_movie_schedule(place, company):

        # 롯데시네마의 영화 스케줄 페이지 URL
        url = f'https://search.naver.com/search.naver?where=nexearch&sm=top_hty&fbm=0&ie=utf8&query={place}+{company}'

        # 웹페이지 요청
        response = requests.get(url)
        # BeautifulSoup을 사용하여 HTML 파싱
        soup = BeautifulSoup(response.content, "html.parser")

        # 영화관 리스트를 포함한 div 선택
        schedule_div = soup.select_one("div.list_tbl_box")
        if not schedule_div:
            print("No schedule found.")
            return

        # <tbody class="_wrap_time_table">를 포함한 부분 선택"
        tbody = schedule_div.find("tbody", class_="_wrap_time_table")

        #prettify()를 사용하여 HTML을 예쁘게 출력
        if not tbody:
            print("No tbody found.")
            return
        data = []
        # 각 영화 항목 찾기
        for row in tbody.find_all("tr"):
            #print(row.prettify())
            #td로 구분하며 추출
            #title 태그를 찾아서 영화 제목 추출
            movie_name = row.find("th",scope="row").find("a").get_text()
            row_data = row.find_all("td")
            time = [data.find("span", class_="time_info").get_text() for data in row_data]
            data.append({
                "movie_name": movie_name,
                "time_info": time[0],
            })
        return data





if __name__ == "__main__":
    print(Web.get_movie_schedule("롯데시네마", "인덕원"))
    print(Web.search_movie("에이리언: 로물루스"))