# Updating the guide

The users' guide is `docs/guide/`, in Markdown. The app shows it in Help → Documentation (`solum/manual.py` renders it, D-290), and GitHub shows the same files. It describes the app as it is. After a major UI change (a menu, pane, dialog or workflow added, renamed or reworked), the agent asks the person whether to update the guide now or leave it for a full docs pass; a change left for later is noted in `notes/PHASES.md` (local, git-ignored) with the pages and screenshots it affects (D-298). A full pass reads every page against the app, makes all the pictures again and goes through those notes.

## Pages

- `docs/guide/README.md` is the first page and the index. The app lists the pages in the order this page links them, so a new page needs a line here.
- Write from the app, not from memory: open it, check what the menu or pane actually says, and use those words in **bold**.
- `whats-included.md` lists every starter and core block. A new one needs a row, under the name the app shows.
- `formulas.md` is also Help → Formulas.

## Links between pages

Link to a page as `[text](page.md)`, or to a heading as `[text](page.md#anchor)`. Link only to headings with no punctuation: the app turns a run of punctuation into one hyphen, GitHub doesn't, so the same link would miss in one of them.

## Pictures

Pictures are `docs/guide/img/<name>.png`, made by `scripts/guide_shots.py`, which drives the real app in a browser, one function per picture:

    make run CMD="python scripts/guide_shots.py"          # all of them
    make run CMD="python scripts/guide_shots.py sweep"    # only the ones named

After a screen changes, make its picture again and look at it before committing. The top README's pictures are made the same way: `readme-logo.png` (the logo as a PNG, since GitHub's app shows no SVG in a README), `readme.png` (the `readme` function) and `readme-frequency.png`, `readme-bias-headroom.png` and `readme-audio.png`, the large views alone, made with the guide's `frequency-large`, `bias-headroom` and `audio-large`. A new picture is a new function in the script, added to its `SHOTS` list.

## Checks

`make test` runs `tests/unit/test_manual.py`, which fails when:

- a link names a page or heading that doesn't exist;
- a page names a picture that isn't in `img/`;
- a starter or core block has no row in `whats-included.md`.

The server reads the guide when it starts, so restart it to see an edit in the app. The image copies `docs/guide/` in (the Dockerfile).
