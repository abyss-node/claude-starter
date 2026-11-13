# Model tiers

**Reviewed: 2026-11-13.** Review monthly, and whenever a provider ships a new
model. This is the only file in the kit that names specific models. Rules,
agents and skills describe roles, so a new release means editing this file and
nothing else.

**For an agent reading this:** if the review date above is more than a month
old, tell the user, check the provider's current model list, and use that
instead of the table where they differ. Then offer to update this file.

## Roles

| Role | What it does | Claude Code alias | Resolves to (at review) |
|---|---|---|---|
| Top | Hardest judgment: design, gnarly debugging, verification | Fable by model ID if your plan offers it, else `opus` | Fable 5.2 (`claude-fable-5-2`), else Opus 5.5 |
| Upper | Hard implementation, independent review voices, verifier default | `opus` | Opus 5.5 (`claude-opus-5-5`) |
| Middle | Standard features, refactors with a clear spec, tests, boilerplate, one-file scripts | `sonnet` | Sonnet 5.5 (`claude-sonnet-5-5`) |
| Bottom | Lookups and formatting | `haiku` | Haiku 5.5 (`claude-haiku-5-5`) |

Aliases follow new releases within a family on their own. What they miss is a
new tier above them or a change in which family is best for a role. Those are
what a review catches.

## What a review checks

1. The provider's current model list: anything new, retired or renamed.
2. Whether the ranking still holds, using the provider's own guidance and your
   experience. Does the top role still need the top model, or does the next tier
   down now do the job?
3. Price per role. If a cheaper tier now does a role well, move the role down.
4. The agents' `model:` fields in `plugins/starter/agents/` still name aliases
   that exist.
5. Update the review date even if nothing changed, so the next reader knows the
   table was checked.

## Other providers

`PORTING.md` maps these roles onto other model families. Fill in the same table
with that family's models, and keep the review date.
