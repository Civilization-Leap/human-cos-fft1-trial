"""Public internal facade for the SBX7 input-driven S6 engineering slice.

This slice freezes Cross Examination, dissent, Actor/World State, Causal Graph and
Critical Integration after the real S5 prefix. It does not claim full S6 or SBX7
acceptance; `s6_terminal_hash` and trial capability acceptance remain unset/open.
"""

from .operator_s6_preflight import OperatorS6SliceError, preflight
from .operator_s6_runtime import _runtime_s6_slice, execute_operator_s6_slice

__all__ = [
    "OperatorS6SliceError",
    "_runtime_s6_slice",
    "execute_operator_s6_slice",
    "preflight",
]
