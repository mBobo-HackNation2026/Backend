"""Uwierzytelnianie użytkowników końcowych aplikacji (nie panelu admina).

Przy pierwszym otwarciu aplikacji tworzony jest anonimowy `User` (patrz
`app.db.models.user`). Symulowane logowanie mObywatel podnosi status tego
samego użytkownika do `authenticated` i uzupełnia dane profilu - nie tworzy
nowego konta. Dzięki temu dane zebrane w trybie anonimowym (np. odpowiedzi
w kalkulatorze) zostają przypisane do tego samego użytkownika po zalogowaniu.
"""
