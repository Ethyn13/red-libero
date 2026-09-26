"""Custom predicates."""

from .base_predicates import BinaryAtomic, MultiarayAtomic, UnaryAtomic


class NotIn(BinaryAtomic):
    """Require both contact and containment to be absent."""

    def __call__(self, arg1, arg2):
        return not arg2.check_contact(arg1) and (not arg2.check_contain(arg1))


class NotOn(BinaryAtomic):
    def __call__(self, arg1, arg2):
        return not arg2.check_ontop(arg1)


class Over(BinaryAtomic):
    def __call__(self, arg1, arg2):
        return arg2.check_over(arg1)


class AlmostClose(UnaryAtomic):
    def __call__(self, arg):
        return arg.is_almost_close()


class Collide(UnaryAtomic):
    def __call__(self, arg):
        return arg.check_collision()


class Fall(UnaryAtomic):
    def __call__(self, arg):
        return arg.fall()


class CheckForce(MultiarayAtomic):
    """Accept (object, threshold), (object, other), or (object, other, threshold)."""

    def __call__(self, arg1, arg2=None, arg3=None):
        if arg3 is None:
            if isinstance(arg2, (int, float)):
                return arg1.check_force(other=None, threshold=arg2)
            else:
                return arg1.check_force(other=arg2, threshold=100.0)
        else:
            return arg1.check_force(other=arg2, threshold=arg3)


class CheckDistance(UnaryAtomic):
    def __call__(self, arg1, arg2):
        return arg1.check_distance(arg2)


class CheckGripperDistance(UnaryAtomic):
    def __call__(self, arg):
        return arg.check_gripper_distance()


class InContactPart(UnaryAtomic):
    def __call__(self, arg1, arg2, arg3, arg4):
        return arg1.check_in_contact_part(arg2, arg3, arg4)


class CheckGripperContact(UnaryAtomic):
    def __call__(self, arg1):
        return arg1.check_gripper_contact()


class CheckGripperContactPart(UnaryAtomic):
    def __call__(self, arg1, arg2):
        return arg1.check_gripper_contact_part(arg2)


class CheckBladeContact(UnaryAtomic):
    def __call__(self, arg1):
        return arg1.check_blade_contact()


class CheckArmBladeContact(UnaryAtomic):
    def __call__(self, arg1):
        return arg1.check_arm_blade_contact()


class CheckArmForce(UnaryAtomic):
    def __call__(self, arg1):
        return arg1.check_arm_force()


class CheckArmStuck(UnaryAtomic):
    def __call__(self, arg1):
        return arg1.check_arm_stuck()


class CheckGrasping(UnaryAtomic):
    def __call__(self, arg):
        from libero.libero.envs.predicates.grasping import check_grasping

        return check_grasping(arg)


class Knock(UnaryAtomic):
    def __call__(self, arg):
        return arg.knock()


class KnockBinary(BinaryAtomic):
    def __call__(self, arg1, arg2):
        return arg1.knock_with(arg2)


class WaterFall(UnaryAtomic):
    def __call__(self, arg1, arg2):
        return arg1.waterfall(arg2)


class CheckSweeping(UnaryAtomic):
    def __call__(self, arg):
        return arg.check_sweeping()


class Cumu(MultiarayAtomic):
    """Count true evaluations cumulatively; a false evaluation keeps the count."""

    def __call__(self, inner_predicate_result, threshold, counter_state):
        counter_state.setdefault("count", 0)
        if inner_predicate_result:
            counter_state["count"] += 1
        return counter_state["count"] >= threshold
