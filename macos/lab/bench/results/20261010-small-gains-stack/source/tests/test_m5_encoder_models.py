import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark_m5_encoder_models import validate_startup,adoption


class EncoderModelGates(unittest.TestCase):
    def log(self,count=2,callback=False):
        return '\n'.join(['M5_ENCODER_INIT '+json.dumps(dict(path='device',requested_n_cb=count,effective_n_cb=count,stats=False)),
                          'M5_ENCODER_INIT '+json.dumps(dict(path='device',requested_n_cb=count,effective_n_cb=count,stats=False)),
                          'M5_ENCODER_ABORT '+json.dumps(dict(has_abort_callback=callback,effective_n_cb=count))])

    def test_actual_count_and_callback_required(self):
        self.assertEqual(validate_startup(self.log(),2)['effective_n_cb'],2)
        no_setter='\n'.join(self.log().splitlines()[:2])
        self.assertEqual(validate_startup(no_setter,2)['abort_setters'],0)
        prefixed='\n'.join('0.01.537.560 I '+line for line in self.log().splitlines())
        self.assertEqual(validate_startup(prefixed,2)['effective_n_cb'],2)
        for text in ('',self.log(callback=True),self.log(count=1),self.log().splitlines()[0], 'bad prefix '+self.log()):
            with self.assertRaises(ValueError):validate_startup(text,2)

    def test_reply_drift_can_disqualify_tps_gain(self):
        def row(name,reply_drift):
            return dict(cached=False,workload=name,vs_control={'encoders2':dict(generation_increase_percent=2,total_time_reduction_percent=2)},
                        control_drift=dict(generation_increase_percent=.1,total_time_reduction_percent=reply_drift))
        self.assertFalse(adoption([row('code',3),row('prose',.1)],'encoders2')['measured_speed_candidate'])
        self.assertTrue(adoption([row('code',.1),row('prose',.1)],'encoders2')['measured_speed_candidate'])


if __name__=='__main__':unittest.main()
