# Propelo illustrations: prompts and requirements

The website has four illustration slots. Each one stays invisible until its file exists in `website/assets/art/`, so nothing half-finished ever shows. Generate the images with the prompts below, save them under the exact file names, and push: the site picks them up on the next build.

The style follows the unslop references (one bright moment per screen, quiet chrome around it, a visual you can explain in one sentence). The subjects are Propelo's own: paper, notices and a kite, because Propelo is about lifting a job search off the notice board.

## The idea in one sentence

**A single paper kite, folded from a printed job notice, rising on a taut string into a calm morning sky.**

Why it fits: paper and print are the product's world (job postings, resumes, notices), a kite rises only while someone holds the string (you stay in control and press Submit), and kites are part of Indian skies.

## Requirements

### Files and sizes

| Slot | File name | Size (px) | Background | Where it shows |
|---|---|---|---|---|
| Hero scene, light | `hero-scene.webp` | 2880 × 1620 | Full scene | Behind the hero on the home page |
| Hero scene, dark | `hero-scene-dark.webp` | 2880 × 1620 | Full scene | Same, when the visitor uses dark mode |
| Stamp object | `stamp.webp` | 480 × 480 | Transparent | Overlapping the corner of the role card in the hero |
| Footer scene, light | `footer-scene.webp` | 2880 × 1100 | Full scene | A band above the footer |
| Footer scene, dark | `footer-scene-dark.webp` | 2880 × 1100 | Full scene | Same, in dark mode |

All sizes are twice the display size, so they stay sharp on phones and retina screens.

### Format

- WebP, quality 80 to 85. Scenes under 450 KB each, the stamp under 120 KB.
- The stamp needs a transparent background: generate it on a plain background, then remove the background (the generator's own tool, Photoshop, or any background remover). Check the edges of the dark wood after removal; background removal can eat dark areas.
- No text, letters, numbers or logos inside any image. Words on the page are real text in the HTML.

### Palette (name these colours in the prompts)

| Role | Light | Dark |
|---|---|---|
| Page background (edges of every scene blend into it) | `#F7F4EE` warm paper | `#161513` warm charcoal |
| Ink (strings, outlines, shadows) | `#1F1B16` | `#EFE9DE` |
| Accent, used once per image | `#F5B8DB` blush pink | `#F5B8DB` |
| Supporting tints, small amounts only | `#B6CAEB` powder blue, `#9AAB63` sage, `#F5D867` soft yellow | same |

### Consistency rules

- One style for all five images: **soft stylized 3D with matte paper materials.**
- The same light everywhere: soft morning sun from the upper left (dusk light from the lower left in the dark versions).
- One subject per image. No collage, no busy background.
- Leave calm, empty space where the page puts text: the left half of the hero, the top 40% of the footer.
- Never: glossy blobs, crystals, orbs, neon, purple or blue-to-purple gradients, robots, rockets, glowing brains, film grain or paper grain (grain makes generators bake in a checker pattern; add texture in code if wanted).

### Tools

Any image generator that exports at least 2880 px wide and follows colour instructions works, for example Midjourney, OpenAI image generation, Google Imagen, Flux or Recraft. Use the same tool and settings for all five images so they match. Generate once, judge the result against the one sentence and the palette, and change the prompt rather than rerolling the same one.

## Prompts

Each prompt follows the same order: subject, setting, light and palette, style, composition, exclusions, format.

### 1. Hero scene, light (`hero-scene.webp`)

```
A single paper kite folded from a cream printed sheet, with a thin blush-pink tail, rising on a taut dark string into a calm morning sky; the paper has soft visible folds that catch the light.
Setting: open sky with a few crisp, soft clouds; low sage-green hills just visible along the very bottom edge.
Light and palette: soft morning sunlight from the upper left; warm off-white sky that fades to exactly #F7F4EE at all four edges; blush pink #F5B8DB only on the kite tail; powder blue #B6CAEB in the cloud shadows; the string in ink #1F1B16.
Style: soft stylized 3D render, matte paper and cloud materials, gentle ambient occlusion, very shallow depth of field, calm and friendly, premium product illustration.
Composition: the kite in the right third, a little above the middle; the string runs down to the bottom-right corner; the whole left half and the bottom fifth are calm empty sky.
Exclusions: no text, no letters, no numbers, no logos, no people, no UI, no watermark, no glossy surfaces, no neon, no purple.
Format: 16:9, 2880 x 1620.
```

### 2. Hero scene, dark (`hero-scene-dark.webp`)

```
The same paper kite with the thin blush-pink tail, rising on a taut string, now at dusk.
Setting: a deep, quiet evening sky with a few faint stars; low dark hills along the very bottom edge.
Light and palette: warm low light from the lower left, as if from a distant streetlamp, catching the kite's folds; the sky is warm charcoal and fades to exactly #161513 at all four edges; blush pink #F5B8DB only on the tail; the string in warm off-white #EFE9DE.
Style: soft stylized 3D render, matte materials, gentle ambient occlusion, calm.
Composition: identical to the light version: kite in the right third, string to the bottom-right corner, left half and bottom fifth empty.
Exclusions: no text, no letters, no numbers, no logos, no people, no UI, no watermark, no glow effects, no neon, no purple.
Format: 16:9, 2880 x 1620.
```

### 3. Stamp object (`stamp.webp`)

```
A single rubber stamp with a polished brass collar and a rounded walnut handle, standing upright, its rubber face freshly inked in blush pink #F5B8DB and just visible at the bottom.
Setting: nothing else in frame.
Light and palette: studio light from the upper left; plain background in exactly #F7F4EE; a soft, small contact shadow under the stamp.
Style: soft stylized 3D render, matte walnut and brushed brass, realistic weight, friendly and simple.
Composition: the stamp centred, tilted 15 degrees to the right, seen slightly from above, filling about 70% of the frame.
Exclusions: no text or letters on the stamp face or anywhere, no logos, no hands, no paper, no watermark.
Format: 1:1, 960 x 960, then remove the background and export at 480 x 480.
```

### 4. Footer scene, light (`footer-scene.webp`)

```
Soft rolling sage-green hills at golden hour with three small paper kites at different heights in the sky, far apart, their strings disappearing behind the hills.
Setting: the hills fill the lower 45% of the frame; one kite has a blush-pink tail, the other two are plain cream paper.
Light and palette: warm golden-hour light from the left; the sky fades to exactly #F7F4EE at the top and both side edges; hills in sage #9AAB63 with soft yellow #F5D867 highlights; blush pink #F5B8DB on one tail only.
Style: soft stylized 3D render, matte grass and paper, gentle depth, calm and open.
Composition: the top 40% is calm empty sky; kites spread across the middle band; nothing important in the outer 10% on each side.
Exclusions: no text, no letters, no logos, no people, no buildings, no UI, no watermark, no crystals or glossy shapes, no purple.
Format: wide, 2880 x 1100.
```

### 5. Footer scene, dark (`footer-scene-dark.webp`)

```
The same rolling hills and three paper kites, after sunset.
Light and palette: the last warm light on the horizon at the left; the sky fades to exactly #161513 at the top and both side edges; hills in deep muted sage; blush pink #F5B8DB on one kite tail only; a few faint stars.
Style, composition and exclusions: the same as the light version.
Format: wide, 2880 x 1100.
```

## Optional: the "drawn in characters" treatment

The unslop hero reference draws its main object as a grid of characters. Propelo can do the same with its own material, letters from the word "hired" or the characters `. · : | +`, rendered in code from the hero kite image. If you want that look, generate one more image:

```
The same paper kite with the pink tail, alone on a perfectly flat black background, high contrast, sharp edges, lit from the upper left, centred, filling 60% of the frame. No string, no clouds, no text.
Format: 1:1, 1600 x 1600, saved as hero-kite-mask.webp.
```

The glyph rendering then happens in the page, so the letters stay sharp and can shift slowly. It needs a small addition to the site's code.

## After you add the files

1. Put them in `website/assets/art/` with the exact names above.
2. Open the site locally or push to main; the pages workflow publishes them.
3. Check the hero on a phone: the headline must stay readable over the sky. If it isn't, move the kite further right in the prompt rather than darkening the image.

---

The visual guidance here adapts unslop by Damir Sokolovsky ([@heydamir](https://x.com/heydamir)), CC BY 4.0.
