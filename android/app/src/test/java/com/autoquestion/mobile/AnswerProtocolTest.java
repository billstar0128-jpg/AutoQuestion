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
    private JSONObject fill() throws Exception {
        return new JSONObject("""
            {"question":{"question_text":"4. 1+1=____；2+2=____。","question_type":"fill_blank","source_type":"VISION",
            "options":[],"blank_count":2},"answer":{"question_type":"fill_blank","blank_answers":["2","4"],
            "confidence":0.95,"short_reason":"分别计算两个算式。"}}
            """);
    }
    private JSONObject subjective() throws Exception {
        return new JSONObject("""
            {"question":{"question_text":"5. 解方程并写出步骤：2x+3=7。","question_type":"short_answer","source_type":"VISION",
            "options":[],"blank_count":null},"answer":{"question_type":"short_answer", "answer_text":"第一步：两边减去 3，得到 2x=4。\\n\\n第二步：两边除以 2，得到 x=2。\\n检验：2×2+3=7，成立。",
            "confidence":0.9,"short_reason":"通过等式两边同减、同除求解。"}}
            """);
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

    @Test public void allFiveTypesCanMixWithoutLosingParagraphsOrBlankOrder() throws Exception {
        JSONObject sixth = subjective(); sixth.getJSONObject("question").put("question_text", "6. 说明你的理由。");
        List<AnswerProtocol.Result> results = AnswerProtocol.parse(batch(single(), multiple(), trueFalse(3), fill(), subjective(), sixth));
        assertEquals(6, results.size());
        assertEquals("单选", results.get(0).typeLabel()); assertEquals("多选", results.get(1).typeLabel());
        assertEquals("判断", results.get(2).typeLabel()); assertEquals("填空", results.get(3).typeLabel());
        assertEquals("简答 / 解答", results.get(4).typeLabel());
        assertEquals(java.util.Arrays.asList("2", "4"), results.get(3).blankAnswers);
        assertEquals("第 1 空：2\n第 2 空：4", results.get(3).answer);
        assertEquals(subjective().getJSONObject("answer").getString("answer_text"), results.get(4).answer);
        assertTrue(results.get(4).answer.contains("\n\n"));
        assertThrows(UnsupportedOperationException.class, () -> results.get(3).blankAnswers.add("changed"));
    }

    @Test public void acceptsSerializedDefaultEmptyFieldsForEveryType() throws Exception {
        JSONObject[] entries = {single(), multiple(), trueFalse(3), fill(), subjective()};
        for (JSONObject entry : entries) {
            JSONObject q = entry.getJSONObject("question"), a = entry.getJSONObject("answer");
            if (!q.has("blank_count")) q.put("blank_count", JSONObject.NULL);
            for (String field : new String[]{"selected_index", "selected_label", "selected_text", "answer_text"})
                if (!a.has(field)) a.put(field, JSONObject.NULL);
            for (String field : new String[]{"selected_indices", "selected_labels", "selected_texts", "blank_answers"})
                if (!a.has(field)) a.put(field, new JSONArray());
        }
        assertEquals(5, AnswerProtocol.parse(batch(entries)).size());
    }

    @Test public void fillBlankCountMustBeAnExplicitStrictIntegerBetweenOneAndTwenty() throws Exception {
        JSONObject entry = fill(); entry.getJSONObject("question").remove("blank_count"); rejected(batch(entry));
        for (Object count : new Object[]{JSONObject.NULL, 0, 21, "2", true}) {
            entry = fill(); entry.getJSONObject("question").put("blank_count", count); rejected(batch(entry));
        }
        rejected(batch(fill()).replace("\"blank_count\":2", "\"blank_count\":2.0"));
    }

    @Test public void fillRejectsMissingExtraEmptyAndNonStringAnswersAtomically() throws Exception {
        for (String values : new String[]{"[]", "[\"2\"]", "[\"2\",\"4\",\"6\"]", "[\"2\",\" \"]",
                "[\"2\",null]", "[\"2\",4]"}) {
            JSONObject entry = fill(); entry.getJSONObject("answer").put("blank_answers", new JSONArray(values));
            rejected(batch(single(), multiple(), trueFalse(3), entry, subjective()));
        }
        JSONObject entry = fill(); entry.getJSONObject("answer").remove("blank_answers"); rejected(batch(entry));
        entry = fill(); entry.getJSONObject("answer").put("blank_answers", new JSONArray().put("2").put("x".repeat(2001))); rejected(batch(entry));
    }

    @Test public void subjectiveMustNotBorrowOptionsOrSelectionFields() throws Exception {
        for (JSONObject entry : new JSONObject[]{fill(), subjective()}) {
            entry.getJSONObject("question").put("options", single().getJSONObject("question").getJSONArray("options")); rejected(batch(entry));
        }
        for (String field : new String[]{"selected_index", "selected_label", "selected_text"}) {
            JSONObject entry = subjective(); entry.getJSONObject("answer").put(field, field.equals("selected_index") ? 0 : ""); rejected(batch(entry));
        }
        for (String field : new String[]{"selected_indices", "selected_labels", "selected_texts"}) {
            JSONObject entry = fill(); entry.getJSONObject("answer").put(field, new JSONArray().put("x")); rejected(batch(entry));
            entry = fill(); entry.getJSONObject("answer").put(field, JSONObject.NULL); rejected(batch(entry));
        }
    }

    @Test public void onlyTheCorrectAnswerFieldsAreAllowedForEachType() throws Exception {
        JSONObject entry = fill(); entry.getJSONObject("answer").put("answer_text", "2 and 4"); rejected(batch(entry));
        entry = subjective(); entry.getJSONObject("answer").put("blank_answers", new JSONArray().put("2")); rejected(batch(entry));
        entry = single(); entry.getJSONObject("answer").put("answer_text", "Paris"); rejected(batch(entry));
        entry = multiple(); entry.getJSONObject("answer").put("blank_answers", new JSONArray().put("2")); rejected(batch(entry));
        entry = single(); entry.getJSONObject("question").put("blank_count", 1); rejected(batch(entry));
        entry = subjective(); entry.getJSONObject("question").put("blank_count", 1); rejected(batch(entry));
    }

    @Test public void shortReasonCannotSubstituteForACompleteSubjectiveAnswer() throws Exception {
        JSONObject entry = subjective(); entry.getJSONObject("answer").remove("answer_text"); rejected(batch(entry));
        for (Object value : new Object[]{JSONObject.NULL, "", " \n\t ", "\u00a0\u3000", 42, "x".repeat(12001)}) {
            entry = subjective(); entry.getJSONObject("answer").put("answer_text", value); rejected(batch(entry));
        }
        entry = subjective(); entry.getJSONObject("answer").put("answer_text", "x".repeat(12000));
        assertEquals(12000, AnswerProtocol.parse(batch(entry)).get(0).answer.length());
        entry = subjective(); entry.getJSONObject("answer").put("answer_text", "😀".repeat(12000));
        String unicode = AnswerProtocol.parse(batch(entry)).get(0).answer;
        assertEquals(12000, unicode.codePointCount(0, unicode.length()));
    }

    @Test public void twentyVisibleBlanksAreSupportedButNotTwentyOne() throws Exception {
        JSONObject entry = fill(); entry.getJSONObject("question").put("blank_count", 20);
        JSONArray values = new JSONArray(); for (int i = 1; i <= 20; i++) values.put("答案" + i);
        entry.getJSONObject("answer").put("blank_answers", values);
        assertEquals(20, AnswerProtocol.parse(batch(entry)).get(0).blankAnswers.size());
        entry.getJSONObject("question").put("blank_count", 21); values.put("答案21"); rejected(batch(entry));
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
