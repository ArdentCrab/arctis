"""Placeholder exceptions referenced by the test suite."""


class SecurityError(Exception):
    pass


class ComplianceError(Exception):
    pass


class SagaError(Exception):
    pass


class GovernancePolicyInjectionError(Exception):
    """Raised when :meth:`~arctis.engine.runtime.Engine.run` would use a pre-set policy without ``policy_db``."""

    pass
