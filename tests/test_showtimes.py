import json
import unittest
from datetime import date, datetime
from unittest.mock import Mock, patch

from crawler import main, naver, theaters, verify


def screening(movie_id, selected_day, date_axis, times):
    response = Mock()
    response.json.return_value = {
        "success": True,
        "result": {
            "metadata": {"dssId": movie_id},
            "dateAxis": [{"date": day, "disabled": disabled} for day, disabled in date_axis],
            "selectedDate": selected_day,
            "theaters": [{
                "placeId": "91",
                "theaterName": "테스트 극장",
                "regionDepth1": "경기",
                "runnings": [{"startTime": time} for time in times],
            }],
        },
    }
    return response


class ShowtimesTests(unittest.TestCase):
    @patch("crawler.theaters.time.sleep")
    def test_date_fallback_is_not_saved_as_requested_day(self, _sleep):
        today = date(2026, 11, 27)
        date_axis = [("2026-11-27", False), ("2026-11-28", True), ("2026-11-29", False),
                     ("2026-11-30", False), ("2026-12-04", False)]
        session = Mock()
        session.get.side_effect = [
            screening("42", "2026-11-27", date_axis, ["24:05", "17:00", "17:00", "invalid"]),
            screening("42", "2026-11-27", date_axis, ["17:00"]),
            screening("42", "2026-11-30", date_axis, ["20:00"]),
        ]

        result = theaters.get_schedule_theaters("42", session, today=today)
        self.assertEqual(result["91"].region, "경기")
        self.assertEqual(result["91"].schedule, {"2026-11-27": ["17:00", "24:05"], "2026-11-30": ["20:00"]})
        self.assertEqual([c.kwargs["params"] for c in session.get.call_args_list],
                         [None, {"date": "2026-11-29"}, {"date": "2026-11-30"}])

    def test_initial_future_date_and_wrong_film(self):
        today = date(2026, 11, 27)
        day = "2026-12-02"
        session = Mock()
        session.get.return_value = screening("42", day, [(day, False)], ["19:30"])
        self.assertEqual(theaters.get_schedule_theaters("42", session, today=today)["91"].schedule,
                         {day: ["19:30"]})
        session.get.return_value = screening("43", day, [(day, False)], ["19:30"])
        with self.assertRaises(theaters.ScheduleError):
            theaters.get_schedule_theaters("42", session, today=today)

    def test_absent_result_is_a_valid_unlisted_film(self):
        session = Mock()
        session.get.return_value.json.return_value = {"code": 200, "success": True}
        self.assertEqual(theaters.get_schedule_theaters("42", session, today=date(2026, 11, 27)), {})

    def test_place_times_belong_to_theater_and_day(self):
        today = datetime.now(theaters.KST).date().isoformat()
        times = [
            {"__typename": "MovieTime", "name": "오늘 영화", "date": today},
            {"__typename": "MovieTime", "name": "어제 영화", "date": "2020-11-26"},
        ]
        data = json.dumps({"__typename": "PlaceDetail", "base": {"__ref": "PlaceDetailBase:100"},
                           "movieTimes": times})
        self.assertEqual(theaters._parse_now_showing(data, "100"), ["오늘 영화"])
        self.assertEqual(theaters._parse_now_showing(data, "101"), [])

    def test_empty_schedule_fails_crawl_and_verification(self):
        movie = naver.Movie("영화", theaters=["91"])
        with self.assertRaises(RuntimeError):
            main._require_showtimes([movie])
        self.assertTrue(verify.check_schedule_coverage({"now_playing": [{"theater_times": {}}]},
                                                      date(2026, 11, 27)))


if __name__ == "__main__":
    unittest.main()
