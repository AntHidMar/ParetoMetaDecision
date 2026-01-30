# core/decision_language/ast.py

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Tuple, Union

JsonDict = Dict[str, Any]


def _sorted_tuple(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


@dataclass(frozen=True)
class Node:
    def to_dict(self) -> JsonDict:
        raise NotImplementedError

    def canonical_key(self) -> str:
        """
        Stable string key for deduplication.
        AND/OR are treated as commutative by sorting child keys.
        """
        raise NotImplementedError

    def to_sentence(self) -> str:
        """
        Deterministic human-readable representation for hover/logs.
        """
        raise NotImplementedError

    def size(self) -> int:
        raise NotImplementedError

    def depth(self) -> int:
        raise NotImplementedError


@dataclass(frozen=True)
class Atom(Node):
    """
    Leaf node: a human-defined policy with parameters.
    Example: policy=absorption, params={theta:0.02, k:2}
    """
    policy: str
    params: JsonDict

    def to_dict(self) -> JsonDict:
        d = {"policy": self.policy, **self.params}
        return d

    def canonical_key(self) -> str:
        # Sort params keys to make key stable
        items = tuple(sorted((k, self.params[k]) for k in self.params.keys()))
        return f"ATOM({self.policy}|{items})"

    def to_sentence(self) -> str:
        # Stable order of params for deterministic sentence
        items = ", ".join(f"{k}={self.params[k]}" for k in sorted(self.params.keys()))
        return f"{self.policy}({items})"

    def size(self) -> int:
        return 1

    def depth(self) -> int:
        return 1


@dataclass(frozen=True)
class And(Node):
    left: Node
    right: Node

    def to_dict(self) -> JsonDict:
        return {
            "policy": "AND",
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }

    def canonical_key(self) -> str:
        a = self.left.canonical_key()
        b = self.right.canonical_key()
        x, y = _sorted_tuple(a, b)
        return f"AND({x},{y})"

    def to_sentence(self) -> str:
        # Keep parentheses to avoid ambiguity in hover
        return f"({self.left.to_sentence()} AND {self.right.to_sentence()})"

    def size(self) -> int:
        return 1 + self.left.size() + self.right.size()

    def depth(self) -> int:
        return 1 + max(self.left.depth(), self.right.depth())


@dataclass(frozen=True)
class Or(Node):
    left: Node
    right: Node

    def to_dict(self) -> JsonDict:
        return {
            "policy": "OR",
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }

    def canonical_key(self) -> str:
        a = self.left.canonical_key()
        b = self.right.canonical_key()
        x, y = _sorted_tuple(a, b)
        return f"OR({x},{y})"

    def to_sentence(self) -> str:
        return f"({self.left.to_sentence()} OR {self.right.to_sentence()})"
        
    def size(self) -> int:
        return 1 + self.left.size() + self.right.size()

    def depth(self) -> int:
        return 1 + max(self.left.depth(), self.right.depth())


AstNode = Union[Atom, And, Or]

def is_ast_dict(x: Any) -> bool:
    return isinstance(x, dict) and "policy" in x


def parse_node(d: JsonDict) -> AstNode:
    """
    MapA-9: parseo canónico dict -> Node.
    Soporta:
      - Atom: {"policy": "<leaf>", ...params...}  (sin left/right)
      - AND/OR: {"policy":"AND"/"OR", "left":{...}, "right":{...}}
    """
    if not isinstance(d, dict):
        raise TypeError("AST must be a dict")

    policy = d.get("policy")
    if policy in ("AND", "OR"):
        left_d = d.get("left")
        right_d = d.get("right")
        if not isinstance(left_d, dict) or not isinstance(right_d, dict):
            raise ValueError(f"{policy} node requires 'left' and 'right' dicts")
        left = parse_node(left_d)
        right = parse_node(right_d)
        return And(left, right) if policy == "AND" else Or(left, right)

    # Atom: todo lo que no sea AND/OR y no tenga hijos es hoja
    params = {k: v for k, v in d.items() if k not in ("policy", "left", "right")}
    return Atom(policy=str(policy), params=params)


def complexity_of(x: Any) -> int:
    """
    MapA-9: complejidad canónica.
    - Node: usa .size()
    - dict AST: parsea y usa .size()
    - otro: 1 (regla simple legacy)
    """
    if isinstance(x, Node):
        return x.size()
    if is_ast_dict(x):
        return parse_node(x).size()
    return 1
