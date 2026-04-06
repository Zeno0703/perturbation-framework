package org.runtime;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public class TestOutcomeTracker {

    private static final Map<String, String> outcomes = new ConcurrentHashMap<>();

    public static void start(String testId) {
        outcomes.compute(testId, (k, current) -> {
            if (current != null && current.startsWith("FAIL")) {
                return current;
            }
            return "STARTED";
        });
    }

    public static void pass(String testId) {
        outcomes.compute(testId, (k, current) -> {
            if (current != null && current.startsWith("FAIL")) {
                return current;
            }
            return "PASS";
        });
    }

    public static void fail(String testId, Throwable cause) {
        String newMsg = getString(cause);
        String newUpper = newMsg.toUpperCase();
        boolean newIsClean = newUpper.contains("ASSERT") || newUpper.contains("COMPARISON") || newUpper.contains("MULTIPLEFAILURES");

        outcomes.compute(testId, (k, current) -> {
            if (current != null && current.startsWith("FAIL")) {
                String currUpper = current.toUpperCase();
                boolean currentIsClean = currUpper.contains("ASSERT") || currUpper.contains("COMPARISON") || currUpper.contains("MULTIPLEFAILURES");
                if (currentIsClean && !newIsClean) {
                    return current;
                }
            }
            return newMsg;
        });
    }

    private static String getString(Throwable cause) {
        Throwable root = cause;
        while (root.getCause() != null && root != root.getCause() &&
                (root instanceof java.lang.reflect.InvocationTargetException ||
                        root.getClass().getName().contains("ExtensionConfigurationException"))) {
            root = root.getCause();
        }

        String excName = root.getClass().getSimpleName();
        if (excName == null || excName.isEmpty()) {
            excName = root.getClass().getName();
        }

        return "FAIL (" + excName + ")";
    }

    public static void abort(String testId) {
        outcomes.compute(testId, (k, current) -> {
            if (current != null && (current.startsWith("FAIL") || current.equals("PASS"))) {
                return current;
            }
            return "UNREACHED";
        });
    }

    public static void clear() {
        outcomes.clear();
    }

    public static void dumpTo(java.nio.file.Path outDir) throws Exception {
        String data = outcomes.entrySet().stream()
                .map(e -> {
                    String k = e.getKey().replace("\\", "\\\\").replace("\"", "\\\"");
                    String v = e.getValue().replace("\\", "\\\\").replace("\"", "\\\"");
                    return "{\"" + k + "\":\"" + v + "\", \"test\":\"" + k + "\", \"outcome\":\"" + v + "\"}";
                })
                .collect(Collectors.joining("\n"));
        java.nio.file.Files.writeString(outDir.resolve("test-outcomes.txt"), data);
    }
}