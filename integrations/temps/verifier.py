"""temps.sh integration verifier."""

from __future__ import annotations

from integrations.temps.client import validate_temps_config
from integrations.temps.config import build_temps_config
from integrations.verification import register_validation_verifier

verify_temps = register_validation_verifier(
    "temps",
    build_config=build_temps_config,
    validate_config=validate_temps_config,
)
