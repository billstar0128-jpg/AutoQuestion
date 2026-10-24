package com.autoquestion.mobile;

import java.io.IOException;
import java.net.URL;
import java.net.URLConnection;
import java.net.URLStreamHandler;
import javax.net.ssl.HttpsURLConnection;

/** One process-wide, deny-by-default HTTPS router for disposable-emulator tests. */
final class MockHttps {
    interface Router { HttpsURLConnection open(URL url) throws IOException; }
    private static volatile Router router;
    private static boolean installed;
    static synchronized void install(Router next) {
        router = next;
        if (installed) return;
        URL.setURLStreamHandlerFactory(protocol -> "https".equals(protocol) ? new URLStreamHandler() {
            @Override protected URLConnection openConnection(URL url) throws IOException {
                Router current = router;
                if (current == null) throw new IOException("No test HTTPS route");
                return current.open(url);
            }
        } : null);
        installed = true;
    }
    private MockHttps() {}
}
