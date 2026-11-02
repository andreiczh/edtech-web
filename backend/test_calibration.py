import asyncio
import io
import unittest
import wave
from unittest.mock import patch, AsyncMock

import numpy as np
import audio_check
import ege_scoring as sc
import scoring
import grading_audio


def wav(pcm, rate=16000):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((pcm * 32767).astype("<i2").tobytes())
    return out.getvalue()


class CalibrationTests(unittest.TestCase):
    def test_apostrophes_do_not_change_a_mark(self):
        for quote in ("'", "’", "‘", "ʼ"):
            brief = f"which activity you{quote}d prefer and why"
            spoken = f"As for me, I{quote}d prefer walking because it is relaxing."
            self.assertTrue(sc.verb_form_matches(sc.plan_form_from_brief(brief),
                                                sc.opinion_form_from_speech(spoken)))
            self.assertFalse(sc.verb_form_matches("you prefer", sc.opinion_form_from_speech(spoken)))

    def test_partial_coverage_is_not_two_types(self):
        c = {"n": 3, "named_first": True, "named_second": False,
             "specific_first": True, "specific_second": True}
        self.assertEqual(sc.aspect_verdicts([c])[2]["verdict"], sc.MISSING)

    def test_consensus_does_not_depend_on_pass_order_for_description(self):
        a = {"aspects": [{"n": 1, "described_first": True}]}
        b = {"aspects": [{"n": 1, "described_first": False}]}
        self.assertEqual(sc.merge_two_passes(a,b)["aspects"], sc.merge_two_passes(b,a)["aspects"])

    def test_complex_sentences_and_fillers(self):
        self.assertEqual(sc.count_phrases("I live in a flat because it is convenient."), 2)
        self.assertEqual(sc.count_phrases("I think that it is convenient."), 1)
        self.assertEqual(sc.count_phrases("It’s green. There are rivers."), 2)
        self.assertEqual(sc.count_phrases("In the city. Near the park."), 0)
        self.assertEqual(sc.count_phrases("I live here. I live here."), 1)

    def test_exam_prompts_are_persona_independent(self):
        for kind, payload in (("dialogue", {"ad":"School", "points":["cost"]}),
                              ("interview", {"questions":["Where do you live?"]}),
                              ("monologue", {"brief":"Explain the photos"})):
            prompts = [scoring._feedback_prompt(kind, payload, "Test answer", p)[0]
                       for p in ("tutor", "critic", "mentor")]
            self.assertEqual(len(set(prompts)), 1)

    def test_point_numbers_survive_reordered_model_output(self):
        obs = {"questions":[{"n":2,"accepted":False,"heard":"missing"},
                             {"n":1,"accepted":True,"heard":"Where is the club?"}]}
        result = scoring._score_feedback("dialogue",obs,{"ad":"club","points":["location","price"]})
        self.assertEqual([x["score"] for x in result["criteria"]], [1,0])

    def test_duration_is_bounded_even_for_small_compressed_files(self):
        data=wav(np.zeros(32000, dtype=np.float32))
        with patch.object(audio_check, "MAX_AUDIO_SECONDS", 1):
            with self.assertRaises(audio_check.AudioTooLong): audio_check.validate_duration(data)
            with self.assertRaises(audio_check.AudioTooLong): audio_check.to_pcm(data,".wav")

    def test_pause_compaction_keeps_speech_samples_and_order(self):
        x=np.zeros(40*16000,dtype=np.float32)
        x[16000:32000]=.2; x[30*16000:31*16000]=-.3
        spans=[{"start":8000,"end":40000},{"start":29*16000,"end":32*16000}]
        with patch("faster_whisper.vad.get_speech_timestamps",return_value=spans):
            out=grading_audio.prepare(wav(x),"a.wav")
        y=audio_check.to_pcm(out,".wav")
        self.assertAlmostEqual(len(y)/16000, 5.5)
        self.assertEqual(np.count_nonzero(y>.1),16000)
        self.assertEqual(np.count_nonzero(y<-.1),16000)

    def test_uncertain_vad_keeps_original(self):
        data=wav(np.zeros(35*16000,dtype=np.float32))
        with patch("faster_whisper.vad.get_speech_timestamps",return_value=[]):
            self.assertEqual(grading_audio.prepare(data,"a.wav"),data)

    def test_transient_capacity_retries_same_recognizer(self):
        import main
        with patch.object(main,"STT_TASK_MODE","transcription"), \
             patch.object(grading_audio,"prepare",return_value=b"prepared"), \
             patch.object(main,"transcribe_remote",new=AsyncMock(side_effect=[
                 main._RemoteSttError(429,"capacity"), "complete answer"])) as remote, \
             patch.object(main.asyncio,"sleep",new=AsyncMock()), \
             patch.object(main,"transcribe_auto",new=AsyncMock()) as fallback:
            self.assertEqual(asyncio.run(main.transcribe_for_task(b"original")),"complete answer")
            self.assertEqual(remote.await_count,2)
            self.assertEqual(remote.await_args_list[0],remote.await_args_list[1])
            fallback.assert_not_called()

    def test_authentication_failure_is_not_retried(self):
        import main
        with patch.object(main,"STT_TASK_MODE","transcription"), \
             patch.object(grading_audio,"prepare",return_value=b"prepared"), \
             patch.object(main,"transcribe_remote",new=AsyncMock(side_effect=main._RemoteSttError(401,"unauthorized"))) as remote:
            with self.assertRaises(main.SttFailed): asyncio.run(main.transcribe_for_task(b"original"))
            self.assertEqual(remote.await_count,1)


if __name__ == "__main__": unittest.main()
