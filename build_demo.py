import csv
import logging

import pandas as pd

from prepare import WEB, read_presidential_csv_2022, write_json

logger = logging.getLogger(__name__)

DEMO = WEB / "data-demo"


def build_result(
    votes: pd.DataFrame, details: pd.DataFrame, candidates: pd.DataFrame
) -> dict:
    votes_by_number = votes.groupby("NR_CANDIDATO").QT_VOTOS_NOMINAIS_VALIDOS.sum()
    totalized_at = pd.to_datetime(
        details.DT_ULTIMA_TOTALIZACAO + " " + details.HH_ULTIMA_TOTALIZACAO,
        format="%d/%m/%Y %H:%M:%S",
    ).max()
    result_candidates = [
        {
            "number": str(row.NR_CANDIDATO),
            "name": row.NM_URNA_CANDIDATO,
            "party": row.SG_PARTIDO,
            "votes": int(votes_by_number.get(row.NR_CANDIDATO, 0)),
            "status": "",
        }
        for row in candidates.itertuples()
    ]
    result_candidates.sort(
        key=lambda candidate: (-candidate["votes"], candidate["number"])
    )
    sections = int(details.QT_TOTAL_SECOES.sum())
    return {
        "as_of": totalized_at.strftime("%d/%m/%Y %H:%M:%S"),
        "sections_total": sections,
        "sections_counted": sections,
        "electorate": int(details.QT_APTOS.sum()),
        "turnout": int(details.QT_COMPARECIMENTO.sum()),
        "valid": int(details.QT_TOTAL_VOTOS_VALIDOS.sum()),
        "blank": int(details.QT_VOTOS_BRANCOS.sum()),
        "null": int(details.QT_TOTAL_VOTOS_NULOS.sum()),
        "candidates": result_candidates,
    }


def main() -> None:
    votes = read_presidential_csv_2022(
        "votacao_candidato_munzona",
        [
            "NR_TURNO",
            "SG_UF",
            "CD_MUNICIPIO",
            "NR_CANDIDATO",
            "NM_URNA_CANDIDATO",
            "SG_PARTIDO",
            "QT_VOTOS_NOMINAIS_VALIDOS",
        ],
    )
    details = read_presidential_csv_2022(
        "detalhe_votacao_munzona",
        [
            "NR_TURNO",
            "SG_UF",
            "CD_MUNICIPIO",
            "QT_APTOS",
            "QT_TOTAL_SECOES",
            "QT_COMPARECIMENTO",
            "QT_TOTAL_VOTOS_VALIDOS",
            "QT_VOTOS_BRANCOS",
            "QT_TOTAL_VOTOS_NULOS",
            "HH_ULTIMA_TOTALIZACAO",
            "DT_ULTIMA_TOTALIZACAO",
        ],
    )
    first_votes, first_details = (
        votes[votes.NR_TURNO == 1],
        details[details.NR_TURNO == 1],
    )
    candidates = first_votes.drop_duplicates("NR_CANDIDATO")[
        ["NR_CANDIDATO", "NM_URNA_CANDIDATO", "SG_PARTIDO"]
    ]
    fetched_at = "2022-10-02T23:59:00-03:00"

    def result_for(mask_votes: pd.Series, mask_details: pd.Series) -> dict:
        return build_result(
            first_votes[mask_votes], first_details[mask_details], candidates
        )

    abroad = result_for(first_votes.SG_UF == "ZZ", first_details.SG_UF == "ZZ")
    write_json(
        DEMO / "states.json",
        {
            "fetched_at": fetched_at,
            "national": result_for(
                first_votes.SG_UF.notna(), first_details.SG_UF.notna()
            ),
            "abroad": abroad,
            "states": {
                state: result_for(
                    first_votes.SG_UF == state, first_details.SG_UF == state
                )
                for state in sorted(first_details.SG_UF.unique())
                if state != "ZZ"
            },
        },
    )

    cities = []
    abroad_codes = set(
        first_details[first_details.SG_UF == "ZZ"].CD_MUNICIPIO.astype(int)
    )
    for city in csv.DictReader((WEB.parent / "abroad_cities.csv").open()):
        code = int(city["tse_code"])
        if code not in abroad_codes:
            continue
        cities.append(
            {
                "code": city["tse_code"],
                "city": city["city"],
                "country": city["country"],
                "region": city["region"],
                "lat": float(city["lat"]),
                "lon": float(city["lon"]),
                **result_for(
                    first_votes.CD_MUNICIPIO == code,
                    first_details.CD_MUNICIPIO.astype(int) == code,
                ),
            }
        )
    write_json(
        DEMO / "abroad.json",
        {"fetched_at": fetched_at, "total": abroad, "cities": cities},
    )

    # The swing tab compares against the 2022 first round, so the demo feeds it the 2022 runoff.
    runoff_votes = votes[(votes.NR_TURNO == 2) & (votes.SG_UF != "ZZ")]
    runoff_details = details[(details.NR_TURNO == 2) & (details.SG_UF != "ZZ")]
    runoff_by_candidate = runoff_votes.pivot_table(
        index="CD_MUNICIPIO",
        columns="NR_CANDIDATO",
        values="QT_VOTOS_NOMINAIS_VALIDOS",
        aggfunc="sum",
        fill_value=0,
    )
    runoff_totals = runoff_details.groupby("CD_MUNICIPIO")[
        ["QT_TOTAL_SECOES", "QT_APTOS", "QT_TOTAL_VOTOS_VALIDOS"]
    ].sum()
    municipalities = {
        f"{int(code):05d}": {
            "sections_total": int(row.QT_TOTAL_SECOES),
            "sections_counted": int(row.QT_TOTAL_SECOES),
            "electorate": int(row.QT_APTOS),
            "valid": int(row.QT_TOTAL_VOTOS_VALIDOS),
            "13": int(runoff_by_candidate.loc[code, 13]),
            "22": int(runoff_by_candidate.loc[code, 22]),
        }
        for code, row in runoff_totals.iterrows()
    }
    write_json(
        DEMO / "municipalities_2026.json",
        {"fetched_at": "2022-10-30T23:59:00-03:00", "municipalities": municipalities},
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    DEMO.mkdir(parents=True, exist_ok=True)
    main()
