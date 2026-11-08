# Moderator guide — keep separate from the participant sheet

Before the first session, check the exercise in the built app. Do not count this
technical rehearsal as a usability session. Reset by reloading the app before
each participant; the task page should remain available in a separate tab.

## Neutral introduction

“We're checking whether the tool is understandable. Please try the task on the
sheet and describe what you're thinking. There are no scores for you. If
something is unclear, that is useful feedback.”

Start the timer when the participant opens the blank app with the comparison
sheet available. Note submission and report arrival separately from time spent
understanding the report. A first useful action means correctly identifying a
relevant route or test and giving a plausible reason for inspecting it; clicking
a button alone does not qualify. Stop after ten minutes if they have not finished,
record the unfinished work, then offer assistance for discussion.

If asked where to click, first say “What would you try?” If they remain stuck,
help them and record the exact hint and time. Later answers are assisted. Never
conceal a confusing step by doing it yourself and marking the task complete.

## Answer reference

The only changed function is `pricing.py::shipping_fee`. Its free-shipping
threshold rises from 50 to 75. The source-level path is:

`shipping_fee → routes.py::shipping → tests/test_shipping.py::test_free_shipping`

- Potentially affected route: **GET /api/checkout/shipping**. The route calls the
  helper; literal router and app prefixes produce the full address.
- Suggested file: **tests/test_shipping.py**. Its unchanged test calls
  `shipping(60)` and expects a zero fee. Reading the code predicts a five-dollar
  fee after the change. ImpactLens has not executed that test.
- Evidence: `routes.py:8` calls `shipping_fee(subtotal)`; `tests/test_shipping.py:4`
  calls `shipping(60)`. The interface should let the participant find these lines.
- The health route and its test are unchanged and have no connection to the helper.
- The PowerShell suggestion is `python -m pytest -- './tests/test_shipping.py'`.
  The file is a starting point; the normal suite remains necessary.

Accept equivalent explanations in the participant's own words. Merely repeating
a route name does not demonstrate that the dependency was understood. A caller
link indicates a possible effect, not a runtime failure or complete coverage.

## Follow-up questions

Ask these after the unassisted attempt, so they do not teach the task beforehand:

1. What did you think the connections meant?
2. What would you actually inspect or run next?
3. If no tests had appeared, what would that tell you?
4. Could you use this on another change? What would stop you?
5. Would you try it during your next review? Why or why not?

Record intention as intention. Repeat use is established only when someone later
chooses to use it again on another change. Get their permission before arranging
follow-up or contacting them; this guide does not authorize outreach.

## Decide what to change

Separate observed behavior from your interpretation and proposed fix. Prioritize
an obstacle that causes a wrong conclusion, blocks evidence inspection, or needs
repeated help. Note how many sessions showed it and quote the relevant notes.
One severe misunderstanding can warrant attention; a tiny sample cannot establish
population frequency. If everyone completes the exercise, try a real review
before concluding that all important usability problems are solved.
