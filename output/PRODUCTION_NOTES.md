# GD TABLEWARE INDUSTRY — RS 3000 — "The Art of the Table"

20-second cinematic product commercial, delivered in two separately composed versions.

| Deliverable | Spec |
|---|---|
| `GD_Tableware_RS3000_Desktop_1300x500.mp4` | 1300×500 (2.6:1), 30 fps, 600 frames, 20.0 s, H.264 High / yuv420p, AAC 48 kHz, faststart |
| `GD_Tableware_RS3000_Mobile_1080x1920.mp4` | 1080×1920 (9:16), 30 fps, 600 frames, 20.0 s, H.264 High / yuv420p, AAC 48 kHz, faststart |
| `GD_Tableware_RS3000_Desktop_Poster.jpg` / `..._Mobile_Poster.jpg` | Poster frames (t = 15.2 s, "RS 3000 COLLECTION") |
| `website_embed_example.html` | Responsive, muted-autoplay embed example (not wired into any site) |

## Production pipeline (what was actually done)

No AI video-generation service was available or authorised in this environment, so no paid APIs were used and no model weights were downloaded. The commercial is **honest 2.5D compositing of the supplied photographs**, rendered frame by frame:

1. **Cutouts.** `project/src/prepare_assets.py` separates each real product from its white studio background. It uses OpenCV GrabCut for the dark pieces; for the white pieces it uses a threshold plus hole-fill, and the white dish also gets a clip polygon through its measured corners to drop its floor shadow. Product pixels are never repainted.
2. **Lighting and camera.** `project/src/render.py` places the cutouts on a #080808 studio stage and lights them in 2D. Product photos are only **scaled and translated**. They are never warped, rotated, re-coloured or re-textured, so geometry, square shapes, handles, lid, marble veins and gold lines stay exactly as photographed. The 2D effects are:
   - a directional key-light falloff;
   - a rim light on the edges facing the light;
   - travelling specular light sweeps and a strip-light reflection;
   - mirror-floor reflections;
   - slow push-ins, parallax and staggered reveals.
3. **Typography.** Native text layers (not baked into footage), using two typefaces:
   - Montserrat Light/Medium, tracked wide;
   - Cormorant Garamond Light.

   Both are SIL Open Font License; the licences are in `project/fonts/`. Only the six approved messages appear.
4. **Finish.** Highlight bloom, soft highlight shoulder (protected highlights), vignette, fine luminance grain.
5. **Soundtrack.** `project/src/audio.py` synthesises an **original** score from scratch: no samples, no stock music, no licensing restrictions. It is 120 BPM luxury industrial minimalism with:
   - a sub drone and deep impacts;
   - FM metallic accents;
   - restrained percussion;
   - noise risers.

   The integrated loudness is about −14 LUFS with a −1 dBFS peak ceiling.
6. **Encode.** FFmpeg libx264 `-preset slow -crf 20 -tune film`, yuv420p, `+faststart`.

## Timeline (120 BPM, one beat = 0.5 s; every cut is on a beat)

| Time | Scene | Picture | Text |
|---|---|---|---|
| 0–3 s | 1 Emerging from darkness | Black serving pot: rim light first, a light band travels across, body slowly revealed, push-in | — |
| 3–6 s | 2 Material beauty | Three macro cuts (3 s / 4 s / 5 s) on the real marble and gold veins (large plate, rectangular tray) | CRAFTED TO IMPRESS |
| 6–9 s | 3 The black collection | Black square bowl → **match cut at 7.5 s** to the serving pot; the light sweep carries across the cut | — |
| 9–12 s | 4 Contrast and elegance | White square dish on black → two-tone bowl at 10.5 s with a vertical strip-light reflection | DESIGNED FOR ELEGANCE |
| 12–17 s | 5 Grand collection | Pieces light up one by one on beats 12.0 / 12.5 / 13.0 / 13.5 / 14.0, then a depth-parallax push-in | RS 3000 COLLECTION → THE ART OF THE TABLE |
| 17–20 s | 6 Brand finale | Red brand light line, the official logo card, a red light pass on the musical hit at 18.0 s | GD TABLEWARE INDUSTRY · WHERE ELEGANCE TAKES SHAPE |

Sound accents (impacts at 0 / 6 / 12 / 17 / 18 s, metallic hits on every cut) come from the same `timeline.py` that drives the picture, so sound and picture stay locked.

## Asset manifest

Originals are preserved untouched (read-only) in `project/assets/original/`.

| Ref | Content (identified visually) | Source file |
|---|---|---|
| @image1 | Official GD Tableware Industry logo (59×48 px) | `GD_logo_official_59x48.jpg` (chat upload 1) |
| @image2 | RS 3000 full collection | `WhatsApp Image 2026-10-12 at 4.03.31 PM.jpeg` |
| @image3 | Black square serving pot with lid | `WhatsApp Image 2026-10-12 at 4.03.32 PM.jpeg` |
| @image4 | Black glossy square bowl | `WhatsApp Image 2026-10-12 at 4.03.32 PM (1).jpeg` |
| @image5 | Two-tone bowl (white interior, dark marble exterior) | `WhatsApp Image 2026-10-12 at 4.03.32 PM (2).jpeg` |
| @image6 | White square dish | `WhatsApp Image 2026-10-12 at 4.03.32 PM (3).jpeg` |
| extra | Large square marble/gold plate (identical to chat upload 2) | `WhatsApp Image 2026-10-12 at 4.03.31 PM (2).jpeg` |
| extra | Square marble/gold plate | `WhatsApp Image 2026-10-12 at 4.03.31 PM (1).jpeg` |
| extra | Small square marble/gold plate | `WhatsApp Image 2026-10-12 at 4.03.31 PM (3).jpeg` |
| extra | Rectangular marble/gold tray | `WhatsApp Image 2026-10-12 at 4.03.31 PM (4).jpeg` |

Cutouts are in `project/assets/prepared/`, with crop boxes recorded in `cutouts.json`.

## Honest limitations and decisions

- **Logo resolution.** The only supplied logo is **59×48 px**. It is shown exactly as supplied, upscaled with Lanczos only, because two reconstruction attempts (colour-layer re-thresholding and unmixing) distorted the letterforms. As a result it is slightly soft at display size, especially on mobile.
  - **Recommended:** supply a vector (SVG/AI/EPS) or ≥1000 px PNG logo and re-render with `--logo path/to/logo.png`. Nothing else changes.
- **Logo card.** The logo's wordmark is black, so on a black screen it would vanish. It is therefore presented on a premium #F5F5F5 card with its original colours untouched. No recoloured or "reversed" logo was invented.
- **Grand collection shot.** The supplied full-set photo has floor shadows and white-on-white pieces that cannot be cut out cleanly. The Scene 5 hero was therefore **arranged from the individual product photographs**, following the reference layout: marble plate and tray behind, bowls flanking, pot as hero, plate and dish in front. Exact real-world relative sizes are not known, so the scale relationships are approximations based on the reference photo.
- **Material claims.** None are made. Lighting is styled for glossy surfaces only.
- **Not true 3D.** No 3D or orbital camera moves were faked. Products are never rotated or re-shaped; all motion is push-in, parallax and light.

## Website integration

- **Desktop / mobile switching.** Use `<video autoplay muted loop playsinline>` with the poster. The example in `website_embed_example.html` switches desktop/mobile sources at 768 px and does not start the video under `prefers-reduced-motion: reduce`.
- **Mobile safe area.** All mobile text and the logo sit inside the central 1080×1350 (4:5) band, roughly y = 285–1635. A shorter mobile hero can therefore use `aspect-ratio: 4/5; object-fit: cover; object-position: 50% 45%` without losing branding. Below 4:5 (e.g. a 1:1 hero), a dedicated square render is recommended. It is a layout-only change in `render.py`.
- **Desktop composition.** Text sits ≥ 90 px from the left and right edges. The products and logo stay fully visible at all times.

## Re-rendering

```bash
pip install scipy opencv-python-headless        # numpy + Pillow + ffmpeg also required
cd project
python3 -I src/prepare_assets.py                # cutouts (only if originals change)
python3 -I src/audio.py                         # build/soundtrack.wav
python3 -I src/render.py desktop                # ~8 min on 3 CPU cores
python3 -I src/render.py mobile
python3 -I src/render.py desktop --stills 1.5,15.2   # quick review frames (960 px wide)
python3 -I src/verify.py                        # technical QC
```
