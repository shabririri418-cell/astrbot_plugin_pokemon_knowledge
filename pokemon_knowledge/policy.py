"""Public adapter policy; no dependency on private companion plugins."""


def permitted(config, origin, proactive=False):
    if not config.get('enabled', True) or proactive:
        return False
    allowed = config.get('allowed_origins', [])
    return not allowed or origin in allowed
