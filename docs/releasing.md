# Releasing

`altium-kicad-cli` releases are tag-driven: pushing a `vX.Y.Z` tag runs
`.github/workflows/release.yml`, which builds the sdist + wheel, verifies the
tag matches `pyproject.toml`, extracts that version's `CHANGELOG.md` section as
the release notes, and creates a GitHub Release with the build artifacts
attached. A separate `publish-pypi` job then publishes to PyPI via
[trusted publishing](https://docs.pypi.org/trusted-publishers/) (OIDC, no API
token) — it only runs if the repo has opted in (see "PyPI publishing" below);
otherwise it is skipped and the release still succeeds.

## Runbook

1. Bump `version` in `pyproject.toml` (run `python tools/sync_version.py` if
   the plugin manifests carry a version too).
2. Move `CHANGELOG.md`'s `## [Unreleased]` section to `## [X.Y.Z]` (that
   section becomes the GitHub Release body verbatim).
3. `git add pyproject.toml CHANGELOG.md ...` and commit.
4. `git tag vX.Y.Z`
5. `git push origin main && git push origin vX.Y.Z`
6. Watch the `Release` workflow run in the Actions tab; verify the GitHub
   Release was created with `dist/*.whl` and `dist/*.tar.gz` attached, and (if
   PyPI publishing is enabled) that the new version appears on PyPI.

The tag (minus the leading `v`) **must** equal the `pyproject.toml` version, or
the workflow fails fast before building anything.

## PyPI publishing

PyPI publishing is opt-in and uses
[trusted publishing](https://docs.pypi.org/trusted-publishers/), so no PyPI
API token is stored in this repo. To enable it, one time:

1. On PyPI, add a trusted publisher for this project pointing at this GitHub
   repo, workflow file `release.yml`, and environment `pypi`.
2. In GitHub repo Settings > Environments, create an environment named `pypi`
   (optionally with required reviewers for extra safety).
3. Add an environment variable `PYPI_TRUSTED_PUBLISHING` set to `true` on that
   `pypi` environment.

Until that's done, the `publish-pypi` job's `if:` condition evaluates false
and the job is skipped — the release itself never fails because PyPI isn't
configured.
