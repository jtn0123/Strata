from pathlib import Path
import json
import tempfile
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from hardware_telemetry import normalize, summarize, Sampler


class HardwareTelemetryTests(unittest.TestCase):
    def test_unknown_values_are_not_reported_as_zero(self):
        row=normalize({}, 2)
        for key in ('gpu_freq_mhz','gpu_temp_c','cpu_temp_c','thermal_state'):
            self.assertIsNone(row[key])
        for bad in (-1, float('nan'), float('inf'), True, '1500'):
            self.assertIsNone(normalize({'gpu_freq_mhz':bad},2)['gpu_freq_mhz'])
        self.assertIsNone(normalize({'gpu_freq_mhz':0},2)['gpu_freq_mhz'])

    def test_temperature_frequency_and_nominal_state_keep_units(self):
        row=normalize(dict(gpu_freq_mhz=1500,gpu_active_ratio=.8,
                           temp=dict(cpu_temp_avg=50,gpu_temp_avg=55),fans=[dict(rpm=2300)]),2,0)
        self.assertEqual(row['gpu_freq_mhz'],1500)
        self.assertEqual(row['gpu_temp_c'],55)
        self.assertEqual(row['thermal_state'],0)
        self.assertEqual(row['fan_rpm'],[2300])

    def test_idle_clocks_do_not_masquerade_as_active_clock_drop(self):
        rows=[normalize(dict(gpu_freq_mhz=338,gpu_active_ratio=.01),1),
              normalize(dict(gpu_freq_mhz=1500,gpu_active_ratio=.8),2)]
        result=summarize(rows)
        self.assertEqual(result['gpu_freq_mhz']['minimum'],338)
        self.assertEqual(result['active_gpu_freq_mhz']['minimum'],1500)
        self.assertIsNone(result['gpu_temp_c'])

    def test_device_window_overlap_and_missing_coverage_stay_explicit(self):
        sampler=Sampler('/unused')
        sampler.rows=[normalize(dict(gpu_freq_mhz=1500,gpu_active_ratio=.8),2)]
        self.assertEqual(sampler.window(1.5,1.6)['samples'],1)
        self.assertEqual(sampler.window(2.1,2.5)['samples'],0)
        self.assertIsNone(sampler.window(2.1,2.5)['gpu_freq_mhz'])

    def test_constructor_does_not_start_tools_or_read_hardware(self):
        sampler=Sampler('/unused')
        self.assertIsNone(sampler.child)
        self.assertIsNone(sampler.thread)

    def test_fault_counters_require_real_monotonic_coverage(self):
        self.assertIsNone(summarize([])['model_pageins'])
        self.assertIsNone(summarize([dict(model_pageins=10)])['model_pageins'])
        rows=[dict(model_pageins=10,model_pfaults=50),dict(model_pageins=10,model_pfaults=70)]
        self.assertEqual(summarize(rows)['model_pageins']['change'],0)
        self.assertEqual(summarize(rows)['model_pfaults']['change'],20)
        self.assertIsNone(summarize([dict(model_pageins=20),dict(model_pageins=10)])['model_pageins'])

    def test_reader_survives_idle_power_gating_then_collects_active_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            sampler=Sampler(folder)
            sampler.thermal=lambda:0
            sampler.child=Mock(pid=987654,stdout=iter([
                json.dumps(dict(gpu_freq_mhz=0,gpu_active_ratio=0,temp=dict(gpu_temp_avg=40)))+'\n',
                json.dumps(dict(gpu_freq_mhz=1600,gpu_active_ratio=.9,temp=dict(gpu_temp_avg=55)))+'\n']))
            with patch('hardware_telemetry.psutil.process_iter',return_value=[]), \
                    patch('hardware_telemetry.psutil.cpu_percent',return_value=0):
                sampler.run()
            self.assertIsNone(sampler.error)
            self.assertEqual(len(sampler.rows),2)
            self.assertIsNone(sampler.rows[0]['gpu_freq_mhz'])
            self.assertEqual(sampler.rows[1]['gpu_freq_mhz'],1600)


if __name__=='__main__':unittest.main()
