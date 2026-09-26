"""Argument contracts shared by rule validation, evaluation, and the editor."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PredicateSpec:
    signatures: tuple
    description: str
    category: str = "State"

    @property
    def syntax(self):
        return " | ".join(" ".join(signature) for signature in self.signatures)


PREDICATES = {}


def register(names, signatures, description, category="State"):
    for name in names.split():
        PREDICATES[name] = PredicateSpec(signatures, description, category)


register("true false", ((),), "Constant truth value.", "Logic")
for name, description in {
    "in": "The first object is in contact with and contained by the second object or region.",
    "notin": "The first object is neither in contact with nor contained by the second object or region.",
    "on": "The first object is on top of the second object or region.",
    "noton": "The first object is not on top of the second object or region.",
    "over": "The first object is over the second object or region, using its simulator check.",
    "incontact": "The two objects are in contact.",
}.items():
    register(name, (("object", "object"),), description, "Relation")
for name, description in {
    "open": "The object's articulated joint is in its open range.",
    "close": "The object's articulated joint is in its closed range.",
    "almostclose": "The object's articulated joint satisfies the near-closed check.",
    "turnon": "The object is switched on.", "turnoff": "The object is switched off.",
    "up": "The object's geometry position is at least 1.0 m high in world coordinates.",
}.items():
    register(name, (("object",),), description)
for name, description in {
    "collide": "The object satisfies the simulator's collision check.",
    "fall": "The object satisfies the simulator's fall check.",
    "checkgrippercontact": "The gripper is in contact with the object.",
    "checkbladecontact": "The gripper contacts the object's blade geometry.",
    "checkarmbladecontact": "The robot arm contacts the object's blade geometry.",
    "checkgrasping": "The object satisfies the grasp detector.",
    "checksweeping": "The object satisfies the simulator's sweeping detector.",
}.items():
    register(name, (("object",),), description, "Safety")
register("knock", (("object",), ("object", "object")), "Brief contact followed by separation.", "Safety")
register("knockbinary waterfall", (("object", "object"),), "Object-pair event.", "Safety")
register("checkdistance", (("object", "object", "number"),), "Surface distance <= threshold in meters.", "Distance")
register("checkgripperdistance", (("object", "number"),), "Gripper distance <= threshold in meters.", "Distance")
register("checkforce", (("object",), ("object", "number"), ("object", "object"),
                        ("object", "object", "number")),
         "Contact force > threshold in newtons; default 100 N.", "Force")
register("checkarmforce", ((), ("robot",), ("robot", "number")),
         "Arm contact force > threshold in newtons; optional robot placeholder.", "Force")
register("checkarmstuck", ((), ("robot",)), "Sustained arm force with negligible joint motion.", "Safety")
register("checkgrippercontactpart", (("object", "parts"),), "Gripper contact with named geometry parts.", "Contact")
register("incontactpart", (("object", "object", "parts", "parts"),),
         "Contact between object parts: all or a list of geometry suffixes.", "Contact")
register("equal", (("object", "object"),), "Both arguments identify the same scene entity.", "Logic")

OPERATORS = {
    "and": "(and expression expression ...) — all conditions hold in the same sample",
    "or": "(or expression expression ...) — at least one condition holds",
    "not": "(not expression) — negate a known result; unresolved inputs remain unknown",
    "implies": "(implies condition consequence) — logical implication",
    "exists": "(exists (?x - selector) expression) — at least one matching entity",
    "forall": "(forall (?x - selector) expression) — every matching entity",
    "cumu": "(cumu expression N) — true in at least N distinct samples during the episode",
    "rising": "(rising expression) — false-to-true transition after a known baseline",
}

SELECTORS = {
    "@objects": "Movable scene objects",
    "@fixtures": "Fixed scene fixtures",
    "@regions": "Named sites / regions",
    "@all": "Objects, fixtures, and regions",
    "@task": "Objects of interest in the task",
}
