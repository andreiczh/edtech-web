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

    def test_summary_and_errors_follow_final_verdict(self):
        obs = {"questions":[{"n":1,"accepted":True,"heard":"Where is the club located?","reason":"correct"}],
               "summary":"Old pass rejected the question", "errors":[
                   {"cat":"order","quote":"Where is the club located?","correction":"Where is the club?","explanation":"old verdict"}]}
        result=scoring._score_feedback("dialogue",obs,{"ad":"club","points":["location"]})
        self.assertEqual(result["score"],1)
        self.assertIn("1 из 1",result["summary"])
        self.assertEqual(result["errors"],[])

    def test_interview_recheck_verifies_all_five_answers(self):
        import main
        from types import SimpleNamespace
        obs={"answers":[{"n":n,"accepted":True,"heard":"I live here. It is nice.","reason":"correct relevant answer"} for n in range(1,6)]}
        verdicts={"items":[{"n":n,"accepted":True,"reason":"verified"} for n in range(1,6)]}
        import json
        completion=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(verdicts)))])
        client=unittest.mock.MagicMock()
        client.chat.completions.create.return_value=completion
        with patch.object(main,"_track_llm"):
            asyncio.run(main._recheck_disputed("interview",obs,{"questions":["Where? Why?"]*5},"I live here. It is nice.","",client))
        self.assertEqual(client.chat.completions.create.call_count,1)
        self.assertGreaterEqual(client.chat.completions.create.call_args.kwargs["max_tokens"],800)

    def test_grading_uses_its_own_pinned_model(self):
        import main
        from types import SimpleNamespace
        client=unittest.mock.MagicMock()
        client.chat.completions.create.return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"answers":[]}'))])
        with patch.object(main,"GRADE_MODEL","fixed-exam-model"), patch.object(main,"LLM_MODEL","fast-chat-model"), patch.object(main,"_track_llm"):
            asyncio.run(main._grading_observations(client,"prompt","spoken answer","interview"))
        self.assertEqual(client.chat.completions.create.call_args.kwargs["model"],"fixed-exam-model")

    def test_incomplete_recheck_retries_complete_schema(self):
        import main, json
        from types import SimpleNamespace
        obs={"answers":[{"n":n,"accepted":True,"heard":"I live here. It is nice.","reason":"correct"} for n in range(1,6)]}
        good={"items":[{"n":n,"accepted":True,"reason":"correct"} for n in range(1,6)]}
        def response(body):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(body)))])
        client=unittest.mock.MagicMock()
        client.chat.completions.create.side_effect=[response({"items":good["items"][:2]}),response(good)]
        with patch.object(main,"_track_llm"):
            result=asyncio.run(main._recheck_disputed("interview",obs,{"questions":["Where? Why?"]*5},"I live here. It is nice.","",client))
        self.assertEqual(len(result["answers"]),5)
        self.assertEqual(client.chat.completions.create.call_count,2)

    def test_persistent_incomplete_recheck_never_assigns_zero(self):
        import main
        from types import SimpleNamespace
        client=unittest.mock.MagicMock()
        client.chat.completions.create.return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"items":[]}'))])
        obs={"answers":[{"n":1,"accepted":True,"heard":"I live here. It is nice.","reason":"correct"}]}
        with patch.object(main,"_track_llm"), patch.object(main,"note_failure"):
            with self.assertRaises(main.HTTPException):
                asyncio.run(main._recheck_disputed("interview",obs,{"questions":["Where? Why?"]},"I live here. It is nice.","",client))
        self.assertEqual(client.chat.completions.create.call_count,2)
        self.assertTrue(obs["answers"][0]["accepted"])

    def test_aspect_explanation_uses_final_observations(self):
        c={"n":2,"named_first":True,"named_second":True,"specific_first":True,
           "specific_second":False,"comment":"No second advantage at all"}
        text=sc.aspect_comment(c)
        self.assertIn("слишком общая",text)
        self.assertNotIn("No second",text)
        self.assertNotIn("первого",text)

    def test_personal_preference_needs_no_fixed_intro(self):
        obs={"aspects":[{"n":4,"opinion_explicit":False,"choice_stated":True,"justified":True}]}
        result=scoring._score_feedback("monologue",obs,{"transcript":"I prefer cycling because it keeps me healthy.","brief":"which activity you prefer"})
        self.assertIn("4+", result["criteria"][0]["comment"])

    def test_monologue_recheck_removes_invalid_error_but_keeps_real_one(self):
        import main, json
        from types import SimpleNamespace
        obs={"aspects":[],"lang_errors":[
            {"quote":"I've got to go","correction":"I have to go","grave":False},
            {"quote":"he go","correction":"he goes","grave":True}],"logic_errors":[]}
        checked={"aspects":[],"error_checks":[{"id":0,"valid":False},{"id":1,"valid":True}]}
        client=unittest.mock.MagicMock()
        client.chat.completions.create.return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(checked)))])
        with patch.object(main,"_track_llm"), patch.object(main,"MONOLOGUE_RECHECK",True):
            result=asyncio.run(main._recheck_aspects("monologue",obs,{},"I've got to go. He go home.","",client))
        self.assertEqual([e["quote"] for e in result["lang_errors"]],["he go"])

    def test_monologue_retries_omitted_rejected_error(self):
        import main, json
        from types import SimpleNamespace
        obs={"aspects":[],"lang_errors":[{"quote":"I've got to go"},{"quote":"he go"}]}
        partial={"aspects":[],"error_checks":[{"id":1,"valid":True}]}
        complete={"aspects":[],"error_checks":[{"id":0,"valid":False},{"id":1,"valid":True}]}
        client=unittest.mock.MagicMock()
        client.chat.completions.create.side_effect=[
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(d)))])
            for d in (partial,complete)]
        with patch.object(main,"_track_llm"), patch.object(main,"MONOLOGUE_RECHECK",True):
            result=asyncio.run(main._recheck_aspects("monologue",obs,{},"I've got to go. He go home.","",client))
        self.assertEqual(client.chat.completions.create.call_count,2)
        self.assertEqual([e["quote"] for e in result["lang_errors"]],["he go"])

    def test_monologue_twice_incomplete_never_mutates_or_grades(self):
        import main, json, copy
        from types import SimpleNamespace
        from fastapi import HTTPException
        obs={"aspects":[],"lang_errors":[{"quote":"he go"}]};before=copy.deepcopy(obs)
        client=unittest.mock.MagicMock()
        client.chat.completions.create.return_value=SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps({"aspects":[],"error_checks":[]})))])
        with patch.object(main,"_track_llm"), patch.object(main,"MONOLOGUE_RECHECK",True):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(main._recheck_aspects("monologue",obs,{},"He go home.","",client))
        self.assertEqual(error.exception.status_code,502)
        self.assertEqual(client.chat.completions.create.call_count,2)
        self.assertEqual(obs,before)

    def test_monologue_recheck_rejects_truthy_strings_and_duplicate_aspects(self):
        import main
        aspect={"n":2,"named_first":True,"named_second":True,
                "specific_first":True,"specific_second":False}
        main._validate_monologue_recheck({"aspects":[aspect],"error_checks":[]},[2],0)
        with self.assertRaises(ValueError):
            main._validate_monologue_recheck({"aspects":[{**aspect,"specific_second":"false"}],"error_checks":[]},[2],0)
        with self.assertRaises(ValueError):
            main._validate_monologue_recheck({"aspects":[aspect,aspect],"error_checks":[]},[2],0)

    def test_absent_difference_is_not_two_independent_content_flaws(self):
        check={"n":1,"described_first":True,"described_second":True,
               "difference_stated":False,"difference_generalised":False,
               "linked_to_topic":False,"factual_error":False}
        self.assertEqual(sc.aspect_verdicts([check])[0]["verdict"],sc.PARTIAL)
        # A separate factual mismatch is still a separate content flaw.
        self.assertEqual(sc.aspect_verdicts([{**check,"factual_error":True}])[0]["verdict"],sc.MISSING)

    def test_duration_is_bounded_even_for_small_compressed_files(self):
        data=wav(np.zeros(32000, dtype=np.float32))
        with patch.object(audio_check, "MAX_AUDIO_SECONDS", 1):
            with self.assertRaises(audio_check.AudioTooLong): audio_check.validate_duration(data)
            with self.assertRaises(audio_check.AudioTooLong): audio_check.to_pcm(data,".wav")

    def test_pause_compaction_keeps_speech_samples_and_order(self):
        x=np.zeros(40*16000,dtype=np.float32)
        x[16000:32000]=.2; x[30*16000:31*16000]=-.3
        spans=[{"start":8000,"end":40000},{"start":29*16000,"end":32*16000}]
        with patch.object(grading_audio, "speech_spans",return_value=spans):
            out=grading_audio.prepare(wav(x),"a.wav")
        y=audio_check.to_pcm(out,".wav")
        self.assertAlmostEqual(len(y)/16000, 5.5)
        self.assertEqual(np.count_nonzero(y>.1),16000)
        self.assertEqual(np.count_nonzero(y<-.1),16000)

    def test_uncertain_vad_keeps_original(self):
        data=wav(np.zeros(35*16000,dtype=np.float32))
        with patch("faster_whisper.vad.get_speech_timestamps",return_value=[]):
            self.assertEqual(grading_audio.prepare(data,"a.wav"),data)

    def test_vad_working_set_is_bounded_and_overlap_is_not_duplicated(self):
        x = np.full(360 * 16000, .1, dtype=np.float32)
        def entire_window(part, options):
            self.assertLessEqual(len(part), 20 * 16000)
            part[-64:] = 0  # upstream implementation mutates its input
            return [{"start": 0, "end": len(part)}]
        with patch("faster_whisper.vad.get_speech_timestamps", side_effect=entire_window):
            self.assertEqual(grading_audio.speech_spans(x), [{"start":0,"end":len(x)}])
        self.assertTrue(np.all(x == np.float32(.1)))

    def test_transient_capacity_retries_same_recognizer(self):
        import main
        with patch.object(main,"STT_TASK_MODE","transcription"), \
             patch.object(grading_audio,"analyze_isolated",return_value=({},b"prepared")), \
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
             patch.object(grading_audio,"analyze_isolated",return_value=({},b"prepared")), \
             patch.object(main,"transcribe_remote",new=AsyncMock(side_effect=main._RemoteSttError(401,"unauthorized"))) as remote:
            with self.assertRaises(main.SttFailed): asyncio.run(main.transcribe_for_task(b"original"))
            self.assertEqual(remote.await_count,1)


if __name__ == "__main__": unittest.main()
