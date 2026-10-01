# Support

LocalDrop is maintained by one person in their spare time. There is no support
contract, no SLA, and no paid tier. Here is where to ask, and what makes an
answer likely.

## Where to ask

| Your question is about | Use |
|---|---|
| A bug or something that looks broken | [Issues](https://github.com/Abhi-Subedi/LocalDrop/issues/new) — use the **bug report** template |
| "Is this supposed to work like this?" or "how do I…"? | [Discussions](https://github.com/Abhi-Subedi/LocalDrop/discussions) |
| A feature request | [Discussions](https://github.com/Abhi-Subedi/LocalDrop/discussions) → *Ideas* |
| How to install or configure | The docs first: [INSTALLATION](docs/INSTALLATION.md), [CONFIGURATION](docs/CONFIGURATION.md) |
| A security problem | **Not** a public issue — see [SECURITY.md](SECURITY.md) |
| A broken or missing release artefact | [Issues](https://github.com/Abhi-Subedi/LocalDrop/issues/new) |

Before opening anything, the odds are the answer is in one of these:

- [`docs/INSTALLATION.md`](docs/INSTALLATION.md) — every install method
- [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) — every setting
- [`docs/BACKUP.md`](docs/BACKUP.md) — backups and restores
- [`docs/SECURITY.md`](docs/SECURITY.md) — threat model and hardening
- [`CHANGELOG.md`](CHANGELOG.md) — what is fixed, and what is still broken
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — running it from source

## How to get an answer

Include these three things and you will usually get a reply:

1. **Version and install method.** `curl -s http://<host>/api/v1/version`, or
   the About panel in Settings. Then say whether it is Docker, the native
   binary, Homebrew, or `pip`.
2. **What you expected, and what happened instead.**
3. **The relevant log lines.** Docker: `docker compose logs app`. Native Linux:
   `journalctl -u localdrop -n 100 --no-pager`. **Redact tokens, passwords and
   file names you do not want public.**

If the problem is only reproducible on your machine, an `ACCESS DENIED` response
from the endpoint is a strong clue. The most common cause is a proxy
misconfiguration, not LocalDrop.

## Before you upgrade

Upgrades are forward-only: database migrations never reverse. If you are
upgrading anything other than a patch release, take a backup first
(`./scripts/backup.sh`, see [`docs/BACKUP.md`](docs/BACKUP.md)). Downgrades are
not supported; recovery means restoring that backup.

## What I cannot promise

- Same-day replies, or any reply at all during holidays.
- Fixes for "nice to have" features, however well argued.
- Support for unsupported versions. Only the latest minor receives fixes.
- Commercial support, SLAs, or custom work. If you need that, this project is
  not the right tool.

## Contributing

Fixes, tests and documentation are genuinely welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md). A PR that comes with a test and passes CI is
far more likely to be merged than one that does not.
