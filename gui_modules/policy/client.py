"""Use the same transport and observation contract as the RedVLA evaluator."""

from __future__ import annotations


def redvla_api():
    try:
        from redvla.models.factory import create_model
        from redvla.envs.observation import from_libero
        from redvla.protocol import validate_actions
    except ImportError as error:
        raise RuntimeError("Install the lightweight RedVLA package in the GUI environment: python -m pip install -e /path/to/redvla") from error
    return create_model, from_libero, validate_actions


def connect(profile, *, probe=False):
    create_model, _, _ = redvla_api()
    options = dict(profile.model["options"])
    if probe:
        if profile.model["type"] == "remote":
            options["timeout"] = min(float(options.get("timeout", 120)), 3)
        else:
            options["connect_timeout"] = min(float(options.get("connect_timeout", 30)), 3)
    return create_model(profile.model["type"], profile.model["path"], options=options)


def probe(profile):
    policy = connect(profile, probe=True)
    try:
        return policy.metadata
    finally:
        policy.close()


def observation(editor):
    _, from_libero, _ = redvla_api()
    env = editor.env
    env.sim.forward()
    raw = dict(env.env._get_observations(force_update=True))
    for camera in ("agentview", "robot0_eye_in_hand"):
        raw[camera + "_image"] = env.sim.render(256, 256, camera_name=camera)
    return from_libero(raw), raw


def actions(values):
    _, _, validate = redvla_api()
    return validate(values)
