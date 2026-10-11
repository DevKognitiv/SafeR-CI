# Decision records

Product and architecture decisions that other work depends on are written down here, one file per
decision, so a fan-out of implementers never has to guess what was agreed and a reviewer can point
at the line that settled a question.

## How a decision is recorded

- One file per decision: `NNNN-short-slug.md`, numbered in creation order and never renumbered.
  `0001-platform-scope.md` is the first one.
- Every file starts with a header block:

  ```
  Status: Proposed | Accepted | Superseded by NNNN
  Decides: product owner | hub maintainer | app maintainer
  Date: YYYY-MM-DD (date of the last status change)
  ```

- Body sections, in this order: **Context** (what forces the decision, with pointers into the
  code), **Options** (every option seriously considered), **Recommended default** (what the
  implementers will build if nobody objects), **Consequences** (what becomes true in the code,
  the CI and the docs once the decision is taken), **Decision** (the line that is filled in).
- A file with several related topics (such as the platform-scope request) carries one
  `Decision: pending` line per topic. Each line is replaced by the actual decision, the name of
  the person who took it and the date.

## Statuses

| Status | Meaning |
|---|---|
| Proposed | Written by an implementer or an agent as a request; nothing in the code may rely on it yet beyond the recommended default. |
| Accepted | Decided by the person named in `Decides`. Implementers build on it. Changing it needs a new record that supersedes this one. |
| Superseded by NNNN | Kept for history; the newer record is the one in force. |

## Who decides

- **Product owner** (the person who owns the SafeR product): platform scope, what the app
  promises to users (emergency numbers, SOS wording, licensing), brand and typography, which
  phase a piece of work lands in.
- **Hub maintainer**: hub-side contracts (`docs/contracts/*.md`), feature flag defaults,
  database migrations.
- **App maintainer**: app-side contract adoption, Android/iOS platform choices that do not
  change what the product promises.

An automated agent or an implementer may write a `Proposed` record with a recommended default
and may build the default behind a feature flag, but may never change a status to `Accepted`.
Only the person named in `Decides` does that, by editing the file (or by replying in the PR
that adds it, after which the implementer edits the file and quotes the reply).

## Where decisions are referenced

- `docs/safer-app.md` links to the records that affect the app surface.
- The CI jobs that depend on a decision (iOS lane, portrait lock check, tablet golden variant)
  cite the record number in their job name or a comment.
- Release notes list the records accepted since the previous tag.

## Index

| # | Title | Status | Decides |
|---|---|---|---|
| 0001 | [Platform scope and Phase 0 product questions](0001-platform-scope.md) | Proposed | product owner |
