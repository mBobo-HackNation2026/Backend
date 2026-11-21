"""Silnik oceny uprawnień do świadczeń. Każde świadczenie ma własną funkcję oceny w
``engine.py`` i własny wpis w ``registry.py`` (kod świadczenia -> funkcja oceny), zasilany
własną wersją reguły w bazie (``app/rules/seed.py``). Obecnie obsługiwane: zasiłek
macierzyński za okres urlopu macierzyńskiego i zasiłek w wysokości zasiłku macierzyńskiego
(po ustaniu ubezpieczenia w ciąży, ustawa zasiłkowa art. 30).

Wynik oceny ma zawsze 4 części: status, uzasadnienie (spełnione/niespełnione
warunki, brakujące dane), możliwe rozwiązania (dopuszczalne działania,
świadczenia alternatywne, ograniczenia) i plan (wnioski, załączniki,
instytucja, terminy, podstawa prawna). Nigdy nie udajemy decyzji ZUS - co
najwyżej wstępną ocenę.
"""
