package org.utils;

public class StringUtils {
    public static String sanitize(String input) {
        if (input == null) return "null";
        return input.replace("\\", "\\\\")
                .replace("\t", "\\t")
                .replace("\n", "\\n")
                .replace("\r", "\\r");
    }
}