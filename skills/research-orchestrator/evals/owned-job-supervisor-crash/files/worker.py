import pathlib, time
pathlib.Path('worker-started').touch()
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    time.sleep(.05)
