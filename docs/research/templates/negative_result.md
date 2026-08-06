# Negative result — <EXP-ID> <title>

> Use this in place of the standard `RESULTS.md` narrative when an experiment
> failed, was abandoned, or returned a null result. **The folder stays.** Set
> `status: failed` or `superseded` in the manifest and fill this in.
>
> A deleted failed experiment is a dead end that gets walked into twice. These
> entries are also what populates the paper's limitations section, and at some
> venues (EXAG explicitly) a well-documented null result is submittable on its own.

## 1. What was attempted

The question, and the shape of the run that was supposed to answer it.

## 2. What happened

Plainly. Crash, null result, or abandonment — say which, and at what point.

## 3. Why

The diagnosis, and how confident it is. Distinguish **"the method does not work"**
from **"our implementation of it did not work"** from **"we ran out of budget"** —
they have completely different implications for the paper, and conflating them is
how a fixable bug becomes a permanently abandoned direction.

## 4. What was ruled out

The useful part. What does the next person now not need to try, and how strongly?
Be precise about scope: a null result at n=3 on one world rules out much less than
it feels like it does.

## 5. What was NOT ruled out

The parameters, scales, and variants this run says nothing about. Guard against the
result being over-read later, including by you.

## 6. Cost

Wall-clock, tokens, money. This is what makes the next go/no-go decision cheap.

## 7. Where this shows up in the paper

Limitations, future work, or a methods footnote. If nowhere, say nowhere.
