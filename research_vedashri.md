# Research, deck and pitch (Vedashree)

Read `contract/README.md` first. Decision points marked **[Qn]** are in `questions.md`.

## 1. Your job in one line

Make sure that every sentence a judge hears or reads is **true, sourced, and memorable**, and that we look more convincing than teams who show demos. You own the deck, the claims register, the pitch, the Q&A, and the real-world evidence.

## 2. What we already have

- The 3-page proposal `TrueClose_Proposal_ChronoForge.pdf` (Round 0, screened in; we are 11th of 40).
- The earlier research dossier and master brief (in the Claude chat history) with prior-art notes.
- Facts in the proposal, with the source we named: Hyderabad about 800 in 1,000 closed without attention (2021 press report, say "reported"); Bengaluru one complaint reopened 15 times; Mumbai 48 days in 2021, same as 2017 (Praja); Pune PMC Care and the June 2026 Standing Committee directive; MGNREGA July 2025 duplicate photos; Bengaluru road maintenance resolved 58% vs electrical 96.4% (86.2% overall, from OpenCity data).

## 3. Task list, in order

### Task 1 (10:00-11:00): Claims register
A single spreadsheet or table, `docs/claims_register.md`, with one row per factual claim in the deck:

| # | Claim | Source name | URL | Date accessed | Exact quote | Confidence (verified / reported / unverified) | Slide |
|---|---|---|---|---|---|---|---|

Rules:
- Open every URL yourself. If you cannot re-find the source, mark it **unverified** and either drop the claim or soften it to "reported".
- Never quote a number we have not computed ourselves as ours. Soham's numbers go in a separate section "Our computed numbers" with a pointer to the notebook or script that produced each one.
- This register is what we show if a judge asks "where is that from?" Printed copy in your bag.

### Task 2 (11:00-13:00): Prior-art table, version 2
Rebuild the "what exists" table so it is checkable. One row per system. Columns: system, who runs it, what the closure check actually is, is the checker independent of the closing officer? (yes/no/unknown), public documentation link, what we do differently. Systems: CPGRAMS (including the feedback call centre and NextGen plans), Swachhata (Janaagraha), BBMP Sahaaya 2.0, GHMC, MCGM Pothole QuickFix, Geo-MGNREGA, Project DIME (Philippines), 311 systems abroad (NYC 311, SeeClickFix), and any academic work. Also search Google Scholar, arXiv and GitHub for "complaint closure verification", "false resolution detection 311", "grievance redressal AI" and note anything close.
Write the **research gap in one sentence a judge can repeat**, for example: "Every existing system asks the closer or the citizen to confirm the fix; none independently verifies the closure with evidence the closer did not supply."
If you find a system that already does this, tell the team immediately. We would sharpen the differentiator (calibrated abstention, budgeted agent, satellite and photo forensics together) and not defend a claim that is wrong.

### Task 3 (11:00-16:00, in parallel): Real field evidence (our edge over demo-only teams)
Teams with a demo have a screen. We can have **real people**. Do this in two hours using WhatsApp:
- A 6-question survey (Google Form), sent to 30-50 people: Have you filed a civic complaint (pothole, garbage, streetlight)? Which app or number? Was it marked resolved? Was it actually fixed? Did anyone ask you to confirm? Would you reply to a WhatsApp "was it fixed?" message?
- 3-4 short interviews (5 minutes each) with a resident association member, a student who has filed complaints, and ideally a ward office clerk or a local journalist. Ask only about their experience. Record names only with permission.
- Report counts exactly ("14 of 37 respondents..."). Say the sample is small and convenience-based. A small honest number beats a big vague one.
- Put 2 real quotes (with consent) on the deck.

### Task 4 (13:00-16:00): Round A deck
Max 8 slides. Round A is 16:00, so the deck is ready at 15:00 for a run-through. Slide plan:
1. Title with the one-line promise: "Closed should mean fixed."
2. The problem, one big number, one real case
3. Why it keeps happening (the incentive: closer supplies the proof, rank rewards closing)
4. What exists and the gap (from Task 2)
5. TrueClose in one picture: ticket, score, cheapest check, evidence, verdict, human approval, re-score
6. What is built already (screenshots of the live skeleton, honestly labelled) and what is next
7. Plan until the final
8. Ask: feedback we want from mentors

### Task 5 (16:00-22:00): Round B deck
Add: real demo screenshots from Ishan, **one real computed number** from Soham, first benchmark results, the citizen survey results, architecture image, and the human-in-the-loop safeguards. 10 slides max.

### Task 6 (22:00-02:00 and 07:00-09:00): Final deck, pitch script and Q&A
- Deck of 12-15 slides, each with speaker notes.
- A **3-minute pitch** and a **7-minute version**, written word for word, timed. Rehearse twice aloud with a timer.
- A one-page **Q&A cheat sheet** (section 6).
- A **90-second backup demo video** recorded by Ishan with your voiceover, saved on two devices.
- README for the GitHub repo: what it is, how to run in one command, what is prior work, what is simulated, known limits.

## 4. Deck design options **[Q17]**

| Option | Look | Pros | Cons |
|---|---|---|---|
| A. Match the proposal (navy, teal, amber) in Canva or PowerPoint (**lean**) | Continuity with the 3-page proposal and the product | Quick, consistent | Risk of looking like every other deck if layouts are generic |
| B. Figma, custom layouts | Strongest custom look, synced with Ishan's design tokens | Best polish | Slow if nobody is fluent |
| C. Reveal.js or Slidev in code | Embed live product, versionable | Cool to a technical jury | Fragile on a venue laptop |

Rules for any option: one idea per slide, a headline that states the conclusion, one visual, big numbers, **no paragraph longer than two lines**, every number has a small source line, same fonts and colours as the product. Avoid stock clipart. Use real screenshots and real maps.

## 5. Pitch narrative (the story spine)

1. **Hook (20 s).** "A Bengaluru resident reopened the same pothole complaint 15 times. The system said resolved every time. Resolved is a status, not a fact."
2. **Why (30 s).** "Cities rank themselves on how many tickets they close, and the person who closes the ticket supplies the proof. That rewards closing, not fixing."
3. **What exists (20 s).** "Call centres, citizen reopen buttons, manual audits. All of them depend on someone's persistence or on the closer's own evidence."
4. **What we built (60 s, with demo).** Score, cheapest check, evidence, verdict, human approval.
5. **Why an agent (20 s).** "Checks cost money and time. The agent decides which check is worth running, and says 'can't tell' when evidence is weak, so a fair officer is never wrongly blamed."
6. **Proof (30 s).** Real number from data, benchmark result, survey result.
7. **Impact and scale (20 s).** Any city with a CSV or API ticket feed; satellite checks extend to large public works (MGNREGA, MPLADS).
8. **Close.** "Closed should mean fixed."

## 6. Judge Q&A cheat sheet (answers to rehearse)

| Likely question | Honest answer |
|---|---|
| Is this already built by someone? | Parts exist: CPGRAMS feedback calls, Swachhata reopen, Geo-MGNREGA geotagging, Project DIME satellite audits. What we found no sign of is an automated, calibrated, budgeted verifier that uses evidence the closer didn't supply, across ticket types. We say "we found none" and show our search (Task 2) |
| How do you know the score is right with no ground truth? | We say exactly what it is: a proxy label (repeat complaint within 14 days of closure), validated on a time split, plus a separate injected-failure benchmark for the verifiers. We publish both, with confidence intervals |
| Satellites can't see potholes. | Correct. The agent knows which categories are checkable (large dump sites, wide road resurfacing, construction) and skips the rest at zero cost. Showing the skip is the point |
| What about privacy? | Hashed IDs, no raw phone numbers, messages only to the original complainant, opt-out in every message, no officer names in public views |
| Could this unfairly blame officers? | No auto-penalty path exists in the code. Every action goes through human approval and the agent can say "can't tell". The tool also protects honest officers by clearing true closures |
| Why would a municipality adopt it? | It improves their own honest metrics and lowers repeat complaints, and it plugs in through a CSV or API. We don't need to replace their system |
| Is the municipal system real? | State it precisely: real open data (BBMP grievances) plus a simulated municipal endpoint that mimics reopen and escalate. We have no partnership and say so |
| WhatsApp, really? | Show the live round trip. If it fails, show Telegram and the recorded WhatsApp run |
| What did you reuse? | GEOAI-04 (deployed satellite change engine, our earlier Fusion entry) and the Catalyst AI engines. Everything else was written in these 24 hours; the Git history shows it |
| What's the business or sustainability model? | Pilot with one ward office or a civic group; subscription for municipal IT cells; open dataset of honest resolution for civic groups |
| What if citizens don't reply? | Silence is treated as weak evidence, never as satisfaction. The agent falls back to photo, satellite or a human spot check |
| How do you scale to 10 million tickets? | The scorer is a batch job on DuckDB/Parquet; only the doubtful top few percent trigger checks; each check is a cached lookup |

## 7. Evidence you must not fake

- The "~80%" Hyderabad figure comes from a 2021 press report quoting officials; say "reported".
- The Bengaluru figures come from OpenCity data; Soham recomputes at least one from the raw file and we cite **our** computation.
- Our benchmark is synthetic. The word "synthetic" appears next to every benchmark number.
- Don't name individual officials or departments as culprits. Talk about systems and incentives.

## 8. Research reading list (use for depth, quote only what you verified)

- CPGRAMS and the Department of Administrative Reforms and Public Grievances: feedback call centre process and NextGen plans.
- Swachhata app and Janaagraha's ward ranking methodology.
- BBMP Sahaaya 2.0 announcements, OpenCity BBMP grievances dataset page.
- Praja Foundation reports on Mumbai complaint resolution.
- Geo-MGNREGA (NRSC/Bhuvan) documentation; Ministry of Rural Development July 2025 NMMS directive.
- Project DIME (Philippines) and AidData's geospatial impact evaluations.
- Academic: "311 service request data", "service request closure" and "equity in complaint response" (NYC 311 studies), "grievance redressal" papers on arXiv and Google Scholar.
- Conformal prediction, abstention and calibration (for one slide on "knowing when we don't know").

## 9. Timeline

| Time | Deliverable |
|---|---|
| 10:00-11:00 | Claims register v1, prior-art search plan |
| 11:00-13:00 | Prior-art table v2, survey live on WhatsApp |
| 13:00-15:00 | Round A deck v1, first run-through at 15:00 |
| 16:00 | **Round A** |
| 16:00-19:00 | Survey results, 3-4 interviews, update claims register |
| 19:00-21:30 | Round B deck |
| 22:00 | **Round B** |
| 22:00-02:00 | Final deck draft, pitch script, Q&A sheet |
| 07:00-09:00 | Rehearse twice, backup video check, printed copies, repo README |
| 09:00-10:00 | Submit and breathe |

## 10. Things to ask the organisers (send at 10:00)

Collected in `questions.md` Q0. You are the point of contact for the organisers, so please ask them: what exactly happens in the 16:00 and 22:00 rounds (demo, deck, or mentor check-in), how long each slot is, whether a working demo is mandatory, whether prior open-source code is allowed with acknowledgement, which internet and power facilities exist, and the exact submission format for the final.
