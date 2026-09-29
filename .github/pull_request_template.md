## Summary

<!-- What changes and why. Link the issue: Closes #NN -->

## Requirement

<!-- F01 to F17 identifier(s) this touches -->

## Checklist

- [ ] Branch named `feature/<id>-<short-name>`, `fix/<short-name>` or `docs/<short-name>`
- [ ] Tests added or updated; suite passes in the Compose stack (`docker compose run --rm api pytest -q`)
- [ ] Migrations generated and `makemigrations --check` clean
- [ ] No new dependency, or the licence is MIT, BSD, Apache 2.0, PostgreSQL or PSF and ADR updated
- [ ] No secrets, personal data or real employee records in code, fixtures or screenshots
- [ ] Writes to personnel data produce audit rows
- [ ] Docs updated (`docs/components.md`, `docs/SETUP.md`) if behaviour or setup changed
