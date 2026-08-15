# Going public without sinking the application

**Status: PLAN. Nothing here has been executed.** Every step below that touches
GitHub is Jonathan's to run or to explicitly hand off. Delete this file once
the sequence is complete — it is an operational checklist, not documentation.

## Why this is order-dependent

Three facts interact badly:

1. The repo lives at `github.com/aminalnam/concordance` and 102 of 138 commits
   carry `29108860+aminalnam@users.noreply.github.com` as author and committer.
   The standing rule is that commits use `jdcap@users.noreply.github.com`, so
   history must be rewritten — and the hosting account itself is the wrong
   public identity for a portfolio project.
2. Rewriting history **changes every SHA**, including `f8fbca2`, the frozen
   checkpoint cited in two submitted form answers, APPLICATION.md, HANDOFF.md
   and the vocabulary artifact. A "check my work" application whose one
   verifiable anchor does not exist in the public repo is worse than no
   anchor.
3. Every other pre-submission fix creates commits, and any commit made before
   the rewrite gets a new SHA too. So the rewrite goes FIRST among the
   GitHub-facing steps, and the SHA references are updated as part of it —
   not before, not after.

## DONE: the account is renamed

The account is now `JonathanCapone` (2026-08-15). All 26 local clones point at
the new name, the repo-local git config uses
`29108860+JonathanCapone@users.noreply.github.com` (the ID-based noreply --
robust against any future rename, and it attributes to the right profile,
which `jdcap@users.noreply.github.com` never did: that address belongs to
whoever holds the username `jdcap`). No GitHub Pages site was live under the
old name; the portfolio serves from the droplet.

Because the repo came along with the rename, there is no second account and
no repo transfer: rewrite -> force-push to the SAME repo -> watch CI -> flip
public -> URL into the form. One nuance: a repo that flips private-to-public
can leave pre-rewrite objects fetchable by SHA until GitHub garbage-collects;
the pre-rewrite history was never public, so practical exposure is nil -- for
zero residue, delete and recreate the repo instead.

## The sequence

1. **Stop minting wrong-email commits.** In the repo:

   DONE (2026-08-15): repo-local config is
   `29108860+JonathanCapone@users.noreply.github.com` / "Jonathan Capone".

2. **Rewrite the history** (local clone, then verify before any push):

   Both old addresses map to the ID-based noreply -- the aminalnam one for
   the obvious reason, and `jdcap@...` because it attributes to whoever holds
   the username `jdcap`, which is not Jonathan:

   ```bash
   pip install git-filter-repo
   git filter-repo --email-callback "return b'29108860+JonathanCapone@users.noreply.github.com' if email in (b'29108860+aminalnam@users.noreply.github.com', b'jdcap@users.noreply.github.com') else email" --force
   ```

   filter-repo removes the origin remote as a safety measure; re-add it:

   ```bash
   git remote add origin https://github.com/JonathanCapone/concordance.git
   ```

   Then verify: `git log --format=%ae%n%ce | sort -u` must print exactly one
   address. Also re-verify no AI trailers survived:
   `git log --format=%B | grep -iE "co-authored|generated with|noreply@anthropic"`
   must print nothing.

3. **Find the rewritten checkpoint.** The commit that was `f8fbca2` keeps its
   tree, message and date; only the SHA changes:

   ```bash
   git log --format="%h %s" | grep -i "checkpoint"
   ```

   Tag it so the reference survives any future history surgery:

   ```bash
   git tag application-checkpoint <new-sha>
   ```

4. **Update every SHA reference** to the new short SHA (and prefer citing the
   tag beside it). Known sites — re-grep before trusting this list:
   - `APPLICATION-FORM.md` (two answers: Project summary, Relevant experience)
   - `APPLICATION.md`
   - `HANDOFF.md` (three places)
   - `README.md` (Status note)
   - `data/vocabulary/vocabulary.json` (`source` field)
   - the `build_vocabulary.py` reproduce command documented in WORKLOG.md

   Commit that (with the corrected git config — it is the first new commit,
   and its email is the proof step 1 worked).

5. **Force-push the rewritten history to the same repo** (it moved with the
   account rename; the remote is already `JonathanCapone/concordance`):

   ```bash
   git push origin main --force
   git push origin --tags
   ```

   The local pre-push hook blocks pushes by design; Jonathan runs the push, or
   explicitly authorizes bypassing the hook for this one operation.

6. **Watch the first CI run.** `.github/workflows/tests.yml` runs the suite on
   Ubuntu and Windows at Python 3.11 and 3.13, and re-scores the accuracy run.
   The suite has only ever run on one Windows machine; if 3.11 or Linux turns
   something up, fix it before flipping public, while nobody is watching.

7. **Flip the new repo public.** Verify while logged out: the repo loads, the
   tag resolves, `git log` shows one email, HANDOFF.md shows no local paths.

8. **The URL is in the application** (done 2026-08-15):
   `github.com/JonathanCapone/concordance` in the Project summary. It resolves
   the moment step 7 flips the repo public — submit after that, not before.

9. **Optionally park the old name.** `aminalnam` is now free for anyone to
   claim; whoever takes it inherits the redirect traffic from any stale links.
   Nothing public ever pointed at it, so this is cheap insurance, not a
   requirement: register it with a placeholder account, or let it go.

## What this plan deliberately does not do

- It does not touch the droplet. Deploy is a separate decision with its own
  runbook, after the repo is public.
- It does not rename the `ground-truth` directory. Local paths are local.
- It does not rebase or squash anything beyond the email rewrite: the history
  is part of the "check my work" story, including the commits that fix wrong
  claims.
