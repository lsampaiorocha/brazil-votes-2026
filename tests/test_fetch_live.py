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
