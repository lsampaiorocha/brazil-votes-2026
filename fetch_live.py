import argparse
import csv
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA = ROOT / "web" / "data"
BRASILIA = ZoneInfo("America/Sao_Paulo")
BASE_URL = "https://resultados.tse.jus.br/oficial/ele2026/6257/dados"
STATES = [
    "ac",
    "al",
    "am",
    "ap",
    "ba",
    "ce",
    "df",
    "es",
    "go",
    "ma",
    "mg",
    "ms",
    "mt",
    "pa",
    "pb",
    "pe",
    "pi",
    "pr",
    "rj",
    "rn",
    "ro",
    "rr",
    "rs",
    "sc",
    "se",
    "sp",
    "to",
]
STATE_INTERVAL_SECONDS = 120
MUNICIPALITY_INTERVAL_SECONDS = 600
# TSE blocks an IP for 10 minutes above 100 requests/second.
MAX_REQUESTS_PER_SECOND = 40

session = requests.Session()
# Two 8-thread pools (states, municipalities) can run at once and share this session.
session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=16))
last_good_results: dict[str, dict] = {}


class RateLimiter:
    def __init__(self, per_second: float) -> None:
        self.interval = 1 / per_second
        self.lock = threading.Lock()
        self.next_slot = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = self.next_slot - now
            self.next_slot = max(now, self.next_slot) + self.interval
        if delay > 0:
            time.sleep(delay)


rate_limiter = RateLimiter(MAX_REQUESTS_PER_SECOND)


def parse_timestamp(text: str) -> datetime:
    return datetime.strptime(text, "%d/%m/%Y %H:%M:%S").replace(tzinfo=BRASILIA)


def combine_results(results: list[dict], calls_from: dict) -> dict:
    votes_by_number: dict[str, int] = {}
    for result in results:
        for candidate in result["candidates"]:
            votes_by_number[candidate["number"]] = (
                votes_by_number.get(candidate["number"], 0) + candidate["votes"]
            )
    candidates = [
        {**candidate, "votes": votes_by_number.get(candidate["number"], 0)}
        for candidate in calls_from["candidates"]
    ]
    candidates.sort(key=lambda candidate: (-candidate["votes"], candidate["number"]))
    totalized = [result["as_of"] for result in results if result["as_of"]]
    combined = {
        key: sum(result[key] for result in results)
        for key in (
            "sections_total",
            "sections_counted",
            "electorate",
            "electorate_counted",
            "turnout",
            "valid",
            "blank",
            "null",
        )
    }
    return {
        "as_of": max(totalized, key=parse_timestamp) if totalized else None,
        **combined,
        "decided": calls_from.get("decided", False),
        "candidates": candidates,
    }


def parse_unified_result(payload: dict) -> dict:
    candidates = [
        {
            "number": candidate["n"],
            "name": candidate["nmu"],
            "party": party["sg"],
            "votes": int(candidate["vap"]),
            "status": candidate["st"],
        }
        for office in payload["carg"]
        for coalition in office["agr"]
        for party in coalition["par"]
        for candidate in party["cand"]
    ]
    candidates.sort(key=lambda candidate: (-candidate["votes"], candidate["number"]))
    totalized_at = f"{payload['dt']} {payload['ht']}".strip()
    generated_at = f"{payload['dg']} {payload['hg']}"
    # The abroad file stamps totalization in a foreign local time (it read "05/10 09:19" on the
    # evening of 04/10), so a totalization time later than the file itself falls back to the file time.
    if totalized_at and parse_timestamp(totalized_at) > parse_timestamp(generated_at):
        totalized_at = generated_at
    return {
        "as_of": totalized_at or None,
        "sections_total": int(payload["s"]["ts"]),
        "sections_counted": int(payload["s"]["st"]),
        "electorate": int(payload["e"]["te"]),
        "electorate_counted": int(payload["e"]["esa"]),
        "turnout": int(payload["e"]["c"]),
        "valid": int(payload["v"]["vv"]),
        "blank": int(payload["v"]["vb"]),
        "null": int(payload["v"]["tvn"]),
        "decided": payload.get("md") == "s",
        "candidates": candidates,
    }


def fetch_result(area: str, state: str) -> dict | None:
    url = f"{BASE_URL}/{state}/{area}-c0001-e006257-u.json"
    rate_limiter.wait()
    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
        result = parse_unified_result(response.json())
    except (
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
    ) as error:
        # Keep showing the previous numbers for this area instead of blanking it.
        logger.warning("%s: %s", area, error)
        return last_good_results.get(area)
    last_good_results[area] = result
    return result


def fetch_many(areas: list[tuple[str, str]]) -> list[dict | None]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(lambda area: fetch_result(*area), areas))


def write_json_atomically(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    os.replace(temporary, path)


def update_states_and_abroad() -> None:
    abroad_cities = list(csv.DictReader((ROOT / "abroad_cities.csv").open()))
    areas = [("br", "br"), ("zz", "zz")] + [(state, state) for state in STATES]
    areas += [(f"zz{city['tse_code']}", "zz") for city in abroad_cities]
    results = fetch_many(areas)
    national, abroad, *rest = results
    if not national or not abroad:
        # Writing null totals would blank the page for every viewer; keep the previous files.
        logger.warning("national or abroad totals unavailable, keeping previous files")
        return
    state_results = rest[: len(STATES)]
    city_results = rest[len(STATES) :]
    if all(state_results):
        # TSE's national file can freeze while the state files keep updating (it stalled for
        # 20+ minutes at 47% on election night), so use the sum of the parts when it is ahead.
        # Candidate statuses (elected, runoff) still come from TSE's national file.
        summed = combine_results([*state_results, abroad], calls_from=national)
        if summed["sections_counted"] > national["sections_counted"]:
            national = summed
    fetched_at = datetime.now(BRASILIA).isoformat(timespec="seconds")
    write_json_atomically(
        DATA / "states.json",
        {
            "fetched_at": fetched_at,
            "national": national,
            "abroad": abroad,
            "states": {
                state.upper(): result
                for state, result in zip(STATES, state_results)
                if result
            },
        },
    )
    write_json_atomically(
        DATA / "abroad.json",
        {
            "fetched_at": fetched_at,
            "total": abroad,
            "cities": [
                {
                    "code": city["tse_code"],
                    "city": city["city"],
                    "country": city["country"],
                    "region": city["region"],
                    "lat": float(city["lat"]),
                    "lon": float(city["lon"]),
                    **result,
                }
                for city, result in zip(abroad_cities, city_results)
                if result
            ],
        },
    )
    if national:
        logger.info(
            "states + abroad updated: %s of %s sections counted nationally",
            f"{national['sections_counted']:,}",
            f"{national['sections_total']:,}",
        )


def update_municipalities() -> None:
    lookup = json.loads((DATA / "municipality_lookup.json").read_text())
    codes = [code for code, place in lookup.items() if place["uf"] != "ZZ"]
    areas = [
        (f"{lookup[code]['uf'].lower()}{code}", lookup[code]["uf"].lower())
        for code in codes
    ]
    results = fetch_many(areas)
    municipalities = {}
    for code, result in zip(codes, results):
        if not result:
            continue
        votes_by_number = {c["number"]: c["votes"] for c in result["candidates"]}
        municipalities[code] = {
            "sections_total": result["sections_total"],
            "sections_counted": result["sections_counted"],
            "electorate": result["electorate"],
            "valid": result["valid"],
            "13": votes_by_number.get("13", 0),
            "22": votes_by_number.get("22", 0),
        }
    write_json_atomically(
        DATA / "municipalities_2026.json",
        {
            "fetched_at": datetime.now(BRASILIA).isoformat(timespec="seconds"),
            "municipalities": municipalities,
        },
    )
    logger.info("municipalities updated: %d of %d", len(municipalities), len(codes))


def run_logging_errors(update: Callable[[], None]) -> None:
    try:
        update()
    except Exception:
        # One bad cycle must not stop the poller for the rest of the night.
        logger.exception("%s failed", update.__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--once", action="store_true", help="run one full cycle and exit"
    )
    arguments = parser.parse_args()
    if arguments.once:
        update_states_and_abroad()
        update_municipalities()
        return
    last_municipality_update = float("-inf")
    municipality_worker = None
    while True:
        cycle_started = time.monotonic()
        # A municipality sweep takes ~3 minutes, so it runs beside the state updates.
        due = cycle_started - last_municipality_update >= MUNICIPALITY_INTERVAL_SECONDS
        if due and not (municipality_worker and municipality_worker.is_alive()):
            municipality_worker = threading.Thread(
                target=run_logging_errors, args=(update_municipalities,), daemon=True
            )
            municipality_worker.start()
            last_municipality_update = cycle_started
        run_logging_errors(update_states_and_abroad)
        time.sleep(max(0, STATE_INTERVAL_SECONDS - (time.monotonic() - cycle_started)))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S"
    )
    main()
