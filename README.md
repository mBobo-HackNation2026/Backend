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
- **Rozbudowany schemat requestu** (`MaternityLeaveEligibilityRequest` w
  `app/eligibility/schemas.py`) — wspólny dla wszystkich świadczeń, ~30 pól z
  cytatem podstawy prawnej przy każdym: okresy wyczekiwania, hospitalizacja
  dziecka (uzupełniający urlop), adopcja/rodzina zastępcza i limity wieku,
  podział urlopu rodzicielskiego między rodzicami, warunki świadczenia
  rehabilitacyjnego, martwe urodzenie/zgon dziecka, oraz pola pod przyszły
  kalkulator (podstawa wymiaru: dochód, okres zatrudnienia, podstawa składki
  dobrowolnej, rodzaj premii, przerwa między zasiłkami). Front może budować
  pełną ankietę na tym kontrakcie już teraz - większość pól nie ma jeszcze
  logiki po stronie silnika (patrz sekcja "W trakcie" niżej).
- **8 świadczeń w pełni zaimplementowane** (realna logika oceny):
  - `zasilek_macierzynski_urlop_macierzynski` — zasiłek macierzyński za okres
    urlopu macierzyńskiego.
  - `zasilek_w_wysokosci_zasilku_macierzynskiego` — alternatywna ścieżka z
    ustawy zasiłkowej art. 30, dostępna gdy ubezpieczenie ustało w ciąży
    wskutek upadłości/likwidacji/śmierci pracodawcy (z weryfikacją, czy
    zapewniono inne zatrudnienie) lub niezgodnego z prawem zwolnienia
    potwierdzonego wyrokiem sądu.
  - `urlop_ojcowski` — 2 tygodnie, 100% podstawy, do 12. miesiąca życia dziecka.
  - `urlop_rodzicielski` — 41/43 tygodni (1 dziecko / 2+), 65/67
    tygodni z zaświadczeniem "Za życiem"; stawka 70% albo 81,5% łącznie z
    macierzyńskim (gdy wniosek o pełny wymiar złożono w ciągu 21 dni po
    porodzie); 9 tygodni z puli jest nieprzenoszalne na rzecz drugiego rodzica
    (pole `other_parent_used_parental_leave_weeks` pomniejsza dostępną pulę
    wnioskującego); opcjonalne łączenie z pracą w niepełnym wymiarze (maks.
    1/2 etatu) proporcjonalnie wydłuża liczbę tygodni w planie. Pełne
    uzasadnienie i cytaty w `app/eligibility/engine.py` →
    `evaluate_parental_leave_eligibility`.
  - `zasilek_chorobowy_w_ciazy` — zasiłek chorobowy w ciąży, 100%
    podstawy, do 270 dni (zamiast standardowych 80%/182 dni poza ciążą).
    Weryfikuje status ciąży (`is_pregnant`), okres wyczekiwania (30 dni przy
    ubezpieczeniu obowiązkowym, 90 dni przy dobrowolnym - zlecenie/działalność,
    pole `insured_days_continuous`) oraz zadłużenie składkowe dla
    samozatrudnionych (art. 2a, ten sam mechanizm co przy zasiłku
    macierzyńskim - wydzielony do współdzielonej funkcji
    `_apply_self_employed_debt_check`). Świadomie NIE modeluje jeszcze
    wyjątków znoszących okres wyczekiwania (absolwenci, wypadek w drodze do
    pracy, wcześniejszy długi staż ubezpieczeniowy) - sygnalizuje to przez
    `warnings`, nie udaje że je sprawdziło. Zob. `app/eligibility/engine.py` →
    `evaluate_sickness_benefit_during_pregnancy_eligibility`.
  - `swiadczenie_rehabilitacyjne` — zupełnie nowe świadczenie
    (nigdy nie było placeholderem - dodane i od razu zaimplementowane w tej
    samej iteracji po priority-reset briefie). Przysługuje po wyczerpaniu
    zasiłku chorobowego (`sickness_benefit_period_exhausted`), gdy lekarz
    orzecznik ZUS stwierdzi rokowanie odzyskania zdolności do pracy
    (`medical_prognosis_recovery_possible`), o ile wnioskodawcy nie
    przysługuje już inne wykluczające świadczenie - emerytura, renta, zasiłek
    dla bezrobotnych itd. (`excluded_from_rehabilitation_benefit`). Stawka
    90% przez pierwsze 3 miesiące / 75% dalej, albo 100% w ciąży
    (`is_pregnant`); maksymalnie 12 miesięcy. Plan pokazuje stawkę startową
    (90% albo 100%) z jawnym ostrzeżeniem, że spadek do 75% po 3 miesiącach
    nie jest jeszcze rozbijany miesiąc po miesiącu - to zadanie przyszłego
    kalkulatora (priorytet #3). Zob. `app/eligibility/engine.py` →
    `evaluate_rehabilitation_benefit_eligibility`.
  - `uzupelniajacy_urlop_macierzynski` — **nowość**: uzupełniający urlop
    macierzyński (hospitalizacja dziecka po porodzie), 1 tydzień urlopu za
    każdy tydzień hospitalizacji (`child_hospitalization_weeks`), 100%
    podstawy. Graniczny termin skorzystania to 15. tydzień po porodzie przy
    urodzeniu <28 tyg. ciąży lub masie ≤1000g, w pozostałych przypadkach 8.
    tydzień (`gestational_week_at_birth`/`birth_weight_grams` ustalają które,
    `postpartum_weeks_elapsed` sprawdza czy termin minął) - uproszczony model
    dwóch progów zgodny z tym, co było już wcześniej udokumentowane publicznie;
    trzeci, węższy przypadek z Kodeksu pracy art. 1802 §1 (poród o czasie z
    późniejszą hospitalizacją) nie jest jeszcze modelowany. Zob.
    `app/eligibility/engine.py` →
    `evaluate_supplementary_maternity_leave_eligibility`.
  - `urlop_na_warunkach_urlopu_macierzynskiego` — **nowość**: adopcja/rodzina
    zastępcza, ta sama tabela tygodni co zasiłek macierzyński (20/31/33/35/37),
    100% podstawy. `is_adoption_or_foster_care` ustala czy to w ogóle dotyczy
    tego świadczenia (w przeciwnym razie wskazuje zwykły zasiłek
    macierzyński); `foster_care_type` odrzuca rodzinę zastępczą zawodową
    (Kodeks pracy art. 183 §1(1)) i ustala limit wieku: 14 lat przy
    przysposobieniu, 7 lat przy rodzinie zastępczej (10 lat przy odroczeniu
    obowiązku szkolnego, `school_obligation_deferred`). Świadomie NIE modeluje
    jeszcze gwarancji minimum 9 tygodni przy adopcji dziecka bliskiego granicy
    wiekowej - sygnalizuje to przez `warnings`. Zob.
    `app/eligibility/engine.py` → `evaluate_adoption_leave_eligibility`.
- **Panel administracyjny (MVP)**: jeden administrator z env, logowanie JWT
  (`POST /api/v1/admin/login`), frontend w `static/admin/`.

### W trakcie / tymczasowe

**1 świadczenie zarejestrowane jako placeholder** — odpowiada `200 OK`, ale bez
realnej logiki oceny: zawsze zwraca `status: requires_verification` z jawnym
ostrzeżeniem `"TYMCZASOWA ODPOWIEDŹ ZASTĘPCZA"` w `warnings` i `plan: null`,
nigdy fałszywe `likely_eligible` — zrobione celowo, żeby front mógł budować
widoki na stabilnym kształcie API, zanim dojedzie realna logika. Szczegóły
parametrów prawnych w `app/eligibility/engine.py` i pamięci projektu
`project-ebobo-stub-benefits-debt`:

| Kod świadczenia | Co to jest |
|---|---|
| `zasilek_pogrzebowy_martwe_urodzenie` | Zasiłek pogrzebowy przy martwym urodzeniu (kwota ryczałtowa, wymaga rozszerzenia schematu `BenefitRuleVersion`) |

Traktuj prośbę "dokończ Fazę 2" / "dopracuj świadczenia" jako niekompletną,
dopóki ten ostatni kod nie przestanie być statyczny.

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
| 1 | **Rozbudowa formularzy wejściowych** — konkretne pytania ustalające sytuację rodzica (zasila wszystko poniżej) | ✅ zrobione (schemat w `app/eligibility/schemas.py`, patrz "Zrobione" wyżej) |
| 2 | Dopracowanie silnika uprawnień, w kolejności: ✅ urlop rodzicielski (+ podział między rodzicami), ✅ zasiłek chorobowy w ciąży, ✅ świadczenie rehabilitacyjne (nowe świadczenie, 90%/75%/100% w ciąży, max 12 mies.), ✅ uzupełniający urlop macierzyński, ✅ adopcja/rodzina zastępcza, zasiłek pogrzebowy przy martwym urodzeniu | 🟡 8 zrobionych, 1 placeholder (patrz wyżej) |
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
