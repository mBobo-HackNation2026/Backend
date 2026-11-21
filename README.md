# eBobo – Zasiłkowy Przewodnik Przyszłego Rodzica

Backend API projektu na HackNation 2026 (brief ZUS). Pomaga przyszłym i obecnym
rodzicom zrozumieć, jakie świadczenia im przysługują, policzyć ich wysokość
oraz zweryfikować uprawnienia — na podstawie deterministycznych reguł, a nie
zgadywania przez AI.

## Stack

- Python 3.12+
- FastAPI + Pydantic v2
- SQLAlchemy (SQLite lokalnie, migracja na PostgreSQL przez zmianę `DATABASE_URL`)
- PyMuPDF (analiza dokumentów PDF)
- pytest
- uv (zarządzanie zależnościami)
- Ruff (lint/format)

## Status

Obecnie gotowy jest szkielet aplikacji (konfiguracja, CORS, obsługa błędów,
Swagger, `GET /api/v1/health`), autoryzacja (sesja anonimowa, symulowane logowanie
mObywatel, `POST /auth/refresh`, `POST /auth/logout`) oraz silnik uprawnień
dostępny przez wspólny, generyczny endpoint `POST /api/v1/eligibility/check/{benefit_code}`.

**W pełni zaimplementowane** (realna logika oceny): `zasilek_macierzynski_urlop_macierzynski`
(zasiłek macierzyński za okres urlopu macierzyńskiego), `zasilek_w_wysokosci_zasilku_macierzynskiego`
(alternatywna ścieżka z ustawy zasiłkowej art. 30, dostępna gdy ubezpieczenie ustało w
ciąży wskutek upadłości/likwidacji/śmierci pracodawcy lub niezgodnego z prawem zwolnienia
potwierdzonego wyrokiem sądu), `urlop_ojcowski` (2 tygodnie, 100% podstawy, do 12. miesiąca
życia dziecka). Każda odpowiedź ma tę samą ustrukturyzowaną postać (status / uzasadnienie /
możliwe rozwiązania / plan) zamiast prostego tak/nie; `possible_solutions` może wskazywać
`related_benefit_code` innego świadczenia do sprawdzenia osobno.

**Tymczasowe placeholdery** (zarejestrowane i odpowiadają `200 OK`, ale bez realnej
logiki oceny - zawsze zwracają `status: requires_verification` z jawnym ostrzeżeniem w
`warnings`, nigdy fałszywe `likely_eligible`; szczegóły w `app/eligibility/engine.py` i
pamięci projektu `project-ebobo-stub-benefits-debt`): `zasilek_chorobowy_w_ciazy`,
`uzupelniajacy_urlop_macierzynski`, `urlop_rodzicielski`,
`urlop_na_warunkach_urlopu_macierzynskiego`, `zasilek_pogrzebowy_martwe_urodzenie`.
Te pięć świadczeń czeka na docelową implementację logiki oceny.

Kolejne moduły (kalkulator, upload/analiza PDF, integracje ZUS/mObywatel) będą
dodawane iteracyjnie w `app/services`, `app/eligibility`, `app/rules` i
`app/api/v1/endpoints`.

## Struktura projektu

```
app/
  core/           # konfiguracja (Settings), wyjątki domenowe
  admin/          # autoryzacja panelu administracyjnego (JWT, jeden użytkownik z env)
  api/v1/
    endpoints/    # pojedyncze routery REST (health, admin, docelowo: calculator, eligibility, documents, integrations)
    router.py     # agregacja routerów v1
  schemas/        # modele Pydantic (request/response)
  services/       # logika biznesowa (obliczenia, weryfikacja, integracje, parsing PDF)
  rules/          # parametry i progi świadczeń, oddzielone od logiki obliczeniowej
  db/             # SQLAlchemy: engine, sesje, modele ORM
  main.py         # fabryka aplikacji FastAPI
static/admin/     # statyczny frontend panelu administracyjnego (vanilla HTML/JS)
tests/            # testy pytest
```

Zasada: **reguły i kwoty świadczeń (`app/rules`) są oddzielone od logiki
obliczeniowej (`app/services`)**, żeby aktualizacja przepisów nie wymagała
zmian w kodzie liczącym. AI może pomagać w interpretacji dokumentów i
tłumaczeniu wyników użytkownikowi, ale same obliczenia świadczeń mają być
deterministyczne i oparte wyłącznie o zweryfikowane reguły z briefu ZUS.

## Uruchomienie lokalne

Wymagany [`uv`](https://docs.astral.sh/uv/):

```bash
# instalacja zależności (w tym dev: pytest, ruff, httpx)
uv sync

# plik środowiskowy
cp .env.example .env

# serwer deweloperski
uv run uvicorn app.main:app --reload
```

API będzie dostępne pod `http://localhost:8000`:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Healthcheck: `http://localhost:8000/api/v1/health`
- Panel administracyjny: `http://localhost:8000/admin` (login: `ADMIN_USERNAME`/`ADMIN_PASSWORD` z `.env`, domyślnie `admin`/`changeme`)

### Panel administracyjny

MVP: jeden użytkownik administratora skonfigurowany przez zmienne środowiskowe
(brak modelu użytkowników w bazie na tym etapie). Logowanie wydaje token JWT
(`POST /api/v1/admin/login`), który frontend (`static/admin/`) trzyma w
`sessionStorage` i wysyła jako `Authorization: Bearer <token>` do chronionych
endpointów (`/api/v1/admin/me`, `/api/v1/admin/dashboard`).

**Zanim cokolwiek wystawisz poza `localhost`, zmień `ADMIN_PASSWORD` i
`SECRET_KEY` w `.env`** — wartości domyślne są tylko do developmentu.

## Testy i lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format .
```

## Konfiguracja

Wszystkie ustawienia czytane są ze zmiennych środowiskowych / pliku `.env`
(zobacz `.env.example`): nazwa aplikacji, prefiks API, dozwolone originy CORS,
`DATABASE_URL`, parametry uploadu plików oraz adresy symulowanych integracji
ZUS/mObywatel.
