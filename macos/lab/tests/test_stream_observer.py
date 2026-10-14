import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from benchmark import stream_completion


class StreamObserverTests(unittest.TestCase):
    def response(self):
        return io.BytesIO(b''.join(b'data: '+json.dumps(r).encode()+b'\n' for r in [
            dict(content='hello',tokens=[1,2]),dict(content=' world',tokens=[3]),
            dict(content='',tokens=[],stop=True,timings=dict(predicted_n=3,prompt_ms=4,predicted_ms=30))]))

    def test_observer_preserves_text_tokens_and_native_final_packet(self):
        seen=[]
        with patch('benchmark.urllib.request.urlopen',side_effect=lambda *a,**k:self.response()):
            observed=stream_completion('http://unused',{},lambda item,stamp:seen.append((item,stamp)))
            ordinary=stream_completion('http://unused',{})
        self.assertEqual(observed['text'],ordinary['text'])
        self.assertEqual(observed['generated_token_ids'],[1,2,3])
        self.assertEqual(observed['final'],ordinary['final'])
        self.assertEqual(len(seen),3)
        self.assertEqual([len(r['tokens']) for r,_ in seen],[2,1,0])
        self.assertTrue(all(b>=a for (_,a),(_,b) in zip(seen,seen[1:])))


if __name__=='__main__':unittest.main()
