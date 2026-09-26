from .base_predicates import (
    BinaryAtomic as BinaryAtomic,
    Close as Close,
    Expression as Expression,
    FalsePredicateFn as FalsePredicateFn,
    In as In,
    InContactPredicateFn as InContactPredicateFn,
    MultiarayAtomic as MultiarayAtomic,
    On as On,
    Open as Open,
    PrintJointState as PrintJointState,
    Stack as Stack,
    TruePredicateFn as TruePredicateFn,
    TurnOff as TurnOff,
    TurnOn as TurnOn,
    UnaryAtomic as UnaryAtomic,
    Up as Up,
)
from .custom_predicates import (
    NotIn as NotIn,
    NotOn as NotOn,
    Over as Over,
    AlmostClose as AlmostClose,
    Collide as Collide,
    Fall as Fall,
    CheckForce as CheckForce,
    CheckDistance as CheckDistance,
    CheckGripperDistance as CheckGripperDistance,
    InContactPart as InContactPart,
    CheckGripperContact as CheckGripperContact,
    CheckGripperContactPart as CheckGripperContactPart,
    CheckBladeContact as CheckBladeContact,
    CheckArmBladeContact as CheckArmBladeContact,
    CheckArmForce as CheckArmForce,
    CheckArmStuck as CheckArmStuck,
    CheckGrasping as CheckGrasping,
    Knock as Knock,
    KnockBinary as KnockBinary,
    WaterFall as WaterFall,
    CheckSweeping as CheckSweeping,
    Cumu as Cumu,
)

VALIDATE_PREDICATE_FN_DICT = {
    "true": TruePredicateFn(),
    "false": FalsePredicateFn(),
    "in": In(),
    "notin": NotIn(),
    "incontact": InContactPredicateFn(),
    "on": On(),
    "noton": NotOn(),
    "over": Over(),
    "up": Up(),
    "printjointstate": PrintJointState(),
    "open": Open(),
    "close": Close(),
    "almostclose": AlmostClose(),
    "turnon": TurnOn(),
    "turnoff": TurnOff(),
    "collide": Collide(),
    "fall": Fall(),
    "checkforce": CheckForce(),
    "checkdistance": CheckDistance(),
    "incontactpart": InContactPart(),
    "checkgrippercontact": CheckGripperContact(),
    "checkgrippercontactpart": CheckGripperContactPart(),
    "checkbladecontact": CheckBladeContact(),
    "checkarmbladecontact": CheckArmBladeContact(),
    "checkarmforce": CheckArmForce(),
    "checkarmstuck": CheckArmStuck(),
    "checkgripperdistance": CheckGripperDistance(),
    "checkgrasping": CheckGrasping(),
    "knock": Knock(),
    "knockbinary": KnockBinary(),
    "waterfall": WaterFall(),
    "cumu": Cumu(),
    "checksweeping": CheckSweeping(),
}
TEMPORAL_PREDICATE_FN_LIST = [
    "incontact",
    "on",
    "up",
    "stack",
    "checkforce",
    "incontactpart",
    "checkdistance",
    "checkgrippercontact",
    "checkgrippercontactpart",
    "checkbladecontact",
    "checkarmbladecontact",
    "checkarmforce",
    "checkarmstuck",
    "checkgripperdistance",
    "checkgrasping",
    "knock",
    "knockbinary",
]


def update_predicate_fn_dict(fn_key, fn_name):
    VALIDATE_PREDICATE_FN_DICT.update({fn_key: eval(fn_name)()})


def eval_predicate_fn(predicate_fn_name, *args):
    assert predicate_fn_name in VALIDATE_PREDICATE_FN_DICT
    return VALIDATE_PREDICATE_FN_DICT[predicate_fn_name](*args)


def get_predicate_fn_dict():
    return VALIDATE_PREDICATE_FN_DICT


def get_predicate_fn(predicate_fn_name):
    return VALIDATE_PREDICATE_FN_DICT[predicate_fn_name.lower()]


def check_temporal_predicate(predicate_fn_name):
    return predicate_fn_name.lower() in TEMPORAL_PREDICATE_FN_LIST
