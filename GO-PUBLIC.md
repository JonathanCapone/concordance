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

## The simpler path: rename the account instead of migrating repos

GitHub supports renaming a user account. Repos, issues and stars come along;
git and web URLs for the old name redirect until someone claims it; profile
links, @mentions and gists do not redirect, but nothing public has ever
pointed at `aminalnam/concordance`, so nothing breaks. This removes steps 5
and 9 below: no second account, no repo transfer, no old repo to retire.

The username and the rewrite email must be decided TOGETHER:
`jdcap@users.noreply.github.com` links commits to a profile only if the
username is actually `jdcap`. Pick the final username first (check it is
free), rename, then rewrite history to
`29108860+<finalname>@users.noreply.github.com` -- the ID-based form is
robust against any future rename, because the ID never changes.

Renamed sequence: rename account -> steps 1-4 (rewriting to the new name's
noreply) -> force-push to the SAME repo -> step 6 (watch CI) -> step 7 (flip
public) -> step 8 (URL into the form, now `github.com/<finalname>/concordance`).

One nuance the fresh-repo path avoided: a repo that flips private-to-public
can leave pre-rewrite objects fetchable by SHA until GitHub garbage-collects.
Since the pre-rewrite history was never public, the practical exposure is nil;
if you want zero residue, delete and recreate the repo under the renamed
account instead -- that is the only remnant of the old step 5.

## The sequence

1. **Stop minting wrong-email commits.** In the repo:

   ```bash
   git config user.email jdcap@users.noreply.github.com
   git config user.name "Jonathan Capone"
   ```

2. **Rewrite the history** (local clone, then verify before any push):

   ```bash
   pip install git-filter-repo
   git filter-repo --email-callback "return b'jdcap@users.noreply.github.com' if email == b'29108860+aminalnam@users.noreply.github.com' else email" --force
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

5. **Create the new repo under the right account** (name: `concordance`),
   private for the moment. Push the rewritten history:

   ```bash
   git remote set-url origin git@github.com:<right-account>/concordance.git
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

8. **Put the URL in the application.** The form currently contains no
   repository link anywhere — the review rated this a blocker on an
   application judged partly on "open source". Add it to the Project summary
   (there is ~6 characters of headroom; "github.com/<account>/concordance"
   fits if the summary loses one clause — re-run `scripts/check_form.py`).

9. **Retire the old repo.** Delete `aminalnam/concordance` (or make it a
   private archive). Do not leave a public fork relationship pointing at the
   wrong identity. GitHub retains old commits by SHA on forks and caches —
   which is exactly why the rewrite happens before anything was ever public.

## What this plan deliberately does not do

- It does not touch the droplet. Deploy is a separate decision with its own
  runbook, after the repo is public.
- It does not rename the `ground-truth` directory. Local paths are local.
- It does not rebase or squash anything beyond the email rewrite: the history
  is part of the "check my work" story, including the commits that fix wrong
  claims.
