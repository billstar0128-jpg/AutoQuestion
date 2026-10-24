package com.autoquestion.mobile;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

public final class UpdatePolicyTest {
    private static final String SHA = "ab".repeat(32);
    private JSONObject release(String version, boolean preview, boolean draft) throws Exception {
        String name = "AutoQuestion-" + version + "-Android.apk";
        return new JSONObject().put("tag_name", "v" + version).put("draft", draft).put("prerelease", preview)
                .put("assets", new JSONArray().put(new JSONObject().put("name", name).put("state", "uploaded")
                        .put("size", 100).put("digest", "sha256:" + SHA).put("browser_download_url",
                                "https://github.com/" + UpdatePolicy.REPOSITORY + "/releases/download/v" + version + "/" + name)));
    }
    private UpdatePolicy.Release choose(JSONObject... values) throws Exception {
        JSONArray releases = new JSONArray(); for (JSONObject value : values) releases.put(value);
        return UpdatePolicy.choose(releases, "0.5.0");
    }

    @Test public void prereleasesAreIncludedAndDraftsAreExcluded() throws Exception {
        UpdatePolicy.Release selected = choose(release("0.6.0", true, false), release("0.9.0", false, true));
        assertEquals("0.6.0", selected.version); assertTrue(selected.prerelease);
    }
    @Test public void choosesHighestNumericVersionRatherThanArrayOrderOrLexicalOrder() throws Exception {
        assertEquals("0.12.0", choose(release("0.9.0", true, false), release("0.12.0", true, false),
                release("0.6.0", false, false)).version);
        assertNull(choose(release("0.4.9", false, false), release("0.5.0", true, false)));
    }
    @Test public void releaseCandidatesAndStableVersionsHavePredictableOrder() {
        assertTrue(UpdatePolicy.compare("v0.5.0rc2", "0.5.0rc1") > 0);
        assertEquals(0, UpdatePolicy.compare("0.5.0-rc.2", "0.5.0rc2"));
        assertTrue(UpdatePolicy.compare("0.5.0", "0.5.0rc99") > 0);
        assertTrue(UpdatePolicy.compare("0.5.0beta9", "0.5.0alpha1") > 0);
        assertThrows(IllegalArgumentException.class, () -> UpdatePolicy.compare("0.5", "0.5.0"));
    }
    @Test public void missingAndUnuploadedAndroidAssetsAreNotInstallable() throws Exception {
        JSONObject value = release("0.6.0", true, false); value.getJSONArray("assets").getJSONObject(0).put("state", "new");
        assertNull(choose(value));
        value = release("0.6.0", true, false); value.getJSONArray("assets").getJSONObject(0).put("name", "AutoQuestion-0.6.0-debug.apk");
        assertNull(choose(value));
        value = release("0.6.0", true, false); value.put("draft", "false"); assertNull(choose(value));
    }
    @Test public void requiresSha256AndBoundedStrictSize() throws Exception {
        for (Object digest : new Object[]{JSONObject.NULL, "", "sha512:" + SHA, "sha256:" + "a".repeat(63)}) {
            JSONObject value = release("0.6.0", true, false); value.getJSONArray("assets").getJSONObject(0).put("digest", digest);
            assertNull(choose(value));
        }
        for (Object size : new Object[]{0, -1, UpdatePolicy.MAX_APK_BYTES + 1, "100", 100.5}) {
            JSONObject value = release("0.6.0", true, false); value.getJSONArray("assets").getJSONObject(0).put("size", size);
            assertNull(choose(value));
        }
    }
    @Test public void initialUrlsMustMatchTheExactRepositoryTagAndFilename() {
        String path = "/" + UpdatePolicy.REPOSITORY + "/releases/download/v0.6.0/AutoQuestion-0.6.0-Android.apk";
        assertTrue(UpdatePolicy.initialAssetUrl("https://github.com" + path, "v0.6.0", "AutoQuestion-0.6.0-Android.apk"));
        for (String url : new String[]{"http://github.com" + path, "https://github.com.evil.example" + path,
                "https://user:pass@github.com" + path, "https://github.com:444" + path, "https://github.com" + path + "?key=x",
                "https://github.com" + path + "#fragment", "https://github.com/other/AutoQuestion/releases/download/v0.6.0/AutoQuestion-0.6.0-Android.apk"})
            assertFalse(url, UpdatePolicy.initialAssetUrl(url, "v0.6.0", "AutoQuestion-0.6.0-Android.apk"));
    }
    @Test public void redirectsAreLimitedToExactOfficialHttpsHosts() {
        assertTrue(UpdatePolicy.redirectAllowed("https://release-assets.githubusercontent.com/a?signature=synthetic"));
        assertTrue(UpdatePolicy.redirectAllowed("https://objects.githubusercontent.com/a"));
        for (String url : new String[]{"http://objects.githubusercontent.com/a", "https://objects.githubusercontent.com.evil/a",
                "https://github.com/other/repo/releases/download/v1/app.apk", "https://api.github.com/a",
                "https://user@release-assets.githubusercontent.com/a", "https://release-assets.githubusercontent.com:80/a"})
            assertFalse(url, UpdatePolicy.redirectAllowed(url));
    }
    @Test public void checksumManifestRequiresExactlyOneMatchingFilenameAndDigest() {
        UpdatePolicy.Asset apk = new UpdatePolicy.Asset("AutoQuestion-0.6.0-Android.apk", "unused", SHA, 100);
        UpdatePolicy.verifyChecksums(SHA.toUpperCase(java.util.Locale.ROOT) + "  " + apk.name + "\n", apk);
        assertThrows(IllegalArgumentException.class, () -> UpdatePolicy.verifyChecksums(SHA + "  different.apk", apk));
        assertThrows(IllegalArgumentException.class, () -> UpdatePolicy.verifyChecksums("cd".repeat(32) + "  " + apk.name, apk));
        String duplicate = SHA + "  " + apk.name + "\n" + SHA + " *" + apk.name;
        assertThrows(IllegalArgumentException.class, () -> UpdatePolicy.verifyChecksums(duplicate, apk));
    }
}
