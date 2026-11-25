from types import SimpleNamespace
from unittest.mock import Mock

from markettwin_execution_orchestrator.supervisor import supervise, CHILD_ENV


def test_unexpected_exit_restarts_with_backoff_and_marks_child(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    first = SimpleNamespace(pid=1, wait=Mock(return_value=1), poll=Mock(return_value=1))
    second = SimpleNamespace(pid=2, wait=Mock(return_value=0), poll=Mock(return_value=0))
    spawn = Mock(side_effect=[first, second])
    waits = []

    def pause(delay):
        waits.append(delay)
        if len(waits) == 2:
            raise KeyboardInterrupt

    supervise(popen=spawn, sleep=pause, clock=lambda: 0)
    assert waits == [2, 4]
    assert all(call.kwargs["env"][CHILD_ENV] == "1" for call in spawn.call_args_list)
    assert "code=1" in (tmp_path / ".local/execution-supervisor.log").read_text()


def test_operator_stop_terminates_child_without_restart(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    child = SimpleNamespace(pid=1, wait=Mock(side_effect=[KeyboardInterrupt, 0]),
        poll=Mock(return_value=None), terminate=Mock(), kill=Mock())
    spawn = Mock(return_value=child)
    supervise(popen=spawn)
    spawn.assert_called_once()
    child.terminate.assert_called_once()
