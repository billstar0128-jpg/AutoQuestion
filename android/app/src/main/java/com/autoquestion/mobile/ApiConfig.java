package com.autoquestion.mobile;

import java.net.URI;
import java.net.URISyntaxException;

/** Only public configuration belongs here; API keys are held separately. */
final class ApiConfig {
    final String baseUrl;
    final String model;

    ApiConfig(String url, String modelName) {
        String normalized = url.trim().replaceAll("/+$", "");
        try {
            URI uri = new URI(normalized);
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null
                    || uri.getRawUserInfo() != null || uri.getRawQuery() != null
                    || uri.getRawFragment() != null || uri.getPort() == 0
                    || uri.getPort() < -1 || uri.getPort() > 65535) {
                throw new IllegalArgumentException("Base URL 需要 HTTPS 地址，不能包含账号、查询参数或 #。");
            }
        } catch (URISyntaxException e) {
            throw new IllegalArgumentException("Base URL 格式不正确。");
        }
        if (normalized.endsWith("/chat/completions")) {
            throw new IllegalArgumentException("Base URL 不需要 /chat/completions，请填写它前面的部分。");
        }
        String cleanModel = modelName.trim();
        if (normalized.length() > 2048 || cleanModel.isEmpty() || cleanModel.length() > 200
                || cleanModel.chars().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException("请填写有效的模型名称（model ID）。");
        }
        baseUrl = normalized;
        model = cleanModel;
    }

    String endpoint() { return baseUrl + "/chat/completions"; }

    String origin() {
        URI uri = URI.create(baseUrl);
        int port = uri.getPort() == -1 ? 443 : uri.getPort();
        return uri.getScheme().toLowerCase(java.util.Locale.ROOT) + "://"
                + uri.getHost().toLowerCase(java.util.Locale.ROOT) + ":" + port;
    }

    String host() { return URI.create(baseUrl).getHost(); }

    static void validateKey(String value) {
        if (value.isEmpty() || value.length() > 8192
                || value.chars().anyMatch(c -> c <= 32 || c >= 127)) {
            throw new IllegalArgumentException("请填写有效的 API Key，不能包含空格或换行。");
        }
    }
}
