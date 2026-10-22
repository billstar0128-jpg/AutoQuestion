package com.autoquestion.mobile;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import java.util.List;
import static org.junit.Assert.*;

public final class AnswerProtocolTest {
    private JSONObject single() throws Exception {
        return new JSONObject("""
            {"question":{"question_text":"1. 法国首都是？","question_type":"single_choice","source_type":"VISION",
            "options":[{"index":0,"label":"A","text":"巴黎"},{"index":1,"label":"B","text":"伦敦"}]},
            "answer":{"question_type":"single_choice","selected_index":0,"selected_label":"A","selected_text":"巴黎",
            "confidence":0.95,"short_reason":"法国首都是巴黎。"}}
            """);
    }
    private JSONObject multiple() throws Exception {
        return new JSONObject("""
            {"question":{"question_text":"2. 以下哪些是偶数？","question_type":"multiple_choice","source_type":"VISION",
            "options":[{"index":0,"label":"A","text":"2"},{"index":1,"label":"B","text":"3"},{"index":2,"label":"C","text":"4"}]},
            "answer":{"question_type":"multiple_choice","selected_indices":[2,0],"selected_labels":["C","A"],"selected_texts":["4","2"],
            "confidence":0.9,"short_reason":"2 和 4 都能被 2 整除。"}}
            """);
    }
    private String batch(JSONObject... entries) throws Exception {
        JSONArray results = new JSONArray(); for (JSONObject entry : entries) results.put(entry);
        return new JSONObject().put("results", results).toString();
    }
    private JSONObject trueFalse(int number) throws Exception {
        JSONObject entry = single();
        JSONObject question = entry.getJSONObject("question"), answer = entry.getJSONObject("answer");
        question.put("question_text", number + ". 2 是偶数。判断对错。").put("question_type", "true_false");
        JSONArray options = question.getJSONArray("options");
        options.getJSONObject(0).put("label", JSONObject.NULL).put("text", "正确");
        options.getJSONObject(1).put("label", JSONObject.NULL).put("text", "错误");
        answer.put("question_type", "true_false").put("selected_label", JSONObject.NULL)
                .put("selected_text", "正确").put("short_reason", "2 能被 2 整除。");
        return entry;
    }
    private void rejected(String value) {
        assertThrows(org.json.JSONException.class, () -> AnswerProtocol.parse(value));
    }

    @Test public void mixedQuestionsKeepIndependentAnswersAndScreenOrder() throws Exception {
        List<AnswerProtocol.Result> results = AnswerProtocol.parse(batch(single(), multiple()));
        assertEquals(2, results.size());
        assertEquals("1. 法国首都是？", results.get(0).question);
        assertEquals("A · 巴黎", results.get(0).answer);
        assertEquals("A · 2\nC · 4", results.get(1).answer);
        assertEquals("多选", results.get(1).typeLabel());
    }

    @Test public void threeThroughSixMixedQuestionsKeepEveryIndependentAnswer() throws Exception {
        JSONObject secondSingle = single(); secondSingle.getJSONObject("question").put("question_text", "4. 法国首都是？");
        JSONObject secondMulti = multiple(); secondMulti.getJSONObject("question").put("question_text", "5. 以下哪些是偶数？");
        JSONObject[] all = { single(), multiple(), trueFalse(3), secondSingle, secondMulti, trueFalse(6) };
        for (int count = 3; count <= 6; count++) {
            List<AnswerProtocol.Result> results = AnswerProtocol.parse(batch(java.util.Arrays.copyOf(all, count)));
            assertEquals(count, results.size());
            assertEquals("A · 巴黎", results.get(0).answer);
            assertEquals("A · 2\nC · 4", results.get(1).answer);
            assertEquals("正确", results.get(2).answer);
            if (count >= 4) assertEquals("A · 巴黎", results.get(3).answer);
            if (count >= 5) assertEquals("A · 2\nC · 4", results.get(4).answer);
            if (count == 6) assertEquals("正确", results.get(5).answer);
        }
    }

    @Test public void aBadAnswerInsideSixQuestionsRejectsTheEntireBatch() throws Exception {
        JSONObject fourth = single(); fourth.getJSONObject("question").put("question_text", "4. 法国首都是？");
        JSONObject fifth = multiple(); fifth.getJSONObject("question").put("question_text", "5. 以下哪些是偶数？");
        JSONObject sixth = trueFalse(6);
        sixth.getJSONObject("answer").put("selected_text", "巴黎");
        rejected(batch(single(), multiple(), trueFalse(3), fourth, fifth, sixth));
    }

    @Test public void legacySingleAndUnlabelledTrueFalseStillWork() throws Exception {
        assertEquals(1, AnswerProtocol.parse(single().toString()).size());
        JSONObject entry = single(); JSONObject question = entry.getJSONObject("question"), answer = entry.getJSONObject("answer");
        question.put("question_type", "true_false"); answer.put("question_type", "true_false");
        JSONArray options = question.getJSONArray("options");
        options.getJSONObject(0).put("label", JSONObject.NULL).put("text", "正确");
        options.getJSONObject(1).put("label", JSONObject.NULL).put("text", "错误");
        answer.put("selected_label", JSONObject.NULL).put("selected_text", "正确");
        assertEquals("正确", AnswerProtocol.parse(batch(entry)).get(0).answer);
    }

    @Test public void rejectsAnswersThatUseAnotherQuestionsOptions() throws Exception {
        JSONObject entry = single(); entry.getJSONObject("answer").put("selected_text", "2"); rejected(batch(entry, multiple()));
    }

    @Test public void rejectsMismatchedTypeDuplicateSelectionAndInventedLabels() throws Exception {
        JSONObject entry = single(); entry.getJSONObject("answer").put("question_type", "true_false"); rejected(batch(entry));
        entry = multiple(); entry.getJSONObject("answer").put("selected_indices", new JSONArray("[0,0]")); rejected(batch(entry));
        entry = single(); entry.getJSONObject("answer").put("selected_label", "C"); rejected(batch(entry));
    }

    @Test public void rejectsEmptyOverLimitAndDuplicateQuestions() throws Exception {
        rejected("{\"results\":[]}");
        rejected(batch(single(), single()));
        JSONObject[] many = new JSONObject[11];
        for (int i = 0; i < many.length; i++) {
            many[i] = single(); many[i].getJSONObject("question").put("question_text", i + ". 题目");
        }
        rejected(batch(many));
    }

    @Test public void requiresOriginalLabelsAndIntegerIndices() throws Exception {
        JSONObject entry = single(); entry.getJSONObject("question").getJSONArray("options").getJSONObject(0).remove("label"); rejected(batch(entry));
        entry = single(); entry.getJSONObject("answer").remove("selected_label"); rejected(batch(entry));
        entry = single(); entry.getJSONObject("answer").put("selected_index", "0"); rejected(batch(entry));
        rejected(batch(single()).replace("\"index\":0", "\"index\":0.0"));
    }

    @Test public void rejectsUnsafeConfidenceAndExtraProtocolFields() throws Exception {
        JSONObject entry = single(); entry.getJSONObject("answer").put("confidence", "0.9"); rejected(batch(entry));
        entry = single(); entry.getJSONObject("answer").put("confidence", 1.1); rejected(batch(entry));
        entry = single(); entry.getJSONObject("answer").put("click", true); rejected(batch(entry));
    }

    @Test public void strictJsonRejectsDuplicateEscapedKeysTrailingObjectsAndNonJsonSyntax() throws Exception {
        String valid = batch(single());
        rejected(valid.replace("\"confidence\":0.95", "\"confidence\":0.95,\"confidence\":0.2"));
        rejected(valid.replace("\"confidence\":0.95", "\"confidence\":0.95,\"\\u0063onfidence\":0.2"));
        rejected(valid + "{}");
        rejected("/*comment*/" + valid);
        rejected(valid.replace("0.95", "NaN"));
        rejected(valid.replace("0.95", "01"));
        rejected(valid.substring(0, valid.length() - 1) + ",}");
        rejected(valid.replace("\"results\"", "'results'"));
        rejected(valid.replace("\"results\"", "\"\\uＦＦＦＦ\""));
    }

    @Test public void errorLiteralInsideAQuestionIsOrdinaryQuestionData() throws Exception {
        JSONObject entry = single(); entry.getJSONObject("question").put("question_text", "字符串 \"unable_to_identify_question\" 是哪项？");
        assertEquals(1, AnswerProtocol.parse(batch(entry)).size());
    }
}
