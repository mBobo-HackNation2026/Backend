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
- **9 świadczeń w pełni zaimplementowane** (realna logika oceny):
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
    (90% albo 100%); pełne rozbicie 90%/75% miesiąc po miesiącu liczy teraz
    kalkulator (zob. niżej). Zob. `app/eligibility/engine.py` →
    `evaluate_rehabilitation_benefit_eligibility`.
  - `uzupelniajacy_urlop_macierzynski` — uzupełniający urlop
    macierzyński (hospitalizacja dziecka po porodzie), 1 tydzień urlopu za
    każdy tydzień hospitalizacji (`child_hospitalization_weeks`), 100%
    podstawy. **Poprawka po recenzji**: 15./8. tydzień po porodzie
    (`gestational_week_at_birth`/`birth_weight_grams` ustalają który) to
    WYŁĄCZNIE granica, które tygodnie hospitalizacji wliczają się do wymiaru
    (Kodeks pracy art. 1802 §1 i §3) - nie termin na skorzystanie z urlopu,
    jak wcześniej błędnie modelowano. Rzeczywisty termin graniczny to
    wniosek złożony nie później niż 21 dni przed zakończeniem podstawowego
    urlopu macierzyńskiego (art. 1802 §4, liczony z `postpartum_weeks_elapsed`
    względem standardowej tabeli tygodni). **Druga poprawka (znaleziona przez
    niezależny test QA ze scenariuszem wcześniaka 650g/17 tyg. hospitalizacji)**:
    `child_hospitalization_weeks` nie było wcześniej ograniczane do granicznego
    tygodnia - 17 zgłoszonych tygodni dawało błędnie 17 tygodni urlopu zamiast
    poprawnych 15 (ustawowy limit dla urodzenia ≤1000g). Silnik i kalkulator
    teraz liczą `min(child_hospitalization_weeks, tydzień graniczny)` i jawnie
    ostrzegają, gdy ograniczenie zostało zastosowane; bez danych o tygodniu
    ciąży/masie urodzeniowej silnik uprawnień nie pokazuje planu wcale (zamiast
    niesprawdzonego, potencjalnie zawyżonego wymiaru), a kalkulator pokazuje
    nieograniczoną wartość z jawnym ostrzeżeniem o braku możliwości weryfikacji.
    Trzeci, węższy przypadek z art. 1802 §1 pkt 3 (poród o czasie z późniejszą
    hospitalizacją) nadal nie jest osobno modelowany. Zob.
    `app/eligibility/engine.py` → `evaluate_supplementary_maternity_leave_eligibility`
    i `app/calculator/engine.py` → `_resolve_segments`.
  - `urlop_na_warunkach_urlopu_macierzynskiego` — adopcja/rodzina
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
  - `zasilek_pogrzebowy_martwe_urodzenie` — **nowość, ostatnie z 9 świadczeń
    Fazy 2 - zamyka cały dług `project-ebobo-stub-benefits-debt`**: świadczenie
    ryczałtowe 7 000 zł (nie procent podstawy wymiaru), wniosek Z-12 w ciągu
    12 miesięcy od pochówku. Wymagało rozszerzenia modelu danych: nowe pole
    `lump_sum_amount_zl` na `BenefitRuleVersion` i `BenefitPlan`, a
    `rate_percentage` w `BenefitPlan` stało się opcjonalne (null dla
    świadczeń kwotowych). Gatuje przez `is_stillbirth_or_infant_death` i
    12-miesięczny termin. **Poprawka po recenzji**: termin liczy się od dnia
    pochówku, nie od zgonu (Poradnik ZUS 2026, s.36) - dodano osobne pole
    `days_since_burial` (zamiast błędnie używanego do tego celu
    `days_since_death`, które zostaje wyłącznie dla gwarancji 7 dni urlopu
    macierzyńskiego po zgonie dziecka, Kodeks pracy art. 1801). Jawne
    ostrzeżenie, że `is_stillbirth_or_infant_death` obejmuje też zgon dziecka
    po żywym urodzeniu przed 8. tygodniem życia, którego ten silnik nie
    rozróżnia od martwego urodzenia. Zob. `app/eligibility/engine.py` →
    `evaluate_stillbirth_funeral_benefit_eligibility`.
- **Zintegrowany kalkulator świadczeń** (`app/calculator/`) — **nowość**, priorytet
  #3 z briefu 2026-11-21, zbudowany od razu razem z porównaniem wariantów
  podziału (nie jako osobna, późniejsza iteracja). Celowo niezależny od
  silnika uprawnień: liczy hipotetyczną kwotę nawet gdy ocena uprawnień
  zwróciłaby `requires_verification`/`not_eligible` - ustalenie uprawnień i
  wyliczenie kwoty to z założenia dwie osobne funkcje.
  - `POST /api/v1/benefits/calculate/{benefit_code}` — dla dowolnego z 9 kodów
    świadczeń: podstawa dzienna (÷30 z miesięcznej, ustawa zasiłkowa art. 36
    ust. 3) × stawka% × liczba dni. Podstawa miesięczna = `average_monthly_income_zl`
    (pracownik) albo `voluntary_contribution_base_zl` ograniczone do 23 550 zł
    (zlecenie/działalność, art. 48), zawsze pomniejszone o 13,71% składek
    ubezpieczonego; stosuje podstawę minimalną wyliczoną ze wzoru (4806 zł ×
    (1-13,71%) = 4147,10 zł), gdy obliczona jest niższa - **tylko dla
    pełnego etatu** (`is_full_time_employment=true`, ustawa zasiłkowa art.
    45 ust. 1 - poprawka po recenzji: wcześniej podstawa minimalna stosowała
    się do każdego pracownika niezależnie od wymiaru etatu). Gdy wymiar
    etatu jest nieznany, kalkulator NIE stosuje podstawy minimalnej zamiast
    zgadywać, i ostrzega o tym jawnie. Ostrzeżenie towarzyszące podstawie
    minimalnej też jasno mówi, że to wzór, nie oficjalna tabela (żadna nie
    istnieje w dostępnych materiałach źródłowych). Świadczenia ryczałtowe (zasiłek
    pogrzebowy) zwracają `lump_sum_amount_zl` wprost. Świadczenia bez znanego
    z góry okresu (zasiłek w wysokości zasiłku macierzyńskiego - "do dnia
    porodu") zwracają samą podstawę/stawkę dzienną z ostrzeżeniem, nie
    zgadują łącznej kwoty. Świadczenie rehabilitacyjne rozbija 360 dni na
    90%/75% (albo płaskie 100% w ciąży) - **nie** uwzględnia jeszcze
    kwartalnej waloryzacji podstawy (ustawa zasiłkowa art. 19 ust. 2).
  - `POST /api/v1/benefits/compare/urlop-rodzicielski` — bierze dane dochodowe
    obojga rodziców (`parent_a`/`parent_b`) i zwraca 3 warianty podziału puli
    tygodni (matka maksymalnie, ojciec maksymalnie, po równo) z kwotą dla
    każdego rodzica i sumą gospodarstwa domowego - widać np. że jeśli jeden
    rodzic zarabia więcej, warianty dają różną łączną kwotę dla rodziny.
    Upraszcza stawkę 81,5%/70% do jednej wartości na wariant (nie dzieli
    wewnętrznie nieprzenoszalnych 9 tygodni każdego rodzica na osobną stawkę) -
    sygnalizuje to przez `warnings`.
  - **Nieużywane jeszcze pola schematu**: `employment_duration_months`,
    `bonus_type`, `months_since_last_benefit` istnieją w requestcie, ale
    podstawa wymiaru ich jeszcze nie uwzględnia (niuanse art. 37/38/42/43) -
    to realny, niedokończony zakres, nie kosmetyka.
  - **Poprawka cytowań**: weryfikacja stawki 81,5%/70% urlopu rodzicielskiego
    przeciwko treści ustawy wykazała błędne cytaty w
    `evaluate_parental_leave_eligibility`/`_ensure_parental_leave_seeded`
    ("art. 31 ust. 3g i ust. 4" dla stawki 81,5% oraz "ust. 3" dla
    tygodni "Za życiem") - poprawione na: art. 30a + ustawa zasiłkowa art. 31
    ust. 3 (stawka 81,5%), ust. 2 (stawka standardowa 70%), ust. 3f (9
    nieprzenoszalnych tygodni drugiego rodzica zawsze 70%), Kodeks pracy
    art. 1821a § 2/§ 4 (wymiar tygodni i nieprzenoszalna rezerwacja - to
    kwestia Kodeksu pracy, nie ustawy zasiłkowej). Logika działania była od
    początku poprawna, poprawione zostały tylko cytaty. Szczegóły w pamięci
    projektu `project-ebobo-calculator`.
- **MockZUSProvider** (`app/mock_zus/`) — **nowość**, priorytet #4 z recenzji FE
  2026-11-22. Kontrakt endpointów zaproponowano i zatwierdzono z użytkownikiem
  PRZED implementacją (żeby FE mogło budować UI równolegle), zgodnie z
  wyraźną prośbą w briefie. Dane symulowane, całkowicie oddzielone od
  silnika uprawnień i kalkulatora - nigdy nie są automatycznie wstrzykiwane
  do oceny, żeby nie zastępować bez wyjaśnienia deklaracji użytkownika.
  - `GET /api/v1/mock-zus/profiles` — lista 5 profili demonstracyjnych
    (`profile_id`, `label`, opis) do ekranu wyboru sprawy.
  - `GET /api/v1/mock-zus/profiles/{profile_id}` — pełne symulowane dane:
    status i tytuł ubezpieczenia, okresy ubezpieczenia, zadłużenie składkowe,
    e-ZLA, historia wykorzystanych świadczeń. Zawsze z
    `data_source: "mock_zus_simulated"` i jawnym ostrzeżeniem, że to nie są
    prawdziwe dane ZUS.
  - `POST /api/v1/mock-zus/profiles/{profile_id}/compare` — przyjmuje
    deklaracje użytkownika (tytuł ubezpieczenia, status ubezpieczenia,
    zadłużenie), zwraca porównanie pole-po-polu (`declared_value` /
    `simulated_value` / `matches`) - `matches: null`, gdy jednej ze stron
    brakuje wartości (odróżnia "sprawdziliśmy i się nie zgadza" od "nie ma
    czego porównać"). To bezpośrednia realizacja wymogu z briefu: przy
    rozbieżności pokazać oba źródła, nigdy nie decydować które jest
    "prawdziwe".
  - 5 profili (`matka_umowa_o_prace_standard`, `zlecenie_okres_wyczekiwania`,
    `upadlosc_pracodawcy`, `dzialalnosc_z_zadluzeniem`,
    `ojciec_urlop_ojcowski`) - każdy świadomie dobrany, żeby realnie
    uruchomić konkretną, już zaimplementowaną ścieżkę silnika uprawnień (okres
    wyczekiwania, art. 30, próg zadłużenia art. 2a, termin urlopu ojcowskiego),
    nie losowe dane. Dane statyczne w Pythonie (`app/mock_zus/profiles.py`),
    bez tabeli w bazie - to dane demonstracyjne, nie parametry prawne
    wymagające wersjonowania jak `BenefitRuleVersion`.
  - Zob. pamięć projektu `project-ebobo-mock-zus-provider`.
- **Przewodnik po formalnościach** (`app/formalities/`) — **nowość**, ostatni
  punkt BE z priorytetów P0 recenzji FE. Treść oparta wprost na tekście
  oficjalnego briefu (`resorces/Projekt.pdf`), nie wymyślona.
  - `GET /api/v1/formalities/general` — ogólne ryzyka utraty uprawnień albo
    obniżenia świadczenia (Projekt.pdf §H: umowa/działalność "dla pozoru",
    sztuczne podwyższenie podstawy w ciąży, niepodleganie ubezpieczeniu na
    dzień porodu), ochrona przed zwolnieniem w okresie ciąży/urlopów
    rodzicielskich (§I), oraz świadoma luka: brief wymaga wskazania
    organizacji charytatywnych wspierających w trudnych sytuacjach (śmierć
    dziecka, przedwczesny poród, poronienie, ciężka choroba dziecka) - sekcja
    jest celowo pusta z jawną notatką, bo projekt nie ma zweryfikowanej listy
    takich organizacji; wymyślanie nazw byłoby gorsze niż przyznanie się do
    braku.
  - `GET /api/v1/formalities/{benefit_code}` — dla konkretnego świadczenia:
    instytucja/dokumenty/terminy/podstawa prawna (z tej samej reguły co
    silnik uprawnień i kalkulator, nie duplikowane), plus te same ogólne
    ryzyka i wygenerowane `next_steps` (sprawdź uprawnienia → oblicz kwotę →
    przygotuj dokumenty → złóż wniosek → sprawdź powiązane świadczenia).
  - Zob. pamięć projektu `project-ebobo-formalities-guide`.
- **Panel administracyjny (MVP)**: jeden administrator z env, logowanie JWT
  (`POST /api/v1/admin/login`), frontend w `static/admin/`.
  - **Nowość**: widok "Wnioski" - log zapytań wysłanych do silnika uprawnień i
    kalkulatora (`POST /eligibility/check`, `POST /benefits/calculate`,
    `POST /benefits/compare/urlop-rodzicielski`), **tylko do odczytu**.
    `GET /api/v1/admin/request-log` (lista, filtr po `benefit_code`) i
    `GET /api/v1/admin/request-log/{id}` (pełny request+response). Świadomie
    bez edycji - admin edytujący cudze zadeklarowane dane po fakcie
    fałszowałby historię oceny, sprzecznie z tym, jak projekt traktuje
    wersjonowanie (nigdy nie nadpisujemy cicho). Pętla feedbacku
    ("oznacz tę ocenę jako błędną i wykorzystaj do poprawy reguł") jest
    świadomie odłożona na później, na wyraźną prośbę użytkownika. Zob.
    pamięć projektu `project-ebobo-admin-request-log`.

### W trakcie / tymczasowe

**Brak placeholderów** — wszystkie 9 świadczeń Fazy 2 mają teraz realną
logikę oceny (zob. listę wyżej). Dług `project-ebobo-stub-benefits-debt` jest
zamknięty, ale kilka świadomych uproszczeń pozostaje nieobsłużonych (patrz
notatki "Świadomie NIE modeluje" przy poszczególnych świadczeniach wyżej oraz
pamięć projektu dla pełnej listy) - nie traktuj "wszystkie świadczenia realne"
jako "każdy niuans prawny jest pokryty".

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
| 2 | Dopracowanie silnika uprawnień (urlop rodzicielski, zasiłek chorobowy w ciąży, świadczenie rehabilitacyjne - nowe świadczenie, uzupełniający urlop macierzyński, adopcja/rodzina zastępcza, zasiłek pogrzebowy przy martwym urodzeniu) | ✅ zrobione - wszystkie 9 świadczeń mają realną logikę, patrz "Zrobione" wyżej |
| 3 | Zintegrowany kalkulator świadczeń (kwoty, okresy, warianty obojga rodziców, łączenie pracy z urlopem, adopcja, sytuacje szczególne) | ✅ zrobione - kwoty per świadczenie + porównanie wariantów urlopu rodzicielskiego, patrz "Zrobione" wyżej; pola podstawy wymiaru dla zatrudnienia <12 mies./premii/przerwy między zasiłkami jeszcze nieobsłużone |
| 4 | `MockZUSProvider` — symulowane ubezpieczenie/okresy/e-ZLA/zadłużenie/historia świadczeń | ✅ zrobione - 5 profili + endpoint porównania rozbieżności, patrz "Zrobione" wyżej |
| 5 | Przygotowane scenariusze testowe — ustrukturyzowane profile + dane wejściowe JSON per sprawa (nie publikujemy chronionych PDF-ów ZUS) | ⬜ nierozpoczęte |
| 6 | Przewodnik po formalnościach — dokumenty, formularze, terminy, miejsce złożenia, ryzyka utraty uprawnień, następne kroki | ✅ zrobione - patrz "Zrobione" wyżej; lista organizacji charytatywnych celowo pusta (wymaga zweryfikowanych danych) |
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
endpointów (`/api/v1/admin/me`, `/api/v1/admin/dashboard`,
`/api/v1/admin/request-log`, `/api/v1/admin/request-log/{id}`).

Widok "Wnioski" w `static/admin/` (karta "Wnioski użytkowników" na dashboardzie)
pokazuje log zapytań do silnika uprawnień/kalkulatora - tabela z filtrem po
`benefit_code`, kliknięcie wiersza pokazuje pełny request/response. Tylko do
odczytu - zob. sekcję "Zrobione" wyżej i pamięć projektu
`project-ebobo-admin-request-log`.

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
