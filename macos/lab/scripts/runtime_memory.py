"""Admission and live guards shared by ordinary Strata app launches."""
from benchmark import Monitor

GIB = 1024**3


def admit_model(model):
    baseline = Monitor.baseline()
    required = (34 if model == 'flash' else 4) * GIB
    level = Monitor.read_pressure_level()
    if baseline['available_bytes'] < required:
        raise RuntimeError(f'Strata needs {required/GIB:.0f} GiB available before loading {model}; '
                           f"currently {baseline['available_bytes']/GIB:.1f} GiB. No model loaded.")
    if level != 1:
        raise RuntimeError('Memory pressure is not normal. No model loaded.')
    return dict(baseline=baseline, minimum_available_before_load_bytes=required,
                minimum_available_while_running_bytes=GIB, swap_guard_bytes=0,
                require_normal_pressure=True, pressure_level_before_load=level)


def app_monitor(child, path, policy):
    return Monitor(child, path, policy['swap_guard_bytes'],
                   policy['minimum_available_while_running_bytes'],
                   baseline=policy['baseline'], require_normal_pressure=True)
