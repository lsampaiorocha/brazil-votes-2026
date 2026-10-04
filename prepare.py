import io
import json
import logging
import zipfile
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

WEB = Path(__file__).parent / "web"
GEO = WEB / "geo"
DATA = WEB / "data"

MUNICIPALITY_CONFIG_URL = (
    "https://resultados.tse.jus.br/oficial/ele2026/6257/config/mun-e006257-cm.json"
)
IBGE_MESH_URL = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    "?intrarregiao={level}&formato=application/vnd.geo%2Bjson&qualidade=minima"
)
WORLD_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"
ARCHIVE_2022_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/{name}/{name}_2022.zip"
)

IBGE_STATE_CODES = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}  # fmt: skip


class HttpRangeFile(io.RawIOBase):
    """Seekable read-only view of a remote file, so zipfile can pull one member
    out of TSE's 642 MB archive without downloading the rest."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.position = 0
        content_range = requests.get(
            url, headers={"Range": "bytes=0-0"}, timeout=60
        ).headers
        self.size = int(content_range["Content-Range"].split("/")[1])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.position, io.SEEK_END: self.size}
        self.position = base[whence] + offset
        return self.position

    def readinto(self, buffer: bytearray) -> int:
        if self.position >= self.size:
            return 0
        end = min(self.position + len(buffer), self.size) - 1
        response = requests.get(
            self.url, headers={"Range": f"bytes={self.position}-{end}"}, timeout=60
        )
        response.raise_for_status()
        chunk = response.content
        buffer[: len(chunk)] = chunk
        self.position += len(chunk)
        return len(chunk)


def read_presidential_csv_2022(name: str, columns: list[str]) -> pd.DataFrame:
    archive = zipfile.ZipFile(
        io.BufferedReader(
            HttpRangeFile(ARCHIVE_2022_URL.format(name=name)), buffer_size=1 << 20
        )
    )
    with archive.open(f"{name}_2022_BR.csv") as csv_file:
        return pd.read_csv(csv_file, sep=";", encoding="latin1", usecols=columns)


def download_json(url: str) -> dict:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.json()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    logger.info(
        "wrote %s (%.0f KB)", path.relative_to(WEB.parent), path.stat().st_size / 1e3
    )


def build_geometry() -> None:
    states = download_json(IBGE_MESH_URL.format(level="UF"))
    for feature in states["features"]:
        feature["properties"]["uf"] = IBGE_STATE_CODES[feature["properties"]["codarea"]]
    write_json(GEO / "states.geojson", states)
    write_json(
        GEO / "municipalities.geojson",
        download_json(IBGE_MESH_URL.format(level="municipio")),
    )
    write_json(GEO / "countries-110m.json", download_json(WORLD_URL))


def build_municipality_lookup() -> None:
    config = download_json(MUNICIPALITY_CONFIG_URL)
    lookup = {
        municipality["cd"]: {
            "uf": state["cd"].upper(),
            "ibge": municipality["cdi"],
            "name": municipality["nm"],
        }
        for state in config["abr"]
        for municipality in state["mu"]
    }
    write_json(DATA / "municipality_lookup.json", lookup)


def build_2022_baseline() -> None:
    votes = read_presidential_csv_2022(
        "votacao_candidato_munzona",
        ["NR_TURNO", "CD_MUNICIPIO", "NR_CANDIDATO", "QT_VOTOS_NOMINAIS_VALIDOS"],
    )
    first_round = votes[votes.NR_TURNO == 1]
    by_municipality = (
        first_round.groupby(["CD_MUNICIPIO", "NR_CANDIDATO"])
        .QT_VOTOS_NOMINAIS_VALIDOS.sum()
        .unstack(fill_value=0)
    )
    national_valid = int(by_municipality.to_numpy().sum())
    for number in (13, 22):
        share = by_municipality[number].sum() / national_valid * 100
        logger.info(
            "2022 1st round, candidate %d: %.2f%% of valid votes", number, share
        )
    baseline = {
        f"{code:05d}": {
            "valid": int(row.sum()),
            "13": int(row[13]),
            "22": int(row[22]),
        }
        for code, row in by_municipality.iterrows()
    }
    write_json(DATA / "municipalities_2022.json", baseline)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    GEO.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    build_geometry()
    build_municipality_lookup()
    build_2022_baseline()
