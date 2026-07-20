from pathlib import Path
from app.diarization import parse_rttm, apply_speakers

def test_rttm_parse_and_apply(tmp_path: Path):
    p=tmp_path/'sample.rttm'
    p.write_text('SPEAKER meeting 1 0.00 2.00 <NA> <NA> SPEAKER_01 <NA> <NA>\nSPEAKER meeting 1 2.00 2.00 <NA> <NA> SPEAKER_02 <NA> <NA>\n')
    intervals=parse_rttm(p)
    segments=apply_speakers([{'start':0.2,'end':1.0,'speaker':'SPEAKER_00','text':'a'},{'start':2.2,'end':3.0,'speaker':'SPEAKER_00','text':'b'}],intervals)
    assert segments[0]['speaker']=='SPEAKER_01'
    assert segments[1]['speaker']=='SPEAKER_02'
