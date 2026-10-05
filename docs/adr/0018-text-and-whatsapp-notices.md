# ADR 0018: Text messages and WhatsApp for urgent notices only

**Status:** proposed (decision D12); not yet taken. Item 0.16 waits for it.
**Date:** 5 October 2026.

## Context

Text messages and WhatsApp cost money per message, and WhatsApp needs message templates approved by Meta.
Push notices to the installed app ([ADR 0011](0011-phone-delivery.md)) and email are free.

## Recommended answer

Not in Release 1. Push and email first. Text or WhatsApp only for urgent notices (a cancelled practical,
a quiz about to close), and only if GSA funds the cost per message.

## Consequences if taken

- No messaging provider, contract or phone-number processing in Release 1.
- If GSA funds it later, the provider is chosen with the transfer rules of the Data Protection Act in mind.
