<p align="center"><img src="media/emblem.png" width="180" alt="rosie emblem"></p>

<h1 align="center">rosie</h1>

<p align="center">a persistent Discord game about roses, rituals, and community.</p>

Rosie is a Discord bot with a rose-and-ring economy, interactive games, seasonal events, collectible companions, and server-wide progression. It is developed and operated privately; this repository documents the project and includes a small, reviewed selection of authentic command modules.

### explore

- **Economy and progression:** rose balances, daily rewards, gardening, foraging, brewing, and quests.
- **Interactive games:** scratch cards, an arcade, bosses, and server events.
- **Collectibles and social play:** pets, relics, marriage, and leaderboards.
- **Seasonal experiences:** rotating activities and timed community challenges.

Read the [features overview](docs/features.md) and [architecture notes](docs/architecture.md) for a closer look.

### selected code

The following files are **unchanged, reviewed snapshots of real Rosie commands**, not fabricated examples:

- [`examples/help.py`](examples/help.py) — organizing application commands into a Discord help interface.
- [`examples/scratch.py`](examples/scratch.py) — buttons, per-user interaction checks, and rendering a scratch card.
- [`examples/parlor.py`](examples/parlor.py) — an application command and Activity entry-point integration.

These files import runtime modules that remain private. **This repository is not a standalone bot distribution** and the snippets are not intended to run without the private application.

### built with

Python · discord.py · SQLite · asynchronous Discord interactions · persistent game state

### code and asset rights

Rosie's full source, gameplay balancing, internal services, and original production assets are not publicly distributed. Selected files are displayed for project review; no open-source license is granted. All rights reserved.
