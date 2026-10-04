# Brazil Votes 2026

A live, unofficial dashboard of Brazil's 2026 presidential election (first round, October 4), built on the Superior Electoral Court's (TSE) public results feed.

**Live site:** https://lsampaiorocha.github.io/brazil-votes-2026/
**Preview with real 2022 results:** https://lsampaiorocha.github.io/brazil-votes-2026/?demo

Official results are at [resultados.tse.jus.br](https://resultados.tse.jus.br).

## What it shows

| Tab | Card (exportable as a 1080 × 1350 PNG) | Side panel |
|---|---|---|
| Brazil, live | State map colored by the leading candidate, share of valid votes against the 50% runoff line, % of sections counted, turnout | Treemap of states sized by registered voters, grouped by region |
| Abroad | World map of the 186 cities where Brazilians abroad vote (president only) | Treemap of cities sized by registered voters, grouped by world region |
| Swing since 2022 | Municipality map of the change in a candidate number's share of valid votes since the 2022 first round (#13 Lula vs. Lula, #22 Flávio vs. Jair Bolsonaro) | Definitions |

A municipality appears on the swing map once at least 90% of its sections are counted, because early partial counts are skewed.

## How it works

```
TSE results feed ──> fetch_live.py ──> web/data/*.json ──> publish_loop.sh ──> GitHub Pages
 (every 2 min)        (≤ 40 req/s)                          (every 10 min)      (web/index.html)
```

- `fetch_live.py` polls TSE's results JSON for the national, state and abroad totals every 2 minutes, and all 5,571 municipalities every 10 minutes. It stays well under TSE's limit of 100 requests per second per IP.
- `prepare.py` is a one-off step. It downloads the state and municipality meshes (IBGE) and the world map (Natural Earth via world-atlas), builds the TSE → IBGE municipality lookup, and builds the 2022 first-round baseline. It pulls only the presidential file out of TSE's 642 MB archive using HTTP range requests.
- `build_demo.py` builds `web/data-demo/` from the real 2022 results, so the page can be previewed with `?demo` before 2026 data exists.
- `abroad_cities.csv` maps TSE's codes for the 186 cities abroad to a city, country, world region and coordinates. Every point was checked against its country's border.
- `web/index.html` is a single page (D3 v7) that re-reads the data every minute.

## Run it locally

Requires Python 3.12 with `requests` and `pandas`.

```bash
python3 prepare.py                      # meshes, lookup, 2022 baseline (one-off)
python3 fetch_live.py                   # keep running: polls TSE
python3 -m http.server -d web 8000      # open http://localhost:8000
python3 build_demo.py                   # optional: 2022 preview at http://localhost:8000/?demo
python3 -m pytest tests                 # tests
```

## Data sources and license

- Results: [TSE results feed](https://resultados.tse.jus.br) and [TSE open data](https://dadosabertos.tse.jus.br) (CC BY)
- Maps: [IBGE meshes API](https://servicodados.ibge.gov.br/api/docs/malhas) and [world-atlas](https://github.com/topojson/world-atlas) (Natural Earth, public domain)

Made by [Leonardo Rocha](https://www.linkedin.com/in/lsrocha85/). Code is released under the [MIT License](LICENSE); charts and exported images under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). This project is not affiliated with TSE.
