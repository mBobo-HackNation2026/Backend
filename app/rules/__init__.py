"""Reguły i parametry świadczeń, oddzielone od logiki obliczeniowej.

Kwoty, progi, okresy i warunki ustawowe mają trafiać tutaj (np. jako pliki
JSON/YAML wczytywane przez loader), a nie być zaszyte w kodzie serwisów z
app.services. Dzięki temu aktualizacja przepisów (np. nowa kwota świadczenia)
nie wymaga zmian w logice obliczeniowej.
"""
