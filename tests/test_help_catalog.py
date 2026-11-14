"""web/rw/help.js: every help id is defined once. A second tip()/more() for an id replaces the first one's text, so the
first control shows the wrong help (v0.23.0 did that to "What H3 receives" and the latent preview)."""

import collections
import os
import re

HELP_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "rw", "help.js")


def test_every_help_id_is_defined_once():
    with open(HELP_JS, encoding="utf-8") as f:
        ids = re.findall(r'^(?:more|tip)\("([^"]+)"', f.read(), re.M)
    assert len(ids) > 300
    twice = sorted(k for k, n in collections.Counter(ids).items() if n > 1)
    assert not twice, twice
