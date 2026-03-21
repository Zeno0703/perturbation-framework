package org.tracking;

import org.utils.FileUtils;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import static org.utils.JsonUtils.jsonString;

public class TestOutcomeTracker {

    private static final Map<String, String> outcomes = new ConcurrentHashMap<>();

    public static void pass(String testId) {
        outcomes.put(testId, "PASS");
    }

    public static void fail(String testId, Throwable cause) {
        if (cause != null) {
            outcomes.put(testId, "FAIL (" + cause.getClass().getSimpleName() + ")");
        } else {
            outcomes.put(testId, "FAIL");
        }
    }

    public static void fail(String testId) {
        fail(testId, null);
    }

    public static void clear() {
        outcomes.clear();
    }

    public static void dumpTo(Path file) throws IOException {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> e : outcomes.entrySet()) {
            sb.append("{\"test\":")
                    .append(jsonString(e.getKey()))
                    .append(",\"status\":")
                    .append(jsonString(e.getValue()))
                    .append("}\n");
        }
        FileUtils.writeAtomic(file, sb.toString());
    }
}