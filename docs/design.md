# Design rules

These rules cover the website, the job board, the dashboard and app, the sign-in, pricing and legal pages, and the extension popup. The pass that set them followed [unslop](https://github.com/heydamir/unslop) by Damir Sokolovsky (CC BY 4.0).

## Direction

- **Product:** a job search workspace for India. It finds fresh roles on companies' own career pages, checks each one against your rules with a quote from the posting, and prepares applications from your real experience. You press Submit.
- **Character:** honest, bright, unhurried.
- **World:** a campus placement notice board, with printed notices, sticky notes and a highlighter.
- **Moments:** the role card with its fit score and quoted checks, and the stage colours. On the website these are the hero card, the five principle notes and the dashboard preview. In the app they are the best-fit card and the four Home tiles.
- **Signature:** a yellow highlighter stroke under the one phrase that matters in a headline. It draws in once, as the headline arrives.

## Colour

| Role | Light | Dark |
|---|---|---|
| Page | `#FAF3E6` (website), `#F7F2E9` (app) | `#141311` |
| Card | `#FFFCF7` | `#1C1A17` |
| Raised, panels | `#F2EADC` | `#26231F` |
| Text: primary, secondary, muted | `#151515`, `#4F4A44`, `#6E675D` | `#F3ECE0`, `#D2CABE`, `#9E978B` |
| Hairlines | ink at 9% | ink at 9% |

- **One accent in the chrome: pink `#FF85BA`.** It marks the selection (the active tab, today's date, the selected list) and the brand dot. Pink used as text on cream is the darker `#B42D6A` (`#FF9CC8` in dark mode) so it passes contrast.
- **The primary button is ink.** Black with cream text in light mode, cream with black text in dark mode.
- **The pastels are notes, not accents:** pink `#FF85BA`, lavender `#BDB6FC`, yellow `#FCF15C`, orange `#FF7034` and gold `#FCC63E`. They only appear inside the moments above, as paper with a 1.5 px ink outline and ink text on top.
- **No hue gradients, glows, coloured shadows or decorative blobs.** Shadows are neutral, soft and only on cards that float over a panel.

## Type

- **Figtree everywhere**, at weights 400, 500 and 600. Headlines are 500 with tight tracking; small text never gets negative tracking.
- **Sentence case** for every label, button and tab. No uppercase tracked labels and no italic emphasis.
- **Figures use tabular numbers** and Indian grouping (32,776; ₹14–18 LPA).
- The logo is the word `propelo` in Figtree 600 with a pink dot. The app icon is a lowercase `p` on a pink tile.

## Shape and spacing

- Everything sits on a 4 px grid. Equal things share one size and one padding.
- Buttons, chips and pills are fully round. Inputs are 12 px, rows 14 to 16 px, cards 20 to 24 px, panels 28 px.
- Sections on the website are 128 px apart (96 on phones). Cards in a row are 16 px apart.

## Labels: one per intent

| Intent | Label |
|---|---|
| Sign up (anywhere on the website or pricing) | Start free |
| Open the dashboard demo | Try the demo |
| The home tab | Home |
| The list of matched roles | Fresh roles |
| Plan, filters, account | Settings |
| Start an application from a posting | New application |
| Approve the day's applications | Review batch |

## Motion

One easing curve, `cubic-bezier(.16,1,.3,1)`, plus `cubic-bezier(.65,0,.35,1)` for the curved reveals. Nothing loops and nothing moves while you read it.

- **Intro (website home):** the wordmark on pink, letter by letter, then the panel lifts away with a curved bottom edge. Once per visit; a click skips it.
- **Headlines:** letters rise into place one after another; the hero headline settles from a slight tilt. The highlighter stroke draws in after the words.
- **Curved reveals:** the hero panel, the dashboard preview, the terminal and the closing card open from the bottom with a rounded edge the first time they scroll into view.
- **Entrances:** other blocks fade and rise 20 px, 70 ms apart. The principle notes arrive one by one; the source bars fill once; the step line under "How it works" follows the scroll.
- **The dot grid** in the hero panel swells and takes colour near the cursor, and only draws while the cursor moves.
- **Feedback:** a press scales to 0.98; a hover is a colour change or a lift of 2 px at most.
- **In the app:** tabs change instantly; Home's best-fit card and tiles fade and rise once; sheets grow from their trigger.
- **Reduce Motion** shows every page at rest, with no intro and no entrances.

## Navigation

- An open sheet, the job sheet and an application page each own one history entry. The first back (Android's back button, the browser's back, Escape) closes them instead of leaving the app.
- Tabs are peers: switching tabs replaces the history entry, so back from any tab leaves the app.
- Sign-in, sign-up and email confirmation are one-way doors: they navigate with `location.replace`, and a signed-in visitor who lands on them goes straight to the app.
- On phones the website's links fold into one menu button.

## States

Every screen has a designed loading state (a skeleton), an empty state that says how to fill it, and inline errors. On Home, the empty state turns into the three steps that produce the first matches.

## Illustrations

There are none in the product for now. When they come back, the prompts and sizes are in [illustrations.md](illustrations.md), and they follow the palette above.

## How this was verified

- **Screenshots:** light and dark themes, at 1440 px and at a 390 px phone width, with no sideways scrolling.
- **Motion:** the home page was recorded scrolling top to bottom and checked frame by frame.
- **Contrast:** ink text on every pastel, and pink text on cream, pass 4.5 to 1.
