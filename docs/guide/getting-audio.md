# Getting audio

To hear a circuit you need three files, none of which come with the app: a recording of your guitar, an amp capture and, usually, a cab IR. This page takes you through getting each one and loading it.

## 1. Record a DI clip

A DI clip is your guitar recorded straight into an audio interface, with nothing in between: no pedals, no amp, no amp simulator.

1. Plug the guitar into the interface's instrument input (marked Hi-Z or Inst). That input is what a DI clip is recorded into, and what the app expects.
2. Set the gain so your hardest playing peaks well under the top of the meter (around −6 dBFS). A clip that hits 0 dBFS is distorted before the pedal ever sees it.
3. Record a phrase of up to **10 seconds**: something with single notes and a chord or two, so you hear both how the pedal cleans up and how it saturates.
4. Export it as a **WAV**: 16-bit, 24-bit or 32-bit float, mono or stereo (stereo is mixed to mono), at any sample rate.
5. Note which pickup you used.

In the app, open the Audio pane's **Guitar** drawer and press **Upload…**. Then pick how hard to play it: **Soft**, **Medium** or **Hard** sets the clip's loudest moment to 0.1, 0.3 or 1 V at the guitar.

In the circuit's **IN** part (the Audio pane's Pedal drawer has **Edit the guitar input…**), pick the pickup you recorded with. The render takes that pickup's sound out of the clip before playing it into the circuit, so a fuzz, which loads the pickup heavily, sounds as it would with the guitar plugged in.

## 2. Download an amp capture

An amp capture is a model of a real amplifier made with NAM (Neural Amp Modeler), as a `.nam` file. Many are shared for free at [tone3000.com](https://www.tone3000.com/).

1. On TONE3000, look for NAM captures of an amp you like. A clean or edge-of-breakup capture shows the pedal best; a high-gain one hides most of what the pedal does.
2. Check whether it's an **amp** capture (the amp's output, no speaker) or a **full rig** (the amp through its cabinet and a microphone). Its description usually says.
3. Download the `.nam` file.

In the app, open the **Amp** drawer and press **Upload…**. Most captures are standard WaveNet ones; if a capture uses something the app can't play yet, it says so: try another capture of that amp.

## 3. Download a cab IR

A cab IR (impulse response) is the sound of a speaker cabinet and microphone, as a short WAV. An amp capture with no cabinet sounds harsh and fizzy on its own; the IR makes it sound like a guitar amp in a room.

1. On TONE3000, look for IRs of a guitar cabinet (a 1×12, 2×12 or 4×12).
2. Download the WAV. An IR is a fraction of a second long; anything over 2 seconds is a room or a reverb, and the app refuses it.

In the app, open the **Cab** drawer and press **Upload…**. With a **full-rig** capture, leave Cab at **None**: the cabinet is already in the capture.

## 4. Render

Press **Render**, then switch between **Dry** and **Pedal** as it plays. See [Audio](audio.md) for what the takes, the squash gauge and the spectrum show.

## Your files

Uploads stay in the data folder on this machine and are listed in each drawer, with their sample rates. A file can be removed from a drawer; to use it again, upload it again. Each file can be up to 50 MB.
