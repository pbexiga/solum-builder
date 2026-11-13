# Troubleshooting

## The page shows only empty frames after an update

The browser mixed new scripts with old ones from its cache. Reload once with **Ctrl+Shift+R** (Cmd+Shift+R on a Mac).

## "Can't simulate yet: …"

Something in the drawing stops the simulation: a net with no DC path to ground (two capacitors in series with nothing else on the net between them), a chip with no power, a DC source on V+, a model that isn't in the library. The banner says which; Problems lists it with the fix. A half-drawn circuit says this until it's wired.

## The curve is greyed out

The Frequency pane greys its curve when a stage is stuck (an op-amp at a supply, a transistor fully on or off): a small-signal curve means nothing then. Fix the bias first; Problems names the stage, and [Bias & headroom](bias-and-headroom.md) can centre it.

## Nothing happens when I change something

Results are from the last run. With **Auto-run** off, press **▶ Run** (Ctrl+Enter); the line *The circuit changed since these results* says when they're out of date. Turning a knob always runs again.

## A part does nothing

A part joined by only one pin is left out of the simulation; Problems names it (*Part not wired in*). Check that each wire ends on the pin's end: a wire that stops beside a pin doesn't connect. Probe the part: its pins table shows which net each pin is on.

## Two nets I didn't mean to join are one

Every label with the same name is one net, and so is everything on V+, V− or ground. *Two names on one net* in Problems means a wire joins two differently named labels. Probe the net to see its name.

## A dropped block or paste lands somewhere else

A block or a paste that would short something (two of its own nets joined through a sheet wire, a supply on a signal net) moves to a clear spot instead of landing where you clicked. Drag it into place afterwards.

## Runs are slow

Some circuits take seconds to settle: a compressor, a charge pump. The Bias & headroom pane waits for each circuit to settle before measuring and shows its progress. Audio renders simulate every sample and take longer; turn off *Charge pump switching* in the Pedal drawer for renders about ten times faster.

## "The simulator got stuck"

Some circuits make ngspice's DC solve run forever, usually a chip or a model wired the wrong way round. The app stops waiting and says so; after that it can't simulate until it's restarted. Undo the last change, then restart the app (`docker compose restart`, or stop and start it).

## An upload is refused

The app says why and what to do:

- **A clip**: it must be a WAV (16-bit, 24-bit or 32-bit float), not silent, and at most 10 s long. Trim it and upload it again.
- **An amp capture**: it must be a `.nam` file. A capture that uses something the app can't play yet says so; try another capture of the same amp.
- **A cab IR**: a WAV under 2 s. A longer one is a room or a reverb.
- Any file over 50 MB is refused.

## "Read-only" in the header

Starters, core blocks and versions marked final can't be changed. File → **Save as…** makes your own copy; a final version can be unlocked in File → **Properties…**.

## A circuit from someone else won't simulate

It may name a model you don't have. Problems says which (*Model not in the library*): add it with Tools → **Add a model…**, or pick another model in the part's form. See [Models](models.md).

## Where are my files?

In the data folder (`data/` in the app's folder, unless `DATA_DIR` names another): circuits, blocks, models and audio uploads. File → **Settings…** shows where it is ([Settings](settings.md)). The cache folder (`CACHE_DIR`) only holds saved results and the search index and can be deleted at any time; the app rebuilds it.
