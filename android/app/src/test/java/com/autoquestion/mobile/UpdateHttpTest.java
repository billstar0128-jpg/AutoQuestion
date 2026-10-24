package com.autoquestion.mobile;

import org.junit.Test;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.InputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.security.cert.Certificate;
import java.util.ArrayList;
import java.util.List;
import javax.net.ssl.HttpsURLConnection;
import static org.junit.Assert.*;

public final class UpdateHttpTest {
    private static final String URL = "https://github.com/" + UpdatePolicy.REPOSITORY + "/releases/download/v0.6.0/AutoQuestion-0.6.0-Android.apk";
    private static UpdatePolicy.Asset asset(byte[] data) throws Exception {
        return new UpdatePolicy.Asset("AutoQuestion-0.6.0-Android.apk", URL,
                UpdateHttp.hex(MessageDigest.getInstance("SHA-256").digest(data)), data.length);
    }
    @Test public void downloadsAndVerifiesExactBytesWithoutModelCredentials() throws Exception {
        byte[] data = "synthetic apk fixture".getBytes(StandardCharsets.UTF_8);
        Fake connection = new Fake(new URL(URL), 200, data);
        UpdateHttp client = new UpdateHttp(url -> connection);
        File output = File.createTempFile("aq-update-test-", ".apk");
        try {
            client.download(asset(data), output, null);
            assertArrayEquals(data, Files.readAllBytes(output.toPath()));
            UpdateHttp.verifyFile(output, asset(data));
            assertNull(connection.getRequestProperty("Authorization"));
            assertFalse(connection.getInstanceFollowRedirects());
            Files.write(output.toPath(), "tampered".getBytes(StandardCharsets.UTF_8));
            assertThrows(Exception.class, () -> UpdateHttp.verifyFile(output, asset(data)));
        } finally { output.delete(); }
    }
    @Test public void checksumOrSizeMismatchStopsTheDownload() throws Exception {
        byte[] expected = "expected".getBytes(StandardCharsets.UTF_8), wrong = "modified".getBytes(StandardCharsets.UTF_8);
        UpdateHttp client = new UpdateHttp(url -> new Fake(url, 200, wrong));
        assertThrows(Exception.class, () -> client.asset(asset(expected)));
        UpdateHttp truncated = new UpdateHttp(url -> new Fake(url, 200, new byte[]{1}));
        assertThrows(Exception.class, () -> truncated.asset(asset(expected)));
    }
    @Test public void onlyOfficialRedirectsAreFollowedAndNeverAutomatically() throws Exception {
        byte[] data = {1, 2, 3}; List<String> visited = new ArrayList<>();
        UpdateHttp client = new UpdateHttp(url -> {
            visited.add(url.toString()); Fake response = new Fake(url, visited.size() == 1 ? 302 : 200, data);
            response.location = "https://release-assets.githubusercontent.com/fixture?signature=test"; return response;
        });
        assertArrayEquals(data, client.asset(asset(data))); assertEquals(2, visited.size());
        UpdateHttp evil = new UpdateHttp(url -> {
            Fake response = new Fake(url, 302, data); response.location = "https://evil.example/app.apk"; return response;
        });
        assertThrows(Exception.class, () -> evil.asset(asset(data)));
    }
    @Test public void releaseApiDoesNotFollowRedirectsAndUsesOnlyFixedEndpoint() throws Exception {
        UpdateHttp client = new UpdateHttp(url -> {
            assertEquals(UpdatePolicy.RELEASES_URL, url.toString());
            Fake response = new Fake(url, 302, new byte[0]); response.location = "https://api.github.com/other"; return response;
        });
        assertThrows(Exception.class, client::releaseMetadata);
    }
    @Test public void cancellationPreventsOpeningAnyNetworkConnection() {
        UpdateHttp client = new UpdateHttp(url -> { fail("Cancelled work opened a connection"); return null; });
        client.cancel(); assertThrows(Exception.class, client::releaseMetadata);
    }

    private static final class Fake extends HttpsURLConnection {
        final int status; final byte[] data; String location;
        Fake(URL url, int status, byte[] data) { super(url); this.status = status; this.data = data; }
        @Override public int getResponseCode() { return status; }
        @Override public long getContentLengthLong() { return data.length; }
        @Override public String getHeaderField(String name) { return "Location".equals(name) ? location : null; }
        @Override public InputStream getInputStream() { return new ByteArrayInputStream(data); }
        @Override public void disconnect() { }
        @Override public void connect() { }
        @Override public boolean usingProxy() { return false; }
        @Override public String getCipherSuite() { return "SYNTHETIC"; }
        @Override public Certificate[] getLocalCertificates() { return null; }
        @Override public Certificate[] getServerCertificates() { return new Certificate[0]; }
    }
}
