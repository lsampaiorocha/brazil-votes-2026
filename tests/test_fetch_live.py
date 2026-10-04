import json
from pathlib import Path

import fetch_live
from fetch_live import parse_unified_result


def test_parse_unified_result_reads_progress_turnout_and_ranked_votes_from_tse_file():
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "sp_2024_prefeito_u.json").read_text()
    )

    assert parse_unified_result(payload) == {
        "as_of": "03/12/2024 10:21:35",
        "sections_total": 26513,
        "sections_counted": 26513,
        "electorate": 9322444,
        "electorate_counted": 9322444,
        "turnout": 6773587,
        "valid": 6108218,
        "blank": 241734,
        "null": 422802,
        "candidates": [
            {
                "number": "15",
                "name": "RICARDO NUNES",
                "party": "MDB",
                "votes": 1801139,
                "status": "2º turno",
            },
            {
                "number": "50",
                "name": "GUILHERME BOULOS",
                "party": "PSOL",
                "votes": 1776127,
                "status": "2º turno",
            },
            {
                "number": "28",
                "name": "PABLO MARÇAL",
                "party": "PRTB",
                "votes": 1719274,
                "status": "Não eleito",
            },
            {
                "number": "40",
                "name": "TABATA AMARAL",
                "party": "PSB",
                "votes": 605552,
                "status": "Não eleito",
            },
            {
                "number": "45",
                "name": "DATENA",
                "party": "PSDB",
                "votes": 112344,
                "status": "Não eleito",
            },
            {
                "number": "30",
                "name": "MARINA HELENA",
                "party": "NOVO",
                "votes": 84212,
                "status": "Não eleito",
            },
            {
                "number": "80",
                "name": "RICARDO SENESE",
                "party": "UP",
                "votes": 5593,
                "status": "Não eleito",
            },
            {
                "number": "16",
                "name": "ALTINO PRAZERES",
                "party": "PSTU",
                "votes": 3017,
                "status": "Não eleito",
            },
            {
                "number": "29",
                "name": "JOÃO PIMENTA",
                "party": "PCO",
                "votes": 960,
                "status": "Não eleito",
            },
            {
                "number": "27",
                "name": "BEBETO HADDAD",
                "party": "DC",
                "votes": 833,
                "status": "Não eleito",
            },
        ],
    }


def test_parse_unified_result_has_no_timestamp_before_counting_starts():
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "sp_2024_prefeito_u.json").read_text()
    )
    payload["dt"] = ""
    payload["ht"] = ""

    assert parse_unified_result(payload)["as_of"] is None


def test_update_states_and_abroad_keeps_previous_files_when_totals_are_unavailable(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(fetch_live, "DATA", tmp_path)
    monkeypatch.setattr(fetch_live, "fetch_many", lambda areas: [None] * len(areas))

    fetch_live.update_states_and_abroad()

    assert list(tmp_path.iterdir()) == []


def test_combine_results_adds_up_areas_and_keeps_national_candidate_statuses():
    def result(as_of, counted, votes_13, votes_22, status_13=""):
        return {
            "as_of": as_of,
            "sections_total": 10,
            "sections_counted": counted,
            "electorate": 100,
            "electorate_counted": counted * 10,
            "turnout": counted * 8,
            "valid": votes_13 + votes_22,
            "blank": 1,
            "null": 2,
            "candidates": [
                {
                    "number": "13",
                    "name": "LULA",
                    "party": "PT",
                    "votes": votes_13,
                    "status": status_13,
                },
                {
                    "number": "22",
                    "name": "FLAVIO BOLSONARO",
                    "party": "PL",
                    "votes": votes_22,
                    "status": "",
                },
            ],
        }

    combined = fetch_live.combine_results(
        [
            result("04/10/2026 19:03:13", 6, 30, 50),
            result("04/10/2026 19:00:25", 4, 40, 20),
        ],
        calls_from=result("04/10/2026 18:44:02", 5, 0, 0, status_13="2º turno"),
    )

    assert combined == {
        "as_of": "04/10/2026 19:03:13",
        "sections_total": 20,
        "sections_counted": 10,
        "electorate": 200,
        "electorate_counted": 100,
        "turnout": 80,
        "valid": 140,
        "blank": 2,
        "null": 4,
        "candidates": [
            {
                "number": "13",
                "name": "LULA",
                "party": "PT",
                "votes": 70,
                "status": "2º turno",
            },
            {
                "number": "22",
                "name": "FLAVIO BOLSONARO",
                "party": "PL",
                "votes": 70,
                "status": "",
            },
        ],
    }


def test_parse_unified_result_ignores_a_totalization_time_later_than_the_file_itself():
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "sp_2024_prefeito_u.json").read_text()
    )
    payload["dg"], payload["hg"] = "04/10/2026", "19:04:22"
    payload["dt"], payload["ht"] = "05/10/2026", "09:19:47"

    assert parse_unified_result(payload)["as_of"] == "04/10/2026 19:04:22"
