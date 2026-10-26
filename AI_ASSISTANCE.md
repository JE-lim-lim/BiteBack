# BiteBack — AI Assistance and Credits

> Before submission, replace the prompts below with accurate details. Do not claim a tool was used unless it was actually used during this project.

## AI tools used

| Tool | How it was used | What the team changed, built, or verified |
|---|---|---|
| [Add each AI tool actually used] | [Describe the real use: coding help, debugging, design feedback, research, or writing] | [Describe your own implementation, edits, decisions, and tests] |

## Human contributions

Describe the parts you personally designed, implemented, integrated, tested, and presented. Be specific about the parts you understand well enough to explain to judges.

## AI in the application

BiteBack has an optional Google Gemini API integration for meal-plan suggestions. If the key is absent, the API fails, or the response fails validation, the app uses local demo suggestions and labels them as demo mode. Local fallback meal suggestions must not be described as live AI output. The photo-based ingredient recognition feature was removed from this version.

## Technologies and external resources

- Python, Flask, SQLite, HTML, CSS and JavaScript.
- Requests and python-dotenv Python packages.
- Google Gemini API, only when configured.
- Three.js via jsDelivr CDN for the landing-page scene.
- Add the actual sources/licences for any third-party images, icons, fonts, and other assets used in the final build.

## Testing performed

Record the actual tests you completed (for example: signup/login, account data separation, add/edit/delete food, used/wasted tracking, Gemini success, missing-key fallback, invalid/over-budget AI response fallback, and mobile/desktop layout). Do not list a test as passed until you have run it.
