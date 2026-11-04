# Design rules

The website, the dashboard, the phone app and the sign-in pages share one set of rules. They follow the anti-slop and motion laws of the [Appllama app design skill](https://github.com/Appllama/appllama-skills). Each rule below can be checked mechanically, and a change that breaks one is a bug.

## Colour

- **One accent: pink `#F5B8DB`.** It marks the primary action (the "+", New application), the active place (the selected tab, today's date) and highlights. Black `#151515` is the second action colour.
- **The four pastels are categories, not accents.** Pink, green `#9AAB63`, blue `#B6CAEB` and yellow `#F5D867` colour tiles, shapes and chart series. Text on a pastel is always `#151515`, in both themes.
- **One grey family: warm.** Cream `#FAF3E6`, sand `#EFE7D9` / `#E6DCCB`, line `#DDD2C1`, text `#5C5852`, muted `#6A645A` (4.9:1 on cream). Dark theme: `#12110F`, `#1E1C19`, `#2A2722`, text `#D6CFC3`, muted `#9C958A`.
- **Status colours are the only others:** an error red and a warning amber, used only for errors and warnings.
- **No gradients** except functional fades.

## Shape

- Actions and chips are **pills**.
- Inputs, small controls, tags and swatches use **12 px**.
- Rows and tiles inside a card use **18 px**.
- Cards, panels, sheets and the dock use **28 px**.
- Icon buttons are **circles**.
- Phone frames in illustrations use **46 px**. They're devices, not UI.
- Data marks (bars, ticks) may use 2 to 4 px.

## Type

- Display type is Bricolage Grotesque; text is Figtree. Emphasis uses the weight of the same face, never a second family.
- Numbers use tabular figures.
- One display size per screen.

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

The order of decisions:

1. **The frequency gate.** Things used dozens of times a day (tab switches, scrolling) don't animate. Tabs change instantly.
2. **The purpose.** Every animation names one purpose (feedback, state change, spatial continuity), or it's deleted. Numbers and text people are reading never move for style: no count-ups, no typing effects, no marquees, no parallax, no floating or spinning decoration.
3. **The vocabulary.**
   - Easing is always `cubic-bezier(.23,1,.32,1)`.
   - Entrances take 280 ms, exits 190 ms and presses 120 ms.
   - Entrances start from opacity 0 with a short rise or `scale(.95)`, never `scale(0)`, never blur.
   - Siblings stagger by 40 ms, capped at eight.
4. **Feedback.** Buttons and cards scale to 0.97 on press. List rows get a background highlight, not a scale. There is no hover lift.
5. **Sheets grow from their trigger.** The "Add..." sheet grows from the "+" and its backdrop fades with it, both ways.
6. **Loading.** Content loads behind a skeleton shaped like the final layout and replaces it in place. There's no second entrance on top.
7. **Reduce Motion.** Spatial motion becomes a 150 ms fade.

## Navigation

- An open sheet, the job sheet and an application page each own one history entry. The first back (Android's back button, the browser's back, Escape) closes them instead of leaving the app.
- Tabs are peers: switching tabs replaces the history entry, so back from any tab leaves the app.
- Sign-in, sign-up and email confirmation are one-way doors: they navigate with `location.replace`, and a signed-in visitor who lands on them goes straight to the app.

## States

Every screen has a designed loading state (a skeleton), an empty state that says how to fill it, and inline errors. On Home, the empty state turns the highlight shapes into the three steps that produce the first matches.

## How this was verified

- **Pre-flight counts:** accent hues, corner radii, gradients and infinite animations, per file.
- **Screenshots:** light and dark themes, at 1440 px and on an iPhone 13 viewport.
- **Motion:** the phone flows were screen-recorded and checked frame by frame at 25 fps (load, opening and closing a sheet, switching tabs) for flashes, pops and cuts.
