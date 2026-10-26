# BiteBack – Improvement Recommendations

These are optional next steps after removing photo-based ingredient recognition.

## Highest priority
1. **Test core journeys end-to-end:** sign up, log in/out, add/edit/delete pantry items, mark ingredients used or wasted, filter/sort pantry items, and generate a meal plan.
2. **Make errors actionable:** show clear inline validation for missing names, invalid quantities, dates, and budget values; preserve user input when a request fails.
3. **Check deployment persistence:** configure a persistent database path on the host and verify records survive redeploys. Never commit a real `.env`, credentials, or a populated local database.
4. **Improve mobile layouts:** check narrow screens for clipped buttons, horizontal overflow, and crowded dashboard cards.

## UI polish
5. **Keep button behaviour consistent:** shared height, radius, font weight, focus ring, hover lift, and pressed state; use colour to distinguish primary from secondary actions.
6. **Add empty and loading states:** explain what to do when the pantry is empty, a meal plan is generating, or a request fails.
7. **Improve accessibility:** use descriptive labels, visible keyboard focus, sufficient contrast, and status messages after successful saves/deletes.
8. **Clarify estimates:** label meal costs and savings as estimates, based on user-entered quantities and values.

## Product improvements
9. **Make “Use First” actionable:** sort by expiry date, highlight overdue/soon items, and allow users to mark an item used in one step.
10. **Strengthen meal plans:** allow users to exclude allergens or ingredients, show a clear shopping list, and avoid implying that expiry dates alone determine food safety.
11. **Add regression tests:** cover authentication, validation, account data isolation, food events, statistics consistency, and meal-plan budget limits.
12. **Document setup and deployment:** keep `.env.example` current and include environment variables, test commands, and run instructions in README.

The image-recognition UI, JavaScript handlers, Flask endpoint, Gemini vision helper, and related tests/styles have been removed. Manual ingredient entry remains available.
