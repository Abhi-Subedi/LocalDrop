# Governance

LocalDrop is maintained by one person with limited time. This document exists so
that expectations are explicit rather than discovered during a heated review.

## Roles

**Maintainer** — Abhi-Subedi. Merges pull requests, cuts releases, and has final
say on scope. Holds the signing keys for the release workflow and the
`ghcr.io/abhi-subedi/localdrop` package.

**Contributors** — anyone who opens an issue or pull request. Contributions are
accepted under the terms in [CONTRIBUTING.md](CONTRIBUTING.md) and the
[AGPL-3.0](LICENSE).

There are no other formal roles, no maintainer committee, and no voting. If that
ever changes, this file changes first.

## How decisions are made

Most decisions are made by the maintainer in the pull request or issue where they
come up, and are written down. The reasoning that is not obvious from the diff
belongs in an ADR under [`docs/adr/`](docs/adr/) — that is what the directory is
for, and two of them ([ADR-010](docs/adr/ADR-010-license.md), on the licence, and
the one on embedded PostgreSQL) already carry decisions you would otherwise
assume were arbitrary.

Disagreements about direction are resolved by whoever maintains the repository.
You can always fork.

## Scope

The stated purpose of LocalDrop is: **move a file to another device on your own
network, privately, without an account or a cloud.** Features that serve that
goal get merged.

Feature requests that expand the product into something else — group accounts,
chat, calendars, a plugin system, activity federation — are not going to be
accepted, even when they are good ideas and even when they are implemented. The
list of things LocalDrop deliberately does not do is maintained in the
[Status](README.md#status) section of the README, and "not yet" entries there are
answered with a reason.

This is not a judgement about those features. It is a statement that a project
with one maintainer has to be small in order to still exist in three years.

## Contributing

- Read [CONTRIBUTING.md](CONTRIBUTING.md) first, including the commit and PR
  conventions.
- Security issues never go through public issues — see
  [SECURITY.md](SECURITY.md).
- Behaviour questions ("why is it like this?") belong in a discussion or issue
  *before* you write code. A PR that answers an unanswered question usually gets
  sent back.

## Changing this document

Open a pull request. If you are asking for a governance change you will get a
straight answer, and "no, and here is why the project is small on purpose" is a
valid outcome.

## Code of conduct

[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) applies in all project spaces.