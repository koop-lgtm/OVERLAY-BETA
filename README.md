# Custom Thermal HUD Overlay

A transparent, click-through Windows overlay that draws your own reticle/HUD
skin on top of the game, while mirroring live values (ammo type, distance,
ready status) read from the game's actual on-screen HUD via OCR.

## What it does

- **Hold `Shift`** (your ADS key) → overlay fades in.
- **Release `Shift`** → overlay disappears.
- **Press `N`** → toggles the thermal system; dot 1 flips **red → green**.
- **Press `Y`** → toggles the thermal color filter layer; dot 2 flips **red → green**.
- **Press `T`** → cycles the thermal background color (WHITE → GREEN → RED → BLUE).
- If the game's death message is detected on screen, the overlay
  force-hides itself, even if you're still holding Shift, until you press
  Shift again.
- Ammo type, distance, and ready text are re-read from the game's HUD and
  displayed in your overlay's own font/style/positions.
- The window is fully click-through and never steals focus — your mouse and
  keyboard input go straight to the game.

## 1. Install (one-click)

1. **Install Python 3.10+** if you don't have it — https://www.python.org/downloads/
   On the first install screen, check **"Add python.exe to PATH"**, then
   click Install. (If Python's already installed, skip this.)
2. **Double-click `install.bat`.** It will:
   - check Python is set up correctly
   - install all the Python packages the overlay needs
   - check for Tesseract-OCR and, if it's missing, open the download page
     for you and tell you what to click
3. If it stops partway asking you to install Tesseract, install it with
   the default options, then double-click `install.bat` again to confirm.

That's it for setup — no typing commands into Command Prompt required.

<details>
<summary>Manual install (if you'd rather not use the .bat files)</summary>

```
pip install -r requirements.txt
```

Tesseract-OCR itself is a separate program (not just a pip package) —
install it from https://github.com/UB-Mannheim/tesseract/wiki with default
options. The overlay auto-detects it from the standard install location or
your PATH, so you shouldn't need to edit `config.json`'s `tesseract_cmd`
unless you installed it somewhere nonstandard.
</details>

## 2. Calibrate your regions

The OCR needs to know exactly which pixels on your screen contain the ammo
type, distance number, ready text, and the death-message area. This is
different for everyone depending on resolution and whether you play
windowed/fullscreen.

1. Get the game visible on screen with the HUD elements showing.
2. Double-click `calibrate.bat` (or run `python calibrate.py` yourself).

3. Click-and-drag a rectangle around one HUD element (e.g. the `APFSDS
   DM23A1` ammo text). When you release the mouse, the console prints a
   region like:

   ```
   [858, 1088, 130, 30]
   ```

4. Copy that into the matching field in `config.json`
   (`ammo_region`, `distance_region`, `ready_region`, `death_region`).
5. Re-run `calibrate.py` for each of the four regions (it re-screenshots
   each time you run it).

If OCR text comes back messy, tighten the box to just the text with a little
padding — tight, high-contrast crops OCR far better than loose ones.

## 3. Tesseract path (usually automatic)

The overlay auto-detects Tesseract from the standard install locations or
your PATH. You only need to touch `tesseract_cmd` in `config.json` if you
installed it somewhere nonstandard:

```json
"tesseract_cmd": "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
```

## 4. Run the overlay

Double-click `run.bat` (or run `python overlay.py` yourself).

Alt-tab back into the game (borderless windowed works best for overlays —
true exclusive fullscreen can prevent overlays from drawing on top). Hold
Shift to bring up the reticle, press N to flip thermal on.

## Tuning

- `hold_mode: true` in `config.json` makes the overlay show only while Shift
  is held (matches "ADS key" behavior). Set it to `false` to make Shift a
  simple on/off toggle instead.
- `poll_interval_ms` controls how often OCR re-reads the HUD (500ms
  default). Lower = more responsive but more CPU.
- `reticle_scale` (default `0.55`) shrinks or grows the whole reticle —
  raise it (e.g. `0.8`) if it's too small, lower it if it's too big.
- `font_size` (default `11`) controls the size of all HUD text.
- Text bar positions live as fractions of screen width/height at the top of
  `render()` in `overlay.py` (e.g. `X_GUNNER = 0.164`), lifted straight from
  the reference layout, so they hold their relative position at any screen
  resolution — nudge individual fractions if you want to reposition one
  element.
- Colors (`hud_color`, `dot_red`, `dot_green`) can be edited directly in
  `config.json`.

## Custom crosshair image

By default the reticle is drawn as vector lines (`draw_reticle` in
`overlay.py`). To use your own image instead:

1. Drop a PNG next to `overlay.py` — a transparent background works best so
   only your crosshair lines show, not a background square.
2. In `config.json`, set:

   ```json
   "crosshair_image": "my_crosshair.png",
   "crosshair_scale": 1.0
   ```

3. Run the overlay — your image now replaces the vector reticle, centered
   on screen. `crosshair_scale` resizes it (e.g. `0.5` for half size, `2.0`
   for double).

Leave `crosshair_image` as `""` (empty string) to go back to the built-in
drawn reticle. If the file can't be found or fails to load, the overlay
prints a warning to the console and automatically falls back to the drawn
reticle rather than crashing.

## Scope housing (vignette)

The overlay now draws a scope-housing silhouette *behind* the reticle/text —
solid black outside a rounded-rectangle "lens," with the lens area
punched fully transparent so the actual game shows through it. Reticle and
text always draw on top of it.

Controlled in `config.json`:

```json
"vignette_enabled": true,
"scope_width": 2000,
"scope_height": 760,
"scope_corner_radius": 280,
"vignette_color": "#000000"
```

- `scope_width` / `scope_height` are in pixels, centered on screen. Set
  `scope_width` larger than your screen width to intentionally clip the
  left/right edges off-screen (the default `2000` clips slightly on a
  1920-wide screen); shrink it if you don't want clipping.
- `scope_corner_radius` controls how rounded the lens corners are.
- Set `vignette_enabled` to `false` to turn the housing off entirely and
  go back to just the bare reticle/text.
- Defaults assume a 1920x1080 screen. If yours is a different resolution,
  adjust `scope_width`/`scope_height` proportionally (the shape always
  centers itself, and the reticle/text positions are already
  resolution-independent).

**Important:** `transparent_key` changed from `"black"` to `"#ff00ff"`
(magenta). This is purely an internal marker for "make this pixel
see-through" — you never actually see that color — but it can no longer be
black now that black is a real, opaque color used by the vignette. If
you're merging this into an older config.json, make sure `transparent_key`
is updated too, or the vignette will make the whole screen transparent.

## Improving OCR accuracy

Recognition (especially ammo type) went through a rework:

- Screen crops are now upscaled 4x, contrast-enhanced (CLAHE), and
  binarized (black/white threshold) in both normal and inverted polarity
  before OCR — raw color screenshots at native size are the main reason
  small HUD fonts misread.
- Ammo and ready-state text get **fuzzy-corrected** against a list of
  values you actually expect to see, in `config.json`:

  ```json
  "known_ammo_types": ["APFSDS", "HEAT", "DM23A1", ...],
  "known_ready_states": ["READY", "RELOADING", "JAMMED", ...]
  ```

  So a noisy read like `"MEAT"` or `"DEAT"` gets snapped to `"HEAT"` as
  long as it's in that list. **Add every ammo type your vehicle actually
  uses** — anything not in the list won't get corrected (it'll just show
  the raw, possibly wrong, OCR text). `fuzzy_cutoff` (default `0.45`)
  controls how lenient the matching is — raise it toward `0.6-0.7` if it's
  correcting to the wrong value too eagerly, lower it if legit noisy reads
  aren't getting fixed.
- Distance keeps a digit+`M` whitelist and regex extraction rather than
  fuzzy matching, since it's numeric.

If ammo/ready text is still unreliable after this, the crop region itself
is probably too loose — re-run `calibrate.py` and draw a tighter box right
around just that text with a couple pixels of padding.

## Notes

- This only reads pixels already visible on your screen and draws a second
  window on top — it doesn't read or modify the game's memory or process in
  any way.
- Exclusive fullscreen mode in many games renders below other windows —
  use borderless/windowed mode so the overlay can sit on top.
- The `keyboard` library's global hotkey hook needs to run with sufficient
  privileges to see keypresses while another window has focus; if Shift/N
  don't register, try running your terminal as Administrator.
