package com.autoquestion.mobile;

import java.util.HashSet;
import java.util.Set;
import org.json.JSONException;
import org.json.JSONObject;

/** Android's JSONTokener accepts malformed JSON and duplicate keys. Gate it first. */
final class StrictJson {
    private final String source;
    private int at;
    private StrictJson(String source) { this.source = source; }

    static JSONObject object(String value) throws JSONException {
        if (value == null || value.length() > 1048576) throw bad();
        StrictJson parser = new StrictJson(value);
        parser.space();
        if (parser.at >= value.length() || value.charAt(parser.at) != '{') throw bad();
        parser.value(0); parser.space();
        if (parser.at != value.length()) throw bad();
        return new JSONObject(value);
    }

    private void value(int depth) throws JSONException {
        if (depth > 32) throw bad();
        space(); char first = peek();
        if (first == '{') {
            at++; space(); Set<String> keys = new HashSet<>();
            if (take('}')) return;
            do {
                space(); if (peek() != '"') throw bad();
                if (!keys.add(string())) throw bad();
                space(); if (!take(':')) throw bad();
                value(depth + 1); space();
                if (take('}')) return;
                if (!take(',')) throw bad();
            } while (true);
        }
        if (first == '[') {
            at++; space(); if (take(']')) return;
            do {
                value(depth + 1); space(); if (take(']')) return;
                if (!take(',')) throw bad();
            } while (true);
        }
        if (first == '"') { string(); return; }
        if (first == 't') { literal("true"); return; }
        if (first == 'f') { literal("false"); return; }
        if (first == 'n') { literal("null"); return; }
        number();
    }

    private String string() throws JSONException {
        if (!take('"')) throw bad();
        StringBuilder decoded = new StringBuilder();
        while (at < source.length()) {
            char c = source.charAt(at++);
            if (c == '"') return decoded.toString();
            if (c < 32) throw bad();
            if (c != '\\') { decoded.append(c); continue; }
            if (at == source.length()) throw bad();
            char escaped = source.charAt(at++);
            switch (escaped) {
                case '"': case '\\': case '/': decoded.append(escaped); break;
                case 'b': decoded.append('\b'); break;
                case 'f': decoded.append('\f'); break;
                case 'n': decoded.append('\n'); break;
                case 'r': decoded.append('\r'); break;
                case 't': decoded.append('\t'); break;
                case 'u':
                    int code = 0;
                    for (int i = 0; i < 4; i++) {
                        if (at >= source.length()) throw bad();
                        char hex = source.charAt(at++);
                        int digit = hex >= '0' && hex <= '9' ? hex - '0'
                                : hex >= 'a' && hex <= 'f' ? hex - 'a' + 10
                                : hex >= 'A' && hex <= 'F' ? hex - 'A' + 10 : -1;
                        if (digit < 0) throw bad(); code = code * 16 + digit;
                    }
                    decoded.append((char) code); break;
                default: throw bad();
            }
        }
        throw bad();
    }

    private void number() throws JSONException {
        take('-');
        if (take('0')) { if (digit(peek())) throw bad(); }
        else {
            if (peek() < '1' || peek() > '9') throw bad();
            while (digit(peek())) at++;
        }
        if (take('.')) {
            if (!digit(peek())) throw bad(); while (digit(peek())) at++;
        }
        if (peek() == 'e' || peek() == 'E') {
            at++; if (peek() == '+' || peek() == '-') at++;
            if (!digit(peek())) throw bad(); while (digit(peek())) at++;
        }
    }
    private void literal(String value) throws JSONException {
        if (!source.startsWith(value, at)) throw bad(); at += value.length();
    }
    private void space() {
        while (at < source.length() && (source.charAt(at) == ' ' || source.charAt(at) == '\n'
                || source.charAt(at) == '\r' || source.charAt(at) == '\t')) at++;
    }
    private char peek() { return at < source.length() ? source.charAt(at) : '\0'; }
    private boolean take(char c) { if (peek() != c) return false; at++; return true; }
    private static boolean digit(char c) { return c >= '0' && c <= '9'; }
    private static JSONException bad() { return new JSONException("JSON 格式无效"); }
}
