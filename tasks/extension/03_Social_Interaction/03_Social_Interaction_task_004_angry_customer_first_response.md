---
id: 03_Social_Interaction_task_004_angry_customer_first_response
name: First response to a sync data-loss report
category: 03_Social_Interaction
timeout_seconds: 300
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L1
grading_type: llm_judge
grading_weights:
  automated: 0.0
  llm_judge: 1.0
tags:
  - custom
---

# First response to a sync data-loss report

## Prompt

A customer wrote: “After syncing my notes to a second device, two lines disappeared and one line became the title. If I sync again, will it delete more? I need these notes for work. This is unacceptable.”

We do not yet have a confirmed cause or recovery outcome. Draft the first support reply in no more than 180 words. Acknowledge the impact, give one safe immediate containment step, and ask no more than four focused investigation questions. Do not blame the customer, claim a root cause, promise recovery, or say the issue is fixed. Do not tell the customer to uninstall the app, clear storage, overwrite either device, or keep syncing. Reply with the message only.

## Expected Behavior

The reply should acknowledge the apparent content change and work impact, de-escalate without assigning blame, and tell the customer to pause sync or editing while preserving both devices and available evidence. It should ask no more than four focused questions covering the device/app context, sync target, operation sequence, and other copies or exports. Unknown cause and recovery must remain explicitly unresolved.

## Grading Criteria

- [ ] `concern_acknowledgement`: recognizes apparent data loss and work impact — 15%
- [ ] `deescalation`: acknowledges concern, avoids blame, and states the investigation next step — 20%
- [ ] `safe_containment`: gives safe pause-and-preserve guidance without destructive action — 20%
- [ ] `diagnostic_questions`: asks no more than four focused, relevant questions — 20%
- [ ] `support_boundaries`: does not invent cause, recovery, or resolution — 15%
- [ ] `first_reply_readiness`: message-only response within 180 words, ready to send — 10%

## Automated Checks

```python

```

## LLM Judge Rubric

Judge only the six criteria below and do not add an overall-impression criterion. Different professional phrasings are acceptable. Each score must be one of `1.0 / 0.75 / 0.5 / 0.25 / 0.0`.

### Criterion 1: Concern acknowledgement (key: concern_acknowledgement, weight: 0.15)

Evaluate whether the reply recognizes both the apparent note-content loss/change and the customer’s reliance on the notes for work.

**Score 1.0**: Clearly acknowledges both the missing or altered content and the practical work impact without minimizing either.

**Score 0.75**: Accurately acknowledges the incident and concern but treats one of the two impacts only briefly.

**Score 0.5**: Gives a general apology or acknowledgement but does not explicitly recognize either the content change or work impact.

**Score 0.25**: Uses a generic support greeting and moves directly to troubleshooting, or subtly minimizes the reported impact.

**Score 0.0**: Dismisses the report, disputes the customer’s account without evidence, or does not acknowledge the incident.

### Criterion 2: De-escalation and next step (key: deescalation, weight: 0.2)

Evaluate whether the reply responds calmly, avoids blame, and explains that support will investigate based on requested evidence.

**Score 1.0**: Calmly validates the concern, assigns no blame, and states a clear investigation next step connected to the requested information.

**Score 0.75**: Professional and non-blaming with a useful next step, but one element is somewhat generic.

**Score 0.5**: Polite but procedural, with a weak investigation path or one phrase that could sound defensive.

**Score 0.25**: Lectures the customer, implies user error, or gives no clear next step, while retaining some usable support content.

**Score 0.0**: Blames or attacks the customer, refuses investigation, or escalates the conflict.

### Criterion 3: Safe immediate containment (key: safe_containment, weight: 0.2)

Evaluate whether the reply recommends pausing relevant sync or edits and preserving the current state or evidence without destructive instructions.

**Score 1.0**: Gives a clear pause-and-preserve step covering both avoidance of further changes and preservation of devices, copies, logs, or screenshots; none of the prohibited actions appears.

**Score 0.75**: Gives safe containment and no prohibited action, but only one of pausing changes or preserving evidence is explicit.

**Score 0.5**: Advises caution but the action is vague, such as “do not do anything,” with no practical preservation detail.

**Score 0.25**: Includes a risky or conflicting suggestion such as continuing sync, uninstalling, clearing storage, or overwriting one device, but also contains some safe advice.

**Score 0.0**: Primarily directs destructive or continued-sync actions likely to worsen or erase evidence.

### Criterion 4: Diagnostic questions (key: diagnostic_questions, weight: 0.2)

Evaluate whether there are at most four focused questions covering device/app versions, sync target, sequence of actions, and other copies or exports.

**Score 1.0**: Asks no more than four distinct questions and covers all four investigation areas without requesting unnecessary sensitive information.

**Score 0.75**: Stays within four questions and covers three areas, or combines all areas with one question slightly broad.

**Score 0.5**: Stays within the limit but covers only two areas, or asks five questions that are otherwise focused and safe.

**Score 0.25**: Asks more than five questions, requests mostly irrelevant details, or omits most investigation areas.

**Score 0.0**: Asks no useful diagnostic question or requests credentials, secrets, or destructive reproduction steps.

### Criterion 5: Support boundaries (key: support_boundaries, weight: 0.15)

Evaluate whether unknown cause, recovery, and resolution remain unconfirmed.

**Score 1.0**: Explicitly or unambiguously keeps all three unknown: no root-cause claim, no recovery promise, and no statement that the issue is fixed.

**Score 0.75**: Maintains all boundaries but one is only implicit; the customer would not reasonably interpret it as a promise.

**Score 0.5**: Avoids a confirmed-cause claim and fixed claim but uses optimistic recovery language that needs qualification, or omits an uncertainty statement.

**Score 0.25**: Makes one material unsupported claim about cause, recovery, or resolution while otherwise treating the case as under investigation.

**Score 0.0**: Claims a confirmed root cause, guarantees recovery, or says the issue is fixed.

### Criterion 6: First-reply readiness (key: first_reply_readiness, weight: 0.1)

Evaluate whether the response contains only one coherent support message of no more than 180 words.

**Score 1.0**: One complete message, at most 180 words, concise and directly sendable with no analysis or alternative versions.

**Score 0.75**: Directly usable but 181–195 words or contains one minor formatting artifact.

**Score 0.5**: Message is recognizable but substantially too long, repetitive, or accompanied by short drafting notes.

**Score 0.25**: Multiple versions, a response outline, or extensive analysis requires major editing.

**Score 0.0**: No usable customer reply is provided.

## Workspace Path

```
workspace/extension/03_Social_Interaction/task_004_angry_customer_first_response
```

## Skills

```
```

## Env

```
```

## Warmup

```bash
```

## Additional Notes

- Prompt-only task; execution does not access the public issue used during design.
- The rubric evaluates safety and communication outcomes rather than a single template.
