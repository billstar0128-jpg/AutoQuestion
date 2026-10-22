package com.autoquestion.mobile;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.SocketTimeoutException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import javax.net.ssl.HttpsURLConnection;

/** Direct, bounded, non-streaming HTTPS request. No server, retries, redirects, or request logs. */
final class VisionClient {
    static final class Failure extends Exception {
        Failure(String message) { super(message); }
    }
    private volatile HttpsURLConnection active;
    private volatile boolean cancelled;

    void cancel() {
        cancelled = true;
        HttpsURLConnection connection = active;
        if (connection != null) connection.disconnect();
    }

    List<AnswerProtocol.Result> analyze(ApiConfig config, String key, byte[] png) throws Failure {
        byte[] requestBytes = null;
        try {
            if (cancelled) throw new Failure("本次识题已停止。");
            JSONArray content = new JSONArray()
                    .put(new JSONObject().put("type", "text").put("text", "请分别识别并回答屏幕中所有完整题目。"))
                    .put(new JSONObject().put("type", "image_url").put("image_url", new JSONObject()
                            .put("url", "data:image/png;base64," + android.util.Base64.encodeToString(png, android.util.Base64.NO_WRAP))));
            JSONObject request = new JSONObject().put("model", config.model).put("stream", false)
                    .put("messages", new JSONArray()
                            .put(new JSONObject().put("role", "system").put("content", AnswerProtocol.PROMPT))
                            .put(new JSONObject().put("role", "user").put("content", content)));
            requestBytes = request.toString().getBytes(StandardCharsets.UTF_8);
            HttpsURLConnection connection = (HttpsURLConnection) new URL(config.endpoint()).openConnection();
            active = connection;
            if (cancelled) throw new Failure("本次识题已停止。");
            connection.setInstanceFollowRedirects(false);
            connection.setRequestMethod("POST");
            connection.setConnectTimeout(15000);
            connection.setReadTimeout(180000);
            connection.setRequestProperty("Authorization", "Bearer " + key);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setFixedLengthStreamingMode(requestBytes.length);
            connection.setDoOutput(true);
            try (OutputStream output = connection.getOutputStream()) { output.write(requestBytes); }
            int code = connection.getResponseCode();
            if (code == 401 || code == 403) throw new Failure("API Key 无效、没有权限或余额不足，请检查服务商控制台。");
            if (code == 429) throw new Failure("服务商限流或额度不足，请稍后再试。");
            if (code == 400 || code == 404 || code == 422) throw new Failure("请求被服务商拒绝，请检查 Base URL、model 和图片输入支持。");
            if (code < 200 || code >= 300) throw new Failure("服务商请求失败（HTTP " + code + "）。请检查配置后重试。");
            String response;
            try (InputStream input = connection.getInputStream(); ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = input.read(buffer)) != -1) {
                    if (cancelled) throw new Failure("本次识题已停止。");
                    if (bytes.size() + read > 1048576) throw new Failure("服务商返回过大，请减少屏幕上的题目数量。");
                    bytes.write(buffer, 0, read);
                }
                response = bytes.toString(StandardCharsets.UTF_8.name());
            }
            JSONObject choice = StrictJson.object(response).getJSONArray("choices").getJSONObject(0);
            if (!"stop".equals(choice.getString("finish_reason"))) throw new Failure("回答未完整结束，请减少题目后重试。");
            JSONObject message = choice.getJSONObject("message");
            if (message.has("refusal") && !message.isNull("refusal")) throw new Failure("服务商没有回答这张图片。");
            String text = message.getString("content");
            JSONObject answer = StrictJson.object(text);
            if (answer.length() == 1 && "unable_to_identify_question".equals(answer.opt("error")))
                throw new Failure("没有找到完整可读的题目。请展开题干和所有选项，再点悬浮按钮。");
            if (cancelled) throw new Failure("本次识题已停止。");
            return AnswerProtocol.parse(text);
        } catch (Failure e) { throw e;
        } catch (SocketTimeoutException e) { throw new Failure("连接或回答超时，请检查网络后重试。");
        } catch (org.json.JSONException e) { throw new Failure("模型返回的题目与答案不一致，未展示不可靠的结果，请重试。");
        } catch (Exception e) { throw new Failure("连接失败，请检查网络、HTTPS 地址和 API Key。未保存截图。");
        } finally {
            if (requestBytes != null) Arrays.fill(requestBytes, (byte) 0);
            Arrays.fill(png, (byte) 0);
            HttpsURLConnection connection = active;
            active = null;
            if (connection != null) connection.disconnect();
        }
    }
}
