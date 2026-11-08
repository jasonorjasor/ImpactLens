# First-review usability checkpoint

Status: exercise prepared; participant sessions have not been completed.

Question: can a new reviewer use ImpactLens to identify a possible effect, inspect
its evidence, and choose a test file without being coached through the interface?

## Start the local exercise

Install the project and build the frontend using the root README. From the
repository folder, run:

```powershell
python -m benchmarks.usability --output "C:\Users\jason\Desktop\ImpactLens-Interview-Notes\usability-session-01"
```

Use a new output folder for each launch. Other users can choose any new folder
outside their checkout. The command refuses existing folders. Open
`http://127.0.0.1:8003/exercise` for the participant sheet and comparison details.
Stop the server with Ctrl+C. The generated repository and comparison JSON remain
in the chosen folder for inspection. Nothing is pushed or deployed.

The runner creates two real local Git commits: a free-shipping threshold changes
from $50 to $75; callers and tests stay unchanged. It analyzes those commits on
each submission and serves the existing built interface, with a visible exercise
banner. The GitHub-shaped repository value is only an exercise label. Only the
exact comparison is accepted; there is no network loader, and the report has no
invented GitHub source links. Fixture application code and tests are never run.
This separate loopback-only server is not part of the production web app.

## Run a session

Give a willing participant the task page, not the moderator guide. Allow about
15 minutes. Do not teach the interface first. The participant may stop or decline
at any time. No automatic analytics or recording is installed. Take anonymous
notes outside the repository; ask separately before recording a person.

Use the [moderator guide](MODERATOR.md) and copy the [observation sheet](SESSION_TEMPLATE.md)
into your private notes. Aim for three to five people with relevant Python review
experience; record their experience level. A beginner can help assess wording,
but does not represent every maintainer's review workflow.

Observe the first attempt before offering help. Record time to a first useful
action, wrong turns, exact confusing phrases, and whether answers were independent
or prompted. Do not use completion of an automated check as a participant result.

This small, explained example tests report comprehension. The local label, supplied
commit IDs, short analysis, and missing public source links do not reproduce public
repository discovery, GitHub loading latency, or private-repository workflows.
Test real input friction separately with a willing reviewer's public change or
the public comparison in DEMO.md on the normal app. Do not combine its timing with
this exercise. Record task order because prior practice can affect results.

After the initial sessions, group observed obstacles, choose one with a concrete
effect on the task, and make a scoped fix. Repeat with someone new if possible;
otherwise record that repeat performance includes practice. Report the raw
observations and limitations, not an adoption or accuracy percentage. A PR-link
input is a later candidate if real input friction warrants it.
