# Security Policy

Andromeda is local-first: the API binds to `127.0.0.1` and rejects non-loopback
clients by default. No data leaves your machine.

## Reporting a vulnerability

If you find a security issue, please **do not open a public issue**.
Contact the author directly (see profile) with a description and steps to
reproduce. You'll get a response within a few days, and credit in the
changelog if you want it.

## Scope notes

- The optional login gate protects the API surface, not the SQLite files on
  disk — protect your user account / disk encryption as usual.
- The code sandbox executes snippets locally with hard timeouts; treat it as
  "run code on my machine", because that is exactly what it does.
