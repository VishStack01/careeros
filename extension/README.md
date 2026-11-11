# Propelo Autofill (Chrome extension)

Fills job application forms from your Propelo profile. You review every answer and press Submit yourself.

## Install

1. Get the zip from the latest **extension** workflow run (GitHub Actions tab), or use this folder directly.
2. Open `chrome://extensions`, turn on **Developer mode**, press **Load unpacked** and pick the `extension` folder (unzipped).
3. In Propelo: Settings, Your computer, **Create computer key**. Copy the key (it starts with `cos_k_`).
4. Click the Propelo icon in Chrome, enter your Propelo address and the key, press **Connect**.

## Use

Open an application form and press **Fill this form**.

- Filled fields get a pink outline. Fields that need you get an orange dashed outline and are listed in the popup.
- Your resume PDF is attached to the resume upload when the form has one.
- Campus questions (CGPA or percentage, branch, state, PIN code) are filled from your application details. Active backlogs stay empty unless you chose an answer in Propelo.
- A question that closely matches one of your **Saved answers** (Writing & interviews) gets that answer, and the popup says how many came from them. An answer saved for one company is only used on that company's forms; essays you haven't saved an answer for are listed for you.
- **Track this application** adds the role to your Propelo applications (or updates it if Propelo already found it).

## What it never does

- Press Submit, tick consent boxes, or overwrite something already typed.
- Fill passwords, one-time codes, Aadhaar, PAN, bank details, passport numbers or dates of birth.
- Answer voluntary questions (gender, disability and the like) or fill in someone else's details (a referrer, a reference).
- Run on LinkedIn, Naukri, Indeed or Wellfound. Those sites don't allow automated filling and it can get your account restricted, so the popup only offers to track the role.
- Run in the background. It reads a page only when you press a button in the popup, and only the tab you're on (`activeTab`).

## Permissions

| Permission | Why |
|---|---|
| `activeTab`, `scripting` | Fill the tab you're looking at, when you press the button |
| `storage` | Keep your Propelo address and computer key in this browser |
| Your Propelo address (asked when you connect) | Read your application details and resume, and track roles |
| A form's frame host (asked only if a form is embedded from another site) | Fill forms embedded from Greenhouse, Lever and similar |

The computer key can only read your application details and report applications. Remove it any time in Propelo (Settings, Your computer) or press **Disconnect**.

## Works best on

Built and tested on Greenhouse, Lever and Ashby style forms and plain HTML forms. Other sites vary: whatever it can't match is listed under Needs you. Workday's custom dropdowns are left for you; its text fields are filled.

## Tests

`python -m pytest tests/test_extension.py` runs the fill script against fixture forms in Chromium.
