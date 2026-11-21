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

Produkt to silnik uprawnień i ścieżek (eligibility-and-pathway engine) — nie sam
kalkulator: eBobo ma sprawdzać, o jakie świadczenia można się ubiegać, wyjaśniać
przeszkody i prowadzić przez zgodne z prawem sposoby uzyskania wsparcia. Każda
odpowiedź silnika ma tę samą ustrukturyzowaną postać (status / uzasadnienie /
możliwe rozwiązania / plan) zamiast prostego tak/nie; `possible_solutions` może
wskazywać `related_benefit_code` innego świadczenia do sprawdzenia osobno.

### Zrobione

- **Szkielet aplikacji**: konfiguracja, CORS, obsługa błędów, Swagger/ReDoc,
  `GET /api/v1/health`.
- **Autoryzacja**: sesja anonimowa, symulowane logowanie mObywatel,
  `POST /auth/refresh` (odnowienie tokenu z zachowaniem `user_id`, działa nawet
  gdy poprzedni token wygasł), `POST /auth/logout` (unieważnia wszystkie
  wydane wcześniej tokeny przez `token_version`, zwraca nową sesję anonimową).
- **Silnik uprawnień**: wspólny, generyczny endpoint
  `POST /api/v1/eligibility/check/{benefit_code}` z rejestrem świadczeń
  (`app/eligibility/registry.py`).
- **3 świadczenia w pełni zaimplementowane** (realna logika oceny):
  - `zasilek_macierzynski_urlop_macierzynski` — zasiłek macierzyński za okres
    urlopu macierzyńskiego.
  - `zasilek_w_wysokosci_zasilku_macierzynskiego` — alternatywna ścieżka z
    ustawy zasiłkowej art. 30, dostępna gdy ubezpieczenie ustało w ciąży
    wskutek upadłości/likwidacji/śmierci pracodawcy (z weryfikacją, czy
    zapewniono inne zatrudnienie) lub niezgodnego z prawem zwolnienia
    potwierdzonego wyrokiem sądu.
  - `urlop_ojcowski` — 2 tygodnie, 100% podstawy, do 12. miesiąca życia dziecka.
- **Panel administracyjny (MVP)**: jeden administrator z env, logowanie JWT
  (`POST /api/v1/admin/login`), frontend w `static/admin/`.

### W trakcie / tymczasowe

**5 świadczeń zarejestrowane jako placeholdery** — odpowiadają `200 OK`, ale bez
realnej logiki oceny: zawsze zwracają `status: requires_verification` z jawnym
ostrzeżeniem `"TYMCZASOWA ODPOWIEDŹ ZASTĘPCZA"` w `warnings` i `plan: null`,
nigdy fałszywe `likely_eligible` — zrobione celowo, żeby front mógł budować
widoki na stabilnym kształcie API, zanim dojedzie realna logika. Szczegóły
parametrów prawnych dla każdego w `app/eligibility/engine.py` i pamięci
projektu `project-ebobo-stub-benefits-debt`:

| Kod świadczenia | Co to jest |
|---|---|
| `zasilek_chorobowy_w_ciazy` | Zasiłek chorobowy w ciąży |
| `uzupelniajacy_urlop_macierzynski` | Uzupełniający urlop macierzyński (hospitalizacja dziecka) |
| `urlop_rodzicielski` | Urlop rodzicielski (w tym podział między rodzicami) |
| `urlop_na_warunkach_urlopu_macierzynskiego` | Adopcja / rodzina zastępcza |
| `zasilek_pogrzebowy_martwe_urodzenie` | Zasiłek pogrzebowy przy martwym urodzeniu (kwota ryczałtowa, wymaga rozszerzenia schematu `BenefitRuleVersion`) |

Traktuj prośbę "dokończ Fazę 2" / "dopracuj świadczenia" jako niekompletną,
dopóki te 5 kodów nie przestanie być statyczne.

### Co zostało (priorytety, reset 2026-11-21)

Główny sposób korzystania z eBobo to **inteligentna ankieta z polami w
aplikacji**, nie przesyłanie dokumentów. Przepływ: (1) rodzic odpowiada na
pytania (zatrudnienie, ubezpieczenie, data porodu, dochody, drugi rodzic),
(2) backend ocenia sytuację (uprawnienia, przeszkody, możliwości, przepisy),
(3) rodzic porównuje warianty (kwoty, długość urlopów, podział między
rodziców), (4) eBobo pokazuje co dalej (dokumenty, terminy, właściwy wniosek,
miejsce złożenia).

**Granica zakresu**: eBobo ustala potencjalne uprawnienia i liczy/porównuje
warianty świadczeń. **Nie buduje własnego systemu składania/rozpatrywania
wniosków** — samo złożenie i rozpatrzenie zostaje po stronie ZUS lub
pracodawcy/płatnika (formularz ZAM idzie przez eZUS albo przez pracodawcę,
zależnie kto jest płatnikiem). Rola eBobo kończy się na wskazaniu właściwej
procedury, dokumentów i terminów.

Wymóg obsługi przykładowych PDF-ów zostaje, ale tylko jako **minimalny
mechanizm dla jury** (nie usuwamy go całkiem - brief wprost wspomina wybór/
upload wybranych wniosków): (A) wybór gotowej sprawy — appka wypełnia
formularz danymi przygotowanymi dla tego scenariusza i uruchamia prawdziwy
silnik + kalkulator; (B) własny przypadek — jury wypełnia pola bezpośrednio w
eBobo; (C) opcjonalny prosty upload PDF, po którym jury ręcznie wprowadza/
potwierdza dane — bez OCR i automatycznego parsowania w obu przypadkach.
Automatyczny OCR i pełne parsowanie skanów są odłożone (ZUS wymaga możliwości
testowania na przykładach, nie wymaga konkretnie OCR).

Ważna zasada do zachowania w UI/API: zaznaczenie przez rodzica „mam
ubezpieczenie” to tylko deklaracja — nie potwierdza rzeczywistego statusu w
ZUS. Dane zadeklarowane przez użytkownika i symulowane potwierdzenie z
`MockZUSProvider` pokazujemy osobno, nigdy scalone w jeden fakt.

| # | Zakres | Status |
|---|---|---|
| 1 | **Rozbudowa formularzy wejściowych** — konkretne pytania ustalające sytuację rodzica (zasila wszystko poniżej) | ⬜ nierozpoczęte |
| 2 | Dopracowanie silnika uprawnień, w kolejności: urlop rodzicielski (+ podział między rodzicami), zasiłek chorobowy w ciąży, **świadczenie rehabilitacyjne** (nowość, 90%/75%/100% w ciąży, max 12 mies.), uzupełniający urlop macierzyński, adopcja/rodzina zastępcza, pozostałe sytuacje szczególne | 🟡 3 zrobione, 5 placeholderów (patrz wyżej) |
| 2a | **Jawne oznaczenie statusu implementacji** (implemented/stub) w odpowiedzi API — placeholdery dziś zwracają `HTTP 200` z ostrzeżeniem tylko w tekście; FE potrzebuje pola, które da się odczytać programistycznie | ⬜ nierozpoczęte |
| 3 | Zintegrowany kalkulator świadczeń (kwoty, okresy, warianty obojga rodziców, łączenie pracy z urlopem, adopcja, sytuacje szczególne) | ⬜ nierozpoczęte |
| 4 | `MockZUSProvider` — symulowane ubezpieczenie/okresy/e-ZLA/zadłużenie/historia świadczeń | ⬜ nierozpoczęte |
| 5 | Przygotowane scenariusze testowe — ustrukturyzowane profile + dane wejściowe JSON per sprawa (nie publikujemy chronionych PDF-ów ZUS) | ⬜ nierozpoczęte |
| 6 | Przewodnik po formalnościach — dokumenty, formularze, terminy, miejsce złożenia, ryzyka utraty uprawnień, następne kroki | ⬜ nierozpoczęte |
| 7 | Minimalna edycja parametrów prawnych w panelu administratora (silnik musi używać aktualnych wartości/wersji) | ⬜ nierozpoczęte |

Niższy priorytet (odłożone, nie zaczynamy bez wyraźnej prośby): automatyczny
OCR, kompleksowe parsowanie skanów, społeczność/forum, rozbudowany niezbędnik
parentingowy, dziennik zdrowia dziecka, zaawansowane przypomnienia push.
Podstawowe informacje o pomocy w trudnych sytuacjach zostają (wymagane przez
ZUS).

Kolejne moduły będą dodawane iteracyjnie w `app/services`, `app/eligibility`,
`app/rules` i `app/api/v1/endpoints`.

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
