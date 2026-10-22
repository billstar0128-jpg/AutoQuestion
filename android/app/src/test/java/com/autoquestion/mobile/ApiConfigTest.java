package com.autoquestion.mobile;

import org.junit.Test;
import static org.junit.Assert.*;

public final class ApiConfigTest {
    @Test public void baseUrlAndOriginAreNormalizedWithoutDuplicatingEndpoint() {
        ApiConfig config = new ApiConfig(" https://api.deepseek.com/ ", " deepseek-flash ");
        assertEquals("https://api.deepseek.com/chat/completions", config.endpoint());
        assertEquals("https://api.deepseek.com:443", config.origin());
        assertEquals(config.origin(), new ApiConfig("https://API.DEEPSEEK.COM:443", "deepseek-flash").origin());
        assertEquals("https://api.openai.com/v1/chat/completions", new ApiConfig("https://api.openai.com/v1", "gpt-4.1-mini").endpoint());
    }

    @Test public void rejectsCleartextCredentialsFragmentsAndInvalidPorts() {
        for (String value : new String[]{"http://example.com", "https://user:pass@example.com", "https://example.com?token=x",
                "https://example.com/#key", "https://example.com:0", "https://example.com:65536", "https://example.com:abc",
                "not-a-url", "https://example.com/chat/completions"}) {
            assertThrows(value, IllegalArgumentException.class, () -> new ApiConfig(value, "vision-model"));
        }
    }

    @Test public void differentHostsAndPortsHaveDifferentCredentialScopes() {
        ApiConfig config = new ApiConfig("https://api.example.com/v1", "model");
        assertNotEquals(config.origin(), new ApiConfig("https://api.other.example/v1", "model").origin());
        assertNotEquals(config.origin(), new ApiConfig("https://api.example.com:444/v1", "model").origin());
        assertEquals(config.origin(), new ApiConfig("https://api.example.com/v2", "model2").origin());
    }

    @Test public void keysCannotInjectHeadersOrContainWhitespace() {
        ApiConfig.validateKey("synthetic-test-value");
        for (String value : new String[]{"", "has space", "line\r\nHeader:value", "中文", "\ttab"})
            assertThrows(IllegalArgumentException.class, () -> ApiConfig.validateKey(value));
    }
}
