# architecture overview

Rosie is a Python Discord application organized around independent command modules and shared services.

1. **Discord interaction layer.** Slash commands, message embeds, select menus, and buttons handle user-facing interactions.
2. **Service layer.** Shared modules coordinate progression, transactions, and game state across commands.
3. **Persistence.** SQLite maintains durable state for recurring actions and multiplayer experiences.
4. **Scheduled work.** Asynchronous tasks support timed events and periodic maintenance.

The public source samples illustrate the interaction layer; the private application implements the remaining services and deployment controls.

## engineering concerns

Stateful Discord interfaces must handle authorization, expired components, duplicate clicks, and persistence across process restarts. Currency and prize operations must also avoid duplicate settlements. The project treats these concerns as first-class implementation requirements.

This diagram is conceptual, not a production network map:

```text
Discord user
    |
command / button
    |
interaction handlers
    |
private application services
    |
persistent game state
```

Production configuration, privileged roles, game probabilities, and operations are intentionally omitted.
