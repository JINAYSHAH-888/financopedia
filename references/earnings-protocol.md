# Module E — Earnings Reviewer

Produces `earnings-<TICKER>-<Q>.md`. This is the only module that tests the
reader rather than the company. Section 4 is the reason it exists.

Report and analyse only. Do not express a view on what the user should do.

## Inputs this module needs

1. **This quarter's transcript.** Required. If not supplied, fetch it; if it
   cannot be fetched, stop the module and say so — do not review a call from
   the press release.
2. **Last quarter's transcript.** Needed for section 2 to be worth anything.
   Fetch it unprompted. Without it, mark section 2
   `COULD NOT VERIFY — prior-quarter transcript unavailable`; do not
   substitute recollection of prior language.
3. **The user's view**, three sentences, from `notes/<TICKER>.md`. If the
   notes file has no view recorded, section 4 cannot run. Construct the
   strongest three-sentence thesis the prior research supports, label it
   `RECONSTRUCTED THESIS — not the user's stated view`, test that, and
   record in the delivery that a real view should be written down.

## Sections

### 1. WHAT THEY SAID
Facts only. Reported numbers against consensus (cite the consensus source
and its date), guidance changes with the old and new figures side by side,
any restatement or change in reporting basis. No interpretation. If a
number was not given, that is a line too.

### 2. HOW THEY SAID IT
A language comparison against last quarter, not a tone summary. Four
specific questions:
- **What is newly hedged?** A metric described without qualification last
  quarter and with one now ("we expect" → "we currently anticipate").
- **What did they stop mentioning?** A KPI, a segment, a customer, a
  timeline that was prominent and is now absent.
- **What got a longer explanation than it needed?** Length is a tell.
- **What changed from passive to active voice, or the reverse?** Who is
  being given agency for a result.

Quote the transcript directly when characterising management's language —
short, exact, attributed to speaker and section of the call. Keep each quote
under 15 words and do not quote the same source twice; paraphrase the rest.
A claim about tone with no quote behind it is not evidence.

### 3. THE ANALYST QUESTIONS
For each substantive question: who asked, what was asked, and whether
management **answered directly, partially, or deflected**. Classify
explicitly; do not leave it to the reader. Deflections are the map — a
question asked three times by three analysts and answered none of them is
the most informative event on the call. Note repeat questions as a group.

### 4. AGAINST MY VIEW
The core. Take the user's three sentences one at a time. For each:

- **Supports / Undermines / Says nothing** — pick one, no hedging.
- **The specific line** in the transcript that does it, quoted or located
  precisely.
- If the call says nothing about a sentence, that is a real finding, not a
  gap to paper over: a thesis the company never discusses is a thesis you
  cannot track from calls.

Do not soften an undermining finding. Do not manufacture balance by finding
one supporting line for each undermining one.

### 5. WHAT WOULD CHANGE MY MIND
Falsifiable, and tied to the next call. "What would have to appear in next
quarter's call for this view to be wrong?" Each item should be something a
reader could check in twenty minutes with the next transcript open: a
specific metric crossing a specific level, a specific phrase disappearing, a
specific question being deflected again.

Write these as checkable conditions, not themes. Then copy them into
`notes/<TICKER>.md` so next quarter's run starts by testing them.

## After the review

Update `notes/<TICKER>.md`:
- `Last reviewed` → this call's date.
- `What changed since` → append the findings of sections 2 and 4, dated.
- Leave the user's three-sentence view untouched.

Six quarters of this file is worth more than any single report, which is
only true if the file is actually maintained. Never skip the update.
