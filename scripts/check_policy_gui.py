"""Policy integration checks used by the isolated Scene Studio validation runner."""

import threading
import time
from unittest.mock import Mock

import numpy as np


def exercise_policy(editor, root, capture):
    from gui_modules.ai_mode import AIController
    from gui_modules.policy.dialog import PolicyDialog
    from gui_modules.policy.profiles import PolicyProfile
    from gui_modules.scene_state import capture_state
    from redvla.serving import make_server

    checks = []
    editor.timer.stop()
    editor.free_mode = True
    observed = []
    model = Mock()
    model.metadata = {"validation_fixture": True}

    def predict(obs, instruction):
        observed.append((obs, instruction))
        time.sleep(.1)
        actions = np.zeros((12, 7), dtype=np.float32)
        actions[:, 0] = .03
        actions[:, -1] = -1
        return actions

    model.predict.side_effect = predict
    server = make_server(model, port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    profile = PolicyProfile("HTTP integration fixture", {"type": "remote", "path": f"http://127.0.0.1:{server.server_port}", "options": {"timeout": 3}}, run={"max_steps": 15, "settle_steps": 0})
    original_controller, original_path = editor.ai_controller, editor.vla_model_path
    try:
        dialog = PolicyDialog(root, profile, editor.policy_service)
        root.update()
        assert dialog.read().key == profile.key
        dialog.operation("check")
        deadline = time.monotonic() + 5
        while editor.policy_service.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(.02)
        assert editor.policy_service.ready, editor.policy_service.status
        capture("policy-connection.png")
        for tab, filename in (("Launch", "policy-launch.png"), ("Run", "policy-run.png"), ("Logs", "policy-logs.png")):
            dialog.notebook.select(dialog.tabs[tab])
            root.update()
            capture(filename)
        dialog.close()
        checks.append("policy tabs and a real HTTP connection check")
        before = capture_state(editor.env.sim)
        before_qpos = editor.env.sim.data.qpos.copy()
        editor.free_mode = False
        editor.ai_controller = AIController(editor, profile)
        editor.studio.select_mode("ai")
        assert editor.ai_mode
        controller = editor.ai_controller
        for _ in range(5):
            editor.update_frame()
            root.update()
        editor.studio.refresh()
        assert str(editor.studio.controls["start"].cget("state")) == "normal"
        assert str(editor.studio.controls["pause"].cget("state")) == "disabled"
        assert str(editor.studio.controls["replay"].cget("state")) == "disabled"
        assert not controller.is_executing and controller.inference_thread is None
        assert controller.rlds_collector is None and not editor.ai_video_frames
        assert not observed
        model.prepare_for_new_episode.assert_not_called()
        model.predict.assert_not_called()
        np.testing.assert_array_equal(editor.env.sim.data.qpos, before_qpos)
        assert editor.env.sim.data.time == before["time"]
        capture("policy-ready.png")
        checks.append("entering AI stays idle: no simulation, model episode, inference, or recording")
        editor.studio.controls["start"].invoke()
        assert controller.is_executing
        editor.studio.refresh()
        assert str(editor.studio.controls["start"].cget("state")) == "disabled"
        assert str(editor.studio.controls["pause"].cget("state")) == "normal"
        assert not editor.start_ai_run()
        deadline = time.monotonic() + 25
        while not controller.execution_done and time.monotonic() < deadline:
            editor.update_frame()
            root.update()
            time.sleep(.01)
        assert controller.execution_done and not controller.error, controller.get_status_text()
        editor.studio.refresh()
        assert str(editor.studio.controls["start"].cget("state")) == "disabled"
        assert str(editor.studio.controls["pause"].cget("state")) == "disabled"
        assert str(editor.studio.controls["replay"].cget("state")) == "normal"
        model.prepare_for_new_episode.assert_called_once()
        assert len(controller.action_history) == 15
        assert len(observed) == 2, len(observed)
        assert observed[0][0].image.shape == (256, 256, 3)
        assert observed[0][0].state.shape == (8,)
        assert not np.array_equal(observed[0][0].state, observed[1][0].state)
        assert observed[0][1] == editor.get_current_instruction()
        assert np.asarray(editor.im.get_array()).std() > 5
        assert np.asarray(editor.im_wrist.get_array()).std() > 5
        assert len(editor.ai_video_frames) == 15
        assert len(controller.rlds_exporter.episode_data) == 1
        episode = controller.rlds_exporter.episode_data[0]
        np.testing.assert_array_equal(episode["states"][0][1:1 + len(before_qpos)], before_qpos)
        capture("policy-execution.png")
        checks.append("real MuJoCo rollout uses fresh 256px observations, current instruction, and complete action chunks")
        checks.append("both cameras stay visible during inference; video and trajectory capture remain available")
        root.after(0, editor.update_frame)
        editor.studio.select_mode("free")
        root.update()
        after = capture_state(editor.env.sim)
        np.testing.assert_array_equal(editor.env.sim.data.qpos, before_qpos)
        assert before["time"] == after["time"]
        for name, values in before["bodies"].items():
            for expected, actual in zip(values, after["bodies"][name]):
                np.testing.assert_array_equal(actual, expected)
        controller.inference_thread.join(3)
        assert not controller.inference_thread.is_alive()
        checks.append("leaving AI preserves robot, objects, fixtures, and time even with a queued frame callback")
        editor.studio.select_mode("ai")
        for _ in range(3):
            editor.update_frame()
            root.update()
        editor.studio.refresh()
        assert str(editor.studio.controls["start"].cget("state")) == "normal"
        assert not controller.is_executing and controller.rlds_collector is None
        model.prepare_for_new_episode.assert_called_once()
        np.testing.assert_array_equal(editor.env.sim.data.qpos, before_qpos)
        assert editor.env.sim.data.time == before["time"]
        checks.append("Start run executes exactly one episode; re-entering AI waits for another explicit start")
    finally:
        if editor.ai_mode:
            editor.exit_ai_mode()
        editor.ai_controller, editor.vla_model_path = original_controller, original_path
        editor.free_mode = True
        server.shutdown()
        server.server_close()
    return checks
