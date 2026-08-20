# Project Briefing

## Purpose

This file is a persistent briefing for future conversations about this project.

It exists so that:

- an AI assistant does not need to rediscover the whole repository every time;
- project discussions can start from the right terminology and assumptions;
- conceptual discussion is separated from implementation details that may be rewritten later.

If a future conversation is about the product idea, the statistical model, or the Nexus/Cronos pitch, this file should be the first thing to read.

## Short version

This project studies how to help a UFABC student decide which class sections are strategically better to request during enrollment.

The core idea is:

- UFABC already has an official priority rule for who gets a seat;
- the missing piece is that we do not fully observe the profile of every student who requested a given section;
- the statistical model exists only to reconstruct the missing part of the competition;
- after that, the official UFABC rule is applied.

Strategically, this probably makes more sense as a feature inside `Cronos` than as a separate app.

## Current strategic recommendation

The best product framing today is:

- `Cronos` answers: "which schedule combinations fit without conflicts?"
- this project answers: "among the viable sections, which ones are strategically better to request and why?"

So the strongest pitch is not "here is another app".

The strongest pitch is:

"There is a useful enrollment intelligence layer that should probably live inside Cronos."

## Important note about the repository

Conceptually, the most important source is the demo model:

- `Functionality example/DEMO_monte_carlo_core.py`
- `Functionality example/DEMO_monte_carlo.py`

For institutional rules, the most important source is:

- `docs/domain/ufabc-rules.md`

For official student profile extraction:

- `docs/architecture/student-data-import.md`

The current backend should not automatically be treated as the canonical expression of the project idea.

It may be reworked or rewritten.

If the discussion is conceptual, prioritize:

1. this file;
2. the demo model;
3. the UFABC rules document.

Only use backend implementation details if the conversation is explicitly about the current code.

## Canonical terminology

These terms should be used consistently in future discussions.

### `requisicao`

A student's request for a specific section during enrollment.

Use `requisicao`, not `solicitacao`, when discussing the model.

### `turma`

A specific section of a subject, with its own code, seats, schedule, teachers, and offering context.

### `materia` / `disciplina`

The curricular component itself.

One discipline may have multiple sections.

### `aluno-alvo`

The student for whom we want to estimate the chance of getting the section.

### `curso ofertante`

The course that offers the section, such as `BCT`, `BCH`, or `BCC`.

This is **not** the student's own course.

It matters because the official priority rule depends on whether the section belongs to an interdisciplinary entry course or to a specific course.

### `base observada`

The local base of student profiles that the system can observe.

This is **not** the whole UFABC population.

It is only the visible sample available to the system.

### `requisicoes conhecidas`

Requests for the target section whose student profiles are known to the model.

### `requisicoes desconhecidas`

Requests for the target section that are known to exist, but whose student profiles are not known to the model.

### `world_population`

This exists only inside the demo.

It is the hidden synthetic "real world" used to validate whether the inference mechanism behaves reasonably.

It is not a production concept.

## The problem the project is solving

The real question is:

"Given a student and a specific section, how strong is that student's chance of getting a seat?"

If we knew everything, this would not require a statistical model.

We would only need:

- the official UFABC enrollment rule;
- the section's number of seats;
- the full set of requests for that section;
- the relevant profile of every requester.

Then the answer would be deterministic: the student gets in or does not.

The statistical model only exists because part of that competition is hidden from us.

## What the model needs to know

For a given section, the model conceptually needs:

- the target student profile;
- the official UFABC rule that orders requesters;
- the section context;
- the known requesters;
- a way to reconstruct the unknown requesters.

## What comes from official sources

### Student profile

The official source for the student's academic profile is the SIGAA history PDF.

From it, the project extracts:

- RA;
- admission year;
- admission shift;
- campus;
- CA;
- CR;
- CP by linked course;
- completed subjects;
- in-progress subjects;
- linked courses identified by curriculum matching.

This exists because the project should not depend on manually typed academic data.

### Curriculum classification

The project follows official UFABC documents to classify how a discipline counts in a curriculum.

This classification depends on:

- course;
- curriculum version;
- discipline.

It is not global to the discipline.

The main categories are:

- `mandatory`;
- `limited`;
- `free`.

### Enrollment priority rule

The project follows the official UFABC first-phase priority logic documented in `docs/domain/ufabc-rules.md`.

The key idea is:

- for interdisciplinary entry courses, the first criterion is whether the discipline is mandatory in that entry course;
- for specific courses, the first criterion is linked-course priority or the non-linked reserve;
- then turn;
- then CP;
- then CA.

For sections of specific courses, there is also the non-linked `20%` reserve.

Two important negatives:

- campus does not enter the initial ordering rule;
- CR does not enter the initial ordering rule.

### Credit limit

The official credit cap is:

- `ceil(20 + 2 * CA)`

This matters for schedule planning and for any future model that reasons about a student's whole set of requests.

## What the demo model is actually doing

The demo is not a product-ready pipeline.

It is an experiment designed to test a specific question:

"If I know the official rule and I only partially know who the competitors are, can I still estimate the target student's chance reasonably?"

### Step 1. Build a hidden synthetic world

The demo creates a full hidden synthetic population called `world_population`.

This world is not available to the inference algorithm.

It exists only so the demo can later compare:

- what really happened in the hidden world;
- what the inference method estimated.

### Step 2. Sample the observed base

From the hidden world, the demo samples an `observed_population`.

This is the visible base.

It is only a fraction of the full synthetic world.

### Step 3. Generate the true requesters

The demo then creates the real requesters of the target section from the hidden world.

This means that:

- some true requesters are inside the observed base;
- some true requesters are outside the observed base.

This is important because it forces the method to deal with partial visibility.

### Step 4. Reveal only part of the requester profiles

Among the true requesters who are inside the observed base, the demo reveals only a fraction of their profiles.

This is controlled by the `coverage` parameter.

This is an experimental device, not a business rule.

It exists to answer:

"What happens if I can match only 25%, 50%, 75%, or 100% of the in-base requests to known profiles?"

So in the demo:

- being in the observed base is not the same thing as being revealed;
- profile reveal is intentionally partial for sensitivity testing.

### Step 5. Build an inference pool from the observed base

The observed base is then used as a donor pool of plausible profiles.

This donor pool is **not** the whole competition.

It is only the source from which missing requester profiles may be imputed.

### Step 6. Reweight the donor pool according to the target section

This point is critical.

The demo does **not** use the raw observed base uniformly.

It reweights the observed profiles according to section-specific demand assumptions.

The weights depend on factors such as:

- course bucket;
- same shift as the section;
- affiliation with the section's specific course, when there is one;
- eligibility, including the idea that someone who already passed the subject should not compete.

So the inferred distribution is:

- not "the distribution of UFABC students in general";
- not "the distribution of everyone outside the base";
- but "a section-specific proxy distribution of plausible requester profiles, estimated from the observed base".

This is a strong modeling assumption.

### Step 7. Impute the unknown requesters

The demo does **not** infer every student missing from UFABC.

It only imputes the profiles of the unknown requesters of the target section.

So the missing object is:

- not the whole outside-base population;
- only the missing profiles behind known existing requests.

This distinction matters a lot.

### Step 8. Apply the official rule

Once a simulation round has:

- the target student;
- the known requester profiles;
- the imputed requester profiles;

the seat allocation is deterministic.

The rule itself is not probabilistic.

The uncertainty is only in the missing requester profiles.

### Step 9. Repeat many times

Monte Carlo enters here.

Each run changes the imputed unknown requester profiles.

The official seat allocation rule is then applied again.

At the end, the estimated probability is:

- the fraction of runs in which the target student got in.

## The single most important clarification about the demo

The demo does **not** do this:

1. infer all students missing from the observed base;
2. build a full synthetic UFABC population from "observed base + inferred outside world";
3. sample competitors from that whole reconstructed population.

The demo does this instead:

1. keep the known requesters fixed;
2. build a weighted donor pool from the observed base;
3. use that pool to impute the missing profiles of the unknown requesters;
4. allocate seats using the official rule.

So the simulated competition is:

- target student;
- known requesters with real profiles;
- unknown requesters with imputed profiles.

The whole observed base never competes directly.

It only donates plausible profiles.

## What `100% coverage` means in the demo

`100% coverage` does **not** mean:

- every requester is known;
- the answer must become `0%` or `100%`.

It means:

- every requester who is inside the observed base has a revealed profile.

There may still be true requesters outside the observed base.

Those remain unknown and still need imputation.

So even with `100% coverage`, the result can remain probabilistic.

## Why `world_population` exists

`world_population` exists only so the demo has a hidden truth.

It lets the experiment answer:

- how many true requesters were outside the observed base;
- whether the method estimated the competition reasonably;
- what the real deterministic outcome would have been if all profiles were known.

Without `world_population`, the demo would not be a validation experiment.

It would just be a simulation with no hidden ground truth.

## What the inferred distribution really means

This is the most delicate conceptual point.

The demo is making the following approximation:

"The profile mix of unknown requesters for this section can be approximated by a reweighted version of the observed base."

That means:

- it is not claiming that all outside-base UFABC students look like the observed base in general;
- it is claiming that the missing requesters of this section can be approximated by a section-specific reweighted slice of the observed base.

This is the central modeling assumption of the demo.

It is also the most attackable assumption.

That is acceptable in a prototype, but it should be presented honestly.

## What the demo is **not** modeling today

The demo is section-local.

It does **not** model a student's full portfolio of requests across multiple sections and disciplines.

So it does not currently account for cases like:

- the same student requesting the same discipline in another section with a different teacher or time slot;
- the same student already being at the global credit cap and only being able to request something else if another request is removed;
- competition effects created by a student's mutually exclusive schedule choices across many sections.

These should be presented as future work if the conversation goes there.

## How to explain the flow simply to Nexus

Use this version:

"The official UFABC rule already tells us how to rank students if we know who the competitors are. The hard part is that we do not fully know the profile of every student who requested a section. So the prototype keeps the known competitors fixed, reconstructs the missing competitor profiles using the observed base, and then applies the official UFABC rule many times across plausible scenarios. The model is not replacing the rule. It is only filling the missing part of the competition."

## Even shorter explanation

"We know the rule, we know the target student, and we know part of the competition. The statistical model only reconstructs the missing part and then runs the official rule."

## How to present the project honestly

The safest honest framing is:

- this is not a finished production system;
- it is a prototype around a real student problem;
- the main validated asset is the problem framing and the modeling idea;
- the current code should not be oversold as final architecture;
- the concept probably belongs inside `Cronos`.

## Recommended self-positioning in conversations with Nexus

The best posture is not:

- "I built a finished system"

The best posture is:

- "I studied a real student problem"
- "I built a prototype to validate the logic"
- "I think the best product decision is to integrate this into Cronos instead of shipping a separate app"
- "I can contribute in product thinking, frontend, prototyping, and iterative improvement of the logic"

## What an AI should assume by default in future conversations

Unless explicitly told otherwise, assume the following:

1. Conceptual discussion should prioritize the demo and the rules document, not the current backend.
2. The preferred product direction is integration into `Cronos`.
3. Terminology should use `requisicao`, `turma`, `curso ofertante`, `base observada`, `requisicoes conhecidas`, and `requisicoes desconhecidas`.
4. The demo's core assumption is a section-specific inferred distribution built from the observed base.
5. The model currently does not represent full multi-section request portfolios or global cross-request credit interactions.

## Files worth reading first

For concept and pitch:

- `docs/project-briefing.md`
- `docs/domain/ufabc-rules.md`
- `docs/architecture/student-data-import.md`

For the demo model:

- `Functionality example/DEMO_monte_carlo_core.py`
- `Functionality example/DEMO_monte_carlo.py`

For UI and product feel:

- `frontend/src/legacy-app.js`

## Last update

This briefing was written on 2026-08-20 and reflects the current understanding of the project at that time.
