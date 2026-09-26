"""Transfer retained simulator state by name when the model structure changes."""


def capture_state(sim):
    model, data = sim.model, sim.data
    joints = {}
    for index in range(model.njnt):
        name = model.joint_id2name(index)
        if name is None:
            continue
        kind = int(model.jnt_type[index])
        nq, nv = {0: (7, 6), 1: (4, 3)}.get(kind, (1, 1))
        q, v = model.jnt_qposadr[index], model.jnt_dofadr[index]
        joints[name] = (
            kind,
            data.qpos[q : q + nq].copy(),
            data.qvel[v : v + nv].copy(),
        )
    bodies = {
        model.body_id2name(index): (
            model.body_pos[index].copy(),
            model.body_quat[index].copy(),
        )
        for index in range(model.nbody)
        if model.body_id2name(index) is not None
    }
    controls = {
        model.actuator_id2name(index): float(data.ctrl[index])
        for index in range(model.nu)
        if model.actuator_id2name(index) is not None
    }
    return {
        "joints": joints,
        "bodies": bodies,
        "controls": controls,
        "time": float(data.time),
    }


def restore_state(sim, state):
    model, data = sim.model, sim.data
    for index in range(model.nbody):
        saved = state["bodies"].get(model.body_id2name(index))
        if saved is not None:
            model.body_pos[index], model.body_quat[index] = saved
    for index in range(model.njnt):
        saved = state["joints"].get(model.joint_id2name(index))
        if saved is None:
            continue
        kind, qpos, qvel = saved
        if int(model.jnt_type[index]) != kind:
            raise ValueError(f"Joint type changed: {model.joint_id2name(index)}")
        q, v = model.jnt_qposadr[index], model.jnt_dofadr[index]
        data.qpos[q : q + len(qpos)] = qpos
        data.qvel[v : v + len(qvel)] = qvel
    for index in range(model.nu):
        name = model.actuator_id2name(index)
        if name in state["controls"]:
            data.ctrl[index] = state["controls"][name]
    data.time = state["time"]
    sim.forward()
