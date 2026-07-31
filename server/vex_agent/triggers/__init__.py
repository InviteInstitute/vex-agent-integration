"""Trigger engine, vendored from lm-dashboard (Approach A of the proactive-triggers
design spec). Pure: no DB, no framework. Turns a student's run stream into an
edit-distance sequence and detects the five behavioral triggers on it."""
