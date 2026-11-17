"""空闲回收锁的确定性测试，不启动浏览器、不访问生产服务。"""
import ast
from pathlib import Path
import threading
import time


tree = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text())
node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ConcurrencyLock")
namespace = {"threading": threading, "time": time}
exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
ConcurrencyLock = namespace["ConcurrencyLock"]


def main():
    now = [0.0]
    lock = ConcurrencyLock(2, clock=lambda: now[0])
    calls = []
    now[0] = 299
    assert not lock.run_if_idle(300, lambda: calls.append(1))
    now[0] = 300
    assert lock.run_if_idle(300, lambda: calls.append(1))
    assert calls == [1]
    assert not lock.run_if_idle(0, lambda: calls.append(2))

    assert lock.acquire(False)
    now[0] = 1000
    assert not lock.run_if_idle(300, lambda: calls.append(3))
    lock.release()
    now[0] = 1299
    assert not lock.run_if_idle(300, lambda: calls.append(4))
    now[0] = 1300

    entered = threading.Event()
    release = threading.Event()
    errors = []

    def cleanup():
        entered.set()
        assert release.wait(5)

    def worker():
        try:
            assert lock.run_if_idle(300, cleanup)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(5)
    try:
        assert not lock.acquire(False), "清理期间不得启动新任务"
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not errors

    def fail():
        raise RuntimeError("fixture")

    try:
        lock.run_if_idle(300, fail)
        raise AssertionError("应传播清理失败")
    except RuntimeError:
        pass
    # 清理失败也必须归还所有槽位；任务完成后重新计算空闲时间。
    assert lock.acquire(False) and lock.acquire(False)
    assert not lock.acquire(False)
    lock.release()
    lock.release()
    assert not lock.run_if_idle(300, lambda: calls.append(5))
    print("PASS: idle threshold, disabled mode, busy protection, exclusive cleanup, failure recovery")


if __name__ == "__main__":
    main()
