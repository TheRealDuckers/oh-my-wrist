"""
adapters — Provider-specific event ingestion and normalization.

Each adapter converts raw upstream events into :class:`CanonicalEvent`
instances.  Import the adapter that matches your upstream source:

    from ohm.adapters.claude_adapter import adapt_claude_hook
    from ohm.adapters.opencode_adapter import adapt_opencode_event
"""
