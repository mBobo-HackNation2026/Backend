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
- **`missing_fields` (nowość)** — `EligibilityResult.missing_data` to zawsze był
  tylko wolny tekst do wyświetlenia, nie identyfikatory pól - FE słusznie
  zgłosił, że nie da się tego bezpiecznie sparsować do zbudowania formularza
  "uzupełnij brakujące dane". Dodatkowe, addytywne pole
  `missing_fields: [{field, message}]` daje stabilną nazwę pola z
  `MaternityLeaveEligibilityRequest` sparowaną z tą samą treścią komunikatu co
  w `missing_data` (może mieć więcej wpisów niż `missing_data`, gdy jeden
  komunikat zależy od więcej niż jednego pola - wtedy ta sama `message`
  powtarza się, raz na pole). Wprowadzone przez wspólny helper `_missing()`/
  `_missing_many()` w `app/eligibility/engine.py`, używany we wszystkich 9
  evaluatorach zamiast surowego `missing_data.append(...)` - gwarantuje, że oba
  pola nigdy się nie rozjadą. `missing_data` bez zmian (kompatybilność wsteczna).
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
    urlopu macierzyńskiego. Uwzględnia Kodeks pracy art. 1801 (**nowość**):
    martwe urodzenie albo zgon dziecka przed 8. tygodniem życia skraca urlop
    do 8 tygodni (zamiast pełnej tabeli wg liczby dzieci) - znaleziona przez
    zewnętrzne testy QA luka, wcześniej pole `is_stillbirth_or_infant_death`
    było odczytywane tylko przez zasiłek pogrzebowy, nigdy przez ten
    evaluator. Przy więcej niż jednym dziecku z tego samego porodu wymiar
    liczy się wg liczby dzieci, które przeżyły (nowe pole
    `children_survived_count`) - bez tej informacji silnik świadomie NIE
    zgaduje i zwraca `requires_verification` zamiast pełnego, zawyżonego
    wymiaru. Świadomie NIE modeluje progu "nie krócej niż 7 dni od zgonu"
    ani odrębnej ścieżki dla zgonu po 8. tygodniu życia dziecka (art. 1801
    §1-2) - wymagałyby dokładnego wieku dziecka w dniu zgonu, którego
    schemat nie przechwytuje; sygnalizowane ostrzeżeniem zamiast zgadywane.
    Ten sam mechanizm (`_resolve_maternity_leave_weeks`, współdzielone z
    kalkulatorem) - **nie** dotyczy urlopu ojcowskiego ani urlopu przy
    adopcji/rodzinie zastępczej (art. 1801 dotyczy wyłącznie urlopu po
    własnym porodzie).
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
    **Poprawka po recenzji (realny bug, nie tylko cytowanie)**: wcześniej
    stawka 81,5% była stosowana jednolicie do całego wymiaru każdego
    wariantu, łącznie z nieprzenoszalnymi 9 tygodniami drugiego rodzica -
    niezgodnie z ustawą zasiłkową art. 31 ust. 3f, który te 9 tygodni
    zawsze płaci 70%, niezależnie od wybranego wariantu stawki. Każdy
    wariant ma teraz osobną stawkę per rodzic
    (`rate_percentage_parent_a`/`rate_percentage_parent_b`): rodzic
    zajmujący "dzieloną" pulę (max wariant) dostaje stawkę podwyższoną,
    jeśli wybrana, drugi rodzic na swoich dokładnie 9 tygodniach zawsze
    70%. W wariancie równego podziału stosowane jest 70% dla obojga - przy
    dowolnym podziale żaden rodzic nie składa wniosku o cały przysługujący
    wymiar w jednym ciągu, więc stawka podwyższona nie ma jednoznacznego
    zastosowania.
  - **Nieużywane jeszcze pola schematu**: `employment_duration_months`,
    `bonus_type`, `months_since_last_benefit` istnieją w requestcie, ale
    podstawa wymiaru ich jeszcze nie uwzględnia (niuanse art. 37/38/42/43) -
    to realny, niedokończony zakres, nie kosmetyka.
  - **Poprawka bezpieczeństwa danych wejściowych**: ekstremalnie duże
    wartości (`average_monthly_income_zl`/`voluntary_contribution_base_zl`/
    `debt_amount_zl`, np. literówka z kilkudziesięcioma cyframi) docierały
    do arytmetyki `Decimal` i powodowały nieobsłużony wyjątek
    `decimal.InvalidOperation` przy `.quantize()` (precyzja kontekstu
    Decimal to domyślnie 28 cyfr) - skutkowało to `HTTP 500` zamiast
    czytelnego błędu walidacji. Dodano górny limit (1 mld zł/miesiąc,
    absurdalnie wysoki względem realnych dochodów) na te pola w schemacie -
    takie wartości są teraz odrzucane z `HTTP 422` jeszcze przed dotarciem
    do obliczeń.
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
- **eBobo Legal Intelligence — Funkcja 1 (nowość)**: AI (OpenRouter) wyjaśnia w
  prostym języku wynik oceny uprawnień (`not_eligible`/`requires_verification`),
  zamiast suchej listy `missing_data`/`unmet_conditions`.
  - `POST /api/v1/legal-advisor/explain/{benefit_code}` — przyjmuje **ten sam**
    payload co `/eligibility/check/{benefit_code}` i **sam ponownie wywołuje
    silnik** (nigdy nie ufa wynikowi zadeklarowanemu przez frontend).
  - AI dostaje wyłącznie zminimalizowane dane: opisy warunków już
    wygenerowane przez silnik (`met_conditions`/`unmet_conditions`/
    `missing_data`/`warnings`) i **faktyczną treść** (nie tylko etykiety)
    fragmentów prawnych z nowej, niewielkiej lokalnej bazy wiedzy
    (`app/legal_knowledge/`) — nigdy surowego payloadu użytkownika (dochody,
    dane zdrowotne dziecka itd.).
  - **Status/kwota zawsze z silnika, nigdy z AI** — schemat odpowiedzi AI
    (`AIExplanationRaw`) nie ma nawet pola na status/kwotę.
  - **"Minimalny RAG" bez bazy wektorowej** (`app/legal_knowledge/`) — 23
    ręcznie skurowane fragmenty (ustawa zasiłkowa, Kodeks pracy, Poradnik ZUS
    2026), każdy z `id`/`source`/`citation`/`content`/`effective_from`/
    `related_benefit_codes`. Treść fragmentów nie jest wymyślona od nowa —
    jest rozbita z cytatów już zweryfikowanych i używanych w
    `BenefitRuleVersion.legal_basis` (w tym poprawionych przy okazji napraw
    Etap 4). Wybór fragmentów = proste filtrowanie po `benefit_code` i dacie
    obowiązywania (`get_fragments_for_benefit`), bez wyszukiwania
    semantycznego — niepotrzebne przy tak małym, statycznym zbiorze.
  - **Każdy cytat prawny i każda rekomendacja AI są sprawdzane** względem
    zbioru fragmentów faktycznie przekazanych modelowi dla danego
    świadczenia — samo istnienie cytowanego id to za mało: rekomendacja
    (`suggested_next_steps`) powołująca się na fragment spoza tego zbioru
    jest odrzucana **w całości** (nie pokazywana jako niepewna — po prostu
    nie pokazywana), a niezweryfikowane cytaty (`verified_legal_basis`) są
    cicho pomijane. Każde odrzucenie wymusza
    `requires_additional_verification=true` i dokłada deterministyczny krok
    "skontaktuj się z ZUS lub doradcą/prawnikiem".
  - **Brak fragmentów wiedzy prawnej dla danego świadczenia** (luka w bazie,
    nie awaria AI) jest obsłużony wprost — backend nie woła wtedy modelu "na
    pusto", tylko zwraca deterministyczny wynik z jawnym zaznaczeniem
    wymaganej weryfikacji.
  - **Niedostępność OpenRouter (brak klucza, timeout, błąd HTTP, nieprawidłowy
    JSON) nigdy nie zwraca HTTP 500** — zwracany jest deterministyczny
    fallback (`ai_available=false`, `source="fallback"`) zbudowany wyłącznie
    z wyniku silnika.
  - Każde wywołanie loguje się do tego samego `request_log` co
    eligibility/calculate/compare (`endpoint="legal_advisor_explain"`,
    `request_log_entry_id` w odpowiedzi) — przygotowanie pod przyszłe
    powiązanie oceny + wersji reguł + analizy AI + feedbacku użytkownika
    (Funkcje 2-4, jeszcze nie zaimplementowane).
  - Konfiguracja: `OPENROUTER_API_KEY`/`OPENROUTER_MODEL`/
    `OPENROUTER_BASE_URL`/`OPENROUTER_TIMEOUT_SECONDS` w `.env` (klucz
    dostarcza użytkownik lokalnie, nigdy w repo). Bez klucza endpoint działa
    normalnie w trybie fallback.
  - Zob. pamięć projektu `project-ebobo-legal-advisor`.
- **eBobo Legal Intelligence — Etap 2, Faza A (nowość)**: zgłaszanie wątpliwości
  co do wyniku oceny (`app/legal_feedback/`). Analiza AI zgłoszenia i panel
  administratora (przeglądanie/zmiana statusu) to **Faza B, osobne zadanie** -
  świadomie nie w tym zakresie.
  - `POST /api/v1/legal-feedback` — wymaga sesji (`Authorization: Bearer <token>`
    z `POST /auth/session`). Body: `{request_log_entry_id, feedback_type:
    "incorrect_result"|"missing_case"|"incorrect_explanation"|"zus_discrepancy"|
    "missing_input", user_comment, expected_result?}`. `expected_result` to
    wyłącznie opinia zgłaszającego - nigdy nowa ocena uprawnienia, nigdy nie
    zmienia zapisanego wyniku.
  - **Luka architektoniczna znaleziona i naprawiona przy tej okazji**:
    `request_log_entries` w ogóle nie zapisywało, kto wykonał dany request -
    `eligibility/check`/`calculate`/`compare`/`legal-advisor/explain` są i
    pozostają w pełni anonimowe (zero wymaganej autoryzacji). Dodano nullable
    `user_id` na `RequestLogEntry`, wypełniane **opcjonalnie** przez nową
    zależność `get_current_user_optional` (nigdy nie zwraca 401 - brak/zły/
    wygasły token = po prostu "anonimowo", jak dotąd). Żaden istniejący
    endpoint nie wymaga teraz tokenu częściej niż wcześniej.
  - **Zgłoszenie można powiązać wyłącznie z własną oceną**: backend sprawdza
    `request_log_entry.user_id == current_user.id` - w przeciwnym razie (albo
    gdy wpis nie istnieje, albo gdy powstał anonimowo i `user_id` jest `None`)
    zwraca `404`, nigdy `403` - nie potwierdzamy w ten sposób istnienia cudzego
    wpisu (ochrona przed IDOR). W praktyce jedyny endpoint zwracający dziś
    `request_log_entry_id` w odpowiedzi to `/legal-advisor/explain` - to
    zamierzona ścieżka: wyjaśnienie → użytkownik się nie zgadza → zgłoszenie.
  - **Rate limiting bez nowej zależności**: proste liczenie w bazie (maks. 10
    zgłoszeń na godzinę na `user_id`) zamiast dodawania biblioteki dla jednego
    endpointu - `HTTP 429` po przekroczeniu.
  - Oryginalny wpis `request_log` **nigdy nie jest modyfikowany** - zgłoszenie to
    osobny rekord (`LegalFeedback`) z własnym `status` (domyślnie `new`),
    przechowujący `rules_version` skopiowane z ORYGINALNEJ oceny (nie z
    momentu zgłoszenia). Minimalizacja danych: zgłoszenie NIE kopiuje pełnego
    `request_payload`/`response_payload` - te już żyją w powiązanym wpisie
    `request_log`, dostępnym przez FK.
  - Zob. pamięć projektu `project-ebobo-legal-feedback`.

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
| 8 | eBobo Legal Intelligence — Funkcja 1: wyjaśnianie wyniku oceny przez AI (OpenRouter), ugruntowane w lokalnej bazie wiedzy prawnej (minimalny RAG) | ✅ zrobione - patrz "Zrobione" wyżej; Funkcje 2-4 (odwołania od ZUS, feedback, zatwierdzanie zmian reguł) odłożone |
| 9 | eBobo Legal Intelligence — Etap 2, Faza A: zgłaszanie wątpliwości co do oceny (`POST /legal-feedback`) | ✅ zrobione - patrz "Zrobione" wyżej; Faza B (analiza AI zgłoszenia + panel administratora) osobne zadanie |

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
  core/             # konfiguracja (Settings, zmienne .env), wyjątki domenowe + handlery FastAPI
  db/
    base.py         # Base (SQLAlchemy declarative)
    session.py      # engine, SessionLocal, get_db(), ensure_seeded() przy starcie
    models/
      benefit_rule.py  # BenefitType, BenefitRuleVersion (wersjonowane reguły/stawki/dokumenty)
      user.py          # User, AuthStatus (sesja end-usera)
      request_log.py   # RequestLogEntry (log "Wnioski" w panelu admina)
  rules/
    seed.py         # jedyne źródło prawdy dla stawek/okresów/dokumentów/terminów - ensure_seeded()
  eligibility/      # SILNIK UPRAWNIEŃ - czysta logika, bez HTTP/DB w środku
    schemas.py      # MaternityLeaveEligibilityRequest (wspólny request), EligibilityResult, MissingFieldInfo, BenefitPlan...
    engine.py       # 9 evaluate_*_eligibility(), _resolve_maternity_leave_weeks, _missing()/_missing_many()
    registry.py     # ELIGIBILITY_EVALUATORS: benefit_code -> funkcja oceny
    rules_repository.py  # get_current_rule(db, benefit_code)
  calculator/       # KALKULATOR KWOT - niezależny od potwierdzonych uprawnień
    schemas.py      # CalculatedAmount, ParentalLeaveCompareRequest/Response...
    engine.py       # calculate_basis_of_calculation(), calculate_benefit(), compare_parental_leave_variants()
  legal_advisor/    # eBobo Legal Intelligence, Funkcja 1 - AI (OpenRouter) wyjaśnia wynik oceny
    schemas.py      # AIExplanationRaw, GroundedRecommendation, LegalAdvisorExplainResponse
    service.py      # explain_eligibility_result() - re-uruchamia silnik, groundinguje w legal_knowledge
  legal_feedback/   # eBobo Legal Intelligence, Etap 2 Faza A - zgłaszanie wątpliwości co do oceny
    schemas.py      # LegalFeedbackCreateRequest/Response
    service.py      # submit_feedback() - sprawdza własność wpisu, rate limit
  legal_knowledge/  # "minimalny RAG" - statyczna baza fragmentów wiedzy prawnej, bez bazy wektorowej
    fragments.py    # LEGAL_FRAGMENTS (23 fragmenty: ustawa zasiłkowa, Kodeks pracy, Poradnik ZUS)
    repository.py   # get_fragments_for_benefit(), get_fragment_by_id()
  ai_provider/      # cienki, dostawca-agnostyczny klient OpenRouter (OpenAI-compatible chat completions)
    client.py       # request_json_completion(), AIProviderUnavailableError/AIProviderInvalidResponseError
  mock_zus/         # MockZUSProvider - symulowane dane ZUS per profil demonstracyjny
    profiles.py     # 5 statycznych profili
    comparator.py   # porównanie deklaracji usera vs. profilu, pole-po-polu
  formalities/      # przewodnik po formalnościach (dokumenty/terminy/ryzyka/next_steps)
    content.py      # statyczne treści wzięte wprost z briefu (Projekt.pdf §H/§I)
  admin/            # panel administracyjny (JWT, jeden użytkownik z env) + log zapytań
    security.py     # create_admin_access_token(), get_current_admin()
    request_log.py  # log_request()/list_request_log_entries()/get_request_log_entry()
  auth/             # sesja end-usera (anonimowa -> symulowane logowanie mObywatel)
    security.py     # create_user_token(), get_current_user(), get_user_for_refresh()
  api/v1/
    endpoints/      # po jednym routerze na moduł: health, auth, eligibility, calculator,
                     #   legal_advisor, mock_zus, formalities, admin
    router.py       # agregacja wszystkich routerów v1
  schemas/common.py # HealthResponse
  services/         # (zarezerwowane, obecnie puste - logika biznesowa żyje w modułach wyżej)
  main.py           # fabryka aplikacji FastAPI (create_app), montuje /admin jako static files
static/admin/       # statyczny frontend panelu administracyjnego (vanilla HTML/JS, bez build stepu)
tests/              # 228 testów pytest, jeden plik na moduł; conftest.py = izolowana baza in-memory per test
```

Zasady architektoniczne:
- **Reguły i kwoty świadczeń (`app/rules`, `BenefitRuleVersion`) są oddzielone od
  logiki obliczeniowej (`app/eligibility`, `app/calculator`)** — aktualizacja
  przepisów (stawki, terminy, dokumenty) nie wymaga zmian w kodzie liczącym,
  tylko nowej wersji reguły w bazie.
- **Silnik uprawnień jest deterministyczny i ma zawsze pierwszeństwo przed AI.**
  `app/legal_advisor` nigdy nie ustala statusu ani kwoty — tylko tłumaczy w
  prostym języku wynik, który silnik już wyliczył, i to tylko w oparciu o
  fragmenty faktycznie zweryfikowane względem `app/legal_knowledge`.
- **Nigdy nie zgaduj** — brakujące dane zawsze trafiają do `missing_data`/
  `missing_fields`, nigdy nie są cicho zakładane (np. `is_full_time_employment`
  nieznane → brak podstawy minimalnej zamiast zgadywania; `children_survived_count`
  nieznane przy wieloraczkach i martwym urodzeniu → `requires_verification`
  zamiast zawyżonego wymiaru).

## Pełna referencja API

Zawsze aktualny, auto-generowany schemat (dokładne typy, przykłady) jest pod
`/docs` (Swagger) i `/redoc`. Poniżej narracyjna referencja wszystkich
endpointów i wspólnego schematu requestu - do szybkiej orientacji bez
klikania po Swaggerze. Prefiks wszystkich ścieżek API: `/api/v1`.

### `MaternityLeaveEligibilityRequest` - wspólny schemat dla eligibility/calculate/legal-advisor

Jeden, wspólny request dla `POST /eligibility/check/{benefit_code}`,
`POST /benefits/calculate/{benefit_code}` i `POST /legal-advisor/explain/{benefit_code}`.
Każde pole dotyczy tylko tych świadczeń, których ocena go faktycznie używa -
pozostałe są po prostu ignorowane. Tylko `children_count` jest wymagane
(`≥1`); wszystkie pozostałe to `| None` - brak/`null` oznacza "nieznane", nigdy
nie jest traktowane jako "nie".

| Pole | Typ | Używane przez |
|---|---|---|
| `children_count` | `int` (wymagane, ≥1) | wszystkie |
| `insured_at_birth` | `bool` | macierzyński, rodzicielski |
| `insurance_title` | `"umowa_o_prace"\|"zlecenie"\|"dzialalnosc_gospodarcza"\|"inny"` | macierzyński, chorobowy w ciąży, kalkulator |
| `debt_amount_zl` | `Decimal` (0-1 mld) | próg zadłużenia art. 2a (5 świadczeń) |
| `employment_ended_reason` | `"upadlosc_likwidacja_smierc_pracodawcy"\|"naruszenie_prawa_wyrokiem_sadu"` | macierzyński, alternatywny |
| `other_employment_secured` | `bool` | alternatywny |
| `father_insured` | `bool` | urlop ojcowski |
| `child_age_months` | `int` | urlop ojcowski |
| `is_pregnant` | `bool` | chorobowy w ciąży, rehabilitacyjne |
| `insured_days_continuous` | `int` | chorobowy w ciąży (okres wyczekiwania) |
| `child_hospitalization_weeks` | `int` | uzupełniający urlop macierzyński |
| `gestational_week_at_birth` | `int` | uzupełniający urlop macierzyński |
| `birth_weight_grams` | `int` | uzupełniający urlop macierzyński |
| `postpartum_weeks_elapsed` | `int` | uzupełniający urlop macierzyński (termin wniosku) |
| `is_adoption_or_foster_care` | `bool` | adopcja/rodzina zastępcza |
| `foster_care_type` | `"rodzina_zastepcza"\|"rodzina_zastepcza_zawodowa"\|"wniosek_o_przysposobienie"` | adopcja/rodzina zastępcza |
| `child_age_years` | `int` | adopcja/rodzina zastępcza |
| `school_obligation_deferred` | `bool` | adopcja/rodzina zastępcza (limit wieku 7 vs 10 lat) |
| `za_zyciem_certificate` | `bool` | urlop rodzicielski (wydłużony wymiar) |
| `full_dose_claimed_within_21_days` | `bool` | urlop rodzicielski (stawka 70% vs 81,5%) |
| `other_parent_used_parental_leave_weeks` | `int` | urlop rodzicielski (pula drugiego rodzica) |
| `part_time_fraction_during_parental_leave` | `Decimal` (≤0.5) | urlop rodzicielski (łączenie z pracą) |
| `sickness_benefit_period_exhausted` | `bool` | świadczenie rehabilitacyjne |
| `medical_prognosis_recovery_possible` | `bool` | świadczenie rehabilitacyjne |
| `excluded_from_rehabilitation_benefit` | `bool` | świadczenie rehabilitacyjne |
| `is_stillbirth_or_infant_death` | `bool` | macierzyński (art. 1801, skraca do 8 tyg.), zasiłek pogrzebowy |
| `children_survived_count` | `int` (**nowość**) | macierzyński - wymiar przy wieloraczkach z martwym urodzeniem/zgonem części dzieci |
| `days_since_death` | `int` | macierzyński (próg 7 dni od zgonu, **jeszcze niemodelowany** - patrz "Zrobione") |
| `days_since_burial` | `int` | zasiłek pogrzebowy (termin 12 mies. od pochówku, **nie** od zgonu) |
| `average_monthly_income_zl` | `Decimal` (0-1 mld) | kalkulator (podstawa wymiaru, pracownik) |
| `is_full_time_employment` | `bool` | kalkulator (podstawa minimalna, art. 45 ust. 1) |
| `employment_duration_months` | `int` | kalkulator (**jeszcze nieużywane**) |
| `voluntary_contribution_base_zl` | `Decimal` (0-1 mld) | kalkulator (podstawa wymiaru, zlecenie/działalność) |
| `bonus_type` | `"miesieczna"\|"kwartalna"\|"roczna"` | kalkulator (**jeszcze nieużywane**) |
| `months_since_last_benefit` | `Decimal` | kalkulator (**jeszcze nieużywane**) |

### Kody świadczeń (`benefit_code`)

| Kod | Nazwa |
|---|---|
| `zasilek_macierzynski_urlop_macierzynski` | Zasiłek macierzyński za okres urlopu macierzyńskiego |
| `zasilek_w_wysokosci_zasilku_macierzynskiego` | Zasiłek w wysokości zasiłku macierzyńskiego (po ustaniu ubezpieczenia w ciąży) |
| `urlop_ojcowski` | Zasiłek macierzyński za okres urlopu ojcowskiego |
| `urlop_rodzicielski` | Zasiłek macierzyński za okres urlopu rodzicielskiego |
| `zasilek_chorobowy_w_ciazy` | Zasiłek chorobowy w ciąży |
| `swiadczenie_rehabilitacyjne` | Świadczenie rehabilitacyjne |
| `uzupelniajacy_urlop_macierzynski` | Zasiłek za okres uzupełniającego urlopu macierzyńskiego |
| `urlop_na_warunkach_urlopu_macierzynskiego` | Zasiłek za okres urlopu na warunkach urlopu macierzyńskiego (adopcja/rodzina zastępcza) |
| `zasilek_pogrzebowy_martwe_urodzenie` | Zasiłek pogrzebowy w razie martwego urodzenia dziecka |

### Auth (sesja end-usera - w pełni symulowana, nie prawdziwe mObywatel)

| Endpoint | Auth | Opis |
|---|---|---|
| `POST /auth/session` | brak | Tworzy anonimową sesję (pierwsze otwarcie appki). Zwraca `access_token`, `user_id`, `status: "anonymous"`. |
| `POST /auth/mobywatel/login` | `Bearer <token>` | Symulowane logowanie - podnosi sesję do `status: "authenticated"`, ustawia przykładowe dane. Body: `{pesel?: string}`. |
| `GET /auth/me` | `Bearer <token>` | `{user_id, status, first_name, last_name, pesel}`. |
| `POST /auth/refresh` | `Bearer <token>` (działa nawet po wygaśnięciu) | Nowy token dla tego samego `user_id`. |
| `POST /auth/logout` | `Bearer <token>` | Unieważnia bieżącą sesję (`token_version`), zwraca nową sesję anonimową. |

### Eligibility

**`POST /eligibility/check/{benefit_code}`** - brak auth. Request: patrz tabela
pól wyżej. Response (`EligibilityResult`):

```
benefit_code, benefit_name
status: "likely_eligible" | "not_eligible" | "requires_verification"
met_conditions: string[]
unmet_conditions: string[]
missing_data: string[]              # wolny tekst do wyświetlenia
missing_fields: [{field, message}]  # stabilne id pól (patrz "Zrobione") - message = ten sam tekst co w missing_data
possible_solutions: [{type: "alternative_benefit"|"corrective_action"|"limitation", description, legal_basis?, related_benefit_code?}]
plan: null | {weeks?, duration_description?, rate_percentage?, lump_sum_amount_zl?, institution, required_documents: [{code,name,when}], deadlines: string[], legal_basis: string[]}
rules_version: int
data_source: "user"
warnings: string[]
```

404 dla nieznanego `benefit_code`, 422 dla złego payloadu. `plan` jest `null`,
gdy status `!= likely_eligible` (poza wyjątkiem: `requires_verification` z
pustymi `unmet_conditions` też może mieć plan, gdy tylko brakuje danych
niezwiązanych bezpośrednio z samym planem).

### Calculator

**`POST /benefits/calculate/{benefit_code}`** - ten sam request co eligibility,
niezależnie od statusu uprawnień. Response (`CalculatedAmount`):

```
benefit_code, benefit_name
basis: null | {monthly_basis_zl, daily_basis_zl, deduction_rate_percent, minimum_basis_applied, warnings[]}
total_days: int | null
total_amount_zl: decimal | null
lump_sum_amount_zl: decimal | null
rate_breakdown: [{days, rate_percentage, amount_zl}]
rules_version: int
warnings: string[]
```

**`POST /benefits/compare/urlop-rodzicielski`** - porównanie 3 wariantów
podziału urlopu rodzicielskiego. Request: `{children_count, za_zyciem_certificate?,
full_dose_claimed_within_21_days?, parent_a: ParentCalculationInput, parent_b: ParentCalculationInput}`,
gdzie `ParentCalculationInput = {label, average_monthly_income_zl?, insurance_title?,
voluntary_contribution_base_zl?, is_full_time_employment?}`. Response:
`{total_pool_weeks, non_transferable_weeks_per_parent, rate_percentage, variants: [{label, weeks_parent_a, weeks_parent_b, rate_percentage_parent_a, rate_percentage_parent_b, amount_parent_a_zl, amount_parent_b_zl, total_household_amount_zl}], warnings[]}`.

### Legal Advisor

**`POST /legal-advisor/explain/{benefit_code}`** - identyczny request co
eligibility (sam ponownie liczy wynik silnikiem). Response
(`LegalAdvisorExplainResponse`):

```
benefit_code, status          # status zawsze = wynik silnika
explanation: string
missing_data_explained: string[]
suggested_next_steps: string[]
other_benefits_to_check: string[]
verified_legal_basis: string[]        # faktyczna treść przepisów, zweryfikowana
requires_additional_verification: bool
rules_version: int
ai_available: bool
source: "ai" | "fallback"
request_log_entry_id: int | null
```

`source=="ai"` oznacza realne wywołanie OpenRouter (do ~15s, pokaż loader).
`source=="fallback"` (brak klucza/timeout/zła odpowiedź/brak fragmentów wiedzy
dla świadczenia) - zawsze HTTP 200 z sensowną treścią zbudowaną z samego
wyniku silnika, nigdy 500.

### Legal Feedback

**`POST /legal-feedback`** - wymaga `Authorization: Bearer <token>` (z
`POST /auth/session`). Request: `{request_log_entry_id, feedback_type, user_comment,
expected_result?}`. Response `201` (`LegalFeedbackResponse`): `{id,
request_log_entry_id, benefit_code, feedback_type, user_comment, expected_result,
status: "new", rules_version, created_at}`. `404` gdy wpis nie istnieje albo
nie należy do tej sesji; `429` po przekroczeniu 10 zgłoszeń/godzinę; `401` bez
tokenu. Analiza AI zgłoszenia i panel admina (przeglądanie/status) - osobne
zadanie (Faza B).

### MockZUSProvider

| Endpoint | Opis |
|---|---|
| `GET /mock-zus/profiles` | `[{profile_id, label, description}]` - 5 profili. |
| `GET /mock-zus/profiles/{profile_id}` | Pełne symulowane dane: ubezpieczenie, okresy, zadłużenie, e-ZLA, historia świadczeń, zawsze z `data_source: "mock_zus_simulated"`. |
| `POST /mock-zus/profiles/{profile_id}/compare` | Body: deklaracje usera. Response: `comparisons: [{field, declared_value, simulated_value, matches: bool\|null}]`, `has_discrepancies: bool`. |

### Formalities

| Endpoint | Opis |
|---|---|
| `GET /formalities/general` | `how_benefits_are_paid`, `general_risks[]`, `employment_protection_note`, `charitable_support_note`, `difficult_situation_benefit_codes[]`. |
| `GET /formalities/{benefit_code}` | `institution`, `required_documents[]`, `deadlines[]`, `legal_basis[]`, `next_steps[]`, `rules_version`. |

### Admin (panel wewnętrzny, osobny login)

`POST /admin/login` (`{username, password}` → JWT) →
`GET /admin/me`, `GET /admin/dashboard`,
`GET /admin/request-log?benefit_code=...&limit=...`,
`GET /admin/request-log/{id}` - wszystkie wymagają
`Authorization: Bearer <admin_token>`.

### Health

`GET /health` - brak auth. `{status, app_name, environment, version}`.

### Błędy ogólne

`404` nieznany `benefit_code`/`profile_id`/id, `422` walidacja body (komunikat
wskazuje pole), `401` brak/zły token. Żaden endpoint eligibility/calculator/
legal-advisor nie zwraca 500 w normalnym działaniu -
`requires_verification`/`not_eligible`/`fallback` to zawsze 200.

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

Każdy test (`tests/conftest.py`) dostaje własną, świeżą bazę SQLite
in-memory (nadpisanie `get_db`) - **nigdy** nie dotyka realnego `app.db` z
dev servera. Wcześniej `client` był podpięty wprost pod `app.db`, więc wpisy
`request_log` z kolejnych uruchomień testów (i z ręcznego smoke-testu)
zostawały na stałe i z czasem łamały asercje liczące wpisy dla danego
`benefit_code` - naprawione przy okazji dodania
`POST /legal-advisor/explain/{benefit_code}` (kolejny endpoint piszący do
`request_log`), zanim zdążyło narobić tej samej szkody co incydent opisany
w pamięci `feedback-ebobo-shared-dev-db`.

## Konfiguracja

Wszystkie ustawienia czytane są ze zmiennych środowiskowych / pliku `.env`
(zobacz `.env.example`): nazwa aplikacji, prefiks API, dozwolone originy CORS,
`DATABASE_URL`, parametry uploadu plików, adresy symulowanych integracji
ZUS/mObywatel oraz dostawcę AI (`OPENROUTER_API_KEY`/`OPENROUTER_MODEL`/
`OPENROUTER_BASE_URL`/`OPENROUTER_TIMEOUT_SECONDS`) dla `/legal-advisor/explain`.
