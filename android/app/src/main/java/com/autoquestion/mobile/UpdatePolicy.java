package com.autoquestion.mobile;

import java.net.URI;
import java.util.Arrays;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/** Public release metadata policy. No API key, device ID, user content, or settings enter it. */
final class UpdatePolicy {
    static final String REPOSITORY = "billstar0128-jpg/AutoQuestion";
    static final String RELEASES_URL = "https://api.github.com/repos/" + REPOSITORY + "/releases?per_page=100";
    static final long MAX_APK_BYTES = 150L * 1024 * 1024;
    private static final Pattern VERSION = Pattern.compile("v?(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(?:(?:-?)(alpha|beta|rc)(?:[.-]?)([0-9]+))?");

    static final class Asset {
        final String name, url, sha256;
        final long size;
        Asset(String name, String url, String sha256, long size) {
            this.name = name; this.url = url; this.sha256 = sha256; this.size = size;
        }
    }
    static final class Release {
        final String tag, version;
        final boolean prerelease;
        final Asset apk, checksums;
        Release(String tag, String version, boolean prerelease, Asset apk, Asset checksums) {
            this.tag = tag; this.version = version; this.prerelease = prerelease; this.apk = apk; this.checksums = checksums;
        }
    }

    static Release choose(JSONArray releases, String installedVersion) throws JSONException {
        numbers(installedVersion); // Never guess the installed version.
        Release best = null;
        for (int i = 0; i < releases.length(); i++) {
            try {
                JSONObject item = releases.getJSONObject(i);
                if (!Boolean.FALSE.equals(item.get("draft")) || !(item.get("prerelease") instanceof Boolean)) continue;
                String tag = item.getString("tag_name"); numbers(tag);
                String version = tag.startsWith("v") ? tag.substring(1) : tag;
                if (compare(version, installedVersion) <= 0 || (best != null && compare(version, best.version) <= 0)) continue;
                String filename = "AutoQuestion-" + version + "-Android.apk";
                Asset apk = null, sums = null;
                JSONArray assets = item.getJSONArray("assets");
                for (int j = 0; j < assets.length(); j++) {
                    JSONObject asset = assets.getJSONObject(j);
                    String name = asset.getString("name");
                    if (name.equals(filename)) {
                        if (apk != null) throw new JSONException("重复更新包");
                        apk = asset(asset, tag, MAX_APK_BYTES);
                    } else if (name.equals("SHA256SUMS.txt")) {
                        if (sums != null) throw new JSONException("重复摘要文件");
                        sums = asset(asset, tag, 128 * 1024);
                    }
                }
                if (apk != null) best = new Release(tag, version, item.getBoolean("prerelease"), apk, sums);
            } catch (JSONException | IllegalArgumentException ignored) {
                // A partial release, unsigned metadata, or an unfamiliar tag is not installable.
            }
        }
        return best;
    }

    private static Asset asset(JSONObject source, String tag, long maximum) throws JSONException {
        if (!"uploaded".equals(source.getString("state"))) throw new JSONException("更新包未就绪");
        Object sizeValue = source.get("size");
        if (!(sizeValue instanceof Integer || sizeValue instanceof Long)) throw new JSONException("大小无效");
        long size = ((Number) sizeValue).longValue();
        if (size < 1 || size > maximum) throw new JSONException("更新包过大");
        String name = source.getString("name"), url = source.getString("browser_download_url");
        if (!initialAssetUrl(url, tag, name)) throw new JSONException("更新地址无效");
        Object digest = source.get("digest");
        if (!(digest instanceof String) || !((String) digest).matches("sha256:[0-9a-fA-F]{64}")) throw new JSONException("缺少更新摘要");
        return new Asset(name, url, ((String) digest).substring(7).toLowerCase(Locale.ROOT), size);
    }

    static int compare(String left, String right) {
        long[] a = numbers(left), b = numbers(right);
        for (int i = 0; i < a.length; i++) if (a[i] != b[i]) return Long.compare(a[i], b[i]);
        return 0;
    }

    private static long[] numbers(String version) {
        if (version == null || version.length() > 80) throw new IllegalArgumentException("版本格式无效");
        Matcher match = VERSION.matcher(version);
        if (!match.matches()) throw new IllegalArgumentException("版本格式无效");
        long major = Long.parseLong(match.group(1)), minor = Long.parseLong(match.group(2)), patch = Long.parseLong(match.group(3));
        String stage = match.group(4);
        long order = stage == null ? 3 : stage.equals("rc") ? 2 : stage.equals("beta") ? 1 : 0;
        long index = stage == null ? 0 : Long.parseLong(match.group(5));
        return new long[]{major, minor, patch, order, index};
    }

    static boolean initialAssetUrl(String value, String tag, String name) {
        try {
            URI uri = URI.create(value);
            return secure(uri) && "github.com".equalsIgnoreCase(uri.getHost()) && uri.getRawQuery() == null
                    && uri.getRawPath().equals("/" + REPOSITORY + "/releases/download/" + tag + "/" + name);
        } catch (IllegalArgumentException ignored) { return false; }
    }

    static boolean redirectAllowed(String value) {
        try {
            URI uri = URI.create(value);
            if (!secure(uri)) return false;
            String host = uri.getHost().toLowerCase(Locale.ROOT);
            return Arrays.asList("release-assets.githubusercontent.com", "objects.githubusercontent.com").contains(host)
                    || ("github.com".equals(host) && uri.getRawQuery() == null
                    && uri.getRawPath().startsWith("/" + REPOSITORY + "/releases/download/"));
        } catch (IllegalArgumentException ignored) { return false; }
    }

    private static boolean secure(URI uri) {
        return "https".equalsIgnoreCase(uri.getScheme()) && uri.getHost() != null && uri.getRawUserInfo() == null
                && uri.getRawFragment() == null && (uri.getPort() == -1 || uri.getPort() == 443);
    }

    static void verifyChecksums(String content, Asset apk) {
        String found = null;
        for (String line : content.split("\\r?\\n")) {
            Matcher match = Pattern.compile("^([0-9a-fA-F]{64})[ \\t]+\\*?([^\\r\\n]+)$").matcher(line);
            if (match.matches() && match.group(2).equals(apk.name)) {
                if (found != null) throw new IllegalArgumentException("摘要文件重复记录");
                found = match.group(1).toLowerCase(Locale.ROOT);
            }
        }
        if (!apk.sha256.equals(found)) throw new IllegalArgumentException("更新摘要不一致");
    }
}
