# INC-YYYY-NNN: Short description of what broke

| Field | Value |
|-------|-------|
| Date found | YYYY-MM-DD |
| Severity | SEV1 / SEV2 / SEV3 (see the [index](README.md#severity)) |
| Found by | Alert / Audit / Verification check / User report |
| Duration | From when it started (or "unknown") to when the fix was verified |
| Started | UTC, `YYYY-MM-DD HH:MM`, or just the date, or "unknown (why)" |
| Detected | When an alert fired or a person noticed (UTC, same format) |
| Resolved | When the fix was verified (UTC, same format) |
| Cause | Change (something we changed, including setup) / Platform (hardware, network, a provider) |
| Status | Investigating / Fixed / Fixed and verified |

## Summary

Two or three sentences: what failed, what it put at risk, what fixed it.

## Impact

What was actually affected and what was only at risk. Say plainly if no data was lost.

## Timeline

All times UTC.

| Time | Event |
|------|-------|
| | |

## Root cause

The technical chain from trigger to failure.

## Contributing factors

Conditions that let the root cause go unnoticed or made it worse.

## What went well

## Where we got lucky

## Fix

What changed, with the commit and file.

## Guardrails added

The test, alert or check that would catch this failure next time.

## Lessons
